# ALMA Studio

ALMA Studio is the existing `alma-comfy` 2D-first movie-production console.
There are two clean layers:

- Brain: one Nemotron 3 Super PP2 runtime across DGX1 and DGX2, reached through
  the canonical local gateway at `http://127.0.0.1:8095`.
- Production workers: DGX3 for image/video/upscale and DGX4 for music, TTS,
  encoding, color, and mastering.

DGX1 and DGX2 are not Studio render workers. Yigal, Perets, the abandoned 340B
GGUF experiment, and duplicate assistant harnesses are not part of this design.

## Verified state — 2026-07-22

- Nemotron: one two-node PP2 service generated a fresh exact marker through
  the canonical port 8095 gateway.
- DGX3 video: Wan 2.2 TI2V produced a fixed-seed 17-frame, 832x480 H.264 MP4.
  Its SHA-256, ffprobe metadata, and full FFmpeg decode passed on ARM64/CUDA 13.
  The NVIDIA cuSPARSELt platform warning remains documented as a packaging-tag
  mismatch; the library ABI probe and CUDA BF16 execution passed without a
  package change.
- DGX3 image models: FLUX.2 passed an exact 24-file SHA-256 tree match and
  Qwen Image passed an exact 93-file, 57,704,605,954-byte SHA-256 tree match
  between DGX2 and DGX3. Both source copies were then removed from DGX2, along
  with the temporary transfer key. LTX-2.3 and Wan I2V A14B downloads are
  complete but still require independent integrity and runtime canaries.
- DGX4 music: ACE-Step produced a fixed-seed, non-silent 10-second stereo WAV.
- DGX4 TTS: Blue ONNX produced a fixed-seed 6.13-second Hebrew, 44.1 kHz mono,
  24-bit PCM WAV on CPU. The WAV hash, ffprobe, finite/non-silent, and
  no-clipping gates passed. Chatterbox weights are preserved, but an unmodified
  Python 3.14 install remains blocked by its old librosa/numba/llvmlite chain;
  no patch or downgrade was made.
- DGX4 finishing: FFmpeg produced a real 3840x2160, 24 fps, Main 10 HEVC
  HDR10/PQ MOV with BT.2020 non-constant-luminance color, mastering-display
  and MaxCLL/MaxFALL SEI, plus 24-bit 48 kHz stereo PCM. This proves the
  finishing path with a synthetic test pattern and the ACE canary; it is not
  yet a beautiful AI-rendered movie or a human-approved master.
- Real AI video and Hebrew TTS machine canaries now pass. A real image-generation
  canary, human visual/listening review, long-form continuity tests, and a
  human-approved 4K HDR master remain acceptance gates.

## Start the existing console

```powershell
python D:\CLAUDE\alma-comfy\studio_server.py --port 8810
```

Open `http://127.0.0.1:8810/`. Automation endpoints are `GET /api/health`,
`GET /api/manifest`, and `GET /api/nodes`. The node endpoint performs bounded,
read-only SSH checks of DGX3 and DGX4 only. `POST /api/brain/plan` sends a
planning request, with the full `STUDIO_PROMPT.md`, through the one canonical
Nemotron gateway on port 8095; it does not create another model runtime.

## Locked preparation (does not start the Studio)

`studio_assets.lock.json` is the one fail-closed preparation contract for
DGX3/DGX4. It pins the official repository revision, exact file count and byte
count, license record, critical hashes, Git source commits, Python environment
versions, finishing tools, and every ComfyUI model link. The preparer contains
no service-start or inference action.

Read-only audit:

```powershell
D:\CLAUDE\alma-comfy\prepare_studio_assets.ps1 -Mode Audit -Node all
```

Download only missing locked files, verify every downloaded file, and create
only declared ComfyUI links:

```powershell
D:\CLAUDE\alma-comfy\prepare_studio_assets.ps1 -Mode Prepare -Node dgx3
D:\CLAUDE\alma-comfy\prepare_studio_assets.ps1 -Mode Prepare -Node dgx4
```

The operation is idempotent. An existing wrong file, wrong symlink, mutable
revision, unknown license, package drift, or source-commit drift blocks the run;
the preparer never overwrites it or falls back to another model. Existing CUDA
environments are preserved and verified rather than modified in place. A new
LTX-2.3 download additionally requires a human license-acceptance receipt.

### Project LoRAs

The former “search Civitai and download the first popular result” behavior has
been removed. `alma_lora.py` now accepts only a per-project allowlist conforming
to `projects/lora_allowlist.schema.json`. Every enabled entry must name one
exact `.safetensors` file with a 40-hex repository revision, byte count,
SHA-256, license/commercial-use decision, compatible locked base model, and a
human approver. No Python, pickle, checkpoint bundle, or arbitrary remote code
is accepted as a project LoRA.

```powershell
python D:\CLAUDE\alma-comfy\alma_lora.py `
  --allowlist D:\path\to\film.loras.json --list
```

The checked-in example allowlist is intentionally empty; no style or character
LoRA has been silently selected for a production.

## Production order

1. Project bible and rights receipts.
2. Script, beats, shot list, and immutable shot IDs.
3. Character/environment sheets and approved keyframes.
4. Controlled image edits and image/keyframe-to-video.
5. Retakes, continuity checks, lip sync, Foley, music, and TTS.
6. OTIO edit, EXR/linear intermediates, OCIO/ACES grade.
7. 3840x2160 10-bit HDR10/PQ or HLG master plus an SDR trim.

Generating ordinary SDR diffusion frames and tagging the result as HDR is not
an accepted deliverable.

## Acceptance rule

A download PID, listener, model listing, or health response is not completion.
A lane becomes ready only after its revision and files are verified, an
ARM64/GB10 runtime creates a real artifact, the artifact opens, and its
technical and human-review checks pass.
