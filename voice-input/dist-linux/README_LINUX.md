# ALMAWARE Hebrew Mic — Linux distribution (`dist-linux/`)

Self-contained Linux **run + package** path for the always-on Hebrew (and
English) dictation mic. Hands-free voice-to-text that types into whatever window
you're focused on.

This folder is the packaged Linux artifact. It does **not** re-implement
anything — it drives the existing cross-platform runtime:

| Piece | File | Role on Linux |
|---|---|---|
| STT engine | `../../hebrew-voice/hebrew_stt.py` | reused as-is (CPU by default) |
| STT shim | `../transcribe.py` | reused as-is |
| Mic capture / VAD | `../mic.py` | reused as-is (pure `sounddevice`) |
| Cross-platform runtime | `../voice_input_xplat.py` | the dictation loop |
| OS input layer (type/paste/focus/undo/duck) | `../backends/linux.py` | xdotool / ydotool / wmctrl / xclip / wl-clipboard / pactl |
| Config | `../config.json` + `../config.linux.json` | shared + Linux override |
| **Launcher** | `dist-linux/run.sh` | venv setup + launch (this folder) |
| **Packager** | `dist-linux/build_appimage.sh` | optional PyInstaller / AppImage bundle |

> The Windows app (`../voice_input.py`) inlines Win32 (`SendInput`,
> `EnumWindows`, pycaw). It is untouched and **does not run here**. The Linux path
> talks only to the clean `InputBackend` contract in `../backends/base.py`.

---

## Quick start

```bash
cd voice-input/dist-linux
chmod +x run.sh
./run.sh --doctor     # diagnose helpers + session type (recommended first)
./run.sh              # first run: install deps + setup, then launch (always-on VAD)
```

First run creates `../.venv-linux`, installs Python deps, wires `hebrew_stt`
onto the venv path, downloads the STT model (~480 MB for `small`, cached after),
and launches always-on VAD. Re-run `./run.sh` any time — setup steps are skipped
once done. Quit with **Ctrl+C**.

### Flags
| Flag | Effect |
|---|---|
| `--doctor` | print environment / helper-tool diagnosis and exit (no install) |
| `--setup` | set up venv + deps + STT wiring only; don't launch |
| `--no-enter` | dictate without auto-pressing Enter |
| `--ptt` | push-to-talk (needs `keyboard` + usually root; **VAD is recommended**) |
| `--gpu` | use the CUDA requirements path (still auto-falls back to CPU) |

---

## 1. System dependencies

The Python backend **degrades gracefully** if a helper is missing (it logs a
clear line and never crashes), but for real dictation install these. `run.sh`
attempts the install for you on apt/dnf/pacman; otherwise install the
equivalents.

| Purpose | X11 | Wayland |
|---|---|---|
| typing / keystrokes | **`xdotool`** | **`ydotool`** (+ `ydotoold` daemon) |
| clipboard | `xclip` (or `xsel`) | `wl-clipboard` (`wl-copy` / `wl-paste`) |
| window list / focus | `wmctrl`, `xdotool` | *(restricted by the compositor)* |
| audio ducking | `pactl` (pulseaudio-utils) | same |
| audio decode | `ffmpeg`, `libsndfile1` | same |
| `sounddevice` build | `portaudio19-dev` | same |

**Debian / Ubuntu / Mint** (one-liner, `run.sh` runs this for you):
```bash
sudo apt install xdotool wmctrl xclip xsel ydotool wl-clipboard \
                 ffmpeg libsndfile1 pulseaudio-utils portaudio19-dev \
                 python3 python3-venv python3-pip
```
**Fedora:**
```bash
sudo dnf install xdotool wmctrl xclip xsel ydotool wl-clipboard \
                 ffmpeg-free libsndfile pulseaudio-utils portaudio-devel
```
**Arch:**
```bash
sudo pacman -S xdotool wmctrl xclip xsel ydotool wl-clipboard \
               ffmpeg libsndfile libpulse portaudio
```

