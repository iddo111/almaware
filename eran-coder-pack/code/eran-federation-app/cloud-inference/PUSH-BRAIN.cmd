@echo off
REM ERAN brain push: eran1 (the living organism) -> federation.iddoperez.ai KV.
REM Fired every 10 minutes by the ERAN-Brain-Push scheduled task, through
REM run_hidden.vbs so no console ever flashes at Iddo.
REM --if-changed: KV free tier allows 1,000 writes/day; 10 min = <=144 max.
setlocal
set PYTHONIOENCODING=utf-8
cd /d "D:\CLAUDE\eran-federation-app\cloud-inference"

REM keep the log from growing forever (truncate past ~1 MB)
for %%A in ("push-brain.log") do if %%~zA GTR 1000000 del "push-brain.log"

"C:\Program Files\Python312\python.exe" push_brain.py --host eran1 --if-changed >> "push-brain.log" 2>&1
endlocal
