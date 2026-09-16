# app/spool.py
import json
import os
import sys
import types
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Ensure a journal module exists with an event() function.
try:
    import journal  # type: ignore
except ImportError:
    journal = types.SimpleNamespace()
    def _event(info: Any) -> None:
        pass
    journal.event = _event
    sys.modules["journal"] = journal  # make it importable for patching in tests


class Spool:
    """
    Write‑ahead spool for audio recordings.

    Each record consists of a WAV file and a JSON side‑car.
    The spool keeps an in‑memory ordered set of pending record IDs.
    """

    def __init__(self, directory: str | Path, max_records: int = 500) -> None:
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.max_records = max_records
        self._pending: "OrderedDict[str, Tuple[Path, Path]]" = OrderedDict()
        self._seen_ids: set[str] = set()  # IDs whose side‑cars have already been swept

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #

    def admit(self, rec_id: str, wav_bytes: bytes, meta: Dict[str, Any]) -> Tuple[Path, Path]:
        """
        Write the WAV and JSON files for ``rec_id`` and register it as pending.
        If the pending count exceeds ``max_records`` the oldest pending record is evicted.
        Returns the paths (wav_path, json_path).
        """
        wav_path = self.dir / f"{rec_id}.wav"
        json_path = self.dir / f"{rec_id}.json"

        # Write files – WAV first, then JSON.
        wav_path.write_bytes(wav_bytes)
        json_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

        # Register in memory.
        self._pending[rec_id] = (wav_path, json_path)

        # Auto‑evict if we exceeded the limit.
        if len(self._pending) > self.max_records:
            self.evict_oldest()

        return wav_path, json_path

    def complete(self, rec_id: str) -> None:
        """Mark a pending record as completed; keep its files on disk."""
        self._pending.pop(rec_id, None)

    def evict_oldest(self) -> str | None:
        """
        Drop the oldest pending record (files stay on disk).
        Calls ``journal.event`` exactly once.
        Returns the evicted record ID or ``None`` if nothing to evict.
        """
        if not self._pending:
            return None
        rec_id, _ = self._pending.popitem(last=False)
        # Notify via journal.
        journal.event({"event": "evict", "rec_id": rec_id})
        return rec_id

    def pending(self) -> List[str]:
        """Return the list of pending record IDs in insertion order."""
        return list(self._pending.keys())

    def sweep(self) -> None:
        """
        Recover side‑car JSON files that exist on disk but are not in memory.
        Each side‑car is examined at most once (tracked via ``_seen_ids``).
        """
        for json_path in self.dir.glob("*.json"):
            rec_id = json_path.stem
            if rec_id in self._pending or rec_id in self._seen_ids:
                continue
            # Register the orphan as pending (files already exist).
            wav_path = self.dir / f"{rec_id}.wav"
            self._pending[rec_id] = (wav_path, json_path)
            self._seen_ids.add(rec_id)
