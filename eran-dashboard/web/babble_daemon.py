#!/usr/bin/env python
"""ALMAWARE babble daemon — generate-on-demand vocal babble from a trained
AudioGPT checkpoint, served over localhost HTTP. ONE process holds the model +
EnCodec codec resident so each /gen request is fast (no reload).

This is the SAME sampling + EnCodec-decode path the trainer uses (the babble()
function in src/train.py), extracted so it can run on cue instead of only every
500 steps during training.

HONEST SCOPE: this generates the child's OWN babble unconditionally (optionally
seeded by a tiny real audio frame to set codebook phase). It does NOT hear or
condition on anything Iddo says — it is generation-on-cue, not a reply.

Run (on the node that holds the model), e.g.:
  ~/eran/.venv/bin/python babble_daemon.py --root ~/eran-vocal --port 8791

Endpoints:
  GET /gen?secs=2.5&temp=0.9   -> audio/wav  (freshly generated babble)
  GET /health                  -> json status
"""
import argparse, io, json, math, os, sys, threading, time
import http.server
import numpy as np

# ----------------------------------------------------------------------
# Lazy heavy imports (torch / encodec / soundfile) happen in load_model so
# /health can answer even while the model is still loading.
# ----------------------------------------------------------------------
_state = {"ready": False, "loading": False, "err": "", "step": None,
          "n_q": 8, "vocab": 1024, "sr": 24000, "gens": 0, "last_ms": None}
_lock = threading.Lock()
_gen_lock = threading.Lock()   # serialize GPU generation (one job at a time)
_M = {}   # holds model, codec, data, meta once loaded


def load_model(root):
    with _lock:
        if _state["ready"] or _state["loading"]:
            return
        _state["loading"] = True
    try:
        import torch, soundfile as sf  # noqa: F401
        sys.path.insert(0, os.path.join(root, "src"))
        from model import AudioGPT
        from encodec import EncodecModel

        dev = "cuda" if __import__("torch").cuda.is_available() else "cpu"
        meta = json.load(open(os.path.join(root, "tokens", "meta.json")))
        n_q, vocab, bw = meta["n_q"], meta["vocab"], meta["bw"]

        # token stream (used only to seed a 1-frame prefix, same as trainer)
        codes = np.load(os.path.join(root, "tokens", "codes.npy"))
        flat = codes.T.reshape(-1).astype(np.int64)
        data = torch.from_numpy(flat)

        CTX = (2048 // n_q) * n_q
        model = AudioGPT(vocab=vocab, n_q=n_q, d=384, h=6, layers=6, ctx=CTX, drop=0.1).to(dev)
        ck = torch.load(os.path.join(root, "ckpt", "last.pt"), map_location=dev)
        model.load_state_dict(ck["model"])
        model.eval()

        codec = EncodecModel.encodec_model_24khz()
        codec.set_target_bandwidth(bw)
        codec.to(dev).eval()

        _M.update(model=model, codec=codec, data=data, meta=meta,
                  n_q=n_q, vocab=vocab, dev=dev, sr=codec.sample_rate, torch=__import__("torch"), sf=sf)
        with _lock:
            _state.update(ready=True, loading=False, step=int(ck.get("step", 0)),
                          n_q=n_q, vocab=vocab, sr=codec.sample_rate)
    except Exception as e:
        with _lock:
            _state.update(loading=False, err=repr(e)[:300])


def _decode_to_tokens(audio_bytes):
    """EnCodec-encode an arbitrary audio clip (browser webm/opus, wav, mp3...) into
    (n_q, T) code tokens. ffmpeg -> 24k mono float -> codec.encode. This is the
    model's AUDITORY FRONT-END: the same ears the trainer used. Returns np (n_q,T)."""
    import subprocess, tempfile, os
    torch = _M["torch"]; codec = _M["codec"]; sf = _M["sf"]; dev = _M["dev"]
    fd, src = tempfile.mkstemp(suffix=".bin"); os.close(fd)
    wavp = src + ".wav"
    try:
        with open(src, "wb") as f:
            f.write(audio_bytes)
        # let ffmpeg sniff the container; force 24k mono PCM out
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                        "-i", src, "-ac", "1", "-ar", str(_M["sr"]), wavp],
                       check=True, timeout=20)
        w, _sr = sf.read(wavp, dtype="float32")
        if getattr(w, "ndim", 1) > 1:
            w = w.mean(axis=1)
        if len(w) < _M["sr"] * 0.2:        # <0.2s -> not enough to condition on
            return None
        x = torch.from_numpy(w).float().unsqueeze(0).unsqueeze(0).to(dev)  # (1,1,T)
        with torch.no_grad():
            enc = codec.encode(x)
            codes = enc[0][0][0].cpu().numpy()    # (n_q, T)
        return codes
    except Exception:
        return None
    finally:
        for p in (src, wavp):
            try: os.unlink(p)
            except OSError: pass