Python deps (`faster-whisper`, `sounddevice`, `soundfile`, `numpy`, `pyperclip`,
`keyboard`) are installed into `../.venv-linux` by `run.sh` from
`../packaging/requirements.txt` (or `requirements-gpu.txt` with `--gpu`).

---

## 2. X11 vs Wayland — the typing injector (read this)

The single most important Linux difference is **how keystrokes get injected**.
Check your session:
```bash
echo "$XDG_SESSION_TYPE"     # -> x11   or   wayland
```

### X11 — fully supported
- **Typing:** `xdotool type` (fast, reliable Unicode → handles Hebrew/RTL).
- **Window list/focus/undo:** `wmctrl -lp` + `xdotool windowactivate`.
- **Clipboard:** `xclip` (or `xsel`). Default mode is clipboard-paste
  (`use_clipboard_paste: true`), which keeps Hebrew bursts fast.
- Nothing extra to configure beyond installing the helpers.

### Wayland — works, with one setup step + one limitation
Wayland compositors (GNOME/Mutter, KDE/KWin, Sway, …) **block synthetic input
and arbitrary window control** for security. Consequences:

1. **Typing requires `ydotool` + a running `ydotoold` daemon.** `ydotool` injects
   at the kernel `uinput` layer (works under Wayland); `xdotool` does **not**
   work on native-Wayland windows. The backend (`../backends/linux.py`) already
   prefers `ydotool` when it detects a Wayland session.
2. **Window enumeration / focus-by-name is unavailable.** `enum_windows()`
   degrades to "the active window only" and `focus_window()` is a best-effort
   no-op. The mic still dictates into the **focused** window — it just can't
   route between windows. (Window routing by app name is Windows-only anyway;
   the shipped default is `default_target: "focused"`, so day-to-day behavior is
   identical.)
3. **Clipboard:** `wl-copy` / `wl-paste` (from `wl-clipboard`).

#### Wayland setup — one-time uinput permission + daemon
```bash
# 1) allow your user to use /dev/uinput without root
sudo modprobe uinput
sudo groupadd -f input
sudo usermod -aG input "$USER"          # then LOG OUT and back in
echo 'KERNEL=="uinput", GROUP="input", MODE="0660"' | sudo tee /etc/udev/rules.d/99-uinput.rules
sudo udevadm control --reload-rules && sudo udevadm trigger

# 2) start the daemon (keep it running; add to autostart for always-on)
ydotoold &
```
`./run.sh --doctor` tells you if `ydotoold` isn't running.

> **XWayland fallback:** if a particular app runs under XWayland (many do),
> `xdotool` may still type into it; the backend tries that as a last resort. But
> for native-Wayland windows you need `ydotool` + `ydotoold`.

---

## 3. Pick your mic

Edit `../config.linux.json` → `input_device` to a substring of your mic's name,
or leave it `null` to use the configured fallbacks / system default. List
devices:
```bash
../.venv-linux/bin/python ../mic.py
```
The Linux config ships `idle_if_no_good_mic: false`, so it uses the system
default rather than going idle — but naming your mic explicitly is more reliable.

---

## 4. CPU vs GPU

- **CPU-first** (`device: "cpu"`, `cpu_model: "small"`). First run downloads the
  ~480 MB multilingual `small` model and caches it. Hebrew on `small` is usable
  (occasional homophone/spelling errors). Bump to `medium` / `large-v3` in
  `../config.linux.json` for better accuracy (slower on CPU).
- **GPU (optional):** set `"device": "cuda"` in `../config.linux.json` **and**
  run `./run.sh --gpu` (uses `requirements-gpu.txt`). Needs an NVIDIA GPU with
  CUDA 11.x/12.x + cuDNN. The engine auto-falls back to CPU if GPU load fails, so
  leaving it on `cpu` is the safe default. The premium Hebrew model and the
  dual-model language router are only practical on GPU.

---

## 5. Voice commands (same Hebrew triggers as Windows)

