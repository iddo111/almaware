#!/usr/bin/env python3
"""Fail-closed ALMA Studio asset preparer.

This program may download pinned files, clone pinned source revisions, verify
existing isolated Python environments, and create explicit ComfyUI symlinks.
It deliberately has no code path for starting ComfyUI, Studio, a worker,
Docker, systemd, or any model inference process.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Iterable


HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
PROJECT_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
HF_ORIGIN = "https://huggingface.co"
USER_AGENT = "alma-studio-asset-preparer/1.0"
CHUNK_BYTES = 8 * 1024 * 1024


class GateError(RuntimeError):
    """A pinned invariant failed; no permissive fallback is allowed."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError(f"cannot read valid JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise GateError(f"JSON root must be an object: {path}")
    return value


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_blob_sha1(path: Path) -> str:
    digest = hashlib.sha1()
    digest.update(f"blob {path.stat().st_size}\0".encode("ascii"))
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_under_posix(path: str, root: str) -> bool:
    clean_path = posixpath.normpath(path)
    clean_root = posixpath.normpath(root)
    return clean_path == clean_root or clean_path.startswith(clean_root + "/")


def validate_lock(lock: dict[str, Any]) -> None:
    if lock.get("schema_version") != 1:
        raise GateError("unsupported studio asset lock schema")
    policy = lock.get("policy")
    if not isinstance(policy, dict) or policy.get("activation") != "forbidden":
        raise GateError("lock must explicitly forbid activation")
    if policy.get("remote_code_execution") is not False:
        raise GateError("remote code execution must be false")
    if policy.get("immutable_revisions_required") is not True:
        raise GateError("immutable revisions must be required")
    allowed_nodes = policy.get("allowed_nodes")
    if allowed_nodes != ["dgx3", "dgx4"]:
        raise GateError("only DGX3 and DGX4 are valid Studio workers")
    nodes = lock.get("nodes")
    if not isinstance(nodes, dict) or set(nodes) != set(allowed_nodes):
        raise GateError("lock nodes must exactly match the worker allowlist")

    asset_ids: set[str] = set()
    destinations: set[str] = set()
    for asset in lock.get("assets", []):
        if not isinstance(asset, dict):
            raise GateError("asset entries must be objects")
        asset_id = asset.get("id")
        if not isinstance(asset_id, str) or not asset_id or asset_id in asset_ids:
            raise GateError(f"invalid or duplicate asset id: {asset_id!r}")
        asset_ids.add(asset_id)
        if asset.get("node") not in allowed_nodes:
            raise GateError(f"asset {asset_id} targets a non-Studio node")
        if asset.get("kind") not in {"hf_snapshot", "hf_file"}:
            raise GateError(f"asset {asset_id} has unsupported kind")
        revision = asset.get("revision", "")
        if not HEX40.fullmatch(revision):
            raise GateError(f"asset {asset_id} does not pin a 40-hex revision")
        repo_id = asset.get("repo_id", "")
        if not isinstance(repo_id, str) or repo_id.count("/") != 1:
            raise GateError(f"asset {asset_id} has invalid repo_id")
        destination = asset.get("destination", "")
        node = nodes[asset["node"]]
        if not isinstance(destination, str) or not destination.startswith("/"):
            raise GateError(f"asset {asset_id} destination must be absolute")
        if not is_under_posix(destination, node["model_root"]):
            raise GateError(f"asset {asset_id} escapes the node model root")
        if destination in destinations:
            raise GateError(f"duplicate asset destination: {destination}")
        destinations.add(destination)
        if not isinstance(asset.get("expected_files"), int) or asset["expected_files"] < 1:
            raise GateError(f"asset {asset_id} needs expected_files")
        if not isinstance(asset.get("expected_bytes"), int) or asset["expected_bytes"] < 1:
            raise GateError(f"asset {asset_id} needs expected_bytes")
        license_info = asset.get("license")
        if not isinstance(license_info, dict) or not license_info.get("id") or not license_info.get("url"):
            raise GateError(f"asset {asset_id} lacks a license record")
        if license_info.get("approval") not in {
            "approved",
            "approved-with-attribution",
            "manual-for-new-download",
        }:
            raise GateError(f"asset {asset_id} has no accepted license policy")
        critical = asset.get("critical_files", {})
        if not isinstance(critical, dict):
            raise GateError(f"asset {asset_id} critical_files must be an object")
        for relative, digest in critical.items():
            if not isinstance(relative, str) or not HEX64.fullmatch(str(digest)):
                raise GateError(f"asset {asset_id} has an invalid critical-file hash")
        if asset["kind"] == "hf_file":
            source_file = asset.get("source_file", "")
            if not isinstance(source_file, str) or source_file.startswith("/") or ".." in Path(source_file).parts:
                raise GateError(f"asset {asset_id} has an unsafe source_file")
        include_files = asset.get("include_files")
        if include_files is not None:
            if (
                not isinstance(include_files, list)
                or not include_files
                or any(
                    not isinstance(name, str)
                    or name.startswith("/")
                    or ".." in Path(name).parts
                    for name in include_files
                )
            ):
                raise GateError(f"asset {asset_id} has unsafe include_files")
        exclude_globs = asset.get("exclude_globs", [])
        if not isinstance(exclude_globs, list) or any(not isinstance(pattern, str) for pattern in exclude_globs):
            raise GateError(f"asset {asset_id} has invalid exclude_globs")

    for checkout in lock.get("source_checkouts", []):
        checkout_id = checkout.get("id", "<unknown>")
        if checkout.get("node") not in allowed_nodes:
            raise GateError(f"checkout {checkout_id} targets a non-Studio node")
        if not HEX40.fullmatch(checkout.get("commit", "")):
            raise GateError(f"checkout {checkout_id} does not pin a commit")
        node = nodes[checkout["node"]]
        if not is_under_posix(checkout.get("destination", ""), node["home"] + "/alma-studio"):
            raise GateError(f"checkout {checkout_id} escapes the Studio root")
        if not str(checkout.get("origin", "")).startswith("https://github.com/"):
            raise GateError(f"checkout {checkout_id} has an unapproved origin")

    checkout_ids = {item["id"] for item in lock.get("source_checkouts", [])}
    for binding in lock.get("runtime_bindings", []):
        binding_id = binding.get("id", "<unknown>")
        node_id = binding.get("node")
        if node_id not in allowed_nodes:
            raise GateError(f"runtime binding {binding_id} targets a non-Studio node")
        if binding.get("source_checkout") not in checkout_ids:
            raise GateError(f"runtime binding {binding_id} lacks a pinned source checkout")
        if not HEX64.fullmatch(binding.get("sha256", "")):
            raise GateError(f"runtime binding {binding_id} lacks a SHA-256")
        node = nodes[node_id]
        if not is_under_posix(binding.get("source", ""), node["home"] + "/alma-studio"):
            raise GateError(f"runtime binding {binding_id} source escapes Studio")
        if not is_under_posix(binding.get("destination", ""), node["model_root"]):
            raise GateError(f"runtime binding {binding_id} destination escapes models")
        if binding.get("policy") != "copy-if-missing-never-overwrite-never-execute":
            raise GateError(f"runtime binding {binding_id} has an unsafe policy")

    for link in lock.get("comfy_links", []):
        link_id = link.get("id", "<unknown>")
        if link.get("node") != "dgx3":
            raise GateError(f"Comfy link {link_id} must target DGX3")
        node = nodes["dgx3"]
        if not is_under_posix(link.get("source", ""), node["model_root"]):
            raise GateError(f"Comfy link {link_id} source escapes the model root")
        if not is_under_posix(link.get("destination", ""), node["comfy_root"] + "/models"):
            raise GateError(f"Comfy link {link_id} destination escapes Comfy models")


