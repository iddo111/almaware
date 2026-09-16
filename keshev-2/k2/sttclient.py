"""KESHEV 2 STT client — eran1:8737, the measured language law built in.

Server contract inherited VERBATIM from A (the server is shared; K2 is a
second client, not a second server): POST /v1/transcribe, bearer token,
X-Request-Id `<session8hex>-<seq:06d>`, X-Lang-Hint, raw s16le 16k mono
PCM body, 6s socket deadline where abandon = close the socket (scar 53:
a late reply has no socket to ride back on).

THE LANGUAGE LAW (ruling D-004 — every clause measured on Iddo's voice):

  * `auto` IS UNREPRESENTABLE. hint=auto transliterated Hebrew
    ("סוכה"->"suka", measured 2026-08-16). This client cannot send it:
    the constructor and transcribe() refuse anything outside ("he","en").
    Not server validation — CLIENT-side unrepresentability, the same move
    that killed `language=None` ("the single line that let noise come
    back as Icelandic").
  * DEFAULT hint "he" — his dictation is Hebrew-first; a wrong argmax in
    the wrong script is VISIBLY wrong and he fixes it; forcing the wrong
    language makes Whisper translate — invisibly wrong.
  * SCRIPT RETRY, not dual-decode: if the decode comes back majority
    opposite-script (>50%), ONE re-decode with the other hint, journalled
    SCRIPT_RETRY(hint_from, hint_to). Same request-id — only one result is
    ever forwarded, so typer dedup is unaffected. Dual-decode stays OFF
    (2026-08-16 12:21: enabling it silenced ALL decodes for 1h50m).
  * vad is handled SERVER-side. This client never re-adds an inner VAD
    (guard species #3: it fired on the only thing that could reach it —
    real speech).

stdlib http.client only: the socket is OURS to close.
"""
from __future__ import annotations

import http.client
import json
import re
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlsplit

# ------------------------------------------------------------- contract

PATH_TRANSCRIBE = "/v1/transcribe"
PATH_HEALTH = "/health"
CONTENT_TYPE_PCM = "audio/pcm;rate=16000;encoding=s16le;channels=1"
HDR_REQUEST_ID = "X-Request-Id"
HDR_AUDIO_DURATION_MS = "X-Audio-Duration-Ms"
HDR_LANG_HINT = "X-Lang-Hint"

LANG_HINTS = ("he", "en")        # "auto" does not exist here (D-004)

DGX_DEADLINE_S = 6.0
CANARY_STALE_S = 900.0           # scar 5: HTTP 200 with a stale canary lies

_SESSION_RE = re.compile(r"^[0-9a-f]{8}$")
REQUEST_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9]{6,}$")

# script classification for the retry law
_HEBREW_RE = re.compile(r"[֐-׿]")
_LATIN_RE = re.compile(r"[A-Za-z]")


def make_request_id(session: str, seq: int) -> str:
    """`<session8hex>-<seq:06d>` — THE dedup key. Widens past 999999
    rather than wrapping (a wrapped id would collide in the dedup LRU and
    silently eat a real utterance)."""
    if not isinstance(session, str) or not _SESSION_RE.match(session):
        raise ValueError(f"session must be 8 lowercase hex chars, got {session!r}")
    if not isinstance(seq, int) or seq < 0:
        raise ValueError(f"seq must be a non-negative int, got {seq!r}")
    return f"{session}-{seq:06d}"


def valid_request_id(rid: object) -> bool:
    return isinstance(rid, str) and REQUEST_ID_RE.match(rid) is not None


def script_ratio(text: str) -> tuple[int, int]:
    """(hebrew_letters, latin_letters) — the raw counts, so tests can pin
    the boundary exactly."""
    return len(_HEBREW_RE.findall(text)), len(_LATIN_RE.findall(text))


def wrong_script_hint(text: str, hint: str) -> Optional[str]:
    """The retry trigger: if >50% of the LETTERS in a decode are in the
    script of the OTHER language, return the other hint; else None.
    Empty/letterless text never triggers (nothing to judge)."""
    if hint not in LANG_HINTS:
        raise ValueError(f"hint must be one of {LANG_HINTS}, got {hint!r}")
    he, la = script_ratio(text)
    total = he + la
    if total == 0:
        return None
    if hint == "he" and la / total > 0.5:
        return "en"
    if hint == "en" and he / total > 0.5:
        return "he"
    return None


