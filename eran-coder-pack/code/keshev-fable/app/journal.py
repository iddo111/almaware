"""journal.py — the append-only event journal. One honest line per fact.

Laws inherited (INSIGHTS §1.3, §3 event-vocabulary lesson):
- CLOSED vocabulary: an unknown event name raises at the WRITER. A typo'd
  event silently vanishing from every dashboard is how A's TelemetryFieldError
  scar happened — three gates, three questions, three names.
- Append-only JSONL, file opened per write, never held: the journal must
  survive the process dying mid-line (the reader skips a torn last line).
- Never lose speech, never lie about it: every drop path in the app calls
  .event() exactly once. The journal is the court record, not a debug log.
- rotate() renames, NEVER deletes — his voice's paper trail is not something
  code gets to erase.
"""
from __future__ import annotations

import datetime
import json
import pathlib
import threading

# The closed vocabulary. Adding an event = adding it HERE, in review, with a
# test — not inventing a string at a call site at 3am.
VOCAB: frozenset[str] = frozenset({
    # lifecycle
    "SESSION_BEGIN", "SESSION_END", "STATE", "HEARTBEAT", "ALARM",
    # capture
    "DEVICE_OPEN", "DEVICE_LOST", "DEVICE_REOPEN", "IDLE_NO_MIC", "SEG",
    # decode
    "DECODE", "DECODE_PARKED", "LANG_FLIP",
    # gates — three gates, three questions, three names (the 09:46 lesson)
    # OWNER_BLOCK (clause-4 owner gate, enforce) was journalled by router.py
    # from commit fe52732 without being HERE: the first cos<0.60 on
    # 2026-08-19 22:19:55 raised JournalVocabError instead of blocking and
    # killed the beat thread — 4 hours without a HEARTBEAT. The lint (G5) had
    # said so; nobody ran it. tests/test_lint_gates.py now runs it under pytest.
    "GATED", "GUARD_DROP", "PRESENCE_REJ", "ARM_REJ", "FOCUS_REJ", "OWNER_BLOCK",
    # output
    "TYPED", "ENTER", "TYPE_VERIFY_FAIL",
    # spool
    "SPOOL_ADMIT", "SPOOL_EVICT", "SPOOL_RECOVERED",
    # config
    "CONFIG_HALT", "CONFIG_STALE",
})

_TZ = datetime.timezone(datetime.timedelta(hours=3))  # Israel daylight time


class JournalVocabError(ValueError):
    """An event name outside VOCAB — fail the writer, not the dashboard."""


class Journal:
    """Append-only JSONL journal. Thread-safe within one process."""

    def __init__(self, path: str | pathlib.Path) -> None:
        self.path = pathlib.Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def event(self, name: str, **fields: object) -> dict:
        """Append one fact. Returns the record written (tests read it back)."""
        if name not in VOCAB:
            raise JournalVocabError(
                f"unknown event {name!r} — add it to journal.VOCAB in review, "
                "not at the call site")
        rec: dict[str, object] = {
            "ts": datetime.datetime.now(_TZ).isoformat(timespec="milliseconds"),
            "evt": name,
        }
        rec.update(fields)
        line = json.dumps(rec, ensure_ascii=False)
        with self._lock:
            # open-per-write: no held handle to go stale, nothing buffered to
            # lose when the process dies. A journal write IS the transaction.
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        return rec

    def rotate(self, max_bytes: int) -> bool:
        """Rename to .1 when over budget. Never deletes; .1 is overwritten
        only by the NEXT rotation (two generations always exist on disk)."""
        with self._lock:
            try:
                if self.path.stat().st_size <= max_bytes:
                    return False
            except FileNotFoundError:
                return False
            old = self.path.with_suffix(self.path.suffix + ".1")
            old.unlink(missing_ok=True)
            self.path.rename(old)
            return True

    def tail(self, n: int = 200) -> list[dict]:
        """Last n parseable records. A torn final line (process died mid-
        write) is skipped silently — the journal must never crash its reader."""
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return []
        out: list[dict] = []
        for ln in lines[-n:]:
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
        return out