def api_url(repo_id: str, revision: str) -> str:
    repo = urllib.parse.quote(repo_id, safe="/")
    rev = urllib.parse.quote(revision, safe="")
    return f"{HF_ORIGIN}/api/models/{repo}/revision/{rev}?blobs=true"


def resolve_url(repo_id: str, revision: str, filename: str) -> str:
    repo = urllib.parse.quote(repo_id, safe="/")
    rev = urllib.parse.quote(revision, safe="")
    name = urllib.parse.quote(filename, safe="/")
    return f"{HF_ORIGIN}/{repo}/resolve/{rev}/{name}?download=true"


def http_json(url: str, timeout: int = 60) -> dict[str, Any]:
    if not url.startswith(HF_ORIGIN + "/"):
        raise GateError(f"network origin is not allowlisted: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            value = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise GateError(f"official Hugging Face metadata request failed: {exc}") from exc
    if not isinstance(value, dict):
        raise GateError("official model metadata was not an object")
    return value


def official_records(asset: dict[str, Any], info: dict[str, Any]) -> list[dict[str, Any]]:
    if info.get("sha") != asset["revision"]:
        raise GateError(
            f"{asset['id']}: official API resolved {info.get('sha')!r}, not locked revision {asset['revision']}"
        )
    siblings = info.get("siblings")
    if not isinstance(siblings, list):
        raise GateError(f"{asset['id']}: official API omitted siblings")
    records: list[dict[str, Any]] = []
    for raw in siblings:
        if not isinstance(raw, dict) or not isinstance(raw.get("rfilename"), str):
            raise GateError(f"{asset['id']}: malformed sibling record")
        filename = raw["rfilename"]
        lfs = raw.get("lfs") if isinstance(raw.get("lfs"), dict) else None
        size = (lfs or raw).get("size")
        if not isinstance(size, int) or size < 0:
            raise GateError(f"{asset['id']}: official size missing for {filename}")
        if lfs:
            digest_kind = "sha256"
            digest = lfs.get("sha256")
            if not isinstance(digest, str) or not HEX64.fullmatch(digest):
                raise GateError(f"{asset['id']}: LFS hash missing for {filename}")
        else:
            digest_kind = "git_blob_sha1"
            digest = raw.get("blobId")
            if not isinstance(digest, str) or not HEX40.fullmatch(digest):
                raise GateError(f"{asset['id']}: Git blob id missing for {filename}")
        records.append(
            {
                "filename": filename,
                "size": size,
                "digest_kind": digest_kind,
                "digest": digest,
            }
        )
    if asset["kind"] == "hf_file":
        records = [item for item in records if item["filename"] == asset["source_file"]]
        if len(records) != 1:
            raise GateError(f"{asset['id']}: locked source file is absent from official revision")
    elif asset.get("include_files") is not None:
        include = set(asset["include_files"])
        records = [item for item in records if item["filename"] in include]
        found = {item["filename"] for item in records}
        if found != include:
            raise GateError(f"{asset['id']}: one or more exact include_files are absent")
    elif asset.get("exclude_globs"):
        records = [
            item
            for item in records
            if not any(fnmatch.fnmatch(item["filename"], pattern) for pattern in asset["exclude_globs"])
        ]
    count = len(records)
    total = sum(item["size"] for item in records)
    if count != asset["expected_files"] or total != asset["expected_bytes"]:
        raise GateError(
            f"{asset['id']}: official revision shape {count} files/{total} bytes does not match lock "
            f"{asset['expected_files']} files/{asset['expected_bytes']} bytes"
        )
    return sorted(records, key=lambda item: item["filename"])


def asset_local_path(asset: dict[str, Any], filename: str) -> Path:
    destination = Path(asset["destination"])
    if asset["kind"] == "hf_file":
        return destination
    return destination / filename


def local_content_files(root: Path, asset: dict[str, Any] | None = None) -> list[Path]:
    if not root.exists():
        return []
    files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and ".cache" not in path.parts
        and ".alma-partial" not in path.parts
        and path.name != ".alma-snapshot.json"
    )
    if asset is None:
        return files
    if asset.get("include_files") is not None:
        include = set(asset["include_files"])
        return [path for path in files if str(path.relative_to(root)).replace(os.sep, "/") in include]
    if asset.get("exclude_globs"):
        return [
            path
            for path in files
            if not any(
                fnmatch.fnmatch(str(path.relative_to(root)).replace(os.sep, "/"), pattern)
                for pattern in asset["exclude_globs"]
            )
        ]
    return files


