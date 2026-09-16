from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "studio_asset_preparer", ROOT / "tools" / "studio_asset_preparer.py"
)
assert SPEC and SPEC.loader
PREP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREP)


def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


class StudioAssetPreparerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.lock = PREP.load_json(ROOT / "studio_assets.lock.json")

    def test_real_lock_is_fail_closed_and_has_corrected_integrity_values(self) -> None:
        PREP.validate_lock(self.lock)
        self.assertEqual(self.lock["policy"]["activation"], "forbidden")
        self.assertFalse(self.lock["policy"]["remote_code_execution"])
        assets = {item["id"]: item for item in self.lock["assets"]}
        self.assertEqual(assets["ltx-2.3"]["expected_bytes"], 157004895857)
        self.assertEqual(assets["wan2.2-i2v-a14b"]["expected_bytes"], 126204155463)
        self.assertEqual(assets["ace-step-1.5"]["exclude_globs"], ["*.py", "**/*.py"])
        self.assertEqual(assets["renikud-hebrew-g2p"]["include_files"], ["README.md", "model.onnx"])
        self.assertEqual(len(self.lock["runtime_bindings"]), 2)
        self.assertTrue(all(item["node"] == "dgx4" for item in self.lock["runtime_bindings"]))

    def test_official_records_require_exact_revision_shape_and_hash_metadata(self) -> None:
        config = b'{"model":"test"}\n'
        weights = b"safe tensor bytes"
        asset = {
            "id": "fixture",
            "kind": "hf_snapshot",
            "revision": "a" * 40,
            "expected_files": 2,
            "expected_bytes": len(config) + len(weights),
        }
        info = {
            "sha": "a" * 40,
            "siblings": [
                {"rfilename": "config.json", "size": len(config), "blobId": git_blob(config)},
                {
                    "rfilename": "model.safetensors",
                    "size": len(weights),
                    "lfs": {"size": len(weights), "sha256": hashlib.sha256(weights).hexdigest()},
                },
            ],
        }
        records = PREP.official_records(asset, info)
        self.assertEqual([item["filename"] for item in records], ["config.json", "model.safetensors"])
        wrong = dict(info)
        wrong["sha"] = "b" * 40
        with self.assertRaises(PREP.GateError):
            PREP.official_records(asset, wrong)

    def test_full_local_hash_verification_covers_lfs_and_git_blob(self) -> None:
        config = b'{"model":"test"}\n'
        weights = b"safe tensor bytes"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "model"
            root.mkdir()
            (root / "config.json").write_bytes(config)
            (root / "model.safetensors").write_bytes(weights)
            asset = {
                "id": "fixture",
                "kind": "hf_snapshot",
                "node": "dgx3",
                "revision": "a" * 40,
                "destination": str(root),
                "expected_files": 2,
                "expected_bytes": len(config) + len(weights),
                "critical_files": {},
            }
            info = {
                "sha": "a" * 40,
                "siblings": [
                    {"rfilename": "config.json", "size": len(config), "blobId": git_blob(config)},
                    {
                        "rfilename": "model.safetensors",
                        "size": len(weights),
                        "lfs": {"size": len(weights), "sha256": hashlib.sha256(weights).hexdigest()},
                    },
                ],
            }
            result = PREP.verify_asset(asset, info=info, full_hash=True)
            self.assertEqual(result["status"], "VERIFIED")
            (root / "model.safetensors").write_bytes(b"tampered tensor!!")
            with self.assertRaises(PREP.GateError):
                PREP.verify_asset(asset, info=info, full_hash=True)

    def test_comfy_mapping_is_idempotent_and_refuses_wrong_existing_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "models" / "approved.safetensors"
            source.parent.mkdir()
            source.write_bytes(b"ok")
            destination = root / "ComfyUI" / "models" / "loras" / "approved.safetensors"
            link = {"id": "approved", "source": str(source), "destination": str(destination)}
            if os.name == "nt":
                # Non-elevated Windows test runners cannot create symlinks.  The
                # production target is Linux; still prove the no-overwrite gate.
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(b"do not overwrite")
                with self.assertRaises(PREP.GateError):
                    PREP.verify_or_create_link(link, create=True)
                return
            first = PREP.verify_or_create_link(link, create=True)
            second = PREP.verify_or_create_link(link, create=True)
            self.assertTrue(first["created"])
            self.assertFalse(second["created"])
            destination.unlink()
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"do not overwrite")
            with self.assertRaises(PREP.GateError):
                PREP.verify_or_create_link(link, create=True)

    def test_runtime_binding_copies_only_exact_pinned_source_and_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.py"
            destination = root / "model" / "source.py"
            source.write_text("PINNED = True\n", encoding="utf-8")
            digest = PREP.sha256_file(source)
            binding = {
                "id": "binding",
                "source": str(source),
                "destination": str(destination),
                "sha256": digest,
            }
            first = PREP.verify_or_create_runtime_binding(binding, create=True)
            second = PREP.verify_or_create_runtime_binding(binding, create=True)
            self.assertTrue(first["created"])
            self.assertFalse(second["created"])
            self.assertFalse(second["executed"])
            destination.write_text("DRIFT = True\n", encoding="utf-8")
            with self.assertRaises(PREP.GateError):
                PREP.verify_or_create_runtime_binding(binding, create=True)

    def test_project_lora_requires_exact_safetensors_hash_license_and_base(self) -> None:
        project = {
            "schema_version": 1,
            "project_id": "film-one",
            "approved_by": "human-owner",
            "approved_at": "2026-07-22T13:00:00Z",
            "loras": [
                {
                    "id": "look-one",
                    "enabled": True,
                    "node": "dgx3",
                    "repo_id": "owner/look-one",
                    "revision": "b" * 40,
                    "source_file": "look-one.safetensors",
                    "bytes": 123,
                    "sha256": "c" * 64,
                    "license": {
                        "id": "Apache-2.0",
                        "url": "https://huggingface.co/owner/look-one",
                        "commercial_use": "allowed",
                    },
                    "compatible_base_assets": ["flux2-klein-fp8"],
                }
            ],
        }
        entries = PREP.validate_project_loras(project, self.lock)
        self.assertEqual(len(entries), 1)
        destination = entries[0]["asset"]["destination"].replace("\\", "/")
        self.assertTrue(destination.endswith("/film-one/look-one.safetensors"))
        project["loras"][0]["source_file"] = "loader.py"
        with self.assertRaises(PREP.GateError):
            PREP.validate_project_loras(project, self.lock)

    def test_ltx_new_download_requires_human_license_receipt(self) -> None:
        ltx = next(item for item in self.lock["assets"] if item["id"] == "ltx-2.3")
        with self.assertRaises(PREP.GateError):
            PREP.require_download_license(ltx, {})
        receipt = {
            "receipt_id": "ltx-2.3-license-acceptance",
            "asset_id": "ltx-2.3",
            "revision": ltx["revision"],
            "license_url": ltx["license"]["url"],
            "accepted": True,
            "accepted_by": "human-owner",
            "accepted_at": "2026-07-22T13:00:00Z",
        }
        PREP.require_download_license(ltx, {receipt["receipt_id"]: receipt})

    def test_legacy_civitai_auto_search_is_removed(self) -> None:
        source = (ROOT / "alma_lora.py").read_text(encoding="utf-8")
        self.assertNotIn("civitai.com", source.lower())
        self.assertIn("--allowlist", source)
        self.assertIn(".safetensors", source)


if __name__ == "__main__":
    unittest.main()
