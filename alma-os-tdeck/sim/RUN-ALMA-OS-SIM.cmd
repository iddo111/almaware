@echo off
title ALMA-OS - T-Deck Simulator
REM Runs ALMA-OS against a virtual T-Deck and opens it in the browser.
REM לזכרה של עלמה ז"ל - ALMAWARE
cd /d "%~dp0"
echo.
echo   ALMA-OS T-Deck simulator  -^>  http://127.0.0.1:8864/
echo   (close this window to stop)
echo.
start "" http://127.0.0.1:8864/
python alma_web.py
pause
