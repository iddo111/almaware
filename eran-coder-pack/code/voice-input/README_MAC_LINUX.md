# Always-On Hebrew Mic — macOS & Linux Port

Hands-free Hebrew (and English) dictation that types into whatever window you're
focused on. This is the **Mac/Linux port** of the Windows hebrew-mic in this
folder. It **reuses** the existing engine and capture code — nothing is
re-implemented:

| Piece | File | Status on Mac/Linux |
|---|---|---|
| STT engine | `../hebrew-voice/hebrew_stt.py` | reused as-is (CPU fallback) |
| STT shim | `transcribe.py` | reused as-is |
| Mic capture / VAD | `mic.py` | reused as-is (pure `sounddevice`) |
| Config | `config.json` + `config.mac.json` / `config.linux.json` | shared + per-OS override |
| Typing / paste / focus / undo / duck | `backends/mac.py`, `backends/linux.py` | the OS layer |
| Cross-platform runtime | `voice_input_xplat.py` | **the port** |

The Windows runtime (`voice_input.py`) inlines Win32 (ctypes `SendInput`,
`EnumWindows`, `os.startfile`, `MessageBeep`) and uses `router.py` / `typer.py` /
`ducking.py` (pycaw) — all Windows-only. `voice_input_xplat.py` talks **only** to
the clean `InputBackend` contract (`backends/base.py`), so the same dictation
loop runs on macOS (AppleScript / System Events) and Linux (xdotool/ydotool).

---

## What runs where (be honest)

- **This is a desktop app** — it needs a real Mac or Linux machine with a
  microphone and a desktop session. It does **not** run in a browser/web sandbox.
- **CPU-first.** CUDA is **optional**. On Mac there is no CUDA, so it always uses
  CPU. On Linux it defaults to CPU; set `device: "cuda"` in `config.linux.json`
  only if you have an NVIDIA GPU with CUDA libs (it auto-falls back to CPU if the
  GPU load fails).
- **Model:** the per-OS config ships `model: "small"` / `cpu_model: "small"` so
  the first run downloads a ~480 MB multilingual model and caches it. Hebrew on
  `small` is usable for dictation (occasional spelling/homophone errors). For
  better Hebrew accuracy on a capable machine bump to `medium` or `large-v3`
  (slower). The premium Hebrew model (`ivrit-ai/...-ct2`) and the dual-model
  language router need GPU to be practical — on CPU they're heavy, so the CPU
  path stays on the generic `small` model.

---

## macOS — install & run

### 1. Prerequisites
- macOS 12+ (Intel or Apple Silicon)
- `python3` (`brew install python`, or python.org)
- Optional: Homebrew (for the optional `cliclick` helper). Core dictation works
  without it via AppleScript.

### 2. Run it
```bash
cd voice-input
chmod +x run_mac.sh
./run_mac.sh
```
First run: creates `.venv-mac`, installs deps (`faster-whisper`, `sounddevice`,
`soundfile`, `numpy`, `pyperclip`), wires `hebrew_stt` onto the venv path,
downloads the model, then launches always-on VAD. Re-run `./run_mac.sh` any time
(setup steps are skipped once done).

