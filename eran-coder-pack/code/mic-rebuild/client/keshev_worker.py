"""KESHEV worker — THE killable subprocess (K9; PHASE2-DESIGN.md sections
3.2, 4.3, 7).

ALL decode and (in K10 integration) ALL network egress live HERE, in a child
the client can TerminateProcess at any instant: kill = true cancellation of
both engines + deterministic VRAM release (scars 13/44/57). One frame in,
one frame out, synchronous — the parent's router is the only concurrency.

Laws implemented here:

  scar 11   "ready" is emitted only AFTER a REAL dummy inference (1s of
            zero audio through the actual loaded model) validates the CUDA
            context — a CUDA context is trusted only after real output.
  scar 14   WARMING begins with a free-VRAM probe (nvidia-smi, NO torch).
            free < need(model)+512MB steps down the pinned ladder with a
            vram_degrade frame; below the bottom rung the worker loads
            NOTHING and reports ready(LOCAL_UNAVAILABLE) — graceful
            degradation, never an OOM attempt.
  scar 47   No torch import. CPU decode has NO code path: the device
            argument is the literal "cuda" at the single construction site;
            no other device string exists in this module (test-pinned).
  scar 10   Every outgoing frame is stamped with THIS process's spawn
            generation (--gen); the parent discards mismatches.
  scar 18   Every failure is a frame (error / fatal / ok:false reply) —
            there is no silent exit path.

Engine spec: `--engine ct2` (default, the real GPU engine) or
`--engine fake:<dotted.module>` — the replay-rig/test injection seam; the
module must expose build(model_name) -> engine with .warm()/.decode().
Behavior triggers ride in the PCM payload, so this module has zero
test-only branches.

DGX path (engine=dgx): the HTTP client module client/dgx_engine.py is owned
by the concurrent K10 milestone; this worker lazy-imports it through a
narrow adapter and answers err=dgx_unconfigured / dgx_unavailable cleanly
until K12 wires the two together.
"""
from __future__ import annotations

import argparse
import importlib
import subprocess
import sys
import time

from pathlib import Path


# --- CUDA DLL discovery (scar: "cublas64_12.dll is not found or cannot be loaded")
# ctranslate2's CUDA engine needs the cuBLAS / cuDNN DLLs. On Python 3.8+ the
# system PATH is NOT enough — dependent DLLs load only from directories registered
# via os.add_dll_directory. The pip `nvidia-*` wheels ship them under
# site-packages/nvidia/*/bin. Register every one, at import, before any CUDA load.
# A directory that vanished between glob and registration is survivable — the PATH
# fallback below still applies — but it is never silently dropped: it lands here so
# a later "cublas64_12.dll is not found" has its evidence instead of a mystery.
CUDA_DLL_SKIPPED: list = []


def _enable_cuda_dlls() -> None:
    import os
    import glob
    import site
    roots = list(site.getsitepackages()) + [site.getusersitepackages()]
    for root in roots:
        for binp in glob.glob(os.path.join(root, "nvidia", "*", "bin")):
            try:
                os.add_dll_directory(binp)
            except OSError as exc:
                CUDA_DLL_SKIPPED.append("%s: %s" % (binp, exc))
            os.environ["PATH"] = binp + os.pathsep + os.environ.get("PATH", "")


_enable_cuda_dlls()


# Runnable both as `python -m client.keshev_worker` (repo cwd) and directly.
if __package__ in (None, ""):  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.protocol import FrameError, pack_frame, read_frame  # noqa: E402

# ---------------------------------------------------------------- constants
# scar 14 — per-model VRAM needs, MEASURED at K9 on the real 3070 Ti (see
# state/reports/k9-model-decision + the K9 RAMCHAT post) and pinned as code
# under git. MARGIN guards co-tenant creep (RC-5).
VRAM_MARGIN_MB = 512