def metadata_path(asset: dict[str, Any], filename: str) -> Path:
    if asset["kind"] == "hf_file":
        destination = Path(asset["destination"])
        # hf_file assets may share one local_dir; use its closest model-root marker.
        marker = destination
        while marker.parent != marker and marker.name not in {
            "FLUX.2-klein-4B-comfy-runtime",
            "project-loras",
        }:
            marker = marker.parent
        root = marker if marker.name != "project-loras" else destination.parent
    else:
        root = Path(asset["destination"])
    return root / ".cache" / "huggingface" / "download" / f"{filename}.metadata"


def verify_cached_revision(asset: dict[str, Any], filename: str) -> str:
    meta = metadata_path(asset, filename)
    if not meta.is_file():
        return "absent"
    lines = meta.read_text(encoding="utf-8", errors="strict").splitlines()
    if len(lines) < 2 or lines[0] != asset["revision"]:
        raise GateError(f"{asset['id']}: cached revision metadata drift for {filename}")
    return "matched"


def verify_record(path: Path, record: dict[str, Any], full_hash: bool) -> dict[str, Any]:
    if not path.is_file():
        raise GateError(f"missing locked file: {path}")
    size = path.stat().st_size
    if size != record["size"]:
        raise GateError(f"size mismatch for {path}: {size} != {record['size']}")
    result = {"path": str(path), "bytes": size, "hash": "not-computed"}
    if full_hash:
        actual = sha256_file(path) if record["digest_kind"] == "sha256" else git_blob_sha1(path)
        if actual != record["digest"]:
            raise GateError(f"content hash mismatch for {path}")
        result["hash"] = f"{record['digest_kind']}:{actual}"
    return result


