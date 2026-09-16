import json
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict

VOCAB = frozenset({
    "SESSION_BEGIN",
    "DEVICE_OPEN",
    "SEG",
    "DECODE",
    "TYPED",
    "DROP",
    "GATED",
    "HEARTBEAT",
    "STATE",
    "WORKER_DIED",
    "WORKER_RESPAWN",
    "ALARM"
})

class JournalVocabError(ValueError):
    pass

class Journal:
    def __init__(self, path: str):
        self._path = path
        self._lock = threading.Lock()

    def event(self, name: str, **fields: Any) -> None:
        if name not in VOCAB:
            raise JournalVocabError(f"Unknown event name: {name}")
        with self._lock:
            ts = datetime.now(timezone.utc).isoformat()
            entry = {"ts": ts, "evt": name, **fields}
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")

    def rotate(self, max_bytes: int) -> None:
        if not os.path.exists(self._path):
            return
        with self._lock:
            if os.path.getsize(self._path) >= max_bytes:
                backup_path = self._path + ".1"
                if os.path.exists(backup_path):
                    os.remove(backup_path)
                os.rename(self._path, backup_path)
