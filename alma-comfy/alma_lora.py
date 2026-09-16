#!/usr/bin/env python3
"""List or prepare only human-approved, pinned project LoRAs.

The former popularity-search downloader has intentionally been removed.  A
LoRA is eligible only when its exact Hugging Face repository, 40-hex revision,
single .safetensors path, byte count, SHA-256, license, human approval, and
compatible locked base model are present in a per-project allowlist.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DEFAULT_LOCK = ROOT / "studio_assets.lock.json"
PREPARER = ROOT / "tools" / "studio_asset_preparer.py"


class AllowlistError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AllowlistError(f"cannot read project allowlist {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AllowlistError("project allowlist root must be an object")
    return value


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="List/audit/prepare exact LoRAs from an approved project allowlist."
    )
    parser.add_argument("--allowlist", required=True, type=Path)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--list", action="store_true")
    action.add_argument("--audit", action="store_true")
    action.add_argument("--prepare", action="store_true")
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--offline", action="store_true")
    return parser.parse_args(argv)


def list_entries(project: dict[str, Any]) -> int:
    print(f"project={project.get('project_id', '<invalid>')}")
    print(f"approved_by={project.get('approved_by', '<missing>')}")
    enabled = [item for item in project.get("loras", []) if item.get("enabled")]
    if not enabled:
        print("approved_loras=0")
        return 0
    for item in enabled:
        bases = ",".join(item.get("compatible_base_assets", []))
        print(
            f"{item.get('id')}|{item.get('repo_id')}@{item.get('revision')}|"
            f"{item.get('source_file')}|sha256={item.get('sha256')}|bases={bases}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project = load_json(args.allowlist)
    if args.list:
        return list_entries(project)
    receipt = args.receipt or (
        ROOT / "provenance" / "studio-asset-preparation" / f"{project.get('project_id', 'invalid')}-loras.json"
    )
    command = [
        sys.executable,
        str(PREPARER),
        "--lock",
        str(args.lock),
        "--node",
        "dgx3",
        "--mode",
        "prepare" if args.prepare else "audit",
        "--project-loras",
        str(args.allowlist),
        "--receipt",
        str(receipt),
        "--skip-sources",
        "--skip-environments",
        "--skip-tools",
    ]
    if args.offline:
        command.append("--offline")
    completed = subprocess.run(command, check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
