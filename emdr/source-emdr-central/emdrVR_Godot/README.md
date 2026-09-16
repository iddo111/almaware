# EMDR VR — HTC Vive Bilateral Stimulation

A therapeutic EMDR (Eye Movement Desensitization and Reprocessing) tool for the **HTC Vive (original)** built in **Godot 4**.

Provides full bilateral stimulation:
- **Visual** — a glowing orb sweeping smoothly left ↔ right
- **Audio** — spatial tones playing from the side the orb arrives at
- **Haptic** — controller vibration in whichever hand the orb is moving towards

---

## Requirements

| Requirement | Version |
|---|---|
| Godot Engine | 4.2+ |
| Godot OpenXR plugin | bundled in Godot 4 |
| SteamVR | latest |
| HTC Vive (original) | via SteamVR |
| OS | Windows 10/11 (SteamVR requirement) |

> The original Vive does **not** support OpenXR natively — SteamVR acts as the
> OpenXR runtime. As long as SteamVR is installed and `steamvr` is set as the
> active OpenXR runtime, Godot's built-in OpenXR interface will work perfectly.

---

## Setup

### 1. Set SteamVR as OpenXR runtime (Windows)
SteamVR installs itself as the default OpenXR runtime automatically.
Verify: **Steam → Settings → OpenXR → SteamVR is the active runtime**.

### 2. Open in Godot
1. Launch **Godot 4.2+**
2. **Import** → select the `emdr_vr/` folder → **Import & Edit**
3. Let the project import all resources

### 3. Enable OpenXR in Project Settings
The `project.godot` already has `xr/openxr/enabled=true` set.
Confirm: **Project → Project Settings → XR → OpenXR → Enabled ✓**

### 4. Run
- Put on the Vive headset (or click **Play** for desktop preview mode)
- The scene initialises and waits for you to press **START**

---

## Controls

### In-headset control panel
A floating panel appears in front of you with:
- **▶ START** — begin session
- **⏸ PAUSE** — freeze orb mid-sweep
- **⏹ STOP** — end session and reset

Point either controller at the panel; pull **trigger** to click buttons.

### Controller shortcuts (no panel needed)
| Controller | Action |
|---|---|
| Right trigger | Start / Resume session |
| Left trigger | Pause session |
| Either menu button | (reserved for future use) |

### Adjustable parameters (via panel sliders)
| Parameter | Range | Default | Effect |
|---|---|---|---|
| Speed | 0.2 – 4.0 sweeps/s | 1.0 | How fast the orb moves left/right |
| Range | 0.3 – 3.0 m | 1.5 m | How far left and right the orb travels |
| Haptic | 0 – 100% | 70% | Vibration intensity at each endpoint |
| Audio volume | −24 – +6 dB | −6 dB | Bilateral tone loudness |

---

## File Structure

```
emdr_vr/
├── project.godot               ← Godot 4 project (OpenXR enabled)
├── openxr_action_map.json      ← HTC Vive controller bindings
├── scenes/
│   └── main.tscn               ← Root scene
└── scripts/
    ├── emdr_main.gd            ← Session controller, haptics, audio
    ├── emdr_orb.gd             ← Orb movement + visual effects
    ├── emdr_ui.gd              ← Floating control panel
    ├── emdr_environment.gd     ← Calm starfield environment
    └── vive_pointer.gd         ← Controller laser pointer for UI
```

---

## How Bilateral Stimulation Works

```
phase (0→1 repeating)
    │
    ▼
cos curve → smooth ease-in/ease-out position (−range → +range)
    │
    ├── reaches LEFT  → audio_left.play()  + left_ctrl.trigger_haptic_pulse()
    │                   + orb glow/scale pulse + emit reached_left signal
    │
    └── reaches RIGHT → audio_right.play() + right_ctrl.trigger_haptic_pulse()
                        + orb glow/scale pulse + emit reached_right signal
```

The orb uses a **cosine** motion curve rather than linear, giving natural
deceleration at each endpoint (same principle as smooth eye movement in EMDR).

---

## Customising Audio

The default sounds are generated procedurally (sine-wave ticks at A4/C5).
To use your own sounds:

1. Place `.ogg` or `.wav` files in `audio/`
2. Call from `emdr_main.gd`:
```gdscript
main_node.load_custom_audio("res://audio/left_tone.ogg",
                            "res://audio/right_tone.ogg")
```

Recommended: soft, short tones (50–150ms). Binaural beats or nature sounds
work well for therapeutic use.

---

## Haptic Technical Notes

HTC Vive (original) controllers support:
- Frequency: ~10 Hz – 320 Hz (sweet spot ~120–200 Hz for tactile feel)
- Amplitude: 0.0 – 1.0
- The haptic motor is a single ERM vibration motor

`trigger_haptic_pulse("haptic", frequency, amplitude, duration, delay)`

The `"haptic"` action name maps to `/user/hand/*/output/haptic` in the
OpenXR action map (`openxr_action_map.json`).

---

## Desktop Preview (No Headset)

If no OpenXR runtime is found, the app falls back to desktop mode:
- Camera is fixed; orb sweeps across the viewport
- Haptics are skipped (no controllers)
- Audio and console logging still work
- Useful for testing session logic and UI

---

## Disclaimer

This software is a **development tool** and is not a substitute for
professional EMDR therapy conducted by a licensed clinician.
EMDR can surface strong emotional responses; always use with appropriate
clinical support.