# ------------------------------------------------------------- errors


class SttError(Exception):
    """Base for everything the DGX path can throw at the router."""


class SttConnError(SttError):
    """TCP-level failure: refused, unreachable, reset mid-flight."""


class SttTimeout(SttError):
    """Deadline hit — the socket was CLOSED (abandoned) before raising."""


class SttAuthError(SttError):
    """401 — wrong/missing token. Not retryable; surface loudly."""


class SttHttpError(SttError):
    def __init__(self, msg: str, status: int):
        super().__init__(msg)
        self.status = status


# ------------------------------------------------------------- results


@dataclass(frozen=True)
class SttResult:
    request_id: str
    text: str
    lang: str
    lang_prob: float
    avg_logprob: float
    no_speech_prob: float
    decode_ms: int
    model: str
    script_retried: bool = False
    hint_used: str = "he"


@dataclass(frozen=True)
class ProbeResult:
    healthy: bool
    state: str            # READY | LOADING | DRAINING | UNKNOWN
    reason: str           # ok | conn | timeout | auth | warming | canary_stale | http_<code>
    http_status: int
    decode_p50_ms: int = 0
    decode_p95_ms: int = 0
    canary_age_s: float = -1.0


def load_token(path: str | Path) -> str:
    """Token from file (config server_token_path). Missing token is a loud
    startup failure, not a 401 surprise mid-dictation."""
    p = Path(path)
    try:
        token = p.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise SttAuthError(f"token file unreadable: {p} ({exc})") from exc
    if not token:
        raise SttAuthError(f"token file empty: {p}")
    return token


