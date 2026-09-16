"""Hash Safetensors tensors directly, without Torch or model imports."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path
from typing import BinaryIO


def hash_range(stream: BinaryIO, offset: int, length: int) -> str:
    stream.seek(offset)
    remaining = length
    digest = hashlib.sha256()
    while remaining:
        chunk = stream.read(min(8 * 1024 * 1024, remaining))
        if not chunk:
            raise ValueError("unexpected end of Safetensors file")
        digest.update(chunk)
        remaining -= len(chunk)
    return digest.hexdigest()


def expert_axis0_hashes(
    stream: BinaryIO,
    data_start: int,
    name: str,
    info: dict,
) -> list[str] | None:
    shape = info["shape"]
    start, end = info["data_offsets"]
    if ".experts." not in name or len(shape) < 2 or shape[0] < 2:
        return None
    total_bytes = end - start
    if total_bytes % shape[0]:
        raise ValueError(f"expert tensor does not divide on axis 0: {name}")
    bytes_per_expert = total_bytes // shape[0]
    return [
        hash_range(
            stream,
            data_start + start + (expert_index * bytes_per_expert),
            bytes_per_expert,
        )
        for expert_index in range(shape[0])
    ]


def inspect_shard(path: Path) -> dict[str, dict[str, object]]:
    with path.open("rb") as stream:
        raw_length = stream.read(8)
        if len(raw_length) != 8:
            raise ValueError(f"invalid Safetensors header: {path}")
        header_length = struct.unpack("<Q", raw_length)[0]
        if header_length > 256 * 1024 * 1024:
            raise ValueError(f"implausible Safetensors header: {path}")
        header = json.loads(stream.read(header_length))
        data_start = 8 + header_length
        result = {}
        for name, info in header.items():
            if name == "__metadata__":
                continue
            start, end = info["data_offsets"]
            tensor = {
                "dtype": info["dtype"],
                "shape": info["shape"],
                "bytes": end - start,
                "sha256": hash_range(stream, data_start + start, end - start),
                "shard": path.name,
            }
            expert_hashes = expert_axis0_hashes(stream, data_start, name, info)
            if expert_hashes is not None:
                tensor["expert_axis0_sha256"] = expert_hashes
            result[name] = tensor
        return result


def snapshot(checkpoint: Path) -> dict[str, object]:
    shards = sorted(checkpoint.glob("*.safetensors"))
    if not shards:
        raise ValueError(f"no .safetensors shards in {checkpoint}")
    tensors: dict[str, dict[str, object]] = {}
    for shard in shards:
        for name, info in inspect_shard(shard).items():
            if name in tensors:
                raise ValueError(f"duplicate tensor name: {name}")
            tensors[name] = info
    return {
        "schema_version": 1,
        "checkpoint": str(checkpoint),
        "shards": [path.name for path in shards],
        "tensor_count": len(tensors),
        "tensors": tensors,
    }


def compare(before: dict, after: dict, require_all_changed: bool) -> dict:
    before_names = set(before["tensors"])
    after_names = set(after["tensors"])
    common = before_names & after_names
    changed = sorted(
        name
        for name in common
        if before["tensors"][name]["sha256"] != after["tensors"][name]["sha256"]
    )
    unchanged = sorted(common - set(changed))
    missing = sorted(before_names - after_names)
    added = sorted(after_names - before_names)
    metadata_mismatch = sorted(
        name
        for name in common
        if (
            before["tensors"][name]["dtype"] != after["tensors"][name]["dtype"]
            or before["tensors"][name]["shape"] != after["tensors"][name]["shape"]
        )
    )
    unchanged_expert_slices = []
    compared_expert_slices = 0
    for name in sorted(common):
        before_slices = before["tensors"][name].get("expert_axis0_sha256")
        after_slices = after["tensors"][name].get("expert_axis0_sha256")
        if before_slices is None and after_slices is None:
            continue
        if (
            before_slices is None
            or after_slices is None
            or len(before_slices) != len(after_slices)
        ):
            metadata_mismatch.append(name)
            continue
        compared_expert_slices += len(before_slices)
        unchanged_expert_slices.extend(
            f"{name}[{index}]"
            for index, (old_hash, new_hash) in enumerate(
                zip(before_slices, after_slices, strict=True)
            )
            if old_hash == new_hash
        )
    metadata_mismatch = sorted(set(metadata_mismatch))
    passed = not missing and not added and not metadata_mismatch and bool(common)
    if require_all_changed:
        passed = passed and not unchanged and not unchanged_expert_slices
    return {
        "before_tensor_count": len(before_names),
        "after_tensor_count": len(after_names),
        "changed_count": len(changed),
        "unchanged_count": len(unchanged),
        "missing_count": len(missing),
        "added_count": len(added),
        "metadata_mismatch_count": len(metadata_mismatch),
        "compared_expert_slices": compared_expert_slices,
        "unchanged_expert_slice_count": len(unchanged_expert_slices),
        "unchanged_sample": unchanged[:20],
        "missing_sample": missing[:20],
        "added_sample": added[:20],
        "metadata_mismatch_sample": metadata_mismatch[:20],
        "unchanged_expert_slice_sample": unchanged_expert_slices[:20],
        "require_all_changed": require_all_changed,
        "pass": passed,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    snapshot_parser = subparsers.add_parser("snapshot")
    snapshot_parser.add_argument("checkpoint", type=Path)
    snapshot_parser.add_argument("output", type=Path)
    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("before", type=Path)
    compare_parser.add_argument("after", type=Path)
    compare_parser.add_argument("--require-all-changed", action="store_true")
    args = parser.parse_args()

    if args.command == "snapshot":
        payload = snapshot(args.checkpoint)
        args.output.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps({"tensor_count": payload["tensor_count"], "pass": True}))
        return

    before = json.loads(args.before.read_text(encoding="utf-8"))
    after = json.loads(args.after.read_text(encoding="utf-8"))
    payload = compare(before, after, args.require_all_changed)
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not payload["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
