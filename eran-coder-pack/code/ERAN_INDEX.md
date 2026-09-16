# ERAN — Master Index

Navigation aid only. Nothing was moved or deleted. All paths relative to `D:\CLAUDE`.
Generated 2026-07-08.

## Training / Live (the actual AI-child)
- `eran-live/` — **ACTIVE, main event.** Byte-LM training run, git repo, checkpoints in `backups/`, curriculum design doc, memory (`eran_longterm_memory.jsonl`), main log. Modified today (07-08); 28 files touched in last ~2 weeks.
- `eran-neuron/` — ACTIVE-ish (last touch 07-02). Neuron-principle experiment code, has README.
- `eran-grid/` — ACTIVE, lightweight. Idle-compute harvesting spec (`SPEC.md`, 07-06). Not much code yet.
- `eran-hardware/` — ACTIVE (07-06). Contains `memristor-neuron/` subproject — hardware-neuron R&D linked to Eran brain research.
- `fleet/eran_live_status.json` — small live-status file, likely written by a monitor/dashboard process.
- `GEMINI_eran_curriculum.json`, `GEMINI_eran_curriculum_design.md` — top-level curriculum design docs (Gemini-authored input for Eran's curriculum).

## Dashboards / Status / Monitoring
- `eran-dashboard/` — ACTIVE (07-03/07-04). PyInstaller-built desktop stats app (`ALMAWARE-Eran-Stats.exe`), Cloudflare `.wrangler` deploy folder, has a `.bak-precodex` backup file sitting alongside the live script.
- `eran-local-dashboard/` — ACTIVE (07-04), `server.py` — looks like a lighter local-only variant of the dashboard above. **Possible duplication with `eran-dashboard/` — worth checking if both are needed.**
- `eran-cloud/` — ACTIVE (07-06), Cloudflare Worker project (`.wrangler`, `.assetsignore`) — likely the cloud-hosted side of dashboard/status.

## Audio / Voice / Babble
- `eran-audio/` — **VERY ACTIVE** (522 files touched since 06-25). `ERAN_ARCHITECTURE_SPEC.md`, audio logs, music-player pid file. Largest live footprint outside eran-live itself.
- `archive/eran-a70-voice/`, `archive/eran-baby-voice/` — archived early voice prototypes (baby-voice has `ERAN-WORDS-FROM-IDDO.txt`).
- `archive/eran-ear/`, `archive/eran-ears/` — archived — two separate "ears" prototypes (receiver script vs. background-service .bat/.vbs version). Likely superseded by `eran-audio/`.
- `archive/eran-voice/`, `archive/eran-syllable/` — archived voice/phoneme experiments.
- `archive/eran-spark-migration/eran-audio/` — an older audio snapshot from a DGX-Spark migration attempt (archived copy, distinct from live `eran-audio/`).

## Rec Room / Playroom / Embodiment
- `eran-recroom/` — **ACTIVE** (07-08, same day). `recroom.py` — current play-space code.
- `archive/eran-nursery/`, `archive/eran-room/` — archived predecessors to recroom (nursery = earliest, room = has `eran_audio.py` + `eran_vision_state.py`).
- `archive/eran-pong/`, `archive/eran-pong-vision/` — archived Pong-based motor/vision experiments (BRIDGE docs + a gif).
- `archive/eran-cognitive-map/`, `archive/eran-third-eye/` — archived cortex-style experiments tied to the "Cognitive Map" / "Third Eye" memory projects.
- `archive/eran-eyes/`, `archive/eran-cameras/`, `archive/eran-cams-viewer/`, `archive/eran-birdscope/` — archived vision/camera input prototypes.
- `archive/eran-robot/` — `ERAN_ROBOT_BODY_BOM.md`, archived robot-body bill of materials.
- `archive/eran-little-brother/` — archived — ties to "Yigael little-brother" memory project.
- `archive/eran-vr/` — archived VR embodiment attempt; also `archive/PeopleAI/eranvr/` and `ERANVR-DESIGN.md` — a **second, separate VR prototype** under PeopleAI (possible duplicate lineage, different era).

## Mesh / Infra / Fleet Ops
- `archive/fleet-backups/eran1..eran4/` — archived node-by-node fleet backups (the 4-node mesh machines).
- `eran-connect.sh` (+ `.bak-2026-06-25`) — top-level connection script, live + one backup copy sitting side by side.
- `fix-eran2-net.sh`, `fix-eran2-net-v2.sh` — top-level network-fix scripts for the `eran2` mesh node (v2 supersedes v1; v1 is stale).
- `harden-erans.sh` — top-level hardening script across the fleet.
- `archive/_tmp/eran-*.ps1` (diagnose, feeders, kill-keeper, status, pause, unstick, follow-up, restart) — a full set of archived ops/troubleshooting scripts from an earlier "keeper" incident.
- `archive/_scratch/*eran*.ps1` — more archived one-off ops scripts (restart, unstick, find-keeper).
- `archive/_nightshift/eran_inventory.ps1` — archived inventory script (predecessor to this very task).
- `archive/_backups/eran-configs-2026-05-11/` — archived config snapshot.
- `archive/_logs/eran-dashboards/` — archived old dashboard logs.
- `archive/COORD/eran_copies/`, `archive/COORD/eran_writes/` — archived coordination-layer read/write scratch dirs.
- `archive/multichat/eran_out.json`, `archive/trainer-orchestrator/eran.out` — archived output logs from multi-agent/trainer coordination experiments.
- `archive/eran-dgx4/` — archived DGX-node-4-specific Eran setup.

## Corpus / Data / Curriculum
- `archive/corpus/eran/`, `archive/corpus/eran-gui/`, `archive/eran-corpus-v2/` — archived text corpus builds for training (v2 supersedes the plain `corpus/eran`).
- `archive/eran/` (top-level archived "eran" folder, distinct from `eran-live`) — `ERAN_DATA_UPBRINGING.md`, `ERAN_HUMAN_READING.md`, `PHONETIC_ERAN_PIPELINE.md`, ingest script + log, persona-chat script, `start_eran.cmd`. This looks like the **original pre-`eran-live` prototype** — largely superseded.
- `archive/eran-poc/` — archived but content-rich: Hebrew niqqud/prayer JSONL data, TTS/voice/web scripts, multiple design docs (soul-stack, neuromorphic brain, memristors, honesty report, one-pager). This was the proof-of-concept phase before `eran-live` went live 06-18.
- `archive/eran-console/` — archived — `ERAN.cmd` + `eran_app.py`, a console-chat interface prototype.
- `archive/eran-status/`, `archive/eran-portal/`, `archive/eran-site/`, `archive/eran-iddoperez/` — archived web/status front-ends for presenting Eran (site variants tied to iddoperez.ai).
- `archive/eran-faces/`, `archive/eran-labels/` — archived asset folders (face images / printed labels — ties to top-level `eran-label.png`, `eran_labels_preview.png`, `eran_labels_oneline_preview.png`, `_make_eran_label.py`).
- `archive/eran-music/` — archived music-generation experiment (predecessor of `eran-audio`'s music player).
- `archive/eran-movie/`, `archive/eran-movie-fixes/` — archived "Eran movie" video project + a fixes-only follow-up folder (two folders for one deliverable).
- `archive/eran-book/`, `archive/_print_ready/AI_Claude_ERAN_Book.*` — archived book manuscript + its print-ready html/pdf/manifest triplet.
- `archive/eran-master/ERAN_MASTER_VISION.md` — archived master-vision doc, likely predecessor to `project_eran_charter` (in the memory system) and `ERANS-RESUME-AFTER-SHUTDOWN.md`.
- `archive/eran-builds/`, `archive/eran-fps/`, `archive/eran-fpga-transformer/`, `archive/eran-soul/` — archived misc build/model experiments (fps = an early inference-speed model attempt; fpga-transformer = hardware transformer idea).
- `archive/_shopping_lists/eran-binah-ai-rig.md` — archived hardware shopping list for a "Binah" AI rig.
- `archive/_recordings/eran_debug_20260605_*.{m4a,mp4}` — archived debug session recordings.

## Top-level docs (not folders)
- `ERANS-RESUME-AFTER-SHUTDOWN.md` — top-level resume/recovery notes, current.
- `eran-label.png`, `eran_labels_preview.png`, `eran_labels_oneline_preview.png`, `_make_eran_label.py` — label-generation assets, active.

## Cleanup candidates (flagged only — NOT acted on)
1. **`eran-dashboard/` vs `eran-local-dashboard/`** — both are dashboard servers modified within days of each other; worth a manual check for whether one has been superseded by the other.
2. **`eran-connect.sh` + `eran-connect.sh.bak-2026-06-25`** sitting side by side at top level — if the `.bak` is confirmed stale, could be moved into `archive/` (not deleted).
3. **`fix-eran2-net.sh` vs `fix-eran2-net-v2.sh`** — v1 is likely fully superseded by v2; candidate to archive v1 only.
4. **`archive/eran-movie/` + `archive/eran-movie-fixes/`** — two folders for one deliverable; could be merged when convenient.
5. **`archive/eran-ear/` vs `archive/eran-ears/`** — near-duplicate singular/plural prototype folders; likely both superseded by live `eran-audio/`.
6. **VR duplication**: `archive/eran-vr/` vs `archive/PeopleAI/eranvr/` + `ERANVR-DESIGN.md` — two separate VR lineages under different parent folders.

## Summary counts
- Top-level active `eran-*` folders: 9 (`eran-audio`, `eran-cloud`, `eran-dashboard`, `eran-grid`, `eran-hardware`, `eran-live`, `eran-local-dashboard`, `eran-neuron`, `eran-recroom`)
- Archived `eran-*` folders under `archive/`: ~55
- Top-level loose eran-related files (scripts/docs/images): ~12
- **Total eran-related locations catalogued: ~75**