Flags: `--setup` (set up only), `--no-enter` (don't auto-press Enter),
`--ptt` (push-to-talk; needs extra perms — VAD is recommended on Mac).

### 3. Grant permissions (REQUIRED — one time)
System Settings → **Privacy & Security**:
- **Microphone** → enable your terminal app (Terminal / iTerm / VS Code).
- **Accessibility** → enable the **same** terminal app. Without this, macOS
  silently blocks the keystrokes, so the mic transcribes but nothing gets typed.

> Tip: the app that needs the grant is the **process that launches python** —
> i.e. your terminal, not "python" itself. If you later run it from a different
> terminal, grant that one too.

### 4. Pick your mic
Edit `config.mac.json` → `input_device` to a substring of your mic's name. List
devices with:
```bash
.venv-mac/bin/python mic.py
```

---

## Linux — install & run

### 1. Prerequisites & system helpers
The Python backend degrades gracefully if a helper is missing, but for real
dictation install these. On **Debian/Ubuntu** the launcher does it for you;
otherwise install the equivalents:

| Purpose | X11 | Wayland |
|---|---|---|
| typing / keys | `xdotool` | `ydotool` (+ `ydotoold` daemon) |
| clipboard | `xclip` (or `xsel`) | `wl-clipboard` (`wl-copy`/`wl-paste`) |
| window list/focus | `wmctrl`, `xdotool` | *(restricted by compositor)* |
| audio ducking | `pactl` (pulseaudio-utils) | same |
| audio decode | `ffmpeg`, `libsndfile1` | same |
| sounddevice build | `portaudio19-dev` | same |

Debian/Ubuntu one-liner (the launcher runs this for you):
```bash
sudo apt install xdotool wmctrl xclip ydotool wl-clipboard \
                 ffmpeg libsndfile1 pulseaudio-utils portaudio19-dev \
                 python3 python3-venv python3-pip
```
Fedora: `sudo dnf install xdotool wmctrl xclip ydotool wl-clipboard ffmpeg-free libsndfile pulseaudio-utils portaudio-devel`
Arch: `sudo pacman -S xdotool wmctrl xclip ydotool wl-clipboard ffmpeg libsndfile libpulse portaudio`

### 2. Run it
```bash
cd voice-input
chmod +x run_linux.sh
./run_linux.sh
```
First run: creates `.venv-linux`, installs python deps, wires `hebrew_stt`,
downloads the model, launches always-on VAD. Flags: `--setup`, `--no-enter`,
`--ptt`.

### 3. Pick your mic
Edit `config.linux.json` → `input_device`, or list with:
```bash
.venv-linux/bin/python mic.py
```

### 4. Wayland extra step (ydotool daemon)
On Wayland, typing needs `ydotool` **and** its background daemon `ydotoold`
running with access to `/dev/uinput`:
```bash
# one-time: allow your user to use uinput without root
sudo modprobe uinput
sudo groupadd -f input
sudo usermod -aG input "$USER"     # then log out / back in
echo 'KERNEL=="uinput", GROUP="input", MODE="0660"' | sudo tee /etc/udev/rules.d/99-uinput.rules
sudo udevadm control --reload-rules && sudo udevadm trigger

# start the daemon (keep it running; add to autostart for always-on)
ydotoold &
```
Check your session type with `echo $XDG_SESSION_TYPE` (`x11` or `wayland`).

---

## Voice commands (work on both OSes)

Speak the Hebrew trigger; English aliases in parentheses:

| Say | Effect |
|---|---|
| `שירי פרומפט` (claude prompt) | enter **prompt mode** — accumulate, send on… |
| `פרומפט סוף` (prompt end) | …send the accumulated prompt + Enter |
| `שירי מהיר` (fast mode) | **fast mode** — accumulate without Enter |
| `שירי שלח` (send fast) | send the fast buffer now |
| `שירי קליפבורד` (to clipboard) | next utterance → clipboard only |
| `שירי בטל` (undo that) | undo (Ctrl+Z / Cmd+Z) in the focused window |
| `שירי שקט` (silent mode) | toggle status-line output |
| `שירי היסטוריה` (open history) | open today's transcript log |
| `שירי סוף` (stop mic) | disarm — stop typing |
| `מיקרופון` / `שירי התחל` (start mic) | re-arm |
| `שירי אנגלית` / `שירי עברית` / `שירי אוטומטי` | force STT language / auto |
| `… עבור` / `… over` (at end) | walkie-talkie: strip it + send with Enter |

Dictation always types into the **focused window** (the LKG Windows default,
`default_target: "focused"`).

---

## Known gotchas / honest limitations

- **Window routing by app name is Windows-only.** The Windows app could "switch
  to Claude/Cursor" by name (`router.py`, EnumWindows). On Mac/Linux that's not
  ported — we type into the **focused** window. Since the shipped default is
  `focused` anyway, normal use is identical. Voice "switch to <app>" is a no-op
  here; just click the window you want first.
- **macOS Accessibility is mandatory for typing.** No grant → transcribes but
  doesn't type. See step 3 above. AppleScript keystroke is also a bit slower than
  Win32 SendInput; clipboard-paste (the default) keeps Hebrew bursts fast.
- **Wayland restricts window control.** Enumerating/focusing arbitrary windows is
  blocked by the compositor for security; we type into the focused window only,
  and typing requires `ydotool` + `ydotoold` (above). **X11 is fully supported.**
- **First-utterance lag.** The model warms up at launch; the very first
  transcription after a cold start can be slow while the model loads/caches.
- **CPU speed.** On a laptop CPU, `small` transcribes a short Hebrew utterance in
  roughly real-time-ish; `medium`/`large-v3` are noticeably slower. Tune
  `model`/`cpu_model` in the per-OS config to taste.
- **PTT (push-to-talk) needs global-hotkey perms.** The `keyboard` library
  usually needs root on Linux and special grants on macOS, so **VAD (always-on)
  is the recommended mode** on both. `--ptt` falls back to VAD if `keyboard`
  isn't usable.
- **Audio ducking is off by default** (`ducking_enabled: false`). The backends
  can duck other apps (`pactl` on Linux, global volume on Mac) but it's disabled
  in the shipped config; leave it off unless you want it.
- **`hebrew-voice/` must sit next to `voice-input/`.** The launchers wire
  `import hebrew_stt` by writing a `.pth` pointing at `../hebrew-voice`. If your
  layout differs, edit `HEBREW_VOICE` at the top of the run script.

---

## Troubleshooting

- **"no good mic … IDLE"** → your mic name isn't in `fallback_devices` or is in
  `never_use_devices`. Run `mic.py` to see the exact name, then set
  `input_device` in the per-OS config. (The per-OS configs set
  `idle_if_no_good_mic: false`, so it will use the system default rather than
  going idle — but naming your mic explicitly is more reliable.)
- **Transcribes but nothing types** → macOS: grant Accessibility. Linux/X11:
  install `xdotool`. Linux/Wayland: install `ydotool` and run `ydotoold`.
- **`import hebrew_stt` fails** → the `.pth` wiring didn't find `../hebrew-voice`.
  Re-run `./run_mac.sh --setup` / `./run_linux.sh --setup` from inside
  `voice-input/`, or fix `HEBREW_VOICE` in the script.
- **`sounddevice` install fails on Linux** → install `portaudio19-dev` then
  re-run setup.

---

ALMAWARE · iddoperez.ai
