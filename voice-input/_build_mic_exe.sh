#!/bin/bash
PY="C:/Users/<user>/AppData/Local/Programs/Python/Python312/python.exe"
cd /d/CLAUDE/voice-input
LOG=/d/CLAUDE/voice-input/_build_app.log
echo "BUILD START $(date +%H:%M:%S)" > "$LOG"
"$PY" -m PyInstaller --onefile --noconsole --clean --noconfirm \
  --name "Hebrew-Mic-App" \
  --icon "D:/CLAUDE/voice-input/mic.ico" \
  --distpath "D:/CLAUDE/voice-input/dist-app" \
  --workpath "D:/CLAUDE/voice-input/build-app" \
  --specpath "D:/CLAUDE/voice-input" \
  --paths "D:/CLAUDE/voice-input" --paths "D:/CLAUDE/hebrew-voice" \
  --collect-all ctranslate2 \
  --collect-submodules faster_whisper \
  --hidden-import sounddevice --hidden-import numpy --hidden-import keyboard \
  --hidden-import pyperclip --hidden-import comtypes --hidden-import pycaw \
  --hidden-import router --hidden-import transcribe --hidden-import typer \
  --hidden-import ducking --hidden-import corrector --hidden-import iqbrainz \
  --hidden-import learner --hidden-import ui_toggle --hidden-import speaker_id \
  --hidden-import hebrew_stt \
  --exclude-module torch --exclude-module torchaudio --exclude-module torchvision \
  --exclude-module tensorflow --exclude-module transformers --exclude-module matplotlib \
  --add-data "D:/CLAUDE/voice-input/config.json;." \
  voice_input.py >> "$LOG" 2>&1
RC=$?
echo "BUILD RC=$RC $(date +%H:%M:%S)" >> "$LOG"
EXE="D:/CLAUDE/voice-input/dist-app/Hebrew-Mic-App.exe"
if [ -f "$EXE" ]; then
  cp "$EXE" "/c/Users/iddo1/Desktop/Hebrew-Mic-App.exe"
  cp "$EXE" "/d/Hebrew-Mic-App.exe"
  echo "DEPLOYED $(du -m "$EXE" | cut -f1)MB -> Desktop + D:\ $(date +%H:%M:%S)" >> "$LOG"
fi
