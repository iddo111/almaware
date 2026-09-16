#!/bin/bash
LOG=/d/CLAUDE/voice-input/_build_app.log
EXE=/d/CLAUDE/voice-input/dist-app/Hebrew-Mic-App.exe
for i in $(seq 1 180); do   # up to 30 min
  if grep -q "Build complete" "$LOG" 2>/dev/null && [ -f "$EXE" ]; then
    cp "$EXE" "/c/Users/iddo1/Desktop/Hebrew-Mic-App.exe" 2>/dev/null
    cp "$EXE" "/d/Hebrew-Mic-App.exe" 2>/dev/null
    SZ=$(du -m "$EXE" | cut -f1)
    echo "BUILD DONE @ $(date +%H:%M:%S) — ${SZ}MB exe copied to Desktop + D:\\"
    exit 0
  fi
  if grep -qE "^.*ERROR:|Traceback|build FAILED" "$LOG" 2>/dev/null && ! pgrep -f "PyInstaller" >/dev/null 2>&1; then
    echo "BUILD MAY HAVE FAILED @ $(date +%H:%M:%S) — last lines:"
    tail -6 "$LOG"
    exit 1
  fi
  sleep 10
done
echo "BUILD still running after 30min — last lines:"; tail -4 "$LOG"
