# Erans — Resume After Shutdown (2026-06-23 ~23:35)

Graceful shutdown for the hardware install (UPS + TL-SX1008 10GbE switch + Silent Wings 4 fans).
All 4 nodes powered off cleanly (passwordless sudo). Disks synced.

## State at shutdown (everything checkpointed)
- **gist2** (eran2, ~/gist/proto2) — step **17,330**, loss 2.77 — was on GPU 95%
- **gist3** (eran3, ~/gist/gist-pong) — step **25,040**, loss 2.56 — on GPU
- **movie render** (eran1) — **2/10** new clips done (gemara_vilna_FIX ✅ + 1). 8 remain.
- eran4 — idle.

## What auto-recovers on next boot (enabled + linger)
- `eran-gist2` on **eran2** → auto-resumes from step ~17,330
- `eran-gist3` on **eran3** → auto-resumes from step ~25,040
- `comfy.service` on **eran1** → ComfyUI server auto-starts on :8188

## What I must restart manually after boot
1. Verify nodes: `ssh eran1` … `ssh eran4`
2. Confirm trainers resumed: check `~/gist/proto2/heartbeat.json` (eran2) + `~/gist/gist-pong/heartbeat.json` (eran3) advancing
3. Confirm ComfyUI: `ssh eran1 'curl -sf http://127.0.0.1:8188/system_stats >/dev/null && echo UP'`
4. Restart movie render (skips the 2 done clips, renders the remaining 8):
   `ssh eran1 'export XDG_RUNTIME_DIR=/run/user/$(id -u); systemctl --user reset-failed eran-render 2>/dev/null; systemd-run --user --unit=eran-render --working-directory=/home/eran1/eran-movie /usr/bin/python3 -u render.py'`

## Hardware install reminder
- **UPS (APC SRV1KI-E):** connect the **yellow battery connector FIRST**. Only 3× C13 outlets — plan the load.
- **TL-SX1008** 10GbE switch — for the cluster network.
- **Silent Wings 4** 140mm fans — the cooling that lets us un-throttle the gists + render later.
