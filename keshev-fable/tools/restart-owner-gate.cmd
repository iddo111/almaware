@echo off
title KESHEV restart - owner gate live
echo Stopping the old mic...
taskkill /F /IM python.exe /FI "WINDOWTITLE eq KESHEV*" 2>nul
for /f "tokens=2" %%p in ('wmic process where "commandline like '%%app.main%%'" get processid ^| findstr [0-9]') do taskkill /F /PID %%p 2>nul
timeout /t 2 /nobreak >nul
echo Starting KESHEV with the owner-gate (floor 0.60)...
cd /d D:\CLAUDE\keshev-fable
set KESHEV_OWNER_FLOOR=0.60
start "KESHEV" /D D:\CLAUDE\keshev-fable "C:\Program Files\Python312\python.exe" -m app.main
echo Done. The mic now types only Iddo's voice.
timeout /t 3 /nobreak >nul
