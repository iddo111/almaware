import json
import mmap
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def dump_mapping(name: str, size: int, expected_magic: bytes, output: str) -> None:
    mapping = mmap.mmap(-1, size, name, access=mmap.ACCESS_READ)
    try:
        mapping.seek(0)
        magic = mapping.read(8)
        if magic != expected_magic:
            raise ValueError(f"invalid magic {magic!r}; is RAMCHAT running?")
        payload_size = struct.unpack("<Q", mapping.read(8))[0]
        if payload_size <= 0 or payload_size > size - 16:
            raise ValueError(f"invalid payload size {payload_size}")
        raw = mapping.read(payload_size).decode("utf-8")
        payload = json.loads(raw)
        temporary = ROOT / (output + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(ROOT / output)
        print(f"{name}: {payload_size} bytes -> {ROOT / output}")
    finally:
        mapping.close()


for args in (
    ("RAMCHAT_COUNCIL_V1", 16 * 1024 * 1024, b"RAMCHAT1", "current_council.json"),
    ("RAMCHAT_QUEUE_V1", 8 * 1024 * 1024, b"RAMQUEU1", "current_queue.json"),
):
    try:
        dump_mapping(*args)
    except Exception as exc:
        print(f"{args[0]} ERROR: {exc}")
