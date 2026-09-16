"""KESHEV STT server — K10 (PHASE2-DESIGN.md sections 3.1 + 6, scar 55).

ONE file, stdlib HTTP (ThreadingHTTPServer) + numpy + faster-whisper.
Runs on eran1:8737 as a systemd user unit (keshev-stt.service — written and
validated at K10, ENABLED only at a later cutover step).

Privacy is STRUCTURAL (scar 55 / criterion 19):
  * request audio lives only in RAM — bytes -> numpy -> decode; this file
    has no code path that constructs a file path for audio (asserted by
    tests/test_stt_contract.py against this source)
  * the status-line logger REFUSES transcript fields at the type level
    (text/transcript/title => TypeError); journald gets status lines only
  * bearer token, constant-time compare, on EVERY endpoint incl. /health
  * bind is explicit LAN addresses; 0.0.0.0/:: are refused by the validator

Contract (section 3.1): POST /v1/transcribe (raw PCM s16le 16k mono,
X-Request-Id mandatory — THE dedup key, scar 53), GET /health (canary_age_s
is REAL output, scar 5), GET /metrics, POST /admin/drain|/admin/undrain.
Errors: 400 malformed / 401 auth / 413 >30s / 429 inflight>2 / 503 LOADING
or DRAINING / 500 decode_timeout (15s wall).

The server never filters text — textguard is client-only, ONE copy
(scar 28). Language routing = common/langpolicy.py, the shared truth.
"""
from __future__ import annotations

import argparse
import hmac
import json
import logging
import math
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from common import langpolicy, protocol

log = logging.getLogger("keshev-stt")

_BANNED_LOG_FIELDS = frozenset({"text", "transcript", "title"})
_START_MONO = time.monotonic()


def _quiet_libraries() -> None:
    """Pin third-party loggers to WARNING. K10's live run proved that
    faster_whisper's own logger writes INFO lines ('Processing audio with
    duration ...') through our root config — benign (numbers only) but
    journald must carry OUR status lines, nothing chattier (section 6;
    the gate-19 whitelist in server/audit_privacy.sh enforces this)."""
    logging.getLogger("faster_whisper").setLevel(logging.WARNING)
    logging.getLogger("ctranslate2").setLevel(logging.WARNING)


def status_line(**fields) -> str:
    """key=value status line. Transcript content is UNREPRESENTABLE:
    a text/transcript/title field raises TypeError (section 6)."""
    banned = _BANNED_LOG_FIELDS.intersection(fields)
    if banned:
        raise TypeError(f"status_line refuses transcript fields: {sorted(banned)}")
    return " ".join(f"{k}={v}" for k, v in fields.items())


def validate_bind(binds) -> None:
    """Explicit LAN/loopback addresses only (scar 55) — a wildcard bind
    exposes all-day dictation to every interface on a shared box."""
    if not binds:
        raise ValueError("bind list is empty")
    for b in binds:
        if b in ("0.0.0.0", "::", ""):
            raise ValueError(f"wildcard bind {b!r} refused — name the interface (scar 55)")


def _percentile(sorted_ms: list, q: float) -> int:
    if not sorted_ms:
        return 0
    idx = min(len(sorted_ms) - 1, max(0, math.ceil(q * len(sorted_ms)) - 1))
    return int(sorted_ms[idx])


def _now_iso_ms() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def should_pet(canary_age_s: float) -> bool:
    """May we pet the systemd watchdog right now? (scar 5)

    The pet must be EARNED by real output, never granted for merely being alive —
    that is the whole difference between this and a liveness ping. A server whose
    model has wedged still runs, still accepts sockets, still looks healthy; what
    it stops doing is producing a fresh canary decode. So we tie the pet to
    canary freshness and let systemd do the killing.

    Pure function of one number so it is testable without a server, a socket or a
    model — see tests/test_watchdog_cadence.py.
    """
    return canary_age_s <= protocol.CANARY_STALE_S


# ---------------------------------------------------------------- engine

