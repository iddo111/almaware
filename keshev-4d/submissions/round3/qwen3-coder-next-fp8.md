```python
"""KESHEV-4D STT Client - STDLIB ONLY, Windows paths, journal-based logging."""
from __future__ import annotations

import json
import pathlib
import socket
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Optional

# Hard-coded paths per spec
APP_DIR = pathlib.Path(r"D:\CLAUDE\keshev-4d")
JOURNAL_PATH = APP_DIR / "journal.log"


@dataclass
class DecodeResult:
    ok: bool
    text: str = ""
    lang: Optional[str] = None
    ms: int = 0
    reason: str = ""
    request_id: Optional[str] = None

    def __post_init__(self):
        if not self.ok and not self.reason:
            self.reason = "unknown"


class Journal:
    """Minimal journal writer using STDLIB only."""
    _lock = threading.Lock()

    @staticmethod
    def event(event_type: str, **kwargs) -> None:
        """Write a journal event atomically."""
        with Journal._lock:
            try:
                timestamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
                entry = {
                    "timestamp": timestamp,
                    "event": event_type,
                    **kwargs
                }
                line = json.dumps(entry, ensure_ascii=False) + "\n"
                with open(JOURNAL_PATH, "a", encoding="utf-8") as f:
                    f.write(line)
            except Exception:
                pass  # Fail silently to avoid cascading failures


class SttClient:
    """STT client for KESHEV-4D - STDLIB only, Windows paths."""

    def __init__(self, base_url: str, token_path: pathlib.Path, timeout_s: int = 5):
        self.base_url = base_url.rstrip("/")
        self.token_path = token_path
        self.timeout_s = timeout_s

    def _read_token(self) -> str:
        """Read token per call per spec."""
        try:
            return self.token_path.read_text(encoding="utf-8").strip()
        except Exception:
            return ""

    def _make_request(self, request_id: str, audio_data: bytes) -> DecodeResult:
        """Internal request builder."""
        token = self._read_token()
        url = f"{self.base_url}/stt"

        headers = {
            "Content-Type": "application/octet-stream",
            "Authorization": f"Bearer {token}",
            "X-Request-Id": request_id,
        }

        try:
            req = urllib.request.Request(url, data=audio_data, headers=headers, method="POST")
            start = time.perf_counter()
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                body = resp.read().decode("utf-8")
                data = json.loads(body)

                # Validate request_id match
                resp_id = data.get("request_id")
                if resp_id != request_id:
                    Journal.event("stt_late_reply", request_id=request_id, response_id=resp_id)
                    return DecodeResult(
                        ok=False,
                        reason="late_reply",
                        ms=elapsed_ms
                    )

                # Success path
                return DecodeResult(
                    ok=data.get("ok", False),
                    text=data.get("text", ""),
                    lang=data.get("lang"),
                    ms=elapsed_ms,
                    request_id=resp_id
                )

        except urllib.error.HTTPError as e:
            Journal.event("stt_http_error", request_id=request_id, status=e.code)
            return DecodeResult(ok=False, reason="http", ms=0)
        except urllib.error.URLError as e:
            Journal.event("stt_url_error", request_id=request_id, reason=str(e.reason))
            return DecodeResult(ok=False, reason="http", ms=0)
        except socket.timeout:
            Journal.event("stt_timeout", request_id=request_id)
            return DecodeResult(ok=False, reason="timeout", ms=0)
        except Exception as e:
            Journal.event("stt_exception", request_id=request_id, error=str(e))
            return DecodeResult(ok=False, reason="http", ms=0)

    def decode(self, request_id: str, audio_data: bytes) -> DecodeResult:
        """Perform STT decode with journaling."""
        Journal.event("stt_decode_start", request_id=request_id)
        result = self._make_request(request_id, audio_data)
        Journal.event("stt_decode_end", request_id=request_id, ok=result.ok, reason=result.reason)
        return result

    def health(self) -> bool:
        """Health check endpoint."""
        url = f"{self.base_url}/health"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                return resp.status == 200
        except Exception:
            return False
```