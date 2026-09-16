"""KESHEV DGX engine — K10 (PHASE2-DESIGN.md sections 3.1 + 3.2, scars 5/53).

The worker's HTTP client for the eran1 STT server. This module will live
INSIDE keshev_worker.py's process (K9) — ALL network egress belongs to the
one killable subprocess (section 7); the elevated client never touches the
LAN. stdlib http.client only: the socket is OURS to close.

The two laws this module embodies:

  * scar 53 structurally: the 6s deadline is a SOCKET timeout, and abandon
    = conn.close(). A late reply after failover has no socket to ride back
    on — it cannot reach the typer, it can only die as the server's
    CLIENT_GONE counter.
  * scar 5: probe() treats `canary_age_s > 900` as UNHEALTHY even on
    HTTP 200 — health is real output, never process-alive. probe() never
    raises; the router consumes a ProbeResult either way.
"""
from __future__ import annotations

import http.client
import json
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit

from common import protocol


class DgxError(Exception):
    """Base for everything the DGX path can throw at the router."""


class DgxConnError(DgxError):
    """TCP-level failure: refused, unreachable, reset mid-flight."""


class DgxTimeout(DgxError):
    """Deadline hit — the socket was CLOSED (abandoned) before raising."""


class DgxAuthError(DgxError):
    """401 — wrong/missing token. Not retryable; surface loudly."""


class DgxBusy(DgxError):
    """429 — server at inflight cap."""

    def __init__(self, msg: str, retry_after: float = 1.0):
        super().__init__(msg)
        self.retry_after = retry_after


class DgxWarming(DgxError):
    """503 — LOADING or DRAINING."""

    def __init__(self, msg: str, state: str = "LOADING"):
        super().__init__(msg)
        self.state = state


class DgxHttpError(DgxError):
    """Any other non-200 (400/404/413/500...)."""

    def __init__(self, msg: str, status: int):
        super().__init__(msg)
        self.status = status


@dataclass(frozen=True)
class DgxResult:
    request_id: str
    text: str
    lang: str
    lang_prob: float
    avg_logprob: float
    no_speech_prob: float
    compression_ratio: float
    decode_ms: int
    rtf: float
    model: str
    server_version: str
    ts: str


@dataclass(frozen=True)
class ProbeResult:
    healthy: bool
    state: str            # READY | LOADING | DRAINING | UNKNOWN
    reason: str           # ok | conn | timeout | auth | warming | canary_stale | http_<code>
    http_status: int      # 0 when no HTTP round-trip happened
    decode_p50_ms: int = 0
    decode_p95_ms: int = 0
    canary_age_s: float = -1.0
    uptime_s: int = 0
    version: str = ""