class FasterWhisperEngine:
    """The real backend (langpolicy protocol). Built ONLY in main() — tests
    inject a stub, the PC never imports faster_whisper (scar 47 lives
    client-side; this class runs server-side).

    `stock_dir`/`lora_dir` are handed straight to faster_whisper's
    WhisperModel(model_size_or_path=...), which accepts EITHER a local
    directory path OR a bare HF repo id (e.g. "ivrit-ai/whisper-large-v3-
    turbo-ct2") — in the repo-id case it auto-downloads into `download_root`
    (or the library default cache) on first run. This is what makes the
    public config (server/server.json) work with zero local model files:
    it names public HF repos, not paths on anyone's disk.

    A personally fine-tuned adapter (Iddo's own iddo-lora, trained on HIS
    voice) is opt-in ONLY, via KESHEV_PERSONAL_LORA_DIR — never a default,
    never shipped, never referenced by the public config (Iddo's order,
    2026-08-25: strangers who download KESHEV must never load his personal
    voice model and must never reach his fleet)."""

    def __init__(self, stock_dir: str, lora_dir: str, device: str = "cuda",
                 compute_type: str = "int8_float16", download_root: str | None = None):
        from faster_whisper import WhisperModel  # server-only dependency
        import os
        personal = os.environ.get("KESHEV_PERSONAL_LORA_DIR")
        if personal:
            lora_dir = personal
            log.info(status_line(evt="PERSONAL_LORA_OVERRIDE"))
        t0 = time.monotonic()
        self._stock = WhisperModel(stock_dir, device=device, compute_type=compute_type,
                                   download_root=download_root)
        self._lora = WhisperModel(lora_dir, device=device, compute_type=compute_type,
                                  download_root=download_root)
        # a bare HF repo id has no filesystem "name" worth reporting — fall
        # back to the id itself rather than Path(...).name mangling it
        def _label(p: str) -> str:
            local = Path(p)
            return local.name if local.exists() else p
        self._names = {langpolicy.MODEL_DETECT: _label(stock_dir),
                       langpolicy.MODEL_HE: _label(lora_dir)}
        log.info(status_line(evt="MODELS_LOADED", load_s=round(time.monotonic() - t0, 1),
                             stock=self._names[langpolicy.MODEL_DETECT],
                             lora=self._names[langpolicy.MODEL_HE]))

    def model_name(self, role: str) -> str:
        return self._names[role]

    def detect_language(self, audio):
        # scar 29: detection on the STOCK model, never the LoRA
        _lang, _prob, all_probs = self._stock.detect_language(audio=audio)
        return all_probs

    def decode(self, audio, *, model: str, language: str, vad: bool, **kw):
        m = self._stock if model == langpolicy.MODEL_DETECT else self._lora
        segments, _info = m.transcribe(audio, language=language, vad_filter=vad,
                                       without_timestamps=True, **kw)
        texts, lps, nsps, crs = [], [], [], []
        for seg in segments:                      # generator — drains the decode
            texts.append(seg.text.strip())
            lps.append(seg.avg_logprob)
            nsps.append(seg.no_speech_prob)
            crs.append(seg.compression_ratio)
        if not texts:
            return langpolicy.DecodeOutcome(text="", avg_logprob=0.0,
                                            no_speech_prob=1.0, compression_ratio=0.0)
        n = len(texts)
        return langpolicy.DecodeOutcome(
            text=" ".join(t for t in texts if t),
            avg_logprob=sum(lps) / n, no_speech_prob=sum(nsps) / n,
            compression_ratio=sum(crs) / n)


# ---------------------------------------------------------------- server

