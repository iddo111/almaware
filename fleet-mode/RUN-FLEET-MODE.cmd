@echo off
REM ==========================================================================
REM  FLEET MODE - control what the 4 DGX are doing, from the phone, no Claude.
REM
REM  Binds 127.0.0.1:8872 and the PC's Tailscale address only. Never 0.0.0.0.
REM  BELOW_NORMAL priority: normal-priority work on this PC starves Iddo's
REM  live microphone.
REM ==========================================================================
setlocal
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set PYTHONUNBUFFERED=1
cd /d "%~dp0"

echo.
echo   FLEET MODE  -  http://127.0.0.1:8872/
echo   Tailscale address is printed below; open it on the phone.
echo.
echo   PROTECTED and untouchable: eran1/eranb-life (ERAN), eran2/eran-senses,
echo   eran4/dmidi-life (DARWISH), eran1/keshev-stt, and anything *-life*.
echo.

start "FLEET MODE" /BELOWNORMAL /WAIT python -u server.py
endlocal
