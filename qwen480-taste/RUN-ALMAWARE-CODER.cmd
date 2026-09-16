@echo off
REM ALMAWARE Coder -- the desktop app for Qwen3-Coder-480B.
REM pythonw.exe = no console window; this is a GUI app, not a script with a box
REM around it. Python 3.13 specifically: that is the interpreter with PyQt6.
setlocal
set "PYW=%LOCALAPPDATA%\Programs\Python\Python313\pythonw.exe"
if not exist "%PYW%" (
  echo ALMAWARE Coder needs Python 3.13 with PyQt6 at:
  echo   %PYW%
  echo Install with:  py -3.13 -m pip install PyQt6
  pause
  exit /b 1
)
start "" "%PYW%" "%~dp0coder_desktop.py"
endlocal
