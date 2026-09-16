@echo off
rem KESHEV-6 STT server on the PC GPU (RTX 3070 Ti), port 8738.
rem
rem This runs BESIDE the live :8737 - it does not replace it, does not touch it,
rem and does not open an audio device. NOT in startup: Iddo approves the switch
rem in the morning, and until he does, :8737 keeps serving the mic.
rem
rem To point the mic at this server (ONE line, no code change):
rem     setx KESHEV_STT_URL http://127.0.0.1:8738/v1/transcribe
rem To roll back:  setx KESHEV_STT_URL ""   (or delete the variable)
rem Either way the mic must be restarted to pick it up.
setlocal
set PY=C:\Users\<user>\AppData\Local\Programs\Python\Python313
set SP=%PY%\Lib\site-packages\nvidia
set PATH=%SP%\cublas\bin;%SP%\cudnn\bin;%SP%\cuda_runtime\bin;%SP%\cuda_nvrtc\bin;%PATH%
set PYTHONIOENCODING=utf-8
cd /d D:\CLAUDE\keshev-6
if not exist state mkdir state
rem 2026-09-11 -- ABOVENORMAL, NOT /HIGH. This said "the mic engine is HIGH too -
rem they are both latency work and neither starves the other on 8 cores", and
rem that was a claim, not a measurement. The engine IS HIGH (gui6.py spawns it
rem with HIGH_PRIORITY_CLASS, the 2026-09-03 19:50 starvation fix), and a CUDA
rem decoder at the SAME priority is a coin toss for the audio callback under
rem load - which is the 2026-09-03 22:43 shape: 57 decode timeouts while the PC
rem sat at 100%% CPU. Nothing on this machine outranks his microphone; the thing
rem that feeds it comes second, above everything else. One step down, on purpose.
start "" /ABOVENORMAL /B /WAIT "%PY%\python.exe" keshev6_server.py --config server-6.json >> state\keshev6.log 2>&1
endlocal
