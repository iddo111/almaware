# -*- coding: utf-8 -*-
"""KESHEV-6 STT server - 127.0.0.1:8738, BESIDE the live :8737, never instead of it.

WHY THIS EXISTS (measured 2026-09-03, 17:00-23:00, Iddo's own dictation):
1,586 segments reached the decoder; the live server returned usable text for
209 of them (13.2%) and nothing for 1,360 (85.8%). Split by level, the story is
not one story:

      peak_rms      ok   empty      the honest reading
      < 4,000       19   1,053      room, fan, keyboard, music - NOT lost speech
      >= 8,000     161      84      HIS VOICE.

KESHEV-EMPTY-20260903.md then settled the empties for good: 30 of 30 sampled
"empty" wavs produced no Hebrew sentence from ANY of three decoders (the live
PC server, eran1, and this model). They are laughter, breath and room. So the
85.8% is the guard WORKING, and this server does not chase it.

WHAT THIS SERVER IS ACTUALLY FOR: the text he does get. Tonight the live path
turned Chinchilla into "tsarli va-hetsi" and "sochen Sonnet" into "lachen
sonat". Names are the wound.

WHAT IS DIFFERENT FROM :8737
  * ONE model, ivrit-ai/whisper-large-v3-turbo-ct2 (a Hebrew fine-tune of
    large-v3-turbo) instead of iddo-lora-run2-ct2. Measured on Iddo's own clips
    on eran2 today: 5/5 (eran-brain/hebrew-ref/HEBREW-JUDGE-20260903.md).
  * initial_prompt carrying his project vocabulary (lexicon.py).
  * NO language routing at all. The client already forces he; routing a
    code-switched sentence to `en` is the historic wall (08-19 inquiry), so
    Latin words the model emits inside a Hebrew sentence stay where they are.
  * speech_ratio is REPORTED on every reply, so the client's hallucination
    stop-list can stop firing on loud speech and keep firing on silence.

WHAT IS DELIBERATELY IDENTICAL
  The wire contract, field for field (tests/test_contract_parity.py reads
  mic-rebuild/common/protocol.py and asserts the constants match). Switching is
  one environment variable, and rolling back is deleting it:
      KESHEV_STT_URL=http://127.0.0.1:8738/v1/transcribe

PRIVACY, unchanged and structural: request audio lives only in RAM - this file
has no code path that writes audio to disk - and the logger REFUSES transcript
fields at the type level.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import importlib.util
import json
import logging
import logging.handlers
import math
import os
import signal
import socket
import sys
import threading
import time
import wave
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lexicon  # noqa: E402

log = logging.getLogger("keshev6")

# ---------------------------------------------------------------- live lexicon
# K6-05 (2026-09-06): the lexicon is DATA and data must not cost the live mic a
# restart. It was read exactly once, at boot, so the 04:30 name edit sat unused
# for 3.6 h while the decoder kept prompting with the stale string, and the only
# way to apply it was to restart Iddo microphone decoder.
#
# Now: a FRESH module object is built from the file whenever its mtime moves
# (SIGHUP forces the check), and the swap is one name rebinding, so a decode
# already holding the old module finishes with the old module - whole, never
# half-swapped. A BROKEN edit never reaches the server: the candidate must
# import and actually repair a probe string before it is allowed to replace a
# working lexicon. server-6.json stays boot-only on purpose (bind and model
# changes need a restart anyway).
_LEX = lexicon
_LEX_PATH = Path(__file__).resolve().parent / "lexicon.py"
_LEX_MTIME = 0.0
_LEX_SHA = ""
_LEX_SERIAL = 0
_HUP = threading.Event()


def current_lexicon():
    """The lexicon in force RIGHT NOW. Read once per request, never cached."""
    return _LEX


def _lexicon_fingerprint(mod) -> str:
    """A hash of the DATA only - the prompt and both repair maps. Not the file,
    so a comment edit cannot masquerade as a behaviour change."""
    h = hashlib.sha256()
    h.update(getattr(mod, "PROMPT_HE", "").encode("utf-8"))
    for k, v in sorted(getattr(mod, "EXACT_REPAIRS", {}).items()):
        h.update(("%s>%s\n" % (k, v)).encode("utf-8"))
    for t in getattr(mod, "FUZZY_TARGETS", ()):   # order is part of the behaviour
        h.update(("~%s\n" % t).encode("utf-8"))
    return h.hexdigest()[:12]


def reload_lexicon_if_changed(force: bool = False) -> bool:
    """True when a NEW lexicon was installed. Never raises: a decoder that dies
    on a typo in a word list is worse than one running last hour's word list."""
    global _LEX, _LEX_MTIME, _LEX_SHA, _LEX_SERIAL
    try:
        mtime = _LEX_PATH.stat().st_mtime
    except OSError as e:
        log.warning(status_line(evt="LEXICON_STAT_FAIL", err=type(e).__name__))
        return False
    if not force and mtime == _LEX_MTIME:
        return False
    try:
        _LEX_SERIAL += 1
        name = "keshev6_lexicon_%d" % _LEX_SERIAL
        spec = importlib.util.spec_from_file_location(name, _LEX_PATH)
        if spec is None or spec.loader is None:
            raise ImportError("no spec for %s" % _LEX_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        # PROVE it works before trusting it with his speech. The probe is a
        # lexicon constant, never a transcript.
        probe = (getattr(mod, "FUZZY_TARGETS", None) or ("bdiqa",))[0]
        out, _changes = mod.repair(probe)
        if not isinstance(out, str) or not isinstance(mod.PROMPT_HE, str):
            raise TypeError("lexicon repair/PROMPT_HE have the wrong type")
    except Exception as e:
        # the file is bad; keep the good one and SAY SO. Silence here would be
        # the same shape as the empty menu: a change that does nothing, quietly.
        _LEX_MTIME = mtime      # do not re-explode every 30 s on the same typo
        log.error(status_line(evt="LEXICON_RELOAD_FAILED", err=type(e).__name__,
                              why=str(e)[:60].replace(" ", "_")))
        return False
    sha = _lexicon_fingerprint(mod)
    same = (sha == _LEX_SHA)
    _LEX = mod
    _LEX_MTIME = mtime
    _LEX_SHA = sha
    log.warning(status_line(evt="LEXICON_RELOADED", sha=sha,
                            data_changed=int(not same),
                            prompt_len=len(mod.PROMPT_HE),
                            exact=len(mod.EXACT_REPAIRS),
                            fuzzy=len(mod.FUZZY_TARGETS)))
    return True

# ---------------------------------------------------------------- wire contract
# Copied, not imported: this server must keep answering if mic-rebuild moves.
# tests/test_contract_parity.py proves the copy has not drifted.
PORT = 8738
PATH_TRANSCRIBE = "/v1/transcribe"
PATH_HEALTH = "/health"
PATH_METRICS = "/metrics"
SAMPLE_RATE = 16000
MAX_BODY_BYTES = 30 * SAMPLE_RATE * 2
HDR_REQUEST_ID = "X-Request-Id"
HDR_LANG_HINT = "X-Lang-Hint"
HDR_CLIENT_ID = "X-Client-Id"          # NEW, optional: the join buffer's key
HDR_JOIN = "X-Join"                    # NEW, optional: "1" opts into joining
LANG_HINTS = ("auto", "he", "en")
INFLIGHT_CAP = 2

_BANNED_LOG_FIELDS = frozenset({"text", "transcript", "title"})


def status_line(**fields) -> str:
    """key=value status line. Transcript content is UNREPRESENTABLE."""
    banned = _BANNED_LOG_FIELDS.intersection(fields)
    if banned:
        raise TypeError(f"status_line refuses transcript fields: {sorted(banned)}")
    return " ".join(f"{k}={v}" for k, v in fields.items())


def _now_iso_ms() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _percentile(sorted_ms: list, q: float) -> int:
    if not sorted_ms:
        return 0
    idx = min(len(sorted_ms) - 1, max(0, math.ceil(q * len(sorted_ms)) - 1))
    return int(sorted_ms[idx])


def valid_request_id(rid: object) -> bool:
    """Looser than :8737's regex ON PURPOSE. keshev-next's decoder.py mints
    `<8hex>-<epoch_ms>`, which :8737's `[0-9]{6,}` happens to accept; anything
    non-empty and sane is accepted here so a client change can never turn into
    a silent 400."""
    return isinstance(rid, str) and 3 <= len(rid) <= 128 and "\n" not in rid


# ---------------------------------------------------------------- speechiness

def speech_ratio(audio: np.ndarray) -> float:
    """Fraction of 30 ms frames that look like a voice rather than a room.

    NOT a VAD library - a VAD is exactly what already failed here (silero's
    inner VAD ate 37% of his real speech; the comment in mic-rebuild's
    langpolicy.py records the measurement). This is a REPORTING number, never a
    gate: two cheap independent cues that silence and steady noise both fail.

      energy      frame RMS above (noise floor x 3)
      modulation  the envelope must actually MOVE - a fan is loud and flat
    """
    if audio.size < SAMPLE_RATE // 10:
        return 0.0
    n = int(0.03 * SAMPLE_RATE)
    frames = audio[: (audio.size // n) * n].reshape(-1, n)
    if frames.shape[0] < 4:
        return 0.0
    rms = np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1)) + 1e-9
    floor = float(np.percentile(rms, 10))
    loud = rms > max(floor * 3.0, 3e-4)
    env = rms / (float(np.mean(rms)) + 1e-9)
    if float(np.std(env)) < 0.25:          # flat envelope == machine, not a mouth
        return 0.0
    return float(np.mean(loud))


# ---------------------------------------------------------------- engine

def _add_cuda_dlls() -> None:
    """The cuBLAS/cuDNN wheels live under site-packages/nvidia and are NOT on
    PATH for a service. RUN-STT-PC.cmd prepends them; a server that only starts
    from one .cmd file is a broken window waiting, so do it in code too.

    K6-06 (2026-09-06): Windows ONLY. This walks a Lib/site-packages layout that
    does not exist on eran1, and os.add_dll_directory does not exist off
    Windows; on the DGX the loader path is set by run_keshev6.sh
    (LD_LIBRARY_PATH -> ct2-install/lib + the cudnn wheel)."""
    if os.name != "nt":
        return
    base = Path(sys.executable).parent / "Lib" / "site-packages" / "nvidia"
    for sub in ("cublas", "cudnn", "cuda_runtime", "cuda_nvrtc"):
        p = base / sub / "bin"
        if p.is_dir():
            try:
                os.add_dll_directory(str(p))
            except (OSError, AttributeError):
                pass
            os.environ["PATH"] = str(p) + os.pathsep + os.environ.get("PATH", "")


def _resolve_local(model_id: str) -> str:
    """Prefer the copy already in the HF cache over a network round trip.

    Measured: the bare repo id costs a 21 s call to huggingface.co on every
    start, and on a dead link it is a startup that fails for no local reason.
    The model is 1.6 GB and already on this disk; a decoder that needs the
    internet to answer a microphone is not a decoder."""
    if os.path.sep in model_id or "/" not in model_id:
        return model_id
    try:
        from huggingface_hub import snapshot_download
        return snapshot_download(model_id, local_files_only=True)
    except Exception:
        return model_id


class IvritEngine:
    """ONE ivrit-ai turbo model. No LoRA, no second model, no detection pass.

    8 GB card, and :8737 already holds ~3.2 GB of it: int8_float16 is not a
    preference, it is the budget. Measured 2026-09-03: 818 MiB resident, 1.29 s
    for a 5.06 s clip while the live server was serving.
    """

    def __init__(self, model_id: str, device: str = "cuda",
                 compute_type: str = "int8_float16"):
        _add_cuda_dlls()
        from faster_whisper import WhisperModel
        t0 = time.monotonic()
        self.model_id = model_id                 # the NAME, for /health and replies
        self._path = _resolve_local(model_id)    # the PATH, for loading and reloading
        self.device = device
        self.compute_type = compute_type
        self._m = WhisperModel(self._path, device=device, compute_type=compute_type)
        log.info(status_line(evt="MODEL_LOADED", model=self._path,
                             load_s=round(time.monotonic() - t0, 1),
                             compute=compute_type))

    def reload(self) -> None:
        """One rebuild after a CUDA OOM, then we stop pretending (503)."""
        import gc
        from faster_whisper import WhisperModel
        self._m = None
        gc.collect()
        # the resolved PATH, never the repo id: a reload after an OOM must not
        # depend on the internet being up.
        self._m = WhisperModel(self._path, device=self.device,
                               compute_type=self.compute_type)
        log.warning(status_line(evt="MODEL_RELOADED"))

    def decode(self, audio: np.ndarray, language: str = "he",
               initial_prompt: str | None = None) -> dict:
        segments, _info = self._m.transcribe(
            audio,
            language=language,
            beam_size=5,
            temperature=[0.0, 0.2],
            condition_on_previous_text=False,   # scar 30: never context feedback
            compression_ratio_threshold=2.4,
            no_speech_threshold=0.6,
            without_timestamps=True,
            vad_filter=False,                   # the client already gated
            initial_prompt=initial_prompt,
        )
        texts, lps, nsps, crs = [], [], [], []
        for s in segments:
            texts.append(s.text.strip())
            lps.append(s.avg_logprob)
            nsps.append(s.no_speech_prob)
            crs.append(s.compression_ratio)
        if not texts:
            return {"text": "", "avg_logprob": 0.0, "no_speech_prob": 1.0,
                    "compression_ratio": 0.0}
        n = len(texts)
        return {"text": " ".join(t for t in texts if t),
                "avg_logprob": sum(lps) / n,
                "no_speech_prob": sum(nsps) / n,
                "compression_ratio": sum(crs) / n}


# ---------------------------------------------------------------- join buffer

class JoinBuffer:
    """Opt-in (X-Join: 1) short-segment joining.

    262 of tonight's empties were under one second. The segmenter cuts on a
    900 ms unvoiced run, and his far-field speech has unvoiced runs INSIDE
    sentences, so a fragment can be half a word.

    Default OFF, and that is not timidity: if the server returned joined text to
    the current client, the previous sentence would be TYPED TWICE. Turning this
    on is a CLIENT change, so it stays behind a header until the client is ready.
    """
    WINDOW_S = 6.0
    SHORT_S = 0.8
    GAP_S = 0.5

    def __init__(self):
        self._buf: dict[str, tuple[float, np.ndarray]] = {}
        self._lock = threading.Lock()

    def offer(self, key: str, audio: np.ndarray) -> tuple[np.ndarray, bool]:
        """(audio_to_decode, joined). Stores every segment; joins only when the
        new one is short AND arrives hot on the last one's heels."""
        now = time.monotonic()
        with self._lock:
            prev = self._buf.get(key)
            self._buf[key] = (now, audio[-int(self.WINDOW_S * SAMPLE_RATE):])
            if prev is None:
                return audio, False
            prev_ts, prev_audio = prev
            if audio.size / SAMPLE_RATE >= self.SHORT_S or (now - prev_ts) > self.GAP_S:
                return audio, False
            return np.concatenate([prev_audio, audio]), True

    def sweep(self, max_age_s: float = 60.0) -> None:
        now = time.monotonic()
        with self._lock:
            for k in [k for k, (ts, _) in self._buf.items() if now - ts > max_age_s]:
                self._buf.pop(k, None)


# ---------------------------------------------------------------- server

class Keshev6Server:
    def __init__(self, config: dict, engine=None, token: str = ""):
        for b in config.get("bind", []):
            if b in ("0.0.0.0", "::", ""):
                raise ValueError(f"wildcard bind {b!r} refused - name the interface")
        self._config = config
        self.engine = engine
        self._token = (token or "").encode("utf-8")
        self._state = "LOADING"
        self._lock = threading.Lock()
        self._inflight = 0
        self._decode_lock = threading.Lock()
        self._decode_ms: list = []
        self._metrics_lock = threading.Lock()
        self.counters = {k: 0 for k in (
            "n_200", "n_400", "n_401", "n_404", "n_413", "n_429", "n_500", "n_503",
            "client_gone", "canary_ok", "canary_fail", "oom", "joined", "repaired")}
        self._canary_ts: float | None = None
        self._consec_timeouts = 0      # K6-03: 3 in a row == DEGRADED, not READY
        self._was_ready = False        # gates the self-heal: a first start is not a RECOVERY
        self._t0 = time.monotonic()
        self.joiner = JoinBuffer()
        self._httpds: list[ThreadingHTTPServer] = []
        self.version = "keshev6-1.0"

    # ---- lifecycle
    def start(self) -> None:
        port = self._config.get("port", PORT)
        for addr in self._config["bind"]:
            httpd = ThreadingHTTPServer((addr, port), _Handler)
            httpd.daemon_threads = True
            httpd.app = self
            self._httpds.append(httpd)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            port = httpd.server_address[1]
        log.info(status_line(evt="LISTENING", bind=",".join(self._config["bind"]),
                             port=self.port, version=self.version))

    def stop(self) -> None:
        for h in self._httpds:
            h.shutdown()
            h.server_close()

    @property
    def port(self) -> int:
        return self._httpds[0].server_address[1]

    @property
    def state(self) -> str:
        return self._state

    def set_ready(self) -> None:
        with self._lock:
            self._state = "READY"
            self._was_ready = True

    # ---- canary: /health is 200 only when a real clip really decodes (scar 5)
    #
    # K6-03 (2026-09-06). It did not do that. The clip was a synthetic 0.1
    # sine chirp and run_canary returned True on "no exception raised", so a
    # model that answered garbage - or answered nothing at all - passed
    # forever; and health() returned 200 on state=="READY" while ignoring
    # canary_age_s entirely. 2,287 requests never exercised the failure path,
    # which is exactly why it was unverified.
    #
    # What changed, and what did NOT: the answer SHAPE is now asserted (a dict,
    # the four contract keys, a str text, finite numbers), a stale canary or
    # three consecutive decode timeouts now take /health to 503, and
    # `canary_clip` is a real door - point it at a 1 s Hebrew wav with
    # `canary_expect` and the canary becomes a real one. Until a clip IDDO EAR
    # has ruled on is put there this is still the weak kind of canary, and
    # /health says so out loud (canary_kind=synthetic). Shipping an unjudged
    # clip with an invented expected token would rebuild the mislabeled exam.
    _CANARY_KEYS = ("text", "avg_logprob", "no_speech_prob", "compression_ratio")
    TIMEOUT_DEGRADE_AT = 3

    def _canary_synthetic(self) -> np.ndarray:
        t = np.arange(SAMPLE_RATE, dtype=np.float32) / SAMPLE_RATE
        return (0.1 * np.sin(2 * np.pi * (200 + 300 * t) * t)).astype(np.float32)

    def _canary_clip(self):
        """(audio, expected_token) from config, or (None, "").

        A configured clip that is MISSING or malformed is a canary FAILURE, not
        a silent skip - the one thing this door must never do is quietly not be
        there."""
        path = self._config.get("canary_clip")
        if not path:
            return None, ""
        with wave.open(str(path), "rb") as w:
            if (w.getnchannels() != 1 or w.getsampwidth() != 2
                    or w.getframerate() != SAMPLE_RATE):
                raise ValueError("canary_clip must be mono s16le 16 kHz")
            raw = w.readframes(w.getnframes())
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if audio.size < SAMPLE_RATE // 4:
            raise ValueError("canary_clip shorter than 0.25 s")
        return audio, str(self._config.get("canary_expect") or "")

    def _assert_canary(self, res, expect: str) -> None:
        """Raise unless the decoder gave a well-formed answer. Never embeds a
        transcript in the message - only key names and lengths."""
        if not isinstance(res, dict):
            raise TypeError("canary result is not a dict")
        missing = [k for k in self._CANARY_KEYS if k not in res]
        if missing:
            raise KeyError("canary result missing:" + ",".join(missing))
        if not isinstance(res["text"], str):
            raise TypeError("canary text is not a str")
        for k in ("avg_logprob", "no_speech_prob", "compression_ratio"):
            v = res[k]
            if (isinstance(v, bool) or not isinstance(v, (int, float))
                    or not math.isfinite(float(v))):
                raise ValueError("canary %s is not a finite number" % k)
        if expect and expect not in res["text"]:
            raise ValueError("canary clip missed its expected token (got %d chars)"
                             % len(res["text"]))

    @property
    def canary_kind(self) -> str:
        return "clip" if self._config.get("canary_clip") else "synthetic"

    def run_canary(self) -> bool:
        kind = self.canary_kind
        wait = float(self._config.get("canary_lock_wait_s", 30.0))
        try:
            clip, expect = self._canary_clip()
            audio = self._canary_synthetic() if clip is None else clip
            t0 = time.monotonic()
            # bounded: a wedged decode holds this lock forever, and a canary
            # that waits forever can never report the wedge.
            if not self._decode_lock.acquire(timeout=wait):
                raise TimeoutError("decode lock held %.0fs" % wait)
            try:
                res = self.engine.decode(audio, language="he")
            finally:
                self._decode_lock.release()
            ms = int((time.monotonic() - t0) * 1000)
            self._assert_canary(res, expect)
        except Exception as e:
            self.counters["canary_fail"] += 1
            log.warning(status_line(evt="CANARY_FAIL", kind=kind,
                                    err=type(e).__name__,
                                    why=str(e)[:70].replace(" ", "_")))
            return False
        self._canary_ts = time.monotonic()
        self.counters["canary_ok"] += 1
        log.info(status_line(evt="CANARY_OK", kind=kind, ms=ms))
        # SELF-HEAL. A failed reload after an OOM parks the server in LOADING so
        # it answers 503 instead of hanging - correct, but without this line it
        # stays parked until a human notices, which is the same broken window
        # wearing a different label. A real decode is the only evidence allowed
        # to un-park it (scar 5: health = output, never uptime).
        if (self._state in ("LOADING", "DEGRADED") and self.engine is not None
                and self._was_ready):
            with self._lock:
                was, self._state = self._state, "READY"
                self._consec_timeouts = 0
            log.warning(status_line(evt="RECOVERED", by="canary", was=was))
        return True

    @property
    def canary_age_s(self) -> float:
        return 1e9 if self._canary_ts is None else time.monotonic() - self._canary_ts

    # ---- auth / metrics
    def check_auth(self, header_value: str | None) -> bool:
        if not self._token or not header_value or not header_value.startswith("Bearer "):
            return False
        return hmac.compare_digest(header_value[7:].encode("utf-8"), self._token)

    def record_decode(self, ms: int) -> None:
        now = time.monotonic()
        with self._metrics_lock:
            self._decode_ms.append((now, ms))
            while self._decode_ms and self._decode_ms[0][0] < now - 3600:
                self._decode_ms.pop(0)

    def decode_window(self, seconds: float) -> dict:
        now = time.monotonic()
        with self._metrics_lock:
            ms = sorted(m for ts, m in self._decode_ms if ts >= now - seconds)
        return {"n": len(ms), "p50_ms": _percentile(ms, 0.50),
                "p95_ms": _percentile(ms, 0.95)}

    @property
    def canary_stale_after_s(self) -> float:
        return 2.0 * float(self._config.get("canary_interval_s", 300))

    @property
    def canary_stale(self) -> bool:
        return self.canary_age_s > self.canary_stale_after_s

    def decode_threads(self) -> int:
        return sum(1 for t in threading.enumerate()
                   if t.name.startswith("decode-"))

    def health_code(self) -> int:
        """K6-03: 200 ONLY when this decoder can be believed.

        It used to be 200 on state=="READY" alone - uptime wearing a health
        badge. canary_age_s was reported beside it and gated nothing, so a
        decoder whose every canary had failed for an hour still answered 200
        and the client kept sending his voice into it."""
        if self._state != "READY":
            return 503
        if self.canary_stale:
            return 503
        return 200

    def note_decode_timeout(self) -> int:
        """One wedged decode is a hiccup; three in a row is a decoder that has
        stopped being one. The abandoned thread is NOT killed (it still holds
        _decode_lock) - what changes is that we stop claiming to be healthy
        while it does."""
        with self._lock:
            self._consec_timeouts += 1
            n = self._consec_timeouts
            if n >= self.TIMEOUT_DEGRADE_AT and self._state == "READY":
                self._state = "DEGRADED"
        return n

    def note_decode_ok(self) -> None:
        if self._consec_timeouts:
            with self._lock:
                self._consec_timeouts = 0

    def health(self) -> dict:
        w = self.decode_window(3600)
        return {"state": self._state,
                "serving": self.health_code() == 200,
                "models": [self.engine.model_id] if self.engine else [],
                "inflight": self._inflight,
                "decode_p50_ms": w["p50_ms"], "decode_p95_ms": w["p95_ms"],
                "canary_age_s": round(self.canary_age_s, 1),
                "canary_kind": self.canary_kind,
                "canary_stale": self.canary_stale,
                "canary_stale_after_s": self.canary_stale_after_s,
                "consec_timeouts": self._consec_timeouts,
                "decode_threads": self.decode_threads(),
                "uptime_s": int(time.monotonic() - self._t0),
                "version": self.version}

    # ---- systemd watchdog: the thing :8737 has and this unit did not
    BOOT_GRACE_S = 600.0

    def watchdog_should_ping(self) -> bool:
        """Ping while healthy -- and, on the FIRST boot only, while the 1.6 GB
        model is still loading.

        Without that second clause this fix would carry the 2026-08-12 scar
        into the box it was written to protect: :8737 petted every 300 s against
        a 90 s watchdog, systemd SIGABRT'd it five times and gave up on the
        unit. A model that takes longer than WatchdogSec to load would be killed
        mid-load, take exactly as long again, and hit StartLimitBurst -- with the
        microphone's decoder down at the end of it.

        The grace is BOUNDED and one-shot: it applies only before this process
        has ever been READY, and only for BOOT_GRACE_S. A load that truly hangs
        is still caught. It is a grace, not a blank cheque."""
        if self.health_code() == 200:
            return True
        if not self._was_ready and (time.monotonic() - self._t0) < self.BOOT_GRACE_S:
            return True
        return False

    def start_systemd_watchdog(self) -> None:
        """Ping WATCHDOG=1 only while health_code()==200.

        Deliberately NOT a liveness ping. A process that is merely running keeps
        no promise: the ping is withheld the moment the canary goes stale or
        three decodes wedge, and systemd then restarts a DECODER that has proven
        it cannot decode. That is the only repair a wedged _decode_lock has -
        and it is a microphone decoder, never a living thing. With no
        WATCHDOG_USEC (a unit without WatchdogSec) this is a no-op, so old unit
        + new code is safe."""
        try:
            usec = int(os.environ.get("WATCHDOG_USEC", "0") or 0)
        except ValueError:
            usec = 0
        if usec <= 0:
            log.info(status_line(evt="SD_WATCHDOG", armed=0))
            return
        period = max(5.0, (usec / 1e6) / 3.0)
        _sd_notify("READY=1")

        def loop():
            while True:
                time.sleep(period)
                if self.watchdog_should_ping():
                    _sd_notify("WATCHDOG=1")
                else:
                    log.warning(status_line(evt="SD_WATCHDOG_WITHHELD",
                                            state=self._state,
                                            canary_age_s=int(self.canary_age_s),
                                            consec_timeouts=self._consec_timeouts))

        threading.Thread(target=loop, daemon=True, name="sd-watchdog").start()
        log.info(status_line(evt="SD_WATCHDOG", armed=1, period_s=round(period, 1)))

    def try_admit(self) -> bool:
        with self._lock:
            if self._inflight >= self._config.get("inflight_cap", INFLIGHT_CAP):
                return False
            self._inflight += 1
            return True

    def release(self) -> None:
        with self._lock:
            self._inflight -= 1


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "keshev6"

    @property
    def app(self) -> Keshev6Server:
        return self.server.app

    def log_message(self, fmt, *args):
        pass

    def _send_json(self, code: int, obj: dict) -> bool:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
            return True
        except (BrokenPipeError, ConnectionError, TimeoutError, OSError):
            self.app.counters["client_gone"] += 1
            self.close_connection = True
            return False

    def _count(self, code: int) -> None:
        self.app.counters[f"n_{code}"] = self.app.counters.get(f"n_{code}", 0) + 1

    def _drain_unread_body(self) -> None:
        """Read-and-discard an unread request body before rejecting it.

        MEASURED 2026-09-04: without this, a 960 KB over-limit POST got a TCP
        reset instead of the 413 - the client raised ChunkedEncodingError and
        never saw why it was refused. :8737 has the same drain for the same
        reason. A refusal the caller cannot read is not a refusal, it is a
        mystery."""
        if getattr(self, "_body_consumed", False):
            return
        self._body_consumed = True
        try:
            remaining = min(int(self.headers.get("Content-Length", "0") or 0),
                            4 * MAX_BODY_BYTES)
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

    def _reject(self, code: int, error: str) -> None:
        if self.command == "POST":
            self._drain_unread_body()
        self.close_connection = True
        self._count(code)
        self._send_json(code, {"error": error})
        log.info(status_line(evt="REQ", code=code, err=error))

    def _authed(self) -> bool:
        if self.app.check_auth(self.headers.get("Authorization")):
            return True
        self._reject(401, "unauthorized")
        return False

    def do_GET(self):
        if not self._authed():
            return
        if self.path == PATH_HEALTH:
            h = self.app.health()
            code = self.app.health_code()      # K6-03: not state alone
            self._count(code)
            self._send_json(code, h)
        elif self.path == PATH_METRICS:
            self._count(200)
            self._send_json(200, {"decode": {"1m": self.app.decode_window(60),
                                             "5m": self.app.decode_window(300),
                                             "60m": self.app.decode_window(3600)},
                                  "counters": dict(self.app.counters)})
        else:
            self._reject(404, "not_found")

    def do_POST(self):
        self._body_consumed = False
        if not self._authed():
            return
        if self.path == PATH_TRANSCRIBE:
            self._transcribe()
        else:
            self._reject(404, "not_found")

    def _transcribe(self):
        app = self.app
        if app.state != "READY":
            self._count(503)
            self._send_json(503, {"state": app.state})
            return
        rid = self.headers.get(HDR_REQUEST_ID)
        if not valid_request_id(rid):
            self._reject(400, "missing or malformed X-Request-Id")
            return
        hint = self.headers.get(HDR_LANG_HINT, "auto")
        if hint not in LANG_HINTS:
            self._reject(400, f"bad lang hint {hint!r}")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._reject(400, "bad Content-Length")
            return
        if length > MAX_BODY_BYTES:
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
            self.close_connection = True
            return
        if len(body) < length:
            app.counters["client_gone"] += 1
            self.close_connection = True
            return
        if not app.try_admit():
            self._reject(429, "server busy")
            return
        try:
            self._decode_and_reply(rid, body, hint)
        finally:
            app.release()

    def _decode_and_reply(self, rid: str, body: bytes, hint: str):
        app = self.app
        audio = np.frombuffer(body, dtype=np.int16).astype(np.float32) / 32768.0
        audio_s = len(audio) / SAMPLE_RATE
        wall = app._config.get("decode_wall_s", 8.0)
        # THE ONE ROUTING RULE: everything is Hebrew unless the client insisted
        # on English. No detection pass, no script re-decode.
        language = "en" if hint == "en" else "he"
        lex = current_lexicon()          # K6-05: read per request, not per boot
        prompt = (lex.PROMPT_HE
                  if language == "he" and app._config.get("use_prompt", True)
                  else None)

        joined = False
        if self.headers.get(HDR_JOIN, "") == "1":
            key = self.headers.get(HDR_CLIENT_ID) or self.client_address[0]
            audio, joined = app.joiner.offer(key, audio)
            if joined:
                app.counters["joined"] += 1

        result: dict = {}

        def work():
            with app._decode_lock:
                t0 = time.monotonic()
                try:
                    result["res"] = app.engine.decode(audio, language=language,
                                                      initial_prompt=prompt)
                except Exception as e:
                    result["err"] = e
                result["ms"] = int((time.monotonic() - t0) * 1000)

        t = threading.Thread(target=work, daemon=True, name=f"decode-{rid}")
        t.start()
        t.join(wall)
        if t.is_alive():
            # K6-03: the abandoned thread still holds app._decode_lock and
            # app.release() is about to free the inflight slot, so without this
            # accounting every further request stacked another blocked thread
            # while /health kept answering READY. Count it, name it, and let
            # three in a row take us out of READY.
            consec = app.note_decode_timeout()
            log.warning(status_line(evt="DECODE_TIMEOUT", id=rid, wall_s=wall,
                                    consec=consec, state=app.state,
                                    decode_threads=app.decode_threads()))
            self._reject(500, "decode_timeout")
            return
        if "err" in result:
            err = result["err"]
            name = type(err).__name__
            if "out of memory" in str(err).lower() or "OutOfMemory" in name:
                # ONE rebuild, then an honest 503. Never a hang: a wedged decoder
                # that keeps accepting sockets is the failure scar 5 is about.
                app.counters["oom"] += 1
                try:
                    app.engine.reload()
                    self._reject(503, "reloaded_after_oom")
                except Exception:
                    app._state = "LOADING"
                    self._reject(503, "oom")
                return
            self._reject(500, f"decode_failed:{name}")
            log.warning(status_line(evt="DECODE_FAIL", id=rid, err=name))
            return

        res = result["res"]
        ms = result["ms"]
        app.note_decode_ok()
        app.record_decode(ms)
        raw = res["text"]
        if app._config.get("use_repair", True):
            text, changes = lex.repair(raw)
        else:
            text, changes = raw, []
        if changes:
            app.counters["repaired"] += 1
            # K6-12: repaired=1 in 2,287 replies said the map is nearly all dead
            # weight, but not WHICH entries are alive - and the only live part is
            # the fuzzy pass, the one that can corrupt a real word. Hash-only:
            # the TARGET is a lexicon constant, what the model produced is his
            # speech, so only its LENGTH is ever written.
            exact = getattr(lex, "EXACT_REPAIRS", {})
            for before, after in changes:
                log.info(status_line(
                    evt="REPAIR", id=rid,
                    kind="exact" if before in exact else "fuzzy",
                    to=str(after).replace(" ", "_"), from_len=len(before)))
        payload = {
            # --- the fields :8737 returns, same names, same types
            "request_id": rid, "text": text, "lang": language, "lang_prob": 1.0,
            "avg_logprob": round(res["avg_logprob"], 4),
            "no_speech_prob": round(res["no_speech_prob"], 4),
            "compression_ratio": round(res["compression_ratio"], 4),
            "decode_ms": ms,
            "rtf": round(ms / 1000.0 / audio_s, 4) if audio_s > 0 else 0.0,
            "model": app.engine.model_id, "server_version": app.version,
            "ts": _now_iso_ms(),
            # --- ADDITIVE. An old client ignores these; textguard v2 uses them.
            "detect_reason": "hint" if hint != "auto" else "forced_he",
            "speech_ratio": round(speech_ratio(audio), 3),
            "repaired": len(changes),
            "joined": joined,
        }
        if self._send_json(200, payload):
            self._count(200)
            log.info(status_line(evt="REQ", id=rid, code=200, bytes=len(body), ms=ms,
                                 rtf=payload["rtf"], lang=language,
                                 lp=payload["avg_logprob"], len=len(text),
                                 sr=payload["speech_ratio"], joined=int(joined)))


# ---------------------------------------------------------------- main

LOG_MAX_BYTES = 8 * 1024 * 1024
LOG_BACKUPS = 5


def install_rotating_log(path: str):
    """K6-14: bound the log FILE. Returns the handler, or None when unset.

    state/keshev6.log was systemd StandardOutput=append: with no logrotate entry
    on the box - 1.3 MB/day into one file with nothing that could ever trim it.
    Empty path -> None, so a unit that still appends is unchanged and nothing is
    written twice."""
    if not path:
        return None
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS,
            encoding="utf-8")
    except OSError as e:
        log.warning(status_line(evt="LOGFILE_FAIL", err=type(e).__name__))
        return None
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.getLogger().addHandler(fh)
    log.info(status_line(evt="LOGFILE", max_mb=LOG_MAX_BYTES // (1024 * 1024),
                         backups=LOG_BACKUPS))
    return fh


