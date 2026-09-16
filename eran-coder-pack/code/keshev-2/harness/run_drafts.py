"""Night-1 module drafts from the 4D workers. Drafts are RAW MATERIAL:
the lead reviews, hardens, tests; kept/rejected is recorded in
WORKERS-LOG.md. This script only collects."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import fleet  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent / "drafts"
OUT.mkdir(exist_ok=True)

LINT_SPEC = """Write a single Python 3.12 stdlib-only file `tools/lint.py` for a Windows
dictation-app repo. It scans production dirs (k2/, harness/acceptance.py) with ast+re and
enforces gates. Requirements:

GATES (each a function returning list of violation strings "file:line: msg"):
G1 no-silent-except: any `except:` or `except Exception:` whose body is only `pass`/`...`/
   `continue` is a violation (ast-based).
G2 no-audio-capture: importing sounddevice, pyaudio, soundcard, winsound, playsound,
   or pygame.mixer anywhere in production code is a violation (this build must never
   open an audio device).
G3 config-writes-only-in-configstore: any production file other than k2/configstore.py
   that calls json.dump/open(...,'w') on a path containing 'config' is a violation
   (regex-based is fine, keep false positives low).
G4 no-torch: importing torch/tensorflow/jax is a violation.
G5 no-createmutex-on-rival: the string 'ALMAWARE_KESHEV_SINGLE' may appear in production
   only in k2/interlock.py, and CreateMutexW may not be called with it anywhere
   (OpenMutexW is the only legal probe of the rival's name).
G6 no-audio-output: calls to winsound.Beep/PlaySound, MessageBeep, or `print('\\a')`
   style bell characters in production code are violations (Sacred Audio law).

CLI: `python tools/lint.py` runs all gates, prints PASS/FAIL per gate, exit 0 only if all
pass. `python tools/lint.py --self-test` creates a temp file per gate containing a
violation, asserts the gate CATCHES it (a lint gate that cannot fire is not shipped),
prints per-gate self-test result, exit 0 only if every gate fired.
No third-party imports. Return ONLY the Python code, no prose, no markdown fences."""

DEVICELAW_CASES = """You are writing adversarial TEST INPUTS for a Windows dictation app's
device-law module. The law: USB wired mics ONLY; a hard-coded deny tuple blocks anything
matching (case-insensitive substring): bluetooth, hands-free, handsfree, headset,
wh-1000xm4, a2dp, hfp, airpods, stereo mix, loopback, virtual, audiorelay, sound mapper,
primary sound capture. If no allowed mic exists the app goes IDLE_NO_MIC, never falls back.
A config may ADD extra deny substrings but can never remove tuple entries.

Produce a JSON object with three arrays of realistic Windows device-name strings:
1. "must_block": 25+ names that MUST be blocked — include real-world tricky ones:
   mixed case, Hebrew device names, names where the marker is mid-string, WH-1000XM4
   variants, 'Headset (WH-1000XM4 Hands-Free AG Audio)', Bluetooth AG audio names,
   virtual cables (VB-Audio, VoiceMeeter), AirPods Pro, 'Microphone (Steam Streaming)',
   OBS virtual, NVIDIA Broadcast, Sound Mapper variants, communications-headset names.
2. "must_allow": 10+ names that MUST pass: BRIO variants ('Microphone (Logi 4K Stream
   Edition)', 'BRIO 4K Stream Edition'), Scarlett variants, generic 'Microphone (USB
   Audio Device)', a wired lav on USB card.
3. "tricky_undecided": 5+ genuinely ambiguous names with one-line reasons, e.g. a USB
   headset that is wired (contains 'headset' -> blocked by law even though wired — say so).
Return ONLY the JSON, no prose."""

DRAFTS = {
    "lint-qwen3-coder-next-fp8": ("qwen3-coder-next-fp8", LINT_SPEC, 3500),
    "devicecases-glm-4.7-flash": ("glm-4.7-flash", DEVICELAW_CASES, 2500),
}


def main() -> None:
    for name, (model, prompt, toks) in DRAFTS.items():
        print(f"--- draft {name}")
        try:
            text = fleet.ask(model, prompt, max_tokens=toks, timeout=600)
        except Exception as exc:  # noqa: BLE001
            text = f"WORKER-DOWN {type(exc).__name__}: {exc}"
        path = OUT / f"{name}.txt"
        path.write_text(text, encoding="utf-8")
        print(f"    {len(text)} chars -> {path.name}")


if __name__ == "__main__":
    main()
