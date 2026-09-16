#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", required=True)
    args = parser.parse_args()
    root = Path(args.model_dir).resolve(strict=True)

    indexes = []
    all_missing = []
    for index_path in sorted(root.rglob("*.safetensors.index.json")):
        data = json.loads(index_path.read_text(encoding="utf-8"))
        shards = sorted(set(data["weight_map"].values()))
        missing = [name for name in shards if not (index_path.parent / name).is_file()]
        indexes.append(
            {
                "index": str(index_path.relative_to(root)),
                "declared_shards": len(shards),
                "missing_shards": missing,
            }
        )
        all_missing.extend(f"{index_path.parent.relative_to(root)}/{name}" for name in missing)

    incomplete = sorted(str(path.relative_to(root)) for path in root.rglob("*.incomplete"))
    files = [path for path in root.rglob("*") if path.is_file() and ".cache" not in path.parts]
    receipt = {
        "model_dir": str(root),
        "model_index_present": (root / "model_index.json").is_file(),
        "noncache_file_count": len(files),
        "noncache_bytes": sum(path.stat().st_size for path in files),
        "weight_indexes": indexes,
        "missing_indexed_shards": sorted(all_missing),
        "incomplete_files": incomplete,
        "complete": bool((root / "model_index.json").is_file() and indexes and not all_missing and not incomplete),
    }
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
