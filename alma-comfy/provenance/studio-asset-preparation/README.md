# ALMA Studio locked preparation receipt — 2026-07-22

Scope: prepare and verify the existing DGX3/DGX4 Studio assets without starting
ComfyUI, Studio, workers, model inference, or generation.

## Verified

- Lock: `alma-studio-assets-20260722-v1`, SHA-256
  `ebf93263cceef756e250e6ee65c817d68c43711069ec098bb6d6dfc0a03a2ef3`.
- DGX3 official revisions, file sets/bytes, cached revision/ETag metadata, and
  critical hashes passed for FLUX.2 Klein FP8, its Qwen text encoder and VAE,
  Qwen Image 2512, LTX-2.3, Wan TI2V 5B, and Wan I2V A14B.
- DGX3 existing isolated environments and the ComfyUI checkout at commit
  `947c2749dd04c51ef0e21b069544d8b0b4f9b411` passed exact-version checks.
- Eleven declared ComfyUI mappings passed. Eight missing links were created on
  the first preparation pass; a second pass proved idempotence (`created=false`
  for all links).
- DGX4 official revisions, file sets/bytes, cached revision/ETag metadata, and
  critical hashes passed for ACE-Step 1.5, Blue ONNX v2, and Renikud.
- ACE-Step model-repository Python files are excluded from the official model
  snapshot. The two runtime binding files exactly match the separately pinned
  clean Git checkout at commit
  `6d467e4b5081ccb0abf1ec1bf4fdf9051a2d34b0`; their SHA-256 values passed and
  the preparer did not execute them.
- BlueTTS source passed at commit
  `f071b9100e15c24575f6e2919312f67057c7b589`; both DGX4 isolated environments
  passed exact critical-package checks.
- DGX4 FFmpeg/ffprobe 6.1.1 and required `libx265`, `hevc_nvenc`, and `zscale`
  capabilities passed.
- `activation_attempted=false` and `remote_code_executed=false` in every
  machine receipt.

Machine-readable receipts:

- `20260722T161618+0300-dgx3-audit.json`
- `20260722T161633+0300-dgx4-audit.json`
- `20260722T161638+0300-dgx3-prepare.json`

## Boundaries

- The audit hashes every critical file and validates all remaining file hashes
  through the pinned Hugging Face revision/ETag metadata. LTX-2.3 and Wan I2V
  also retain their earlier independent full-content verification manifests.
- The DGX3 preparation receipt performs a fresh full official-file hash over
  the selected FLUX.2 FP8 asset; `downloaded=[]` because it was already intact.
- No project LoRA was downloaded. The project allowlist is empty until a human
  approves an exact file, revision, hash, license, and compatible base model.
- This is preparation evidence, not a runtime or artistic acceptance claim.
