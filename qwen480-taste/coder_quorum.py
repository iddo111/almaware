# לזכרה של עלמה ז״ל
"""ALMAWARE Coder <-> QUORUM bridge — no Qt in this file, on purpose.

Everything here is plain stdlib (urllib, json, threading) so it can be unit
tested without a display and safely driven from a QThread by the caller
(coder_desktop.py). This module never touches a Qt widget and never starts a
debate on import or at module load — only when a caller explicitly builds and
runs a QuorumRun.

QUORUM (D:/CLAUDE/quorum/server.py) is a SEPARATE, already-live process on
:8099 (its own ai_clients.py/registry.py/shakla.py — owned by muse-code per
the ONE HARNESS split). This module is a client of that HTTP door only: it
never imports quorum's modules directly (two projects share generic module
names like "config" and would collide in sys.modules), and it never edits
anything under D:/CLAUDE/quorum.

Contract (see coder_quorum interface notes):
  QUORUM_URL              — the one QUORUM door.
  seatable(timeout=5)      -> {model_id: bool}   -- GET /api/models, "up" only.
  map_brain_to_quorum(model, seatable) -> str|None
  QuorumRun(topic, model_ids, rounds=2, url=QUORUM_URL).run(on_event) -> dict
  QuorumRun.cancel()       -- thread-safe, closes the stream.

Events forwarded to on_event(name, data) are QUORUM's own SSE event names,
unchanged: plan | status | delta | error | done (see quorum/shakla.py — every
run always ends in a "done" frame, even a failed one; run() returns that
frame's data verbatim as its own return value).
"""
from __future__ import annotations

import json
import os
import select
import threading
import time
import urllib.request
from typing import Callable, Optional

QUORUM_URL = "http://127.0.0.1:8099"

# QUORUM's /api/models probes every seat live and was measured at ~4.8 s on
# 2026-09-15, so a 5 s probe turned "slow" into "no seats". ONE constant, used by
# both the desktop seat probe and the tailnet twin.
SEATABLE_TIMEOUT_S = 20.0

# QUORUM's own per-turn and synthesis timeouts live in quorum/config.py. They are
# read from that file (ast, never imported or executed -- its generic module name
# "config" would collide in sys.modules), so the debate budget can never again be
# shorter than QUORUM's own worst case. The fallback is the 2026-09-15 value.
_QUORUM_CONFIG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "quorum", "config.py")
_FALLBACK_LIMITS = {"PER_TURN_TIMEOUT": 200.0, "SYNTH_TIMEOUT": 220.0}
_BUDGET_MARGIN_S = 120.0


def quorum_limits(path: str = _QUORUM_CONFIG) -> dict:
    """{'PER_TURN_TIMEOUT': s, 'SYNTH_TIMEOUT': s} from quorum/config.py. Never raises."""
    out = dict(_FALLBACK_LIMITS)
    try:
        import ast  # noqa: PLC0415
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in tree.body:
            if (isinstance(node, ast.Assign) and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name) and node.targets[0].id in out
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, (int, float))
                    and not isinstance(node.value.value, bool) and node.value.value > 0):
                out[node.targets[0].id] = float(node.value.value)
    except Exception:
        pass
    return out


def debate_budget_s(n_models, rounds, limits: Optional[dict] = None) -> float:
    """Wall-clock budget for one debate, never shorter than QUORUM's own worst case:
    every seat may use a full turn in the opening positions and in each round (turns
    run one after another), then the synthesis, plus a margin."""
    lim = limits or quorum_limits()
    try:
        n = max(1, int(n_models))
    except (TypeError, ValueError):
        n = 2
    try:
        r = max(0, int(rounds))
    except (TypeError, ValueError):
        r = 2
    return n * (r + 1) * lim["PER_TURN_TIMEOUT"] + lim["SYNTH_TIMEOUT"] + _BUDGET_MARGIN_S

