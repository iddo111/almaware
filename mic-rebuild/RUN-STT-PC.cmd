@echo off
rem KESHEV STT server on the PC GPU (RTX 3070 Ti) - Iddo's order 2026-08-20 01:00
rem ("תעביר את הפענוח לפיסי ושנה את החוקים בהתאם") - repeals no-inference-on-PC
rem for MIC DECODE ONLY. Training stays on the fleet.
set PY=C:\Users\<user>\AppData\Local\Programs\Python\Python313
set SP=%PY%\Lib\site-packages\nvidia
set PATH=%SP%\cublas\bin;%SP%\cudnn\bin;%SP%\cuda_runtime\bin;%SP%\cuda_nvrtc\bin;%PATH%
set PYTHONIOENCODING=utf-8
cd /d D:\CLAUDE\mic-rebuild
rem 2026-09-03 22:55: ABOVENORMAL so the decoder is not starved by renders on the PC
rem (57 DECODE_TIMEOUT today, all in 100%-CPU windows). Never HIGH: the mic engine is HIGH.
start "" /ABOVENORMAL /B /WAIT "%PY%\python.exe" -m server.stt_server --config server\server-pc.json >> state\stt-pc.log 2>&1
