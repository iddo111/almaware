@echo off
REM MUSE DOOR - tailnet-only remote access to Muse Code CLI.
setlocal
netstat -ano | findstr ":8900 " | findstr "LISTENING" >nul 2>&1
if %ERRORLEVEL%==0 goto :eof
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
cd /d "D:\CLAUDE\ezra-hasofer"
start "muse-door" /B /BELOWNORMAL "C:\Program Files\Python312\pythonw.exe" "D:\CLAUDE\ezra-hasofer\muse_door.py" >> "D:\CLAUDE\ezra-hasofer\muse_door_stdout.log" 2>&1
endlocal