_MAX_RESPONSE = 8 * 1024 * 1024      # a debate transcript is text; this is generous
_DEFAULT_POLL = 0.5                  # seconds between cancellation checks while streaming


def _safe_call(fn: Optional[Callable], *args) -> None:
    """A caller's callback must never be able to kill this thread — the SSE
    stream keeps running (and cancel() keeps working) even if on_event raises."""
    if fn is None:
        return
    try:
        fn(*args)
    except Exception:
        pass


# ── /api/models — read-only seat check ───────────────────────────────────────

def seatable(timeout: float = 5.0, url: str = QUORUM_URL) -> dict:
    """GET <url>/api/models -> {model_id: is_up}.

    Never raises. QUORUM not running, not reachable, or answering garbage all
    come back as {} — an empty seatable, never an exception — so a caller can
    always do `seatable().get(model)` safely.

    "up" means registry.py's own live HTTP probe reported health.state=="up".
    A CLI id merely *installed* (claude/grok/gemini — "presence is discovery;
    first turn is the gate", per registry.py) is NOT counted as seated here,
    and neither is "down"/"auth"/"unknown" — this function answers "can QUORUM
    reach it right now", not "does QUORUM know about it"."""
    try:
        req = urllib.request.Request(url.rstrip("/") + "/api/models", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read(_MAX_RESPONSE) or b"{}")
    except Exception:
        return {}
    out: dict = {}
    models = data.get("models") if isinstance(data, dict) else None
    for m in (models or []):
        if not isinstance(m, dict) or not m.get("id"):
            continue
        health = m.get("health") if isinstance(m.get("health"), dict) else {}
        out[str(m["id"])] = (health.get("state") == "up")
    return out


# ── brain id -> QUORUM seat id ───────────────────────────────────────────────
#
# coder_brains.py names a brain by the model id ALMAWARE Coder itself uses on
# its own door (e.g. "qwen-coder-dgx4:latest", "nvidia/nemotron-3-super-120b-a12b").
# QUORUM names its seats independently (registry.py BUILTIN_MODELS + ai_clients
# CLI ids + state/registry.json overrides) and the two lists are NOT the same
# vocabulary. Only alias a brain to a seat when they are verifiably the same
# model behind the alias — a family resemblance (e.g. Coder's
# "z-ai/glm-5.3-flash" vs QUORUM's "glm-5.2", a different parameter count and
# door) is deliberately left unaliased: guessing would put a transcript line
# under the wrong name.
#
# Sourced 2026-09-15 from D:\CLAUDE\CLAUDE.md's QUORUM provider table
# (alma:nemotron / alma:gptoss120b -> the Alma Harness routes) and a live read
# of quorum/registry.py's BUILTIN_MODELS + quorum/state/registry.json.
_ALIASES: dict = {
    "gpt-oss-120b": ("gpt-oss-120b", "alma:gptoss120b"),
    "nvidia/nemotron-3-super-120b-a12b": ("alma:nemotron",),
    # quorum/state/registry.json defines seat nvidia-kimi-k3 with
    # "model": "moonshotai/kimi-k3" -- the same model, same NVIDIA cloud.
    "moonshotai/kimi-k3": ("nvidia-kimi-k3",),
}

# QUORUM's seats on Iddo's own PC ollama: "ollama-local" / "ollama-local:<tag>"
# (registry.py, base http://127.0.0.1:11434, one seat per local model) and
# "ollama:<tag>" (ai_clients.py, from the PC's own `ollama list`).
PC_OLLAMA_SEAT_PREFIX = "ollama-local"
_PC_SEAT_PREFIXES = (PC_OLLAMA_SEAT_PREFIX + ":", "ollama:")


def is_pc_local_seat(seat_id) -> bool:
    """True for a QUORUM seat that runs inference on Iddo's PC (its ollama)."""
    s = str(seat_id or "")
    return s == PC_OLLAMA_SEAT_PREFIX or s.startswith(_PC_SEAT_PREFIXES)