class SttServer:
    """State + metrics + the HTTP servers (one per bind address)."""

    def __init__(self, config: dict, engine=None, token: str | None = None,
                 notifier=None):
        validate_bind(config.get("bind", []))
        self._config = config
        self.engine = engine
        self.notifier = notifier
        self._token = (token or "").encode("utf-8")
        self._state = "LOADING"
        self._state_lock = threading.Lock()
        self._inflight = 0
        self._decode_lock = threading.Lock()      # single-flight decode
        self._decode_ms: list = []                # (mono_ts, ms), trimmed to 60m
        self._metrics_lock = threading.Lock()
        self.counters = {k: 0 for k in (
            "n_200", "n_400", "n_401", "n_404", "n_413", "n_429",
            "n_500", "n_503", "client_gone", "canary_ok", "canary_fail")}
        self._canary_ts: float | None = None
        self._t0 = time.monotonic()
        self.version = self._read_version()
        self._httpds: list[ThreadingHTTPServer] = []
        self._threads: list[threading.Thread] = []

    @staticmethod
    def _read_version() -> str:
        vf = Path(__file__).resolve().parent / "VERSION"
        if vf.is_file():
            return vf.read_text(encoding="utf-8").strip()
        return "dev"

    # ---- lifecycle
    def start(self) -> None:
        port = self._config.get("port", protocol.PORT)
        for addr in self._config["bind"]:
            httpd = ThreadingHTTPServer((addr, port), _Handler)
            httpd.daemon_threads = True
            httpd.app = self
            self._httpds.append(httpd)
            t = threading.Thread(target=httpd.serve_forever, daemon=True,
                                 name=f"keshev-stt-{addr}")
            t.start()
            self._threads.append(t)
            port = httpd.server_address[1]        # port 0 -> same real port for all binds
        log.info(status_line(evt="LISTENING",
                             bind=",".join(self._config["bind"]), port=self.port,
                             version=self.version))

    def stop(self) -> None:
        for httpd in self._httpds:
            httpd.shutdown()
            httpd.server_close()

    @property
    def port(self) -> int:
        return self._httpds[0].server_address[1]

    @property
    def state(self) -> str:
        return self._state

    @property
    def inflight(self) -> int:
        return self._inflight

    def attach_engine(self, engine) -> None:
        self.engine = engine

    def set_ready(self) -> None:
        with self._state_lock:
            self._state = "READY"
            if self._canary_ts is None:
                self._canary_ts = time.monotonic()

    def drain(self) -> None:
        with self._state_lock:
            self._state = "DRAINING"

    def undrain(self) -> None:
        with self._state_lock:
            if self.engine is not None:
                self._state = "READY"

    # ---- canary (scar 5: health = real output)
    _CANARY_SR = protocol.SAMPLE_RATE

    def _canary_audio(self):
        import numpy as np
        t = np.arange(self._CANARY_SR, dtype=np.float32) / self._CANARY_SR
        # 1s deterministic chirp 200->800Hz at speech-like level
        return (0.1 * np.sin(2 * np.pi * (200 + 300 * t) * t)).astype(np.float32)

    def run_canary(self) -> bool:
        """Self-decode the embedded 1s reference clip through the REAL path.
        Success resets canary_age_s and pets the systemd watchdog; failure
        pets NOTHING — a wedged model stops the petting and systemd restarts
        us (section 6)."""
        try:
            t0 = time.monotonic()
            langpolicy.transcribe(self._canary_audio(), self.engine, lang_hint="he")
            ms = int((time.monotonic() - t0) * 1000)
        except Exception as e:
            self.counters["canary_fail"] += 1
            log.warning(status_line(evt="CANARY_FAIL", err=type(e).__name__))
            return False
        self._canary_ts = time.monotonic()
        self.counters["canary_ok"] += 1
        log.info(status_line(evt="CANARY_OK", ms=ms))
        if self.notifier is not None:
            self.notifier.watchdog()
        return True

    @property
    def canary_age_s(self) -> float:
        if self._canary_ts is None:
            return float(10 ** 9)
        return time.monotonic() - self._canary_ts

    # ---- auth / metrics helpers
    def check_auth(self, header_value: str | None) -> bool:
        if not self._token or not header_value or not header_value.startswith("Bearer "):
            return False
        presented = header_value[len("Bearer "):].encode("utf-8")
        return hmac.compare_digest(presented, self._token)

    def record_decode(self, ms: int) -> None:
        now = time.monotonic()
        with self._metrics_lock:
            self._decode_ms.append((now, ms))
            cutoff = now - 3600
            while self._decode_ms and self._decode_ms[0][0] < cutoff:
                self._decode_ms.pop(0)

    def decode_window(self, seconds: float) -> dict:
        now = time.monotonic()
        with self._metrics_lock:
            ms = sorted(m for ts, m in self._decode_ms if ts >= now - seconds)
        return {"n": len(ms), "p50_ms": _percentile(ms, 0.50), "p95_ms": _percentile(ms, 0.95)}

    def health(self) -> dict:
        w = self.decode_window(3600)
        models = []
        if self.engine is not None:
            name = getattr(self.engine, "model_name", None)
            if callable(name):
                models = [name(langpolicy.MODEL_DETECT), name(langpolicy.MODEL_HE)]
        return {"state": self._state, "models": models, "inflight": self._inflight,
                "decode_p50_ms": w["p50_ms"], "decode_p95_ms": w["p95_ms"],
                "canary_age_s": round(self.canary_age_s, 1),
                "uptime_s": int(time.monotonic() - self._t0), "version": self.version}

    # ---- admission (single-flight + depth-2 queue -> 429 above cap)
    def try_admit(self) -> bool:
        cap = self._config.get("inflight_cap", protocol.INFLIGHT_CAP)
        with self._state_lock:
            if self._inflight >= cap:
                return False
            self._inflight += 1
            return True

    def release(self) -> None:
        with self._state_lock:
            self._inflight -= 1


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "keshev-stt"

    @property
    def app(self) -> SttServer:
        return self.server.app

    def log_message(self, fmt, *args):              # BaseHTTPRequestHandler default is noisy
        pass_through = status_line(evt="HTTPD", line=fmt % args)
        log.debug(pass_through)

    # ---- plumbing
    def _send_json(self, code: int, obj: dict, extra_headers: dict | None = None) -> bool:
        """Write a JSON response; a dead client is COUNTED, never a crash
        (the abandon side of scar 53 — the server must see the reset)."""
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            for k, v in (extra_headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
            return True
        except (BrokenPipeError, ConnectionError, TimeoutError, OSError):
            self.app.counters["client_gone"] += 1
            log.info(status_line(evt="CLIENT_GONE", path=self.path, code=code))
            self.close_connection = True
            return False

    def _client_still_there(self) -> bool:
        """After a long decode, probe for the peer's FIN before replying —
        an abandoned socket is registered even when the TCP stack would
        happily swallow one last write."""
        try:
            self.connection.setblocking(False)
            try:
                chunk = self.connection.recv(1)
                return chunk != b""                # b"" == orderly FIN == abandoned
            except (BlockingIOError, InterruptedError):
                return True                        # no FIN — still with us
            finally:
                self.connection.setblocking(True)
        except OSError:
            return False

    def _count(self, code: int) -> None:
        self.app.counters[f"n_{code}"] = self.app.counters.get(f"n_{code}", 0) + 1

    def _drain_unread_body(self) -> None:
        """Read-and-discard an unread request body (bounded) so a reject on
        a large POST doesn't reset the connection under the client before
        the error reaches it. Called only while the body is UNREAD."""
        if getattr(self, "_body_consumed", False):
            return
        self._body_consumed = True
        try:
            remaining = min(int(self.headers.get("Content-Length", "0") or 0),
                            4 * protocol.MAX_BODY_BYTES)
        except ValueError:
            return
        try:
            while remaining > 0:
                chunk = self.rfile.read(min(65536, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
        except (TimeoutError, OSError):
            self.close_connection = True

    def _reject(self, code: int, error: str, extra_headers: dict | None = None) -> None:
        self._drain_unread_body()
        # rejects never keep-alive — the next request starts on a fresh socket
        self.close_connection = True
        self._count(code)
        self._send_json(code, {"error": error}, extra_headers)
        log.info(status_line(evt="REQ", path=self.path, code=code, err=error))

    def _authed(self) -> bool:
        if self.app.check_auth(self.headers.get("Authorization")):
            return True
        self._reject(401, "unauthorized")
        return False

    # ---- routing
    def do_GET(self):
        if not self._authed():
            return
        if self.path == protocol.PATH_HEALTH:
            h = self.app.health()
            code = 200 if h["state"] == "READY" else 503
            self._count(code)
            self._send_json(code, h)
        elif self.path == protocol.PATH_METRICS:
            self._count(200)
            self._send_json(200, {
                "decode": {"1m": self.app.decode_window(60),
                           "5m": self.app.decode_window(300),
                           "60m": self.app.decode_window(3600)},
                "counters": dict(self.app.counters)})
        else:
            self._reject(404, "not_found")

    def do_POST(self):
        self._body_consumed = False
        if not self._authed():
            return
        if self.path == protocol.PATH_DRAIN:
            self.app.drain()
            self._count(200)
            self._send_json(200, {"state": self.app.state, "inflight": self.app.inflight})
            log.info(status_line(evt="DRAIN"))
        elif self.path == protocol.PATH_UNDRAIN:
            self.app.undrain()
            self._count(200)
            self._send_json(200, {"state": self.app.state})
            log.info(status_line(evt="UNDRAIN"))
        elif self.path == protocol.PATH_TRANSCRIBE:
            self._transcribe()
        else:
            self._reject(404, "not_found")

    # ---- the endpoint
    def _transcribe(self):
        app = self.app
        if app.state != "READY":
            self._count(503)
            self._send_json(503, {"state": app.state})
            return

        rid = self.headers.get(protocol.HDR_REQUEST_ID)
        if not protocol.valid_request_id(rid):
            self._reject(400, "missing or malformed X-Request-Id")
            return

        hint = self.headers.get(protocol.HDR_LANG_HINT, "auto")
        if hint not in protocol.LANG_HINTS:
            self._reject(400, f"bad lang hint {hint!r}")
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._reject(400, "bad Content-Length")
            return
        if length > protocol.MAX_BODY_BYTES:
            self._reject(413, "body exceeds 30s of 16kHz PCM")
            return
        if length <= 0 or length % 2 != 0:
            self._reject(400, "body must be non-empty s16le PCM (even byte count)")
            return

        self._body_consumed = True
        try:
            body = self.rfile.read(length)
        except (TimeoutError, OSError):
            app.counters["client_gone"] += 1
            log.info(status_line(evt="CLIENT_GONE", path=self.path, code=0))
            self.close_connection = True
            return
        if len(body) < length:
            app.counters["client_gone"] += 1
            self.close_connection = True
            return

        if not app.try_admit():
            self._reject(429, "server busy", {"Retry-After": "1"})
            return
        try:
            self._decode_and_reply(rid, body, hint)
        finally:
            app.release()

    def _decode_and_reply(self, rid: str, body: bytes, hint: str):
        import numpy as np  # deferred: keeps module import light for tooling
        app = self.app
        audio = np.frombuffer(body, dtype=np.int16).astype(np.float32) / 32768.0
        audio_s = len(audio) / protocol.SAMPLE_RATE
        wall = app._config.get("decode_wall_s", protocol.SERVER_DECODE_WALL_S)

        result: dict = {}

        def work():
            with app._decode_lock:                 # single-flight decode
                t0 = time.monotonic()
                try:
                    result["res"] = langpolicy.transcribe(audio, app.engine, lang_hint=hint)
                except Exception as e:             # decode failure -> honest 500
                    result["err"] = e
                result["ms"] = int((time.monotonic() - t0) * 1000)

        t = threading.Thread(target=work, daemon=True, name=f"decode-{rid}")
        t.start()
        t.join(wall)
        if t.is_alive():
            self._reject(500, "decode_timeout")
            log.warning(status_line(evt="DECODE_TIMEOUT", id=rid, wall_s=wall))
            return
        if "err" in result:
            self._reject(500, f"decode_failed:{type(result['err']).__name__}")
            log.warning(status_line(evt="DECODE_FAIL", id=rid,
                                    err=type(result["err"]).__name__))
            return

        res: langpolicy.PolicyResult = result["res"]
        ms = result["ms"]
        app.record_decode(ms)
        model = res.model_role
        name = getattr(app.engine, "model_name", None)
        if callable(name):
            model = name(res.model_role)
        payload = {
            "request_id": rid, "text": res.text, "lang": res.lang,
            "lang_prob": round(res.lang_prob, 4),
            "avg_logprob": round(res.avg_logprob, 4),
            "no_speech_prob": round(res.no_speech_prob, 4),
            "compression_ratio": round(res.compression_ratio, 4),
            "decode_ms": ms,
            "rtf": round(ms / 1000.0 / audio_s, 4) if audio_s > 0 else 0.0,
            "model": model, "server_version": app.version, "ts": _now_iso_ms(),
        }
        if not self._client_still_there():
            app.counters["client_gone"] += 1
            log.info(status_line(evt="CLIENT_GONE", id=rid, code=200))
            self.close_connection = True
            return
        if self._send_json(200, payload):
            self._count(200)
            # status line: numbers only, NEVER text (scar 55)
            log.info(status_line(evt="REQ", id=rid, code=200, bytes=len(body),
                                 ms=ms, rtf=payload["rtf"], lang=res.lang,
                                 lp=payload["avg_logprob"], len=len(res.text),
                                 reason=res.detect_reason))


# ---------------------------------------------------------------- main

def load_config(path: Path) -> dict:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    validate_bind(cfg.get("bind", []))
    return cfg


def _read_token(cfg: dict) -> str:
    import os
    token_file = os.environ.get("KESHEV_TOKEN_FILE") or cfg["token_file"]
    p = Path(token_file).expanduser()
    token = p.read_text(encoding="utf-8").strip()
    if len(token) != 64:
        raise ValueError(f"token in {p} must be 64 hex chars, got {len(token)}")
    return token


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="KESHEV STT server (K10)")
    ap.add_argument("--config", type=Path, required=True)
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)s %(message)s")
    _quiet_libraries()      # journald carries OUR status lines only (gate 19)
    cfg = load_config(args.config)
    try:
        from server.sdnotify import Notifier       # repo/package layout (PC)
    except ImportError:
        from sdnotify import Notifier              # flat deploy layout (eran1 ~/keshev)
    notifier = Notifier()

    srv = SttServer(cfg, engine=None, token=_read_token(cfg), notifier=notifier)
    srv.start()                                     # serve 503 LOADING immediately

    def pet_loop():
        """Cheap, frequent systemd pet — gated on the canary still being fresh.

        Decoupled from warm_and_canary_loop on purpose (see protocol.PET_INTERVAL_S):
        the pet must beat WatchdogSec/2, the real decode must not run that often on
        Qwen's machine. A wedged model stops refreshing canary_age_s, should_pet()
        goes False, the petting stops and systemd restarts us — scar 5 intact.
        """
        while True:
            time.sleep(protocol.PET_INTERVAL_S)
            if should_pet(srv.canary_age_s):
                notifier.watchdog()

    def _model_ref(v: str) -> str:
        """A bare HF repo id ("org/name") passes through untouched; anything
        that looks like a filesystem path gets ~-expanded. Public configs
        name repo ids (auto-download); personal/local configs name paths."""
        if "/" in v and not (Path(v).expanduser().exists() or v.startswith((".", "~", "/")) or ":" in v):
            return v
        return str(Path(v).expanduser())

    def warm_and_canary_loop():
        models = cfg["models"]
        engine = FasterWhisperEngine(
            _model_ref(models["stock"]),
            _model_ref(models["lora"]),
            device=cfg.get("device", "cuda"),
            compute_type=cfg.get("compute_type", "int8_float16"),
            download_root=cfg.get("download_root"))
        srv.attach_engine(engine)
        if not srv.run_canary():                    # READY only after real output
            log.error(status_line(evt="FIRST_CANARY_FAIL"))
            raise SystemExit(3)
        srv.set_ready()
        notifier.ready()
        log.info(status_line(evt="READY", version=srv.version))
        while True:
            time.sleep(protocol.CANARY_INTERVAL_S)
            srv.run_canary()                        # failure -> no pet -> systemd restarts

    threading.Thread(target=warm_and_canary_loop, daemon=True, name="warm-canary").start()
    threading.Thread(target=pet_loop, daemon=True, name="watchdog-pet").start()

    import signal
    stop = threading.Event()

    def on_term(_sig, _frm):
        notifier.stopping()
        stop.set()

    signal.signal(signal.SIGTERM, on_term)
    signal.signal(signal.SIGINT, on_term)
    stop.wait()
    srv.stop()
    log.info(status_line(evt="STOPPED"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