# MEASURED 2026-08-12 (tools/measure_k9_model.py vram — real CT2-CUDA load +
# scar-11 dummy inference + one real Hebrew decode on the RTX 3070 Ti, live
# crutch resident; kill released 100% of each footprint, criterion 2):
#   small 529MB resident / 915ms real decode
#   base  305MB resident / 686ms
#   tiny  241MB resident / 340ms
# Pinned with rounding headroom over the measured residents:
VRAM_NEED_MB = {
    "small": 600,
    "base": 350,
    "tiny": 300,
}

# The degrade ladder (section 4.3). Design names small->base->distil; the
# distil family has no Hebrew-capable small variant (distil-*.en is
# English-only), so the bottom rung is whisper tiny — decision recorded in
# the K9 model report.
#
# K9 MODEL DECISION (2026-08-12, 12 real Hebrew voice_corpus clips, CER vs
# the eran1 iddo-lora primary): small median CER 0.325 / ivrit-turbo 0.266 /
# base 0.64 / tiny 0.56. ivrit-turbo buys ~6 CER points over small for ~2x
# the VRAM (1.6GB weights, GPU footprint DEFERRED under the shared-GPU
# guardrail) — on an 8GB shared GPU with weekly co-tenant creep (RC-5),
# `small` is the configured rung per section 7's criteria; base/tiny are
# last-resort degrade rungs only (their fallback text still passes
# textguard + recovered.txt, better than DEAF). Revisit-post-cutover note:
# the crutch's 2.6GB frees at K18, making ivrit-turbo viable if criterion-1
# quality demands it.
LADDER = ("small", "base", "tiny")

# HF snapshot ids resolved by faster-whisper (all already in the local cache).
MODEL_SOURCES = {
    "small": "Systran/faster-whisper-small",
    "base": "Systran/faster-whisper-base",
    "tiny": "Systran/faster-whisper-tiny",
}

# K2-matched compute type (eran1 runs the same); fp16 accumulate on the PC GPU.
COMPUTE_TYPE = "int8_float16"

LANG_WHITELIST = ("he", "en")


class VramProbeError(RuntimeError):
    """Free-VRAM could not be read — WARMING may not proceed blind (scar 14)."""


# ---------------------------------------------------------------- VRAM probe

def parse_free_vram_mb(text: str) -> int:
    """First line of `nvidia-smi --query-gpu=memory.free
    --format=csv,noheader,nounits` (device 0 — the only GPU on this PC)."""
    line = text.strip().splitlines()[0].strip() if text.strip() else ""
    if not line.isdigit():
        raise VramProbeError(f"unparseable nvidia-smi output: {text[:80]!r}")
    return int(line)


def read_free_vram_mb() -> int:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise VramProbeError(f"nvidia-smi failed: {exc}") from exc
    return parse_free_vram_mb(out)


def choose_model(configured: str, free_mb: int, need_mb: dict | None = None,
                 ladder: tuple | None = None):
    """scar 14 ladder walk. Returns (chosen_or_None, degrade_event_or_None).
    None chosen = LOCAL_UNAVAILABLE: load NOTHING, never attempt an OOM."""
    need_mb = VRAM_NEED_MB if need_mb is None else need_mb
    ladder = LADDER if ladder is None else ladder
    if configured not in ladder:
        raise ValueError(f"configured model {configured!r} not on the ladder {ladder}")
    for name in ladder[ladder.index(configured):]:
        if name not in need_mb:
            raise ValueError(f"ladder model {name!r} has no pinned VRAM need")
        if free_mb >= need_mb[name] + VRAM_MARGIN_MB:
            if name == configured:
                return name, None
            return name, {"want": configured, "got": name, "free_mb": free_mb}
    return None, None


# ---------------------------------------------------------------- engines