def verify_asset(
    asset: dict[str, Any],
    *,
    info: dict[str, Any] | None,
    full_hash: bool,
) -> dict[str, Any]:
    started = utc_now()
    result: dict[str, Any] = {
        "id": asset["id"],
        "node": asset["node"],
        "revision": asset["revision"],
        "started_at": started,
        "hash_scope": "all-official-files" if full_hash else "critical-files-and-cached-etags",
    }
    if info is not None:
        records = official_records(asset, info)
    elif asset["kind"] == "hf_file":
        critical_digest = next(iter(asset.get("critical_files", {}).values()), None)
        if not critical_digest:
            raise GateError(f"{asset['id']}: offline hf_file requires a critical SHA-256")
        records = [
            {
                "filename": asset["source_file"],
                "size": asset["expected_bytes"],
                "digest_kind": "sha256",
                "digest": critical_digest,
            }
        ]
    else:
        root = Path(asset["destination"])
        files = local_content_files(root, asset)
        count = len(files)
        total = sum(path.stat().st_size for path in files)
        if count != asset["expected_files"] or total != asset["expected_bytes"]:
            raise GateError(
                f"{asset['id']}: local shape {count} files/{total} bytes does not match lock "
                f"{asset['expected_files']} files/{asset['expected_bytes']} bytes"
            )
        records = [
            {
                "filename": str(path.relative_to(root)).replace(os.sep, "/"),
                "size": path.stat().st_size,
                "digest_kind": "unknown",
                "digest": "",
            }
            for path in files
        ]
        if full_hash:
            raise GateError(f"{asset['id']}: full-hash verification requires official metadata")

    checked: list[dict[str, Any]] = []
    revision_metadata = {"matched": 0, "absent": 0}
    for record in records:
        path = asset_local_path(asset, record["filename"])
        check_hash = full_hash and record["digest_kind"] != "unknown"
        checked.append(verify_record(path, record, check_hash))
        metadata_state = verify_cached_revision(asset, record["filename"])
        revision_metadata[metadata_state] += 1

    for relative, expected in asset.get("critical_files", {}).items():
        critical_path = Path(asset["destination"]) if relative == "." else Path(asset["destination"]) / relative
        if not critical_path.is_file():
            raise GateError(f"{asset['id']}: missing critical file {relative}")
        actual = sha256_file(critical_path)
        if actual != expected:
            raise GateError(f"{asset['id']}: critical SHA-256 mismatch for {relative}")

    result.update(
        {
            "status": "VERIFIED" if full_hash else "VERIFIED_SHAPE_REVISION_CRITICAL_HASHES",
            "files": len(records),
            "bytes": sum(item["size"] for item in records),
            "revision_metadata": revision_metadata,
            "critical_hashes": len(asset.get("critical_files", {})),
            "completed_at": utc_now(),
        }
    )
    return result


def license_receipts(paths: Iterable[Path]) -> dict[str, dict[str, Any]]:
    receipts: dict[str, dict[str, Any]] = {}
    for path in paths:
        receipt = load_json(path)
        receipt_id = receipt.get("receipt_id")
        if not isinstance(receipt_id, str) or not receipt_id:
            raise GateError(f"license receipt lacks receipt_id: {path}")
        receipts[receipt_id] = receipt
    return receipts


def require_download_license(asset: dict[str, Any], receipts: dict[str, dict[str, Any]]) -> None:
    license_info = asset["license"]
    if license_info["approval"] != "manual-for-new-download":
        return
    receipt_id = license_info.get("receipt_id")
    receipt = receipts.get(receipt_id)
    if not receipt:
        raise GateError(f"{asset['id']}: new download requires license receipt {receipt_id!r}")
    required = {
        "receipt_id": receipt_id,
        "asset_id": asset["id"],
        "revision": asset["revision"],
        "license_url": license_info["url"],
        "accepted": True,
    }
    for key, expected in required.items():
        if receipt.get(key) != expected:
            raise GateError(f"{asset['id']}: license receipt field {key} does not match")
    if not receipt.get("accepted_by") or not receipt.get("accepted_at"):
        raise GateError(f"{asset['id']}: license receipt lacks human attribution/time")