def _decode_codes_to_wav(arr):
    """(n_q, T) int codes -> WAV bytes via EnCodec decoder (the model's MOUTH)."""
    torch = _M["torch"]; codec = _M["codec"]; sf = _M["sf"]; dev = _M["dev"]
    arr = np.clip(arr, 0, _M["vocab"] - 1)
    cd = torch.from_numpy(arr).long().unsqueeze(0).to(dev)   # (1,n_q,T)
    with torch.no_grad():
        wav = codec.decode([(cd, None)]).squeeze().cpu().numpy()
    buf = io.BytesIO()
    sf.write(buf, wav, _M["sr"], format="WAV")
    return buf.getvalue()


def generate_wav(secs=2.5, temp=0.9, prefix_audio=None, prefix_frames=40):
    """Return WAV bytes for a freshly generated babble.

    If prefix_audio (raw bytes of the user's voice clip) is given, the child
    genuinely HEARS it: we EnCodec-encode the clip and use its tail as the
    GENERATION PREFIX, so the AudioGPT CONTINUES from the user's actual sound
    (acoustic conditioning / continuation). This is real hearing+response at the
    babble level — NOT comprehension of words. If no/too-short audio, falls back
    to an unconditional seed (1 real frame), same as the trainer's babble()."""
    torch = _M["torch"]; model = _M["model"]
    data = _M["data"]; n_q = _M["n_q"]; vocab = _M["vocab"]; dev = _M["dev"]
    secs = max(0.8, min(6.0, float(secs)))
    temp = max(0.3, min(1.5, float(temp)))
    n_new = int(secs * 75) * n_q

    conditioned = False
    if prefix_audio:
        codes = _decode_to_tokens(prefix_audio)
        if codes is not None and codes.shape[1] >= 4:
            # use the TAIL of his clip (most recent ~prefix_frames frames) as prefix,
            # flattened frame-major exactly like training (f0c0..f0c7, f1c0..).
            T = codes.shape[1]
            take = min(prefix_frames, T)
            tail = codes[:, T - take:]                      # (n_q, take)
            flat = tail.T.reshape(-1).astype(np.int64)      # frame-major
            prefix = torch.from_numpy(flat).unsqueeze(0).to(dev)
            conditioned = True
    if not conditioned:
        start = torch.randint(0, len(data) - n_q, (1,)).item()
        start = (start // n_q) * n_q
        prefix = data[start:start + n_q].unsqueeze(0).to(dev)

    out = model.generate(prefix, n_new, temp=temp, top_k=150)[0].cpu().numpy()
    # If conditioned, drop the echoed prefix so we return only the CONTINUATION.
    if conditioned:
        out = out[prefix.shape[1]:]
    L = (len(out) // n_q) * n_q
    arr = out[:L].reshape(-1, n_q).T                        # (n_q, T)
    wav_bytes = _decode_codes_to_wav(arr)
    return wav_bytes, conditioned


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        b = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        try:
            self.wfile.write(b)
        except Exception:
            pass

    def _q(self):
        q = {}
        if "?" in self.path:
            for kv in self.path.split("?", 1)[1].split("&"):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    q[k] = v
        return q

    def _serve_gen(self, prefix_audio=None):
        with _lock:
            ready = _state["ready"]
        if not ready:
            self._json(503, {"error": "model not ready", **_state})
            return
        q = self._q()
        # serialize GPU generation so concurrent requests don't thrash the model
        with _gen_lock:
            try:
                t0 = time.time()
                wav, conditioned = generate_wav(
                    secs=q.get("secs", 2.5), temp=q.get("temp", 0.9),
                    prefix_audio=prefix_audio)
                ms = int((time.time() - t0) * 1000)
                with _lock:
                    _state["gens"] += 1
                    _state["last_ms"] = ms
            except Exception as e:
                self._json(500, {"error": repr(e)[:300]})
                return
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(wav)))
        self.send_header("X-Gen-Ms", str(ms))
        self.send_header("X-Conditioned", "1" if conditioned else "0")
        self.end_headers()
        try:
            self.wfile.write(wav)
        except Exception:
            pass

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/health":
            with _lock:
                self._json(200, dict(_state))
            return
        if path == "/gen":              # unconditional babble (no audio)
            self._serve_gen(prefix_audio=None)
            return
        self._json(404, {"error": "not found"})

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path == "/gen":              # CONDITIONED: body = the user's voice clip
            try:
                ln = int(self.headers.get("Content-Length", "0"))
                audio = self.rfile.read(ln) if ln else b""
            except Exception:
                audio = b""
            self._serve_gen(prefix_audio=audio or None)
            return
        self._json(404, {"error": "not found"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--port", type=int, default=8791)
    a = ap.parse_args()
    root = os.path.expanduser(a.root)
    # load model in the background so the port binds immediately
    threading.Thread(target=load_model, args=(root,), daemon=True).start()
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", a.port), H)
    print(f"babble_daemon up on 127.0.0.1:{a.port} root={root}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
