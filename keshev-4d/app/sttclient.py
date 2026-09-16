# app/sttclient.py
"""STT client for KESHEV-4D.

Implements a minimal HTTP client using only the Python standard library.
All failures are reported via ``journal.event`` exactly once per call.
"""

from __future__ import annotations

import json
import pathlib
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

# ----------------------------------------------------------------------
# Journal stub – real implementation may be provided elsewhere.
# ----------------------------------------------------------------------
try:
    import journal  # type: ignore
except Exception:  # pragma: no cover
    class _JournalStub:
        @staticmethod
        def event(event_name: str, payload: dict | None = None) -> None:
            """Placeholder that silently discards events."""
            pass

    journal = _JournalStub()  # type: ignore


# ----------------------------------------------------------------------
# Public data structures
# ----------------------------------------------------------------------
@dataclass
class DecodeResult:
    """Result of a decode request.

    Attributes:
        ok: Whether the request succeeded.
        reason: Failure reason when ``ok`` is ``False``.
        text: Recognised text (empty when ``ok`` is ``False``).
        lang: Language code if supplied by the server.
        ms: Decoding time in milliseconds.
    """
    ok: bool
    reason: str = ""
    text: str = ""
    lang: Optional[str] = None
    ms: int = 0


# ----------------------------------------------------------------------
# STT client implementation
# ----------------------------------------------------------------------
class SttClient:
    """Thin wrapper around the remote STT service."""

    def __init__(self, base_url: str, token_path: pathlib.Path | str, timeout_s: float = 5.0):
        self.base_url = base_url.rstrip("/")
        self.token_path = pathlib.Path(token_path)
        self.timeout = timeout_s

    # ------------------------------------------------------------------
    # Helper: read token on every call (required by the tests)
    # ------------------------------------------------------------------
    def _read_token(self) -> str:
        try:
            return self.token_path.read_text(encoding="utf-8").strip()
        except Exception as exc:
            # Token read failure is a hard error – report and re‑raise.
            journal.event("token_read_failure", {"path": str(self.token_path), "error": str(exc)})
            raise

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def decode(self, request_id: str, audio: bytes) -> DecodeResult:
        """Send audio for transcription and return a :class:`DecodeResult`.

        The method never raises; all error conditions are encoded in the
        returned ``DecodeResult`` and reported via ``journal.event`` exactly
        once.
        """
        try:
            token = self._read_token()
            url = f"{self.base_url}/decode"
            req = urllib.request.Request(url, data=audio, method="POST")
            req.add_header("Content-Type", "application/octet-stream")
            req.add_header("X-Request-Id", request_id)
            req.add_header("Authorization", f"Bearer {token}")

            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status != 200:
                    raise urllib.error.HTTPError(url, resp.status, resp.reason, resp.headers, None)
                raw = resp.read()
                payload = json.loads(raw.decode())
        except Exception as exc:
            # Distinguish timeout from generic HTTP/network errors.
            if isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, TimeoutError):
                reason = "timeout"
            elif isinstance(exc, urllib.error.HTTPError) and exc.code == 504:
                reason = "timeout"
            else:
                reason = "http"
            journal.event("decode_failure", {"request_id": request_id, "reason": reason, "error": str(exc)})
            return DecodeResult(ok=False, reason=reason)

        # ------------------------------------------------------------------
        # Validate request_id echo – late replies are rejected.
        # ------------------------------------------------------------------
        resp_req_id = payload.get("request_id")
        if resp_req_id is not None and resp_req_id != request_id:
            journal.event("decode_late_reply", {"request_id": request_id, "response_id": resp_req_id})
            return DecodeResult(ok=False, reason="late_reply")

        # ------------------------------------------------------------------
        # Normal success / failure handling.
        # ------------------------------------------------------------------
        ok = bool(payload.get("ok"))
        if not ok:
            reason = payload.get("reason", "unknown")
            journal.event("decode_failure", {"request_id": request_id, "reason": reason})
            return DecodeResult(ok=False, reason=reason)

        text = payload.get("text", "")
        lang = payload.get("lang")
        ms = int(payload.get("decode_ms", 0))
        return DecodeResult(ok=True, text=text, lang=lang, ms=ms)

    def health(self) -> bool:
        """Check service health – returns ``True`` on HTTP 200."""
        try:
            url = f"{self.base_url}/health"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status == 200
        except Exception:
            return False
