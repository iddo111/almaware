@echo off
REM start_mic_diamond.bat - ALMAWARE diamond always-on Hebrew mic launcher.
REM Starts the watchdog (supervisor.py), which keeps voice_input.py alive across
REM crashes. Double-click this, or let the "ALMAWARE-HebMic-Diamond" scheduled
REM task run it at logon.
REM
REM rez.ai

setlocal
set "PY=C:\Users\<user>\AppData\Local\Programs\Python\Python312\python.exe"
set "DIR=D:\CLAUDE\voice-input"

cd /d "%DIR%"

if not exist "%PY%" (
  echo [start_mic_diamond] Python not found at %PY%
  echo [start_mic_diamond] Edit PY in this .bat to point at your python.exe
  pause
  exit /b 1
)

echo [start_mic_diamond] launching diamond always-on Hebrew mic watchdog...
"%PY%" "%DIR%\supervisor.py"

REM If the supervisor itself ever returns (it shouldn't), keep the window so the
REM reason is visible instead of vanishing.
echo [start_mic_diamond] supervisor exited (rc=%errorlevel%)
pause
endlocal