class SttClient:
    """One server, one token, one deadline. Stateless between calls —
    every request rides a fresh connection so close() is a TRUE abandon."""

    def __init__(self, base_url: str, token: str,
                 timeout: float = DGX_DEADLINE_S,
                 default_hint: str = "he",
                 emit: Optional[Callable[..., None]] = None) -> None:
        parts = urlsplit(base_url)
        if parts.scheme != "http" or not parts.hostname or not parts.port:
            raise ValueError(f"base_url must be http://host:port, got {base_url!r}")
        if default_hint not in LANG_HINTS:
            raise ValueError(
                f"default_hint must be one of {LANG_HINTS}, got "
                f"{default_hint!r} — 'auto' is unrepresentable (D-004)")
        self._host = parts.hostname
        self._port = parts.port
        self._token = token
        self._timeout = timeout
        self._default_hint = default_hint
        self._emit = emit

    # --------------------------------------------------------- transcribe

    def transcribe(self, pcm: bytes, *, request_id: str, duration_ms: int,
                   lang_hint: Optional[str] = None) -> SttResult:
        """One utterance -> text, with the script-retry law applied.
        At most TWO decodes ever leave this method for one utterance, and
        exactly ONE result returns to the caller."""
        hint = self._default_hint if lang_hint is None else lang_hint
        if hint not in LANG_HINTS:
            raise ValueError(
                f"lang_hint must be one of {LANG_HINTS}, got {hint!r} — "
                f"'auto' is unrepresentable in this client (D-004)")
        first = self._post_once(pcm, request_id=request_id,
                                duration_ms=duration_ms, hint=hint)
        other = wrong_script_hint(first.text, hint)
        if other is None:
            return first
        second = self._post_once(pcm, request_id=request_id,
                                 duration_ms=duration_ms, hint=other)
        # D-009 (adversarial find, qwen): a mixed-script utterance with a
        # loanword majority ("סוכה event") trips the letter-count trigger
        # on a CORRECT decode. So the retry must EARN its place: the result
        # with the higher model confidence wins (ties go to the retry —
        # the trigger is evidence). Both logprobs are journalled, so the
        # rule is auditable against real dictation.
        keep_retry = second.avg_logprob >= first.avg_logprob
        if self._emit is not None:
            self._emit("SCRIPT_RETRY", hint_from=hint, hint_to=other,
                       rid=request_id,
                       kept="retry" if keep_retry else "first",
                       lp_first=round(first.avg_logprob, 3),
                       lp_retry=round(second.avg_logprob, 3))
        winner = second if keep_retry else first
        return SttResult(
            request_id=winner.request_id, text=winner.text,
            lang=winner.lang, lang_prob=winner.lang_prob,
            avg_logprob=winner.avg_logprob,
            no_speech_prob=winner.no_speech_prob,
            decode_ms=first.decode_ms + second.decode_ms,
            model=winner.model, script_retried=True,
            hint_used=winner.hint_used)

    def _post_once(self, pcm: bytes, *, request_id: str, duration_ms: int,
                   hint: str) -> SttResult:
        if not valid_request_id(request_id):
            raise ValueError(f"malformed request id {request_id!r}")
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": CONTENT_TYPE_PCM,
            HDR_REQUEST_ID: request_id,
            HDR_AUDIO_DURATION_MS: str(int(duration_ms)),
            HDR_LANG_HINT: hint,
        }
        conn = http.client.HTTPConnection(self._host, self._port,
                                          timeout=self._timeout)
        try:
            try:
                conn.connect()
            except (socket.timeout, TimeoutError, ConnectionError, OSError) as e:
                raise SttConnError(
                    f"{request_id}: connect: {type(e).__name__}: {e}") from e
            try:
                conn.request("POST", PATH_TRANSCRIBE, body=pcm,
                             headers=headers)
                resp = conn.getresponse()
                status = resp.status
                body = resp.read()
            except (socket.timeout, TimeoutError) as e:
                # THE abandon (scar 53): deadline -> the finally closes the
                # socket before this raise reaches anyone; a late reply has
                # nowhere to land.
                raise SttTimeout(
                    f"{request_id}: no reply within {self._timeout}s — "
                    f"abandoned") from e
            except (ConnectionError, OSError) as e:
                raise SttConnError(
                    f"{request_id}: {type(e).__name__}: {e}") from e
        finally:
            conn.close()

        if status == 200:
            res = json.loads(body.decode("utf-8"))
            if res.get("request_id") != request_id:
                raise SttError(f"response id {res.get('request_id')!r} != "
                               f"sent {request_id!r}")
            return SttResult(
                request_id=res["request_id"], text=res["text"],
                lang=res["lang"], lang_prob=res["lang_prob"],
                avg_logprob=res["avg_logprob"],
                no_speech_prob=res["no_speech_prob"],
                decode_ms=res["decode_ms"], model=res["model"],
                hint_used=hint)
        if status == 401:
            raise SttAuthError(f"{request_id}: 401 unauthorized")
        raise SttHttpError(f"{request_id}: HTTP {status}", status=status)

    # --------------------------------------------------------------- probe

    def probe(self) -> ProbeResult:
        """GET /health, scar-5 rules: 200 with a stale canary is a LIE and
        comes back unhealthy. NEVER raises — the caller consumes a
        ProbeResult either way."""
        conn = http.client.HTTPConnection(self._host, self._port,
                                          timeout=self._timeout)
        try:
            try:
                conn.connect()
                conn.request("GET", PATH_HEALTH,
                             headers={"Authorization": f"Bearer {self._token}"})
                resp = conn.getresponse()
                status = resp.status
                body = resp.read()
            except (socket.timeout, TimeoutError):
                return ProbeResult(False, "UNKNOWN", "timeout", 0)
            except (ConnectionError, OSError):
                return ProbeResult(False, "UNKNOWN", "conn", 0)
        finally:
            conn.close()

        if status == 401:
            return ProbeResult(False, "UNKNOWN", "auth", 401)
        try:
            h = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return ProbeResult(False, "UNKNOWN", f"http_{status}", status)
        state = h.get("state", "UNKNOWN")
        canary_age = float(h.get("canary_age_s", -1))
        base = dict(state=state, http_status=status,
                    decode_p50_ms=int(h.get("decode_p50_ms", 0)),
                    decode_p95_ms=int(h.get("decode_p95_ms", 0)),
                    canary_age_s=canary_age)
        if status != 200 or state != "READY":
            return ProbeResult(healthy=False, reason="warming", **base)
        if canary_age > CANARY_STALE_S:
            return ProbeResult(healthy=False, reason="canary_stale", **base)
        return ProbeResult(healthy=True, reason="ok", **base)
