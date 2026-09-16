"""KESHEV wire spec — K10 (PHASE2-DESIGN.md section 3, THE one source of truth).

Shared client<->server<->worker. Everything here is design LAW: the numbers
come verbatim from PHASE2-DESIGN.md and tests/test_protocol.py pins them —
changing a constant requires changing the design first.

Three things live here:
  * request-id format `<session8hex>-<seq:06d>` — THE dedup key (scar 53)
  * the HTTP contract constants for eran1:8737 (section 3.1)
  * the worker IPC framing `4-byte LE length | UTF-8 JSON header | raw PCM
    payload`, every frame carrying "gen" (section 3.2, scar 10 promoted to
    the process boundary)

stdlib only. No torch, no numpy, no network.
"""
from __future__ import annotations

import json
import re
import struct
from typing import BinaryIO

# ---------------------------------------------------------------- HTTP contract (section 3.1)

PORT = 8737                      # claimed in RAMCHAT before first bind (section 6)
PATH_TRANSCRIBE = "/v1/transcribe"
PATH_HEALTH = "/health"
PATH_METRICS = "/metrics"
PATH_DRAIN = "/admin/drain"
PATH_UNDRAIN = "/admin/undrain"

CONTENT_TYPE_PCM = "audio/pcm;rate=16000;encoding=s16le;channels=1"
SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2
MAX_BODY_BYTES = 30 * SAMPLE_RATE * BYTES_PER_SAMPLE      # 960,000 = 30s -> 413 above

HDR_REQUEST_ID = "X-Request-Id"                           # 400 if missing (scar 53)
HDR_AUDIO_DURATION_MS = "X-Audio-Duration-Ms"
HDR_LANG_HINT = "X-Lang-Hint"
LANG_HINTS = ("auto", "he", "en")

# section 3.2 deadlines: DGX 6s (abandon = close socket), local 10s hard.
# Budget check: worst-case failover 6s + ~2s local ~= 8s < criterion 2's 10s.
DGX_DEADLINE_S = 6.0
LOCAL_DEADLINE_S = 10.0
SERVER_DECODE_WALL_S = 15.0                               # server-side -> 500 decode_timeout

INFLIGHT_CAP = 2                                          # inflight > 2 -> 429
CANARY_INTERVAL_S = 300                                   # self-decode cadence (EXPENSIVE: real GPU decode)
CANARY_STALE_S = 900                                      # client treats older as UNHEALTHY (scar 5)
PET_INTERVAL_S = 30                                       # systemd watchdog pet cadence (CHEAP: no decode)
# PET_INTERVAL_S must stay <= WatchdogSec/2 in server/keshev-stt.service (90 -> 45).
# It is NOT the same number as CANARY_INTERVAL_S and must never be merged with it:
# on 2026-08-12 the server petted every 300 s against a 90 s watchdog and systemd
# SIGABRT'd it five times in a row, then gave up on the unit. Both numbers were
# individually sensible; they lived in different files and nobody read them together.
# The split is what keeps scar 5 affordable: the cheap pet is frequent, the real
# decode stays rare (eran1 is Qwen's machine), and the pet is gated on canary
# freshness so a wedged model still stops the petting. See tests/test_watchdog_cadence.py.

# ---------------------------------------------------------------- request-id (scar 53)

_SESSION_RE = re.compile(r"^[0-9a-f]{8}$")
REQUEST_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9]{6,}$")


def make_request_id(session: str, seq: int) -> str:
    """`<session8hex>-<seq:06d>`. The seq field is at LEAST 6 digits — it
    widens past 999999 rather than wrapping (a wrapped id would collide and
    the dedup LRU would silently eat a real utterance)."""
    if not isinstance(session, str) or not _SESSION_RE.match(session):
        raise ValueError(f"session must be 8 lowercase hex chars, got {session!r}")
    if not isinstance(seq, int) or seq < 0:
        raise ValueError(f"seq must be a non-negative int, got {seq!r}")
    return f"{session}-{seq:06d}"


def valid_request_id(rid: object) -> bool:
    return isinstance(rid, str) and REQUEST_ID_RE.match(rid) is not None


# ---------------------------------------------------------------- worker IPC framing (section 3.2)

class FrameError(ValueError):
    """A frame that violates the wire spec — corrupt, truncated, or genless."""


# A JSON header larger than this is corruption, not a header (payload PCM is
# carried OUTSIDE the header; 30s of PCM is under 1MB and headers are tiny).
MAX_HEADER_BYTES = 1 * 1024 * 1024
_LEN = struct.Struct("<I")


def pack_frame(header: dict, payload: bytes = b"") -> bytes:
    """`4-byte LE length | UTF-8 JSON header | raw payload`.

    Every frame MUST carry "gen" (scar 10: the client discards frames whose
    gen != current spawn generation — zombie revival is unrepresentable, so
    a genless frame is refused at pack time, not merely discouraged).
    `n_bytes` is auto-filled from the payload; a header that lies about its
    payload is refused.
    """
    if "gen" not in header:
        raise FrameError("every IPC frame must carry 'gen' (scar 10)")
    if "n_bytes" in header and header["n_bytes"] != len(payload):
        raise FrameError(
            f"n_bytes={header['n_bytes']} lies about payload len {len(payload)}")
    hdr = dict(header)
    hdr["n_bytes"] = len(payload)
    raw = json.dumps(hdr, ensure_ascii=False).encode("utf-8")
    if len(raw) > MAX_HEADER_BYTES:
        raise FrameError(f"header too large: {len(raw)} bytes")
    return _LEN.pack(len(raw)) + raw + payload


def read_frame(stream: BinaryIO) -> tuple[dict, bytes] | None:
    """Read one frame. Returns (header, payload); None on clean EOF.
    Raises FrameError on truncation or garbage."""
    head = stream.read(4)
    if head == b"" or head is None:
        return None                       # clean EOF between frames
    if len(head) < 4:
        raise FrameError(f"truncated length prefix ({len(head)} bytes)")
    (n,) = _LEN.unpack(head)
    if n == 0 or n > MAX_HEADER_BYTES:
        raise FrameError(f"implausible header length {n}")
    raw = stream.read(n)
    if len(raw) < n:
        raise FrameError(f"truncated header ({len(raw)}/{n} bytes)")
    try:
        header = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise FrameError(f"header is not UTF-8 JSON: {e}") from e
    if not isinstance(header, dict):
        raise FrameError(f"header must be a JSON object, got {type(header).__name__}")
    n_bytes = header.get("n_bytes", 0)
    if not isinstance(n_bytes, int) or n_bytes < 0:
        raise FrameError(f"bad n_bytes {n_bytes!r}")
    payload = stream.read(n_bytes) if n_bytes else b""
    if len(payload) < n_bytes:
        raise FrameError(f"truncated payload ({len(payload)}/{n_bytes} bytes)")
    return header, payload
