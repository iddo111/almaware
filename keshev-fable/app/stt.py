"""stt.py — the decode client. eran1:8737, deadline, one retry, park-never-drop.

Laws inherited (INSIGHTS §4, §1.11; keshev-2 D-009):
- No local model, no worker process: decode is an HTTP POST with a hard
  deadline. What does not exist cannot die.
- request-id discipline (A's scar 53): a reply carrying a different id than
  asked is discarded LOUDLY — a late reply must never surface under another
  record's decode.
- One retry, then PARK: the record stays in the spool, journalled
  DECODE_PARKED. Speech is never dropped because a server blinked.
- lang_hint is a standing order and both standing orders are wrong (§4);
  default 'auto' and let the server's whitelist-argmax policy decide.
- The auth token lives in a file (state/stt-token), never in code or config.
"""
from __future__ import annotations

import json
import pathlib
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass


@dataclass
class DecodeResult:
    ok: bool
    text: str = ""
    lang: str | None = None
    avg_logprob: float | None = None
    ms: int = 0
    reason: str = ""            # '' when ok; else timeout|http|late_reply|server


class SttClient:
    def __init__(self, base_url: str, token_file: str | pathlib.Path,
                 timeout_s: float = 8.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.token_file = pathlib.Path(token_file)
        self.timeout_s = timeout_s

    def _token(self) -> str:
        # read per call: rotating the token never requires a mic restart
        return self.token_file.read_text(encoding="utf-8").strip()

    def health(self) -> bool:
        try:
            req = urllib.request.Request(
                f"{self.base_url}/health",
                headers={"Authorization": f"Bearer {self._token()}"})
            with urllib.request.urlopen(req, timeout=3) as r:
                return r.status == 200
        except (urllib.error.URLError, OSError, ValueError):
            return False

    def decode(self, rec_id: str, pcm_s16le_16k: bytes,
               lang_hint: str = "auto") -> DecodeResult:
        """One attempt. The router (caller) owns the one-retry-then-park law.

        Body is RAW PCM s16le/16kHz/mono — the eran1 protocol
        (mic-rebuild/common/protocol.py): Content-Type audio/pcm, request id
        matching ^[0-9a-f]{8}-[0-9]{6,}$, X-Audio-Duration-Ms required."""
        req_id = rec_id or str(uuid.uuid4())
        body = pcm_s16le_16k
        duration_ms = len(body) // 32          # 16000 Hz * 2 B / 1000 ms
        req = urllib.request.Request(
            f"{self.base_url}/v1/transcribe",
            data=body,
            headers={
                "Authorization": f"Bearer {self._token()}",
                "Content-Type": "audio/pcm;rate=16000;encoding=s16le;channels=1",
                "X-Request-Id": req_id,
                "X-Audio-Duration-Ms": str(duration_ms),
                "X-Lang-Hint": lang_hint,
            })
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
                payload = json.load(r)
        except TimeoutError:
            return DecodeResult(ok=False, reason="timeout")
        except urllib.error.URLError as e:
            # covers connection refused, DNS, and socket timeouts wrapped by
            # urllib — one family, one reason, the router parks either way
            reason = "timeout" if "timed out" in str(e).lower() else "http"
            return DecodeResult(ok=False, reason=reason)
        except (json.JSONDecodeError, OSError):
            return DecodeResult(ok=False, reason="server")

        got_id = str(payload.get("request_id") or "")
        if got_id and got_id != req_id:
            # scar 53: the late-reply ghost. Loud discard, never surface.
            return DecodeResult(ok=False, reason="late_reply")
        if not payload.get("ok", True) and "text" not in payload:
            return DecodeResult(ok=False, reason="server")
        return DecodeResult(
            ok=True,
            text=str(payload.get("text") or ""),
            lang=payload.get("lang"),
            avg_logprob=payload.get("avg_logprob"),
            ms=int(payload.get("decode_ms") or 0),
        )


class OwnerShadow:
    """Clause-4 shadow client (eran4:8739). NEVER blocks: a failure or a
    timeout is a shadow-miss, typed anyway - enforcement comes only after
    thresholds are measured from journalled cos values."""

    def __init__(self, base_url: str = "http://<lan-ip>:8739",
                 timeout_s: float = 2.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def cos(self, pcm_s16le_16k: bytes) -> float | None:
        try:
            req = urllib.request.Request(
                f"{self.base_url}/v1/verify", data=pcm_s16le_16k,
                headers={"Content-Type": "application/octet-stream"})
            with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
                payload = json.load(r)
            return float(payload["cos"]) if payload.get("ok") else None
        except Exception:  # noqa: BLE001 - shadow never bites
            return None
