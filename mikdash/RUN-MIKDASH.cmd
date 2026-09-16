@echo off
REM  MIKDASH - a walk through the Temple of Yechezkel 40-43.
REM  Serves the WebXR page and opens it in the default browser.
title MIKDASH
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
start "" http://127.0.0.1:8875/
echo.
echo   Desktop : http://127.0.0.1:8875/
echo   Quest   : https://<tailnet-ip>:8876/    (accept the certificate warning once)
echo.
echo   Close this window to stop the server.
echo.
python serve.py