def download_stream(url: str, staging: Path, expected_size: int) -> None:
    if not url.startswith(HF_ORIGIN + "/"):
        raise GateError("download origin is not allowlisted")
    staging.parent.mkdir(parents=True, exist_ok=True)
    existing = staging.stat().st_size if staging.exists() else 0
    headers = {"User-Agent": USER_AGENT}
    if existing:
        headers["Range"] = f"bytes={existing}-"
    request = urllib.request.Request(url, headers=headers)
    try:
        response = urllib.request.urlopen(request, timeout=120)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise GateError(f"download failed for {url}: {exc}") from exc
    status = getattr(response, "status", None)
    if existing and status != 206:
        response.close()
        raise GateError("server did not honor safe resume; remove the scoped partial file explicitly")
    mode = "ab" if existing else "xb"
    try:
        with response, staging.open(mode) as handle:
            shutil.copyfileobj(response, handle, CHUNK_BYTES)
    except FileExistsError as exc:
        raise GateError(f"unexpected staging collision: {staging}") from exc
    size = staging.stat().st_size
    if size != expected_size:
        raise GateError(f"partial download size {size} does not equal expected {expected_size}")


def prepare_asset(
    asset: dict[str, Any],
    *,
    info: dict[str, Any],
    receipts: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    records = official_records(asset, info)
    downloaded: list[str] = []
    for record in records:
        target = asset_local_path(asset, record["filename"])
        if target.exists():
            verify_record(target, record, True)
            continue
        require_download_license(asset, receipts)
        target.parent.mkdir(parents=True, exist_ok=True)
        if asset["kind"] == "hf_file":
            staging_root = target.parent / ".alma-partial"
        else:
            staging_root = Path(asset["destination"]) / ".alma-partial"
        staging = staging_root / (hashlib.sha256(record["filename"].encode("utf-8")).hexdigest() + ".part")
        download_stream(
            resolve_url(asset["repo_id"], asset["revision"], record["filename"]),
            staging,
            record["size"],
        )
        verify_record(staging, record, True)
        if target.exists():
            raise GateError(f"target appeared during download; refusing overwrite: {target}")
        os.replace(staging, target)
        downloaded.append(str(target))

    receipt_path = (
        Path(asset["destination"]) / ".alma-snapshot.json"
        if asset["kind"] == "hf_snapshot"
        else Path(asset["destination"]).parent / f".{Path(asset['destination']).name}.alma-snapshot.json"
    )
    snapshot = {
        "schema_version": 1,
        "asset_id": asset["id"],
        "repo_id": asset["repo_id"],
        "revision": asset["revision"],
        "official_records_sha256": canonical_sha256(records),
        "files": len(records),
        "bytes": sum(item["size"] for item in records),
        "prepared_at": utc_now(),
        "remote_code_executed": False,
    }
    receipt_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    verified = verify_asset(asset, info=info, full_hash=True)
    verified["downloaded"] = downloaded
    return verified


def run_checked(command: list[str], cwd: Path | None = None) -> str:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=1800,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GateError(f"command failed to run: {command[0]}: {exc}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-1000:]
        raise GateError(f"command failed ({completed.returncode}): {command[0]}: {detail}")
    return completed.stdout.strip()


def verify_checkout(checkout: dict[str, Any]) -> dict[str, Any]:
    destination = Path(checkout["destination"])
    if not (destination / ".git").is_dir():
        raise GateError(f"checkout missing: {destination}")
    origin = run_checked(["git", "-C", str(destination), "remote", "get-url", "origin"])
    commit = run_checked(["git", "-C", str(destination), "rev-parse", "HEAD"])
    dirty = run_checked(["git", "-C", str(destination), "status", "--porcelain", "--untracked-files=no"])
    if origin != checkout["origin"]:
        raise GateError(f"{checkout['id']}: Git origin drift")
    if commit != checkout["commit"]:
        raise GateError(f"{checkout['id']}: Git commit drift")
    if dirty:
        raise GateError(f"{checkout['id']}: tracked source modifications are present")
    return {"id": checkout["id"], "status": "VERIFIED", "origin": origin, "commit": commit}


def prepare_checkout(checkout: dict[str, Any]) -> dict[str, Any]:
    destination = Path(checkout["destination"])
    if destination.exists():
        return verify_checkout(checkout)
    destination.parent.mkdir(parents=True, exist_ok=True)
    run_checked(["git", "clone", "--filter=blob:none", "--no-checkout", checkout["origin"], str(destination)])
    run_checked(["git", "-C", str(destination), "fetch", "--depth", "1", "origin", checkout["commit"]])
    run_checked(["git", "-C", str(destination), "checkout", "--detach", checkout["commit"]])
    return verify_checkout(checkout)


def verify_environment(environment: dict[str, Any]) -> dict[str, Any]:
    python = Path(environment["python"])
    if not python.is_file() and not python.is_symlink():
        raise GateError(f"environment interpreter missing: {python}")
    package_names = list(environment["packages"])
    probe = (
        "import importlib.metadata as m,json,sys;"
        "names=json.loads(sys.argv[1]);"
        "out={'python':'.'.join(map(str,sys.version_info[:3])),'packages':{}};"
        "exec(\"for n in names:\\n try: out['packages'][n]=m.version(n)\\n except m.PackageNotFoundError: out['packages'][n]=None\");"
        "print(json.dumps(out,sort_keys=True))"
    )
    output = run_checked([str(python), "-c", probe, json.dumps(package_names)])
    try:
        actual = json.loads(output)
    except json.JSONDecodeError as exc:
        raise GateError(f"environment probe returned invalid JSON: {environment['id']}") from exc
    if actual.get("python") != environment["python_version"]:
        raise GateError(f"{environment['id']}: Python version drift")
    drift = {
        name: {"expected": expected, "actual": actual["packages"].get(name)}
        for name, expected in environment["packages"].items()
        if actual["packages"].get(name) != expected
    }
    if drift:
        raise GateError(f"{environment['id']}: package drift: {json.dumps(drift, sort_keys=True)}")

    for name, vcs in environment.get("vcs_packages", {}).items():
        direct_probe = (
            "import importlib.metadata as m,json,sys;"
            "d=m.distribution(sys.argv[1]);"
            "p=d.locate_file(d.read_text('direct_url.json') and '');"
            "print(d.read_text('direct_url.json') or '{}')"
        )
        direct = json.loads(run_checked([str(python), "-c", direct_probe, name]))
        if direct.get("url") != vcs["origin"] or direct.get("vcs_info", {}).get("commit_id") != vcs["commit"]:
            raise GateError(f"{environment['id']}: VCS provenance drift for {name}")
    return {
        "id": environment["id"],
        "status": "VERIFIED",
        "python": actual["python"],
        "packages": actual["packages"],
        "policy": environment["policy"],
    }


def verify_or_create_runtime_binding(binding: dict[str, Any], create: bool) -> dict[str, Any]:
    source = Path(binding["source"])
    destination = Path(binding["destination"])
    if not source.is_file():
        raise GateError(f"runtime binding source missing: {source}")
    source_hash = sha256_file(source)
    if source_hash != binding["sha256"]:
        raise GateError(f"runtime binding source hash drift: {binding['id']}")
    created = False
    if destination.exists():
        if not destination.is_file() or sha256_file(destination) != binding["sha256"]:
            raise GateError(f"runtime binding destination drift: {binding['id']}")
    else:
        if not create:
            raise GateError(f"runtime binding is not prepared: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as input_handle, destination.open("xb") as output_handle:
            shutil.copyfileobj(input_handle, output_handle, CHUNK_BYTES)
        if sha256_file(destination) != binding["sha256"]:
            raise GateError(f"runtime binding copy verification failed: {binding['id']}")
        created = True
    return {
        "id": binding["id"],
        "status": "VERIFIED",
        "sha256": binding["sha256"],
        "created": created,
        "executed": False,
    }


def verify_or_create_link(link: dict[str, Any], create: bool) -> dict[str, Any]:
    source = Path(link["source"])
    destination = Path(link["destination"])
    if not source.exists():
        raise GateError(f"Comfy source missing: {source}")
    if destination.is_symlink():
        actual = os.readlink(destination)
        actual_path = (destination.parent / actual).resolve() if not os.path.isabs(actual) else Path(actual).resolve()
        if actual_path != source.resolve():
            raise GateError(f"Comfy link points to the wrong source: {destination}")
        return {"id": link["id"], "status": "VERIFIED", "created": False}
    if destination.exists():
        raise GateError(f"refusing to replace existing non-symlink Comfy path: {destination}")
    if not create:
        raise GateError(f"Comfy link is not prepared: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.symlink_to(source, target_is_directory=source.is_dir())
    return {"id": link["id"], "status": "VERIFIED", "created": True}


def verify_system_tool(tool: dict[str, Any]) -> dict[str, Any]:
    path = Path(tool["path"])
    if not path.is_file():
        raise GateError(f"system tool missing: {path}")
    version = run_checked([str(path), "-version"])
    if tool["version_contains"] not in version:
        raise GateError(f"{tool['id']}: version drift")
    feature_text = version
    if path.name == "ffmpeg":
        feature_text += "\n" + run_checked([str(path), "-hide_banner", "-encoders"])
        feature_text += "\n" + run_checked([str(path), "-hide_banner", "-filters"])
    missing = [feature for feature in tool.get("required_features", []) if feature not in feature_text]
    if missing:
        raise GateError(f"{tool['id']}: missing required features: {missing}")
    return {
        "id": tool["id"],
        "status": "VERIFIED",
        "version": version.splitlines()[0],
        "features": tool.get("required_features", []),
    }


def validate_project_loras(project: dict[str, Any], lock: dict[str, Any]) -> list[dict[str, Any]]:
    if project.get("schema_version") != 1:
        raise GateError("unsupported project LoRA schema")
    project_id = project.get("project_id", "")
    if not PROJECT_ID.fullmatch(project_id):
        raise GateError("project_id is invalid")
    if not project.get("approved_by") or project.get("approved_by") == "REPLACE_WITH_HUMAN_APPROVER":
        raise GateError("project LoRA allowlist needs a real human approver")
    if not project.get("approved_at"):
        raise GateError("project LoRA allowlist needs approved_at")
    core = {asset["id"]: asset for asset in lock["assets"] if asset.get("enabled")}
    seen: set[str] = set()
    loras: list[dict[str, Any]] = []
    for item in project.get("loras", []):
        if not item.get("enabled"):
            continue
        item_id = item.get("id", "")
        if not PROJECT_ID.fullmatch(item_id) or item_id in seen:
            raise GateError(f"invalid or duplicate LoRA id: {item_id!r}")
        seen.add(item_id)
        if item.get("node") != "dgx3":
            raise GateError(f"LoRA {item_id} may only target DGX3")
        revision = item.get("revision", "")
        digest = item.get("sha256", "")
        source_file = item.get("source_file", "")
        if not HEX40.fullmatch(revision) or not HEX64.fullmatch(digest):
            raise GateError(f"LoRA {item_id} lacks immutable revision/hash pins")
        if (
            not isinstance(source_file, str)
            or not source_file.endswith(".safetensors")
            or source_file.startswith("/")
            or ".." in Path(source_file).parts
            or "\\" in source_file
        ):
            raise GateError(f"LoRA {item_id} is not an exact safe .safetensors path")
        if not isinstance(item.get("bytes"), int) or item["bytes"] < 1:
            raise GateError(f"LoRA {item_id} lacks an exact byte count")
        license_info = item.get("license")
        if not isinstance(license_info, dict) or license_info.get("commercial_use") == "forbidden":
            raise GateError(f"LoRA {item_id} is not approved for this production lock")
        bases = item.get("compatible_base_assets")
        if not isinstance(bases, list) or not bases:
            raise GateError(f"LoRA {item_id} has no compatible base model")
        for base in bases:
            if base not in core or core[base]["node"] != "dgx3":
                raise GateError(f"LoRA {item_id} references an unapproved base asset: {base}")
        destination = (
            Path(lock["nodes"]["dgx3"]["model_root"])
            / "project-loras"
            / project_id
            / Path(source_file).name
        )
        synthetic = {
            "id": f"project-{project_id}-{item_id}",
            "kind": "hf_file",
            "enabled": True,
            "node": "dgx3",
            "repo_id": item["repo_id"],
            "revision": revision,
            "source_file": source_file,
            "destination": str(destination),
            "expected_files": 1,
            "expected_bytes": item["bytes"],
            "license": {
                "id": license_info["id"],
                "url": license_info["url"],
                "approval": "approved",
            },
            "critical_files": {".": digest},
        }
        loras.append(
            {
                "asset": synthetic,
                "link": {
                    "id": synthetic["id"] + "-comfy",
                    "node": "dgx3",
                    "source": str(destination),
                    "destination": str(
                        Path(lock["nodes"]["dgx3"]["comfy_root"])
                        / "models"
                        / "loras"
                        / "projects"
                        / project_id
                        / Path(source_file).name
                    ),
                },
            }
        )
    return loras


def write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare pinned Studio assets without starting services.")
    parser.add_argument("--lock", required=True, type=Path)
    parser.add_argument("--node", required=True, choices=("dgx3", "dgx4"))
    parser.add_argument("--mode", choices=("audit", "prepare"), default="audit")
    parser.add_argument("--asset", action="append", default=[], help="Limit to one or more asset IDs.")
    parser.add_argument("--offline", action="store_true", help="Use locked shape and cached revision metadata only.")
    parser.add_argument("--full-hash", action="store_true", help="Hash every official file; may read hundreds of GB.")
    parser.add_argument("--project-loras", type=Path)
    parser.add_argument("--license-receipt", action="append", type=Path, default=[])
    parser.add_argument("--skip-sources", action="store_true")
    parser.add_argument("--skip-environments", action="store_true")
    parser.add_argument("--skip-tools", action="store_true")
    parser.add_argument("--skip-comfy-links", action="store_true")
    parser.add_argument("--receipt", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    started = utc_now()
    receipt: dict[str, Any] = {
        "schema_version": 1,
        "started_at": started,
        "node": args.node,
        "mode": args.mode,
        "activation_attempted": False,
        "remote_code_executed": False,
        "assets": [],
        "sources": [],
        "runtime_bindings": [],
        "environments": [],
        "comfy_links": [],
        "system_tools": [],
    }
    try:
        lock = load_json(args.lock)
        validate_lock(lock)
        receipt["lock_id"] = lock["lock_id"]
        receipt["lock_sha256"] = sha256_file(args.lock)
        receipts = license_receipts(args.license_receipt)
        selected = {
            asset["id"]: asset
            for asset in lock["assets"]
            if asset.get("enabled") and asset["node"] == args.node
        }
        if args.asset:
            unknown = sorted(set(args.asset) - set(selected))
            if unknown:
                raise GateError(f"unknown/not-enabled asset selection for {args.node}: {unknown}")
            selected = {key: selected[key] for key in args.asset}

        project_loras: list[dict[str, Any]] = []
        if args.project_loras:
            if args.node != "dgx3":
                raise GateError("project LoRAs may only be prepared on DGX3")
            project = load_json(args.project_loras)
            project_loras = validate_project_loras(project, lock)
            for entry in project_loras:
                selected[entry["asset"]["id"]] = entry["asset"]
            receipt["project_lora_allowlist_sha256"] = sha256_file(args.project_loras)

        for asset in selected.values():
            info = None if args.offline else http_json(api_url(asset["repo_id"], asset["revision"]))
            if args.mode == "prepare":
                if info is None:
                    raise GateError("prepare mode cannot run offline")
                receipt["assets"].append(prepare_asset(asset, info=info, receipts=receipts))
            else:
                receipt["assets"].append(
                    verify_asset(asset, info=info, full_hash=args.full_hash)
                )

        if not args.skip_sources:
            for checkout in lock["source_checkouts"]:
                if checkout["node"] == args.node:
                    receipt["sources"].append(
                        prepare_checkout(checkout) if args.mode == "prepare" else verify_checkout(checkout)
                    )

        for binding in lock.get("runtime_bindings", []):
            if binding["node"] == args.node:
                receipt["runtime_bindings"].append(
                    verify_or_create_runtime_binding(binding, create=args.mode == "prepare")
                )

        if not args.skip_environments:
            for environment in lock["environments"]:
                if environment["node"] == args.node:
                    receipt["environments"].append(verify_environment(environment))

        if not args.skip_comfy_links and args.node == "dgx3":
            links = list(lock["comfy_links"]) + [entry["link"] for entry in project_loras]
            for link in links:
                receipt["comfy_links"].append(
                    verify_or_create_link(link, create=args.mode == "prepare")
                )

        if not args.skip_tools:
            for tool in lock["system_tools"]:
                if tool["node"] == args.node:
                    receipt["system_tools"].append(verify_system_tool(tool))

        receipt["status"] = "VERIFIED"
        receipt["completed_at"] = utc_now()
        write_receipt(args.receipt, receipt)
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        receipt["status"] = "BLOCKED"
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        receipt["completed_at"] = utc_now()
        try:
            write_receipt(args.receipt, receipt)
        except Exception:
            pass
        print(json.dumps(receipt, indent=2, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
