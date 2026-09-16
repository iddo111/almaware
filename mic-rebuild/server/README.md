# KESHEV server (eran1) — K10

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

`stt_server.py` per PHASE2-DESIGN.md sections 3.1 + 6. One stdlib-HTTP file:
token auth (constant-time, EVERY endpoint), RAM-only audio, single-flight
decode + depth-2 queue (429 above), 15s decode wall (500), canary self-decode
every 300s gating the systemd watchdog pet, drain/undrain, status-line-only
logging (transcript fields are a TypeError). Language routing is
`common/langpolicy.py` — the shared truth, scar 29.

## Deploy layout on eran1 (K10 state)

```
~/keshev/
  stt_server.py  sdnotify.py  run_server.sh  server.json  VERSION
  keshev-stt.service            (also copied to ~/.config/systemd/user/)
  common/                       (protocol.py langpolicy.py decode_params.py)
  models/large-v3-turbo-ct2/    (stock: detection + EN decode)
~/keshev-spike/                 (proven K2 venv: CUDA CTranslate2 source build)
  venv/  ct2-install/  iddo-lora-run2-ct2/   README-K2-VERDICT.md
~/.config/keshev-stt/token      (64-hex, 0600)
```

RUNTIME REQUIREMENT (K2 verdict): `LD_LIBRARY_PATH` must carry
`~/keshev-spike/ct2-install/lib` and the venv's `nvidia/cudnn/lib` — baked
into BOTH `run_server.sh` and the unit file. The PyPI ctranslate2 aarch64
wheel is CPU-only; only the source build has CUDA.

## systemd unit status

`keshev-stt.service` is WRITTEN and VALIDATED (`systemd-analyze --user verify`
exit 0, zero warnings, 2026-08-12) but **NOT ENABLED** — enabling is the K11+
cutover step, after gate 19 (privacy audit) passes. For tests the server runs
under `nohup ~/keshev/run_server.sh` and is stopped afterwards.

The design's canonical `~/keshev-stt` path is adopted at cutover; K10 works
under `~/keshev` per wave guardrails.

## Verified at K10 (live LAN, 2026-08-12)

Models load 5.1s; canary 55ms; Hebrew round-trip on iddo-lora-run2-ct2:
decode 486ms / rtf 0.16 (3.1s clip, detect he p=0.995); 401s from a second
host on every endpoint; 400/413; abandon-closes-socket registered by the
server (`client_gone` counter). Port 8737 claimed in RAMCHAT. Qwen :8080
healthy before and after; server stopped clean (SIGTERM → `evt=STOPPED`).
