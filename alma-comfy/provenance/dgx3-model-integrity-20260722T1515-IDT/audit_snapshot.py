#!/usr/bin/env python3
"""Read-only integrity audit for Hugging Face local-dir snapshots."""

from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import struct
import sys
import time


REQUIRED = {
    "LTX-2.3": [
        ".gitattributes",
        "LICENSE",
        "README.md",
        "ltx-2.3-22b-dev.safetensors",
        "ltx-2.3-22b-distilled-1.1.safetensors",
        "ltx-2.3-22b-distilled.safetensors",
    ],
    "Wan2.2-I2V-A14B-Diffusers": [
        "model_index.json",
        "scheduler/scheduler_config.json",
        "text_encoder/config.json",
        "text_encoder/model.safetensors.index.json",
        "tokenizer/special_tokens_map.json",
        "tokenizer/spiece.model",
        "tokenizer/tokenizer.json",
        "tokenizer/tokenizer_config.json",
        "transformer/config.json",
        "transformer/diffusion_pytorch_model.safetensors.index.json",
        "transformer_2/config.json",
        "transformer_2/diffusion_pytorch_model.safetensors.index.json",
        "vae/config.json",
        "vae/diffusion_pytorch_model.safetensors",
    ],
}


def safetensors_header_error(path: Path) -> str | None:
    size = path.stat().st_size
    if size < 10:
        return "file_too_small"
    with path.open("rb") as handle:
        raw = handle.read(8)
        if len(raw) != 8:
            return "missing_header_length"
        header_len = struct.unpack("<Q", raw)[0]
        if header_len <= 1 or header_len > size - 8:
            return f"invalid_header_length:{header_len}"
        if header_len > 512 * 1024 * 1024:
            return f"header_over_safety_cap:{header_len}"
        header = handle.read(header_len)
    try:
        parsed = json.loads(header)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return f"invalid_header_json:{type(exc).__name__}"
    if not isinstance(parsed, dict):
        return "header_not_object"
    return None


def audit(root: Path) -> dict:
    tree_files = sorted((root / ".cache/huggingface/trees").glob("*.json"))
    if len(tree_files) != 1:
        return {
            "root": str(root),
            "fatal": f"expected_one_tree_json_found_{len(tree_files)}",
        }

    tree_path = tree_files[0]
    tree = json.loads(tree_path.read_text(encoding="utf-8"))
    expected = tree["files"]
    expected_paths = set(expected)
    actual_paths = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and ".cache" not in path.relative_to(root).parts
    }

    size_mismatches = []
    for relative in sorted(expected_paths & actual_paths):
        actual_size = (root / relative).stat().st_size
        expected_size = int(expected[relative]["size"])
        if actual_size != expected_size:
            size_mismatches.append(
                {"path": relative, "expected": expected_size, "actual": actual_size}
            )

    metadata_missing = []
    metadata_bad_commit = []
    metadata_bad_etag = []
    metadata_count = 0
    commit = tree_path.stem
    for relative, item in sorted(expected.items()):
        metadata_path = root / ".cache/huggingface/download" / f"{relative}.metadata"
        if not metadata_path.is_file():
            metadata_missing.append(relative)
            continue
        metadata_count += 1
        lines = metadata_path.read_text(encoding="utf-8").splitlines()
        if not lines or lines[0] != commit:
            metadata_bad_commit.append(relative)
        expected_etag = item.get("lfs_sha256", item.get("blob_id"))
        if len(lines) < 2 or lines[1] != expected_etag:
            metadata_bad_etag.append(relative)

    locks = sorted((root / ".cache/huggingface/download").rglob("*.lock"))
    lock_summary = [
        {
            "path": path.relative_to(root).as_posix(),
            "bytes": path.stat().st_size,
            "mtime_ns": path.stat().st_mtime_ns,
        }
        for path in locks
    ]
    partial_suffixes = (
        ".incomplete",
        ".partial",
        ".part",
        ".tmp",
        ".aria2",
        ".crdownload",
    )
    partial_like = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name.lower().endswith(partial_suffixes)
    )

    json_errors = []
    for path in sorted(root.rglob("*.json")):
        if ".cache" in path.relative_to(root).parts:
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            json_errors.append(
                {"path": path.relative_to(root).as_posix(), "error": type(exc).__name__}
            )

    safetensors_errors = []
    safetensors_count = 0
    for path in sorted(root.rglob("*.safetensors")):
        if ".cache" in path.relative_to(root).parts:
            continue
        safetensors_count += 1
        error = safetensors_header_error(path)
        if error:
            safetensors_errors.append(
                {"path": path.relative_to(root).as_posix(), "error": error}
            )

    shard_index_results = []
    for index_path in sorted(root.rglob("*.safetensors.index.json")):
        if ".cache" in index_path.relative_to(root).parts:
            continue
        data = json.loads(index_path.read_text(encoding="utf-8"))
        shards = sorted(set(data.get("weight_map", {}).values()))
        missing_shards = [
            shard for shard in shards if not (index_path.parent / shard).is_file()
        ]
        shard_index_results.append(
            {
                "path": index_path.relative_to(root).as_posix(),
                "weight_keys": len(data.get("weight_map", {})),
                "referenced_shards": len(shards),
                "missing_shards": missing_shards,
            }
        )

    visible_bytes = sum((root / relative).stat().st_size for relative in actual_paths)
    required_missing = [
        relative for relative in REQUIRED[root.name] if not (root / relative).is_file()
    ]
    return {
        "root": str(root),
        "snapshot_commit": commit,
        "tree_format_version": tree.get("format_version"),
        "tree_files": len(expected_paths),
        "tree_bytes": sum(int(item["size"]) for item in expected.values()),
        "visible_files": len(actual_paths),
        "visible_bytes": visible_bytes,
        "missing_files": sorted(expected_paths - actual_paths),
        "extra_files": sorted(actual_paths - expected_paths),
        "size_mismatches": size_mismatches,
        "required_missing": required_missing,
        "metadata_files": metadata_count,
        "metadata_missing": metadata_missing,
        "metadata_bad_commit": metadata_bad_commit,
        "metadata_bad_etag": metadata_bad_etag,
        "lock_files": lock_summary,
        "lock_count": len(lock_summary),
        "nonzero_lock_files": [item["path"] for item in lock_summary if item["bytes"]],
        "partial_like_files": partial_like,
        "json_errors": json_errors,
        "safetensors_files": safetensors_count,
        "safetensors_header_errors": safetensors_errors,
        "shard_indexes": shard_index_results,
    }


