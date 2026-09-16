@echo off
REM ALMA SECOND BRAIN - the door. BELOW_NORMAL so KESHEV is never starved (09-03 scar).
REM Port 8897 claimed in RAMCHAT 2026-09-11 10:04 (8895 taken, 8896 is CONTROL).
setlocal
REM Guard added 2026-09-12 so the watchdog task (every 5 min) does not spawn duplicates.
netstat -ano | findstr ":8897 " | findstr "LISTENING" >nul 2>&1
if %ERRORLEVEL%==0 goto :eof
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
cd /d "D:\CLAUDE\alma-brain2"
start "brain2" /B /BELOWNORMAL "C:\Program Files\Python312\pythonw.exe" "D:\CLAUDE\alma-brain2\brain2_server.py" >> "D:\CLAUDE\alma-brain2\state\server.log" 2>&1
endlocal