| Say | English alias | Effect |
|---|---|---|
| `שירי פרומפט` | claude prompt | enter **prompt mode** (accumulate) |
| `פרומפט סוף` | prompt end | send accumulated prompt + Enter |
| `שירי מהיר` | fast mode | **fast mode** (accumulate, no Enter) |
| `שירי שלח` | send fast | send the fast buffer now |
| `שירי קליפבורד` | to clipboard | next utterance → clipboard only |
| `שירי בטל` | undo that | Ctrl+Z in the focused window |
| `שירי שקט` | silent mode | toggle status-line output |
| `שירי היסטוריה` | open history | open today's transcript log |
| `שירי סוף` | stop mic | disarm (stop typing) |
| `מיקרופון` / `שירי התחל` | start mic | re-arm |
| `שירי אנגלית/עברית/אוטומטי` | — | force STT language / auto |
| `… עבור` / `… over` (at end) | — | walkie-talkie: strip it + send with Enter |

Dictation always types into the **focused** window.

---

## 6. Packaging — PyInstaller / AppImage

For a one-file or `.AppImage` distribution use the optional packager:
```bash
cd voice-input/dist-linux
chmod +x build_appimage.sh
./build_appimage.sh                # builds a PyInstaller onedir + AppImage if appimagetool is present
```
**Honest caveat:** PyInstaller-bundling `faster-whisper` / `ctranslate2`
(especially the CUDA build) is fragile and produces large (multi-hundred-MB to
multi-GB) binaries, and the STT model is still downloaded at first run. For most
users the **venv + `run.sh`** path (or the `--systemd` user service from
`../packaging/install_linux.sh`) is the recommended "install". The AppImage path
is provided for offline/kiosk distribution; verify on the real target machine.

### Always-on as a service
`../packaging/install_linux.sh --systemd` installs a `--user` systemd service and
a `.desktop` launcher. On Wayland it sets `Environment=GDK_BACKEND=x11` as a
commented hint, and you still need `ydotoold` running in the session.

---

## 7. Troubleshooting

- **Transcribes but nothing types.** X11 → install `xdotool`. Wayland → install
  `ydotool` **and** run `ydotoold` (section 2). Run `./run.sh --doctor`.
- **`import hebrew_stt` fails.** The `.pth` wiring didn't find
  `../../hebrew-voice`. Put the `hebrew-voice` folder next to `voice-input/` and
  re-run `./run.sh --setup`.
- **`sounddevice` install fails.** Install `portaudio19-dev` (Debian) /
  `portaudio-devel` (Fedora) / `portaudio` (Arch), then re-run.
- **"no good mic … IDLE".** Your mic name isn't in `fallback_devices` or is in
  `never_use_devices`. Run `../mic.py` and set `input_device` in
  `../config.linux.json`.
- **First utterance is slow.** Cold-start model load; subsequent utterances are
  fast once warm.
- **Audio ducking does nothing.** It's off by default
  (`ducking_enabled: false`). The backend can duck via `pactl` if enabled.

---

## 8. What genuinely needs the real Linux machine

Honest scope. Everything here was authored and **syntax-verified** on the dev
box, but the following can only be fully confirmed on a real Linux desktop with
a mic — none of it can be exercised on Windows:

- **Live typing on X11 (`xdotool`) and Wayland (`ydotool` + `ydotoold`)** —
  including Hebrew/RTL injection and the uinput permission flow.
- **Microphone capture / device fallback** via `sounddevice` + PortAudio against
  real ALSA / PulseAudio / PipeWire devices.
- **First-run model download + CPU (or CUDA) inference latency** on the target
  hardware.
- **AppImage** produced by `build_appimage.sh` — must be built and smoke-tested
  on Linux (PyInstaller bundling of ctranslate2 is environment-specific).
- **`pactl` ducking** against real sink-inputs (off by default regardless).

---

ALMAWARE · iddoperez.ai · לזכרה של עלמה ז"ל
