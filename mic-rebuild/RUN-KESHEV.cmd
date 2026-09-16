@echo off
title KESHEV starting...
set PY=C:\Users\<user>\AppData\Local\Programs\Python\Python313
set SP=%PY%\Lib\site-packages\nvidia
set PATH=%SP%\cublas\bin;%SP%\cudnn\bin;%SP%\cuda_runtime\bin;%SP%\cuda_nvrtc\bin;%PATH%
cd /d D:\CLAUDE\mic-rebuild
echo.
echo   KESHEV is starting.
echo   The window appears when the engine is warm (about a minute).
echo   This box closes by itself - nothing to click.
echo.
start "" "%PY%\pythonw.exe" -m client.app
powershell -NoProfile -ExecutionPolicy Bypass -File tools\wait-keshev-window.ps1
