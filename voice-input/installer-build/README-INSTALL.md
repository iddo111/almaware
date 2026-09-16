# ALMAWARE Hebrew Mic — Windows Installer

**File:** `ALMAWARE-HebrewMic-Setup.msi` (~204 KB)
**Version:** 1.0.0 — built from the LKG "translate" snapshot (git `heb-mic-lkg-2026-06-19-translate`, commit `c37b26d`)
לזכרה של עלמה ז"ל — iddoperez.ai

---

## What this installs

Double-click the `.msi`. It installs **per-user** (no admin / no UAC prompt) to:

```
%LOCALAPPDATA%\ALMAWARE\HebrewMic
```

and creates:

- a **Desktop** shortcut — "ALMAWARE Hebrew Mic"
- a **Startup** shortcut — the mic **auto-starts every time you log in** (always-on)
- a Programs-list entry so you can uninstall it from "Add or remove programs"

The shortcuts launch the mic **windowless** (no console flash) via
`wscript.exe → launch.vbs → ALMAWARE_HebMic.pyw`.

This is the **LKG TRANSLATOR** build:
- deliberate **🌐 Translate ON/OFF toggle** (defaults OFF = plain transcription)
- the old "say the word *translate* and it flips into translate mode" auto-trigger
  is **disabled** — translation now happens **only** when you click the toggle.

---

## ⚠️ IMPORTANT — the model + Python are downloaded on FIRST RUN (not bundled)

This installer is **small on purpose** (~204 KB). It contains the **app code only**.
The heavy parts — Python packages, CUDA runtime, and the Hebrew Whisper model
(several GB) — are **NOT** inside the MSI, because bundling them would make a
multi-GB installer that breaks across machines.

So the **first time you launch** the app, a one-time setup window runs and:

1. finds a system **Python 3.10–3.12** (install one from python.org if you have none),
2. creates a private virtual-env in the install folder,
3. `pip install`s the requirements
   (auto-detects an **NVIDIA GPU** via `nvidia-smi` → uses the CUDA requirements;
   otherwise CPU),
4. downloads the Hebrew Whisper model from Hugging Face
   (`ivrit-ai/whisper-large-v3-turbo-ct2` + a base multilingual model, **~2–3 GB**).

**First run therefore needs:** internet + a few minutes + (ideally) an NVIDIA GPU
with a working CUDA/cuDNN runtime for real-time speed. On CPU it works but is slow.
After the first run a `.setup_complete` marker is written and it never re-runs.

If the model pre-download fails (offline, etc.) setup still completes and the model
downloads on the first actual mic start. Logs: `…\HebrewMic\history\setup.log`.

---

## Requirements

- Windows 10/11 (64-bit)
- A microphone
- **Python 3.10–3.12** on the machine (the app builds its own venv from it)
- Internet for the one-time first-run download
- Recommended: NVIDIA GPU + CUDA for real-time transcription

## Privacy / safety

This installer ships **NO personal voice data** — no recordings, no
`samples.jsonl`, no correction history, no profile. It installs an **empty**
`profiles/default` and a generic `config.json` (mic auto-detect). Your learning
data stays only on your own machine after you use it.

## Uninstall

"Add or remove programs" → **ALMAWARE Hebrew Mic** → Uninstall.
(Verified clean: removes the install folder, both shortcuts, and the registry key.)

## Build provenance (tested)

Built with Python 3.12 `msilib` from `installer-build/build_msi.py` over the
`installer-build/payload/` tree. Verified by a full install→inspect→uninstall
cycle: 36 files install, both shortcuts created, installed `router.py` carries the
LKG "auto-translate disabled" marker and `ui_toggle.py` the Translate toggle,
uninstall leaves the system clean (0 products, dir + shortcuts removed).