class DgxEngine:
    """One server, one token, one deadline. Stateless between calls — every
    request rides a fresh connection so close() is a TRUE abandon."""

    def __init__(self, base_url: str, token: str,
                 timeout: float = protocol.DGX_DEADLINE_S):
        parts = urlsplit(base_url)
        if parts.scheme != "http" or not parts.hostname:
            raise ValueError(f"base_url must be http://host[:port]/, got {base_url!r}")
        self._host = parts.hostname
        self._port = parts.port or protocol.PORT
        self._token = token
        self._timeout = timeout

    # ---------------------------------------------------------------- transcribe
    def transcribe(self, pcm: bytes, *, request_id: str, duration_ms: int,
                   lang_hint: str = "auto") -> DgxResult:
        if not protocol.valid_request_id(request_id):
            raise ValueError(f"malformed request id {request_id!r}")
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": protocol.CONTENT_TYPE_PCM,
            protocol.HDR_REQUEST_ID: request_id,
            protocol.HDR_AUDIO_DURATION_MS: str(int(duration_ms)),
            protocol.HDR_LANG_HINT: lang_hint,
        }
        conn = http.client.HTTPConnection(self._host, self._port,
                                          timeout=self._timeout)
        try:
            try:
                conn.connect()                     # connect-phase failure != abandon
            except (socket.timeout, TimeoutError, ConnectionError, OSError) as e:
                raise DgxConnError(f"{request_id}: connect: {type(e).__name__}: {e}") from e
            try:
                conn.request("POST", protocol.PATH_TRANSCRIBE, body=pcm,
                             headers=headers)
                resp = conn.getresponse()
                status = resp.status
                body = resp.read()
                retry_after = resp.getheader("Retry-After", "1")
            except (socket.timeout, TimeoutError) as e:
                # THE abandon (scar 53): deadline -> close the socket. The
                # finally below closes it before this raise reaches anyone;
                # a late reply now has nowhere to land.
                raise DgxTimeout(
                    f"{request_id}: no reply within {self._timeout}s — abandoned") from e
            except (ConnectionError, OSError) as e:
                raise DgxConnError(f"{request_id}: {type(e).__name__}: {e}") from e
        finally:
            conn.close()

        if status == 200:
            res = json.loads(body.decode("utf-8"))
            if res.get("request_id") != request_id:
                raise DgxError(
                    f"response id {res.get('request_id')!r} != sent {request_id!r}")
            return DgxResult(
                request_id=res["request_id"], text=res["text"], lang=res["lang"],
                lang_prob=res["lang_prob"], avg_logprob=res["avg_logprob"],
                no_speech_prob=res["no_speech_prob"],
                compression_ratio=res["compression_ratio"],
                decode_ms=res["decode_ms"], rtf=res["rtf"], model=res["model"],
                server_version=res["server_version"], ts=res["ts"])
        if status == 401:
            raise DgxAuthError(f"{request_id}: 401 unauthorized")
        if status == 429:
            try:
                ra = float(retry_after)
            except (TypeError, ValueError):
                ra = 1.0
            raise DgxBusy(f"{request_id}: 429 busy", retry_after=ra)
        if status == 503:
            state = "LOADING"
            try:
                state = json.loads(body.decode("utf-8")).get("state", state)
            except (ValueError, UnicodeDecodeError):
                state = "UNKNOWN"
            raise DgxWarming(f"{request_id}: 503 {state}", state=state)
        raise DgxHttpError(f"{request_id}: HTTP {status}", status=status)

    # ---------------------------------------------------------------- probe
    def probe(self) -> ProbeResult:
        """GET /health, scar-5 rules applied. NEVER raises."""
        conn = http.client.HTTPConnection(self._host, self._port,
                                          timeout=self._timeout)
        try:
            try:
                conn.connect()
            except (socket.timeout, TimeoutError, ConnectionError, OSError):
                return ProbeResult(healthy=False, state="UNKNOWN",
                                   reason="conn", http_status=0)
            try:
                conn.request("GET", protocol.PATH_HEALTH,
                             headers={"Authorization": f"Bearer {self._token}"})
                resp = conn.getresponse()
                status = resp.status
                body = resp.read()
            except (socket.timeout, TimeoutError):
                return ProbeResult(healthy=False, state="UNKNOWN",
                                   reason="timeout", http_status=0)
            except (ConnectionError, OSError):
                return ProbeResult(healthy=False, state="UNKNOWN",
                                   reason="conn", http_status=0)
        finally:
            conn.close()

        if status == 401:
            return ProbeResult(healthy=False, state="UNKNOWN", reason="auth",
                               http_status=401)
        try:
            h = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return ProbeResult(healthy=False, state="UNKNOWN",
                               reason=f"http_{status}", http_status=status)
        state = h.get("state", "UNKNOWN")
        canary_age = float(h.get("canary_age_s", -1))
        base = dict(state=state, http_status=status,
                    decode_p50_ms=int(h.get("decode_p50_ms", 0)),
                    decode_p95_ms=int(h.get("decode_p95_ms", 0)),
                    canary_age_s=canary_age, uptime_s=int(h.get("uptime_s", 0)),
                    version=str(h.get("version", "")))
        if status != 200 or state != "READY":
            return ProbeResult(healthy=False, reason="warming", **base)
        if canary_age > protocol.CANARY_STALE_S:
            # scar 5: HTTP 200 with a stale canary is a LIE — refuse it
            return ProbeResult(healthy=False, reason="canary_stale", **base)
        return ProbeResult(healthy=True, reason="ok", **base)