def hash_snapshot(root: Path) -> dict:
    tree_path = next((root / ".cache/huggingface/trees").glob("*.json"))
    expected = json.loads(tree_path.read_text(encoding="utf-8"))["files"]
    started = time.monotonic()
    checked = []
    mismatches = []
    bytes_read = 0
    lfs_files = 0
    git_blob_files = 0
    manifest_digest = hashlib.sha256()
    for relative, item in sorted(expected.items()):
        path = root / relative
        lfs_sha256 = item.get("lfs_sha256")
        if lfs_sha256:
            digest = hashlib.sha256()
            expected_digest = lfs_sha256
            digest_type = "lfs_sha256"
            lfs_files += 1
        else:
            digest = hashlib.sha1()
            digest.update(f"blob {path.stat().st_size}\0".encode("ascii"))
            expected_digest = item["blob_id"]
            digest_type = "git_blob_sha1"
            git_blob_files += 1
        with path.open("rb") as handle:
            while chunk := handle.read(16 * 1024 * 1024):
                digest.update(chunk)
                bytes_read += len(chunk)
        actual_digest = digest.hexdigest()
        manifest_digest.update(relative.encode("utf-8"))
        manifest_digest.update(b"\0")
        manifest_digest.update(actual_digest.encode("ascii"))
        manifest_digest.update(b"\n")
        result = {
            "path": relative,
            "bytes": path.stat().st_size,
            "digest_type": digest_type,
            "expected": expected_digest,
            "actual": actual_digest,
            "match": actual_digest == expected_digest,
        }
        checked.append(result)
        if not result["match"]:
            mismatches.append(result)
    return {
        "root": str(root),
        "snapshot_commit": tree_path.stem,
        "files_hashed": len(checked),
        "matched_files": len(checked) - len(mismatches),
        "lfs_sha256_files": lfs_files,
        "git_blob_sha1_files": git_blob_files,
        "bytes_hashed": bytes_read,
        "seconds": round(time.monotonic() - started, 3),
        "verification_manifest_sha256": manifest_digest.hexdigest(),
        "mismatches": mismatches,
    }


if __name__ == "__main__":
    hash_mode = "--hash" in sys.argv[1:]
    roots = [arg for arg in sys.argv[1:] if arg != "--hash"]
    for arg in roots:
        result = hash_snapshot(Path(arg)) if hash_mode else audit(Path(arg))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
