# EMDR Central

Open-source EMDR (Eye Movement Desensitization and Reprocessing) tools built for veterans and PTSD survivors.
All hardware designs, firmware, and software are free to use, build, and share.

Built by Iddo — 100% pro bono volunteer work for war veterans with PTSD.

---

## What is EMDR?

EMDR is an evidence-based psychotherapy technique for PTSD and trauma.
It uses bilateral stimulation (alternating left-right sensory input — visual, auditory, tactile)
to help the brain reprocess traumatic memories.

Normally EMDR requires expensive clinical equipment. This project makes it accessible to anyone.

---

## Projects in this repo

### 1. EMDR DIY Kit (`EMDR1_Arduino/`)

A low-cost bilateral stimulation device anyone can build at home.

**Components:**
- Arduino (any model)
- LEDs — alternating left/right visual stimulation
- Piezo buzzers — alternating left/right audio tones
- Vibration motors inside a soft physio squishy ball — tactile bilateral stimulation
- Eye/ear hairband for hands-free use
- Total parts cost: ~30-50 ILS / $10-15 USD

**Features:**
- Left/right LED alternation (pins 2 & 7)
- Simultaneous tactile vibration alternation (pins 4 & 5)
- Adjustable timing (default 1 second per side)
- All open-source — schematic, code, parts list

**Files:**
- `EMDR1_Arduino/EMDR1.ino` — Arduino firmware
- `EMDR1_Arduino/Blink.txt` — pin wiring notes

---

### 2. EMDR VR (`emdrVR_Godot/`)

A full VR therapy tool built in Godot 4 for HTC Vive.

**Features:**
- Glowing white orb sweeping smoothly left to right in 3D space
- Bilateral audio — spatial tones (A4/C5) firing from whichever side the orb reaches
- Haptic feedback — controller vibration in sync with orb position
- Floating control panel in VR — therapist adjusts speed, range, volume, haptic strength
- Works in desktop preview mode (no headset needed for testing)
- Smooth cosine motion curve — natural deceleration at endpoints, like real eye movement

**Controls:**
- Speed: 0.2–4.0 sweeps/second
- Range: 0.3–3.0 metres
- Haptic: 0–100%
- Audio volume: -24 to +6 dB

**Requirements:** Godot 4.2+, SteamVR, HTC Vive (or any OpenXR headset)

**Files:**
- `emdrVR_Godot/emdr_main.gd` — session controller, haptics, audio
- `emdrVR_Godot/emdr_orb.gd` — orb motion, visuals, signals
- `emdrVR_Godot/emdr_ui.gd` — floating VR control panel
- `emdrVR_Godot/emdr_environment.gd` — calming starfield environment
- `emdrVR_Godot/vive_pointer.gd` — controller laser pointer for UI
- `emdrVR_Godot/project.godot` — Godot 4 project file

---

### 3. EMDR Audio Resources

- `Mark Grant - Pain Control with EMDR/` — guided MP3 sessions
- `Overcome Stress and Anxiety with EMDR/` — stress management audio

---

## Roadmap

- [ ] EMDR DIY Kit v2 — ESP32 + BLE app control from phone
- [ ] Android companion app for kit control and session logging
- [ ] Remote EMDR — therapist controls patient's device over internet
- [ ] Cheaper VR option — Google Cardboard version
- [ ] Clinical trial partnership
- [ ] Full parts list + ordering guide on AliExpress

---

## License

MIT — free for personal, clinical, and research use.
If you build this, please share what you make.

---

## Contact

Built by Iddo (iddo111 on GitHub).
If you are a therapist, veteran organization, or researcher who wants to collaborate — open an issue or reach out directly.

---

## Desktop Widget — `emdr_widget.py`

Small floating always-on-top "Distress Call" button for Windows. Click it
and a white glowing orb sweeps across the screen left-right-left at ~1 Hz
for 90 seconds, with a soft beep at each edge — classic EMDR bilateral
stimulation. After 90s it collapses back to the button.

### Run
```
py -3.12 D:\NEWCLAUDE\EMDR\emdr_widget.py
```
Deps: `PyQt6` (with `QtMultimedia`). Install with `py -3.12 -m pip install PyQt6`.

### Design
- **No focus theft**: `Qt.Tool | FramelessWindowHint | WindowStaysOnTopHint | WindowDoesNotAcceptFocus`, plus `WA_ShowWithoutActivating` on the button and `WA_TransparentForMouseEvents` on the sweep overlay. Keep typing in any other app during the 90s sequence.
- **No busy loops**: single 60 FPS `QTimer`, sinusoidal orb position (cpu_temp_rule).
- **One audio source**: only a short 100ms edge beep via `QSoundEffect`. Music stays with `music_daemon.py` (one_music_rule, one_audio_rule).
- **Draggable button**: click-drag to reposition; short click triggers the sequence.

### TODO — bilateral music panning
`music_daemon.py` currently has no `set_pan` API. When added (e.g. a `pan <-1..1>` command backed by an ffmpeg `pan`/`stereotools` filter, or a VB-Cable chain), wire it into `EmdrSequence._tick` at ~10 Hz using normalized orb X `(orb_x - mid)/amp` -> pan position. Never brute-kill ffplay; always go through the daemon (vaad_hakirah_case_001_music).

### Autostart
Open `shell:startup` and drop a shortcut with target:
```
py -3.12 "D:\NEWCLAUDE\EMDR\emdr_widget.py"
```
Or a Task Scheduler task at user logon with the same command.
