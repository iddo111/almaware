@echo off
REM Direct launch, no "start /B" (that pattern dies under Task Scheduler's
REM console lifetime, found 2026-09-12) and no bare console host (that's the
REM popup flash, found 2026-09-14). Wrapped by run_hidden.vbs so THIS cmd.exe
REM itself never paints a window; pythonw.exe needs no hiding, it has none.
netstat -ano | findstr "127.0.0.1:8897 " | findstr "LISTENING" >nul 2>&1
if %ERRORLEVEL%==0 goto :eof
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
cd /d "D:\CLAUDE\alma-brain2"
"C:\Program Files\Python312\pythonw.exe" "D:\CLAUDE\alma-brain2\brain2_server.py" >> "D:\CLAUDE\alma-brain2\state\server.log" 2>&1
