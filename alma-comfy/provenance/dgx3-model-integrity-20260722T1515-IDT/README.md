# DGX3 model snapshot integrity — 2026-07-22

Audit completed: `2026-07-22T15:22:22+03:00`  
Host: `edgexpert-01e6` (`eran3@<lan-ip>`)  
Scope: read-only verification of the two completed Hugging Face `local_dir`
downloads below. No inference, package change, file deletion, or remote write was
performed. The full content pass ran with `ionice -c3` and `nice -n 19`.

## Verdict

### VERIFIED — `Lightricks/LTX-2.3`

- Local snapshot commit: `4229404625088d21c4f112eb640fb04a0900ee25`.
- Official Hugging Face API `main` commit at audit time: the same commit;
  `lastModified=2026-07-09T11:12:53Z`.
- Exact tree: `13/13` files, `157,004,895,857` bytes; no missing, extra, or
  size-mismatched paths.
- Full content: `10` LFS objects matched their recorded SHA-256 and `3` normal
  files matched their recorded Git-blob SHA-1; `13/13` matched across
  `157,004,895,857` bytes.
- Verification-manifest SHA-256:
  `cf158300a8c7827f9d9d70b663574a8ac15571a3d5f88d53da276fb038433ffc`.
- All `9` Safetensors headers parsed; all non-cache JSON parsed; all `13`
  `.metadata` files matched both snapshot commit and expected ETag.
- No `.incomplete`, `.partial`, `.part`, `.tmp`, `.aria2`, or `.crdownload`
  file exists.
- The `13` Hugging Face `.lock` artifacts are zero-byte and inactive: no
  matching download process, kernel lock, or open cache file was present.
- This upstream repository is a single-file checkpoint/upscaler bundle. It has
  no `model_index.json` or component config tree in the official 13-file
  snapshot; their absence is not a local omission.

### VERIFIED — `Wan-AI/Wan2.2-I2V-A14B-Diffusers`

- Local snapshot commit: `596658fd9ca6b7b71d5057529bbf319ecbc61d74`.
- Official Hugging Face API `main` commit at audit time: the same commit;
  `lastModified=2025-08-09T03:33:59Z`.
- Exact tree: `50/50` files, `126,204,155,463` bytes; no missing, extra, or
  size-mismatched paths.
- Full content: `35` LFS objects matched their recorded SHA-256 and `15`
  normal files matched their recorded Git-blob SHA-1; `50/50` matched across
  `126,204,155,463` bytes.
- Verification-manifest SHA-256:
  `4ec7365bae3a30570e073c40ef3314d7c4d1c13c84be3f6af826028194ea95ad`.
- All `28` Safetensors headers and all non-cache JSON files parsed.
- Required pipeline files are present: `model_index.json`, scheduler, tokenizer,
  text-encoder, both transformer configs/indexes, and VAE config/weights.
- Shard indexes resolve completely: text encoder `3/3`; transformer `12/12`;
  transformer_2 `12/12`; no referenced shard is missing.
- All `50` `.metadata` files matched both snapshot commit and expected ETag.
- No partial/incomplete file exists. The `50` zero-byte `.lock` artifacts were
  inactive by process, kernel-lock, and open-file checks.

## Local metadata discrepancy — NEEDS UPDATE

The model downloads are intact, but `MODEL_MANIFEST.json` had stale
`expected_bytes` values at audit time:

- LTX recorded `157,004,866,317`; verified official snapshot is
  `157,004,895,857` (`+29,540`).
- Wan recorded `126,203,713,911`; verified official snapshot is
  `126,204,155,463` (`+441,552`).

These values should be updated in the Studio manifest. This discrepancy does
not indicate corrupt model files: local bytes, local snapshot metadata, full
content hashes, and the official current Hugging Face API all agree.

## Sources and reproducibility

- Official model: https://huggingface.co/Lightricks/LTX-2.3
- Official API: https://huggingface.co/api/models/Lightricks/LTX-2.3?blobs=true
- Official model: https://huggingface.co/Wan-AI/Wan2.2-I2V-A14B-Diffusers
- Official API: https://huggingface.co/api/models/Wan-AI/Wan2.2-I2V-A14B-Diffusers?blobs=true
- Audit script: `audit_snapshot.py`
- Audit-script SHA-256:
  `84a6143efebe23772aa3135b690c1848b29523c79b1a306e413a674450624297`

The audit script compares the exact local path set and sizes with the
Hugging Face tree cache, validates commit/ETag metadata, parses JSON and
Safetensors headers, resolves shard indexes, and then streams every file to
recompute its official LFS SHA-256 or Git-blob SHA-1.
