"""setup_py2app.py — build a double-clickable HebrewMic.app with py2app.

WHY py2app over PyInstaller on macOS: py2app produces a proper .app bundle
whose Info.plist can declare the Microphone + Accessibility usage strings macOS
requires, and the bundle (not your Terminal) becomes the entity the user grants
Privacy permissions to. That is the right packaging for an always-on dictation
agent. (PyInstaller also works and is scripted in build_pyinstaller.sh as an
alternative — it gives a CLI-style binary rather than a permissions-friendly app.)

BUILD (on a real Mac — see README_MAC.md):
    python3 -m venv .venv-build && source .venv-build/bin/activate
    pip install -r requirements-mac.txt py2app
    python setup_py2app.py py2app          # -> dist/HebrewMic.app
    # first launch will prompt for Microphone + Accessibility — approve both.

HONEST: this script is COMPLETE but UNVERIFIED — it has never been run on a Mac
(this artifact was authored on Windows). py2app data-bundling of the shared
hebrew_stt.py engine + the faster-whisper / ctranslate2 native dylibs almost
always needs a tweak pass on the target machine. Treat the first build as a
debugging session, not a one-shot. See README_MAC.md "What needs a real Mac".

לזכרה של עלמה ז״ל · ALMAWARE · iddoperez.ai
"""
import os
from setuptools import setup

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.abspath(os.path.join(HERE, ".."))
HEBREW_VOICE = os.path.abspath(os.path.join(CORE, "..", "hebrew-voice"))

# The cross-platform entry point lives in the core dir, so we point py2app at it.
APP = [os.path.join(CORE, "voice_input_xplat.py")]

# Bundle the config + the core python modules + the shared STT engine. (py2app
# follows imports, but mic/transcribe/backends are imported by name from the
# core dir, and hebrew_stt is imported via a .pth at runtime — so we add their
# folders to sys.path inside the bundle via `includes`/`packages` below and ship
# the loose files as resources for safety.)
DATA_FILES = [
    ("", [
        os.path.join(CORE, "config.json"),
        os.path.join(CORE, "config.mac.json"),
        os.path.join(CORE, "mic.py"),
        os.path.join(CORE, "transcribe.py"),
    ]),
]
if os.path.isfile(os.path.join(HEBREW_VOICE, "hebrew_stt.py")):
    DATA_FILES.append(("", [os.path.join(HEBREW_VOICE, "hebrew_stt.py")]))

OPTIONS = {
    "argv_emulation": False,
    "packages": ["faster_whisper", "ctranslate2", "sounddevice", "numpy",
                 "soundfile", "backends"],
    "includes": ["mic", "transcribe", "hebrew_stt"],
    # Keep the bundle lean — torch is NOT required by faster-whisper (CT2 backend).
    "excludes": ["torch", "tkinter", "PyQt5", "PySide6", "matplotlib"],
    "plist": {
        "CFBundleName": "HebrewMic",
        "CFBundleDisplayName": "ALMAWARE Hebrew Mic",
        "CFBundleIdentifier": "ai.iddoperez.almaware.hebrewmic",
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        "LSBackgroundOnly": False,
        "LSUIElement": True,  # menubar/agent style — no Dock icon for an always-on mic
        # ── the usage strings macOS REQUIRES for these privacy-gated APIs ──
        "NSMicrophoneUsageDescription":
            "Hebrew Mic listens to your microphone to transcribe speech into text.",
        "NSAppleEventsUsageDescription":
            "Hebrew Mic uses System Events to type the transcribed text into the "
            "focused window. Grant Accessibility access for typing to work.",
    },
}

setup(
    app=APP,
    name="HebrewMic",
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