class CT2LocalEngine:
    """The warm-resident GPU fallback decoder (section 7).

    GPU-only by construction: `device` is the literal "cuda" at the single
    WhisperModel call site — there is no code path that could name another
    device (scar 47). Loaded once per spawn, never unloaded by routing
    (scar 57); the only unload is process death.
    """

    def __init__(self, model_name: str, vram_probe_fn=read_free_vram_mb):
        import numpy as np  # local import: the fake-engine path never needs it
        from faster_whisper import WhisperModel
        from common.decode_params import decode_kwargs
        self._np = np
        self._decode_kwargs = decode_kwargs
        self._vram_probe_fn = vram_probe_fn
        self.model_name = model_name
        self._free_before = vram_probe_fn()
        self.model = WhisperModel(
            MODEL_SOURCES[model_name], device="cuda", compute_type=COMPUTE_TYPE,
        )

    def warm(self) -> dict:
        """scar 11: a REAL 1s zero-audio inference through the loaded model.
        The CUDA context is proven by output, never assumed."""
        t0 = time.monotonic()
        audio = self._np.zeros(16000, dtype=self._np.float32)
        segments, _info = self.model.transcribe(audio, language="he",
                                                **self._decode_kwargs())
        list(segments)  # generator — consuming it IS the inference
        warm_ms = int((time.monotonic() - t0) * 1000)
        vram_mb = max(0, self._free_before - self._vram_probe_fn())
        return {"vram_mb": vram_mb, "warm_ms": warm_ms}

    def decode(self, pcm: bytes, lang_hint: str) -> dict:
        audio = (self._np.frombuffer(pcm, dtype=self._np.int16)
                 .astype(self._np.float32) / 32768.0)
        language = lang_hint if lang_hint in LANG_WHITELIST else None
        segments, info = self.model.transcribe(audio, language=language,
                                               **self._decode_kwargs())
        parts = [s for s in segments]
        text = " ".join(s.text.strip() for s in parts).strip()
        logprobs = [s.avg_logprob for s in parts]
        return {
            "text": text,
            "lang": info.language,
            "avg_logprob": (sum(logprobs) / len(logprobs)) if logprobs else 0.0,
            "no_speech_prob": parts[0].no_speech_prob if parts else 1.0,
        }


def build_engine(spec: str, model_name: str, vram_probe_fn):
    if spec == "ct2":
        return CT2LocalEngine(model_name, vram_probe_fn=vram_probe_fn)
    if spec.startswith("fake:"):
        return importlib.import_module(spec[len("fake:"):]).build(model_name)
    raise ValueError(f"unknown engine spec {spec!r}")


# ---------------------------------------------------------------- rss probe