def map_brain_to_quorum(model: str, seatable: dict) -> Optional[str]:
    """A coder_brains.py brain's `model` id (never its `id`) -> a currently-seated
    QUORUM model id, or None if there is no confident, currently-live match.
    `seatable` is the dict this module's seatable() returns (or a test double).
    A PC ollama seat matches only by its exact tag ("ollama-local:<model>") --
    never "the first ollama-local seat", which can be a different model."""
    if not model or not seatable:
        return None
    if seatable.get(model):
        return model
    for alias in _ALIASES.get(model, ()):
        if seatable.get(alias):
            return alias
    for prefix in _PC_SEAT_PREFIXES:
        pc_seat = prefix + model
        if seatable.get(pc_seat):
            return pc_seat
    return None


# ── SSE framing ───────────────────────────────────────────────────────────────

def _parse_sse_frame(frame: bytes):
    """One '\\n\\n'-delimited SSE frame -> (event_name, data_dict).
    Mirrors quorum/server.py's own _sse_frame() writer and the reference JS
    reader baked into its PAGE template: default event 'message', last
    'data:' line(s) concatenated and JSON-decoded. Returns (None, {}) for a
    blank/keep-alive frame."""
    text = frame.decode("utf-8", errors="replace")
    if not text.strip():
        return None, {}
    event = "message"
    data_parts = []
    for line in text.split("\n"):
        if line.startswith("event:"):
            event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            data_parts.append(line[len("data:"):].strip())
    raw = "".join(data_parts)
    try:
        data = json.loads(raw) if raw else {}
    except Exception:
        data = {"_raw": raw}
    if not isinstance(data, dict):
        data = {"_raw": data}
    return event, data


# ── one debate run ────────────────────────────────────────────────────────────