def _sd_notify(message: str) -> bool:
    """sd_notify without the systemd python bindings (not in this venv).

    No NOTIFY_SOCKET (run by hand, or a unit with no WatchdogSec) -> a no-op
    returning False. Never raises: a notification socket is not allowed to take
    down a microphone decoder."""
    addr = os.environ.get("NOTIFY_SOCKET")
    if not addr:
        return False
    try:
        if addr.startswith("@"):          # abstract namespace
            addr = "\0" + addr[1:]
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sk:
            sk.sendto(message.encode("utf-8"), addr)
        return True
    except (OSError, AttributeError):
        return False


def _single_instance_lock(path: Path):
    """One server per port.

    THIS FUNCTION WAS WRONG WHEN FIRST WRITTEN AND THE TEST CAUGHT IT (2026-09-04).
    The first version just did open(path, "w") and assumed Windows would refuse a
    second writer. It does not - CPython opens with FILE_SHARE_WRITE, so a second
    process opened the same "lock" happily and reported success. A lock that
    always succeeds is worse than no lock: it is a guarantee you will rely on.

    msvcrt.locking() with LK_NBLCK takes a real, OS-enforced, non-blocking byte
    lock that dies with the process. On anything not Windows, fcntl.flock does
    the same job. The port bind is the backstop underneath both.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "a+", encoding="utf-8")
    try:
        try:
            import msvcrt
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        except ImportError:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        raise SystemExit(f"another keshev-6 server holds {path} - refusing to start")
    # The locked byte is unreadable to everyone, including us, so the PID goes in
    # a plain sibling file - the same split mic-rebuild uses (server.pid / mic.pid).
    # An ops file nobody can open is not an ops file.
    try:
        path.with_suffix(".pid").write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        pass
    return fh


def _set_priority(level: str) -> None:
    """K6-06 (2026-09-06): on Linux the UNIT owns priority (Nice=5, CPUWeight=30)
    and psutil is not in this venv, so all five boots on eran1 logged
    PRIORITY_FAIL err=ModuleNotFoundError - a warning that meant nothing and
    trained the reader to skip warnings. Say who owns it instead."""
    if os.name != "nt":
        log.info(status_line(evt="PRIORITY", owner="systemd", asked=level,
                             nice=os.nice(0)))
        return
    try:
        import psutil
        psutil.Process().nice({
            "high": psutil.HIGH_PRIORITY_CLASS,
            "above": psutil.ABOVE_NORMAL_PRIORITY_CLASS,
            "normal": psutil.NORMAL_PRIORITY_CLASS,
            "below": psutil.BELOW_NORMAL_PRIORITY_CLASS}[level])
        log.info(status_line(evt="PRIORITY", level=level))
    except Exception as e:
        log.warning(status_line(evt="PRIORITY_FAIL", err=type(e).__name__))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="KESHEV-6 STT server")
    ap.add_argument("--config", default=str(Path(__file__).parent / "server-6.json"))
    ap.add_argument("--no-prompt", action="store_true",
                    help="disable the lexicon initial_prompt (for A/B)")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("faster_whisper").setLevel(logging.WARNING)
    logging.getLogger("ctranslate2").setLevel(logging.WARNING)
    # K6-14: state/keshev6.log was systemd StandardOutput=append: with no
    # logrotate entry anywhere - 1.3 MB/day into one file, forever. The unit now
    # sends stdout to the journal and hands the FILE to us through this env var,
    # rotated. Both mismatch orders are safe: env unset (old unit) -> systemd
    # keeps appending exactly as before; new unit + old code -> journal only.
    install_rotating_log(os.environ.get("KESHEV6_LOG_FILE", "").strip())

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    if args.no_prompt:
        cfg["use_prompt"] = False
    lock = _single_instance_lock(Path(cfg.get("lock_file", "state/keshev6.lock")))
    token = Path(cfg["token_file"]).read_text(encoding="utf-8").strip()

    reload_lexicon_if_changed(force=True)      # K6-05: record the boot fingerprint
    try:
        signal.signal(signal.SIGHUP, lambda *_a: _HUP.set())
    except (AttributeError, ValueError):       # no SIGHUP on Windows
        pass

    srv = Keshev6Server(cfg, token=token)
    srv.start()
    # armed BEFORE the model loads: the load is exactly the window a watchdog
    # would otherwise kill (see watchdog_should_ping).
    srv.start_systemd_watchdog()
    # 2026-09-11: the DEFAULT is "above", not "high". Nothing on this PC may
    # outrank Iddo's microphone engine (HIGH since the 09-03 starvation fix);
    # a config that forgets the key must not quietly tie with it.
    _set_priority(cfg.get("priority", "above"))

    srv.engine = IvritEngine(cfg["model"], device=cfg.get("device", "cuda"),
                             compute_type=cfg.get("compute_type", "int8_float16"))
    if not srv.run_canary():
        log.error(status_line(evt="CANARY_FAILED_AT_START"))
        return 2
    srv.set_ready()
    log.info(status_line(evt="READY", port=srv.port, lexicon=_LEX_SHA,
                         canary_kind=srv.canary_kind))

    interval = float(cfg.get("canary_interval_s", 300))
    tick = min(30.0, interval)
    try:
        while True:
            time.sleep(tick)
            # K6-05: a lexicon edit takes effect on the next tick (<=30 s), or
            # immediately on SIGHUP. No restart of his microphone decoder.
            if _HUP.is_set():
                _HUP.clear()
                reload_lexicon_if_changed(force=True)
            else:
                reload_lexicon_if_changed()
            # K6-03: DEGRADED retries fast. The canary is the ONLY thing allowed
            # to clear it, so it must not be five minutes away.
            due = interval if srv.state == "READY" else min(interval, 60.0)
            if srv.canary_age_s >= due:
                srv.run_canary()
                srv.joiner.sweep()
    except KeyboardInterrupt:
        srv.stop()
        lock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
