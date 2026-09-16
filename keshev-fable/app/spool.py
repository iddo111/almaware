"""spool.py — how speech survives every crash. Write-ahead, evict-keeps-files.

Laws inherited (INSIGHTS §1.3; ADDENDUM #1 twin scar; mic-rebuild 33df038):
- Disk BEFORE memory: the wav + sidecar land on disk before the record is
  admitted to any queue. A crash between the two loses a queue entry, never
  audio.
- Evict = drop the RECORD, keep the FILES. The spool bounds memory, not the
  archive; deleting Iddo's voice is a human decision, never backpressure.
- Every admit/evict/recover journals one line.
- sweep() is O(new): A stalled 13–19 s per segment because its sweep
  re-read the whole journal per sidecar. Here sweep remembers what it has
  seen and reads only new sidecars.
"""
from __future__ import annotations

import json
import pathlib
from collections import OrderedDict
from typing import Protocol


class _JournalLike(Protocol):
    def event(self, name: str, **fields: object) -> dict: ...


class Spool:
    def __init__(self, root: str | pathlib.Path, journal: _JournalLike,
                 max_records: int = 500) -> None:
        self.root = pathlib.Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.journal = journal
        self.max_records = max_records
        self._pending: OrderedDict[str, dict] = OrderedDict()
        self._seen_sidecars: set[str] = set()
        # ids found by sweep(): crash leftovers. INSIGHTS §1.3 — a recovered
        # record decodes to recovered.txt, NEVER into live focus.
        self.recovered_ids: set[str] = set()

    # ------------------------------------------------------------- admit --
    def admit(self, rec_id: str, wav_bytes: bytes, meta: dict) -> tuple[pathlib.Path, pathlib.Path]:
        """Write-ahead: files first, memory second, journal always."""
        wav = self.root / f"{rec_id}.wav"
        sidecar = self.root / f"{rec_id}.json"
        wav.write_bytes(wav_bytes)
        sidecar.write_text(json.dumps({"id": rec_id, **meta}, ensure_ascii=False),
                           encoding="utf-8")
        self._pending[rec_id] = dict(meta)
        self._seen_sidecars.add(sidecar.name)
        self.journal.event("SPOOL_ADMIT", id=rec_id, bytes=len(wav_bytes))
        while len(self._pending) > self.max_records:
            self.evict_oldest()
        return wav, sidecar

    def complete(self, rec_id: str) -> None:
        """Decoded and delivered — off the pending index. Files remain: the
        corpus pipeline owns the archive, the spool owns only the queue."""
        self._pending.pop(rec_id, None)

    def evict_oldest(self) -> str | None:
        """Bound memory. The record leaves the queue; the files stay put."""
        try:
            rec_id, _ = self._pending.popitem(last=False)
        except KeyError:
            return None
        self.journal.event("SPOOL_EVICT", id=rec_id, kept_files=True)
        return rec_id

    def pending(self) -> list[str]:
        return list(self._pending)

    # ------------------------------------------------------------- sweep --
    def sweep(self) -> list[str]:
        """Crash recovery: sidecars on disk that memory has never seen.
        O(new) — already-seen sidecar files are never opened again."""
        recovered: list[str] = []
        for sidecar in self.root.glob("*.json"):
            if sidecar.name in self._seen_sidecars:
                continue
            self._seen_sidecars.add(sidecar.name)
            try:
                meta = json.loads(sidecar.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            rec_id = str(meta.get("id") or sidecar.stem)
            if rec_id in self._pending:
                continue
            wav = self.root / f"{rec_id}.wav"
            if not wav.exists():
                continue
            self._pending[rec_id] = {k: v for k, v in meta.items() if k != "id"}
            recovered.append(rec_id)
            self.recovered_ids.add(rec_id)
            self.journal.event("SPOOL_RECOVERED", id=rec_id)
        return recovered