class QuorumRun:
    """One QUORUM debate (POST /debate, SSE response). run() blocks the
    calling thread until the stream ends or is cancelled — a PyQt caller MUST
    run this on a QThread, never the UI thread (see coder_desktop.py's own
    rule for door calls).

    Every parsed frame is forwarded to on_event(event_name, data_dict) in
    server order, verbatim. shakla.run_shakla() never raises and always ends
    the stream with a "done" frame — even a disabled/failed run — so run()'s
    return value is simply that frame's data; a transport-level failure (QUORUM
    unreachable, connection dropped before any "done") is reported the same
    shape: {"error": "..."}.
    """

    def __init__(self, topic: str, model_ids, rounds: int = 2,
                 url: str = QUORUM_URL, timeout: Optional[float] = None,
                 poll_interval: float = _DEFAULT_POLL):
        self.topic = topic
        self.model_ids = list(model_ids or [])
        self.rounds = rounds
        self.url = url
        # Overall wall-clock budget for the whole debate. None (the default, used by
        # the desktop and the twin) sizes it from THIS request with debate_budget_s():
        # a fixed 900 s cut real debates off before QUORUM wrote the conclusion.
        self.timeout = (float(timeout) if timeout is not None
                        else debate_budget_s(len(self.model_ids), rounds))
        self.poll_interval = poll_interval
        self._lock = threading.Lock()
        self._cancel_event = threading.Event()
        self._resp = None               # the open response, while streaming

    def cancel(self) -> None:
        """Thread-safe. Safe to call before run() starts, during it, or after
        it finished — a no-op once the stream is already closed."""
        self._cancel_event.set()
        with self._lock:
            resp = self._resp
        if resp is not None:
            try:
                resp.close()
            except Exception:
                pass

    def run(self, on_event: Callable[[str, dict], None]) -> dict:
        payload = json.dumps({
            "topic": self.topic,
            "models": self.model_ids,
            "rounds": self.rounds,
        }, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.url.rstrip("/") + "/debate", data=payload,
            headers={"Content-Type": "application/json"}, method="POST")

        if self._cancel_event.is_set():
            return {"error": "cancelled"}

        # Connecting + the round trip to the FIRST byte (opening the SSE
        # response, headers included) gets a generous timeout — a slow
        # Tailscale hop to a real fleet door must not be mistaken for
        # "unreachable" just because poll_interval is short.
        connect_timeout = max(self.poll_interval, min(self.timeout, 30.0))
        try:
            resp = urllib.request.urlopen(req, timeout=connect_timeout)
        except Exception as e:  # noqa: BLE001 — failure-is-a-value, like everything QUORUM
            err = {"error": str(e)[:300]}
            _safe_call(on_event, "error", err)
            return err

        with self._lock:
            self._resp = resp
        done_payload: dict = {}
        buf = b""
        deadline = time.monotonic() + self.timeout
        try:
            while True:
                if self._cancel_event.is_set():
                    if not done_payload:
                        done_payload = {"error": "cancelled"}
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    if not done_payload:
                        done_payload = {"error": "timeout"}
                    break
                # Wait for data with select() rather than a short socket-level
                # read timeout: once a blocking socket read on a makefile()'d
                # stream times out, CPython's SocketIO latches "cannot read
                # from timed out object" and EVERY later read on that same
                # stream fails immediately (see socket.SocketIO.readinto) —
                # so a real model's ordinary multi-second thinking gap would
                # permanently kill the debate. select() lets us poll for
                # cancel()/the deadline without ever touching a socket that
                # has nothing to give yet.
                try:
                    ready, _, _ = select.select([resp], [], [], min(self.poll_interval, remaining))
                except (OSError, ValueError, AttributeError):
                    # fd already closed — either cancel() raced us here, or
                    # the connection dropped; both end the run the same way.
                    # (AttributeError: cancel()'s resp.close() set resp.fp to
                    # None between the is_set() check and select -> fileno().)
                    if not done_payload:
                        done_payload = {"error": "cancelled" if self._cancel_event.is_set() else "closed"}
                    break
                if not ready:
                    continue  # a quiet stretch — loop back to the checks above
                try:
                    # resp.read(n) is the wrong call here: HTTPResponse.read(n)
                    # asks its BufferedReader to fill up to n bytes, which
                    # loops issuing more raw reads until it actually HAS n
                    # bytes or the connection closes — on a trickle of small
                    # SSE frames that means it silently blocks until EOF and
                    # hands back the whole debate in one lump at the end.
                    # .fp.read1(n) does at most one underlying read, i.e. real
                    # streaming: whatever is available right now, up to n.
                    # Safe here because quorum/server.py answers HTTP/1.0 with
                    # a close-delimited body (self.close_connection = True,
                    # no Transfer-Encoding) — never chunked, so there is no
                    # chunk-framing for read1() to bypass and corrupt.
                    chunk = resp.fp.read1(4096)
                except Exception as e:  # noqa: BLE001 — connection dropped mid-stream
                    # cancel() on another thread can close resp between our
                    # select() and this read (resp.fp -> None mid-race) —
                    # that is a cancellation, not a backend failure, and must
                    # be reported as one.
                    if self._cancel_event.is_set():
                        if not done_payload:
                            done_payload = {"error": "cancelled"}
                    elif not done_payload:
                        _safe_call(on_event, "error", {"error": str(e)[:300]})
                        done_payload = {"error": str(e)[:300]}
                    break
                if not chunk:
                    break  # server closed the stream cleanly
                buf += chunk
                while b"\n\n" in buf:
                    frame, buf = buf.split(b"\n\n", 1)
                    name, data = _parse_sse_frame(frame)
                    if name is None:
                        continue
                    _safe_call(on_event, name, data)
                    if name == "done":
                        done_payload = data
        finally:
            with self._lock:
                self._resp = None
            try:
                resp.close()
            except Exception:
                pass
        if not done_payload:
            done_payload = {"error": "cancelled" if self._cancel_event.is_set() else "no_done_frame"}
        return done_payload
