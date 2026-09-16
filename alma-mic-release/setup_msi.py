"""Almaware Voice Typer — MSI installer build (cx_Freeze bdist_msi).

Build (needs `pip install cx_Freeze` in the build env):
    python setup_msi.py bdist_msi --dist-dir dist

Privacy: ships ONLY code + config.example.json. Never config.json,
mic_debug*.log, voice_corpus/, *.bak*, caches.
"""
import sys
from cx_Freeze import setup, Executable

build_exe_options = {
    "packages": [
        "faster_whisper", "ctranslate2", "sounddevice", "numpy",
        "onnxruntime", "av", "huggingface_hub", "tokenizers", "tqdm",
    ],
    "excludes": [
        "torch", "torchaudio", "torchvision", "tensorflow", "transformers",
        "datasets", "peft", "matplotlib", "pandas", "IPython", "pytest",
        "pip", "setuptools", "cx_Freeze",
    ],
    "include_files": [
        ("config.example.json", "config.example.json"),
    ],
    "include_msvcr": True,
}

bdist_msi_options = {
    # Stable upgrade code so future MSIs upgrade in place.
    "upgrade_code": "{7A3E9B14-52C6-4D8F-9E01-AB6C0F2D7E55}",
    "add_to_path": False,
    "all_users": False,
    # Per-user, writable location: the app saves config.json next to itself.
    "initial_target_dir": r"[LocalAppDataFolder]\AlmawareVoiceTyper",
}

setup(
    name="Almaware Voice Typer",
    version="1.0.0",
    description="Almaware Voice Typer — offline voice dictation (ALMA-MIC)",
    options={"build_exe": build_exe_options, "bdist_msi": bdist_msi_options},
    executables=[
        Executable(
            "gui.py",
            base="Win32GUI",
            target_name="AlmawareVoiceTyper.exe",
            shortcut_name="Almaware Voice Typer",
            shortcut_dir="ProgramMenuFolder",
        ),
        # console sanity-check tool: transcribe a WAV without a microphone
        # (lets support verify STT works on any machine: AlmawareTranscribeFile x.wav)
        Executable(
            "transcribe_file.py",
            base=None,
            target_name="AlmawareTranscribeFile.exe",
        ),
    ],
)