def _rss_mb() -> int:
    """Own resident set, MB. -1 = honestly unknown (never a fake zero)."""
    try:
        if sys.platform == "win32":
            import ctypes
            import ctypes.wintypes as wt

            class PMC(ctypes.Structure):
                _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t),
                            ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                            ("PagefileUsage", ctypes.c_size_t),
                            ("PeakPagefileUsage", ctypes.c_size_t)]

            k32 = ctypes.windll.kernel32
            psapi = ctypes.windll.psapi
            # 64-bit HANDLE law: without restype/argtypes the pseudo-handle
            # truncates to a 32-bit int -> ERROR_INVALID_HANDLE (found at K9).
            k32.GetCurrentProcess.restype = wt.HANDLE
            psapi.GetProcessMemoryInfo.argtypes = [
                wt.HANDLE, ctypes.POINTER(PMC), wt.DWORD]
            psapi.GetProcessMemoryInfo.restype = wt.BOOL
            pmc = PMC()
            pmc.cb = ctypes.sizeof(PMC)
            ok = psapi.GetProcessMemoryInfo(
                k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
            if not ok:
                return -1
            return int(pmc.WorkingSetSize // (1024 * 1024))
        with open("/proc/self/statm", encoding="ascii") as fh:
            pages = int(fh.read().split()[1])
        import os
        return int(pages * os.sysconf("SC_PAGE_SIZE") // (1024 * 1024))
    except (OSError, ValueError, AttributeError):
        return -1


# ---------------------------------------------------------------- main loop

class WorkerMain:
    """One spawn generation of the worker. Synchronous frame loop."""

    def __init__(self, *, gen: int, model: str, engine_spec: str = "ct2",
                 free_vram_mb_fn=read_free_vram_mb, stdin=None, stdout=None,
                 server_url: str | None = None, token_file: str | None = None,
                 ladder: tuple | None = None, need_mb: dict | None = None):
        self.gen = gen
        self.model = model
        self.engine_spec = engine_spec
        self.free_vram_mb_fn = free_vram_mb_fn
        self.stdin = stdin if stdin is not None else sys.stdin.buffer
        self.stdout = stdout if stdout is not None else sys.stdout.buffer
        self.server_url = server_url
        self.token_file = token_file
        self.ladder = ladder
        self.need_mb = need_mb
        self.engine = None
        self._dgx_obj = None
        self.local_state = "LOCAL_UNAVAILABLE"
        self.warm_before_ready = False

    # ------------------------------------------------------------- plumbing

    def _send(self, header: dict, payload: bytes = b"") -> None:
        header = dict(header)
        header["gen"] = self.gen
        self.stdout.write(pack_frame(header, payload))
        self.stdout.flush()

    def _send_fatal(self, exc: BaseException) -> None:
        try:
            self._send({"event": "fatal",
                        "err": f"{type(exc).__name__}: {str(exc)[:300]}"})
        except OSError as pipe_exc:  # parent already gone — say so on stderr
            print(f"keshev_worker fatal (pipe dead: {pipe_exc}): {exc}",
                  file=sys.stderr)

    # ------------------------------------------------------------- startup

    def run(self) -> int:
        try:
            self._send({"event": "loading"})
            free_mb = self.free_vram_mb_fn()
            chosen, degrade = choose_model(self.model, free_mb,
                                           need_mb=self.need_mb,
                                           ladder=self.ladder)
            if degrade is not None:
                self._send({"event": "vram_degrade", **degrade})
            if chosen is None:
                # scar 14: load NOTHING — DGX still works through us.
                self.engine = None
                self.local_state = "LOCAL_UNAVAILABLE"
                self._send({"event": "ready", "local_state": self.local_state,
                            "model": None, "vram_mb": 0, "warm_ms": 0,
                            "free_mb": free_mb})
            else:
                self.engine = build_engine(self.engine_spec, chosen,
                                           self.free_vram_mb_fn)
                warm = self.engine.warm()  # scar 11 — REAL inference first
                self.warm_before_ready = True
                self.local_state = "READY"
                self._send({"event": "ready", "local_state": self.local_state,
                            "model": chosen, "vram_mb": int(warm["vram_mb"]),
                            "warm_ms": int(warm["warm_ms"])})
        except Exception as exc:  # noqa: BLE001 — any startup failure is fatal+loud
            self._send_fatal(exc)
            return 13
        return self._loop()

    # ------------------------------------------------------------- commands

    def _loop(self) -> int:
        while True:
            try:
                got = read_frame(self.stdin)
            except FrameError as exc:
                # Framing lost = unrecoverable stream: die loudly, parent respawns.
                self._send_fatal(exc)
                return 12
            if got is None:
                return 0  # parent closed the pipe — leave quietly
            header, payload = got
            cmd = header.get("cmd")
            if cmd == "shutdown":
                return 0
            if cmd == "ping":
                self._send({"event": "pong", "rss_mb": _rss_mb()})
            elif cmd == "probe":
                self._probe()
            elif cmd == "decode":
                self._decode(header, payload)
            else:
                self._send({"event": "error", "err": "unknown_cmd",
                            "cmd": str(cmd)[:40]})

    def _decode(self, header: dict, payload: bytes) -> None:
        rid = header.get("id")
        engine_name = header.get("engine", "local")
        lang_hint = header.get("lang_hint", "auto")
        t0 = time.monotonic()
        if engine_name == "dgx":
            reply = self._dgx_decode(rid, payload, lang_hint,
                                     header.get("deadline_ms"))
        elif engine_name == "local":
            if self.engine is None:
                reply = {"ok": False, "err": "local_unavailable"}
            else:
                try:
                    reply = {"ok": True, **self.engine.decode(payload, lang_hint)}
                except Exception as exc:  # noqa: BLE001 — reply, don't die
                    reply = {"ok": False, "err": "engine_error",
                             "detail": f"{type(exc).__name__}: {str(exc)[:200]}"}
        else:
            reply = {"ok": False, "err": "unknown_engine"}
        reply["id"] = rid
        reply["engine"] = engine_name
        reply["decode_ms"] = int((time.monotonic() - t0) * 1000)
        self._send(reply)

    # ------------------------------------------------------------- dgx seam
    # client/dgx_engine.py is K10's module (DgxEngine class, typed errors).
    # Built lazily on first use so a worker without --server-url never
    # touches the network stack at all.

    def _dgx(self):
        if not self.server_url:
            return None
        if self._dgx_obj is None:
            from client.dgx_engine import DgxEngine
            token = ""
            if self.token_file:
                token = Path(self.token_file).read_text(encoding="utf-8").strip()
            self._dgx_obj = DgxEngine(self.server_url, token)
        return self._dgx_obj

    def _dgx_decode(self, rid, payload, lang_hint, deadline_ms) -> dict:
        try:
            eng = self._dgx()
            if eng is None:
                return {"ok": False, "err": "dgx_unconfigured"}
            res = eng.transcribe(payload, request_id=str(rid),
                                 duration_ms=len(payload) // 32,
                                 lang_hint=lang_hint)
            return {"ok": True, "text": res.text, "lang": res.lang,
                    "avg_logprob": res.avg_logprob,
                    "no_speech_prob": res.no_speech_prob,
                    "server_decode_ms": res.decode_ms, "model": res.model}
        except ImportError:
            return {"ok": False, "err": "dgx_unavailable"}
        except ValueError as exc:
            return {"ok": False, "err": "bad_request", "detail": str(exc)[:200]}
        except Exception as exc:  # noqa: BLE001 — every failure is a frame
            return {"ok": False, "err": _classify_dgx_err(exc),
                    "detail": f"{type(exc).__name__}: {str(exc)[:200]}"}

    def _probe(self) -> None:
        try:
            eng = self._dgx()
            if eng is None:
                self._send({"event": "probe_result", "state": "UNKNOWN",
                            "err": "dgx_unconfigured"})
                return
            res = eng.probe()  # NEVER raises (scar 5 rules inside)
            self._send({"event": "probe_result", "state": res.state,
                        "healthy": res.healthy, "reason": res.reason,
                        "decode_p50_ms": res.decode_p50_ms,
                        "decode_p95_ms": res.decode_p95_ms,
                        "canary_age_s": res.canary_age_s,
                        "uptime_s": res.uptime_s})
        except Exception as exc:  # noqa: BLE001
            self._send({"event": "probe_result", "state": "UNKNOWN",
                        "err": f"{type(exc).__name__}: {str(exc)[:200]}"})


def _classify_dgx_err(exc: BaseException) -> str:
    """Map dgx_engine's typed errors to section-3.2 err strings."""
    name = type(exc).__name__
    return {
        "DgxTimeout": "timeout",
        "DgxConnError": "conn",
        "DgxAuthError": "auth",
        "DgxBusy": "http_429",
        "DgxWarming": "http_503",
        "DgxHttpError": "http",
    }.get(name, "conn")


# ---------------------------------------------------------------- entry

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="KESHEV killable worker (K9)")
    ap.add_argument("--gen", type=int, required=True,
                    help="spawn generation — stamped on every frame (scar 10)")
    ap.add_argument("--model", default=LADDER[0], help="configured ladder rung")
    ap.add_argument("--engine", default="ct2",
                    help='"ct2" or "fake:<dotted.module>" (rig/test seam)')
    ap.add_argument("--free-vram-mb", type=int, default=None,
                    help="rig override for the free-VRAM probe")
    ap.add_argument("--server-url", default=None)
    ap.add_argument("--token-file", default=None)
    args = ap.parse_args(argv)

    if args.free_vram_mb is not None:
        free_fn = lambda: args.free_vram_mb  # noqa: E731
    else:
        free_fn = read_free_vram_mb

    worker = WorkerMain(gen=args.gen, model=args.model, engine_spec=args.engine,
                        free_vram_mb_fn=free_fn, server_url=args.server_url,
                        token_file=args.token_file)
    return worker.run()


if __name__ == "__main__":
    sys.exit(main())
