# FLUX.2 Klein DGX3 technical canary

- Result: **PASS** through the existing ComfyUI checkout at commit
  `947c2749dd04c51ef0e21b069544d8b0b4f9b411`.
- Model: `black-forest-labs/FLUX.2-klein-4B-fp8`.
- Fixed seed: `20260722`; 4 Euler steps; CFG `1.0`; 512 x 512.
- Output: `flux2-klein-fixed-seed.png`, 275,088 bytes, RGB PNG.
- SHA-256: `2bd82bb4f87b7afed3b59249e6a2783a6d4498a6458a56d46b48ce6c344c2bc6`.
- Full Pillow verify plus full pixel decode passed; pixel range 0-255 and standard
  deviation 70.1162, so the artifact is nonempty and nonblank.
- ComfyUI reported execution in 6.27 seconds; end-to-end driver time, including
  model hashing and API verification, was 15.229 seconds.
- Telemetry: 15 samples; peak GPU utilization 96%, peak temperature 50 C,
  peak power 46.03 W, and minimum available system/unified memory
  103,061,983,232 bytes.
- Post-stop scan found no CUDA, OOM, illegal-memory, kernel, cuBLAS, cuDNN, or
  segmentation-fault signature in the complete server and driver logs.
- Human visual review: **not recorded**.

The initial Diffusers-only attempt is preserved separately in
`../flux2-klein-20260722T151956+0300`. It failed before generation because the
Diffusers single-file FP8 converter attempted `torch.chunk` on a scalar
quantization-scale tensor. No package was patched. The successful canary used
ComfyUI's native mixed-precision loader instead.

The server log contains nonfatal startup warnings for optional `kornia_rs`
extras and the workflow-template frontend path. All 12 required core nodes and
all three model files were discovered, the API prompt completed successfully,
and the temporary loopback server was stopped after evidence collection.
