@echo off
REM ALMAWARE HUD collector — silent launcher.
REM Uses pythonw so no console window opens. Runs detached.
REM Safe/idempotent: collector.py owns a Windows singleton. This launcher never
REM kills a process, and a second launch request exits without another writer.

setlocal enableextensions
set "COL_DIR=%~dp0"
set "COL_DIR=%COL_DIR:~0,-1%"
set "COL_PY=%COL_DIR%\collector.py"

REM Prefer Python 3.13 pythonw explicitly; fall back to PATH.
set "PYW=C:\Users\<user>\AppData\Local\Programs\Python\Python313\pythonw.exe"
if not exist "%PYW%" set "PYW=pythonw.exe"

REM Launch fully detached via `start "" /B` — pythonw has no console.
start "" /B "%PYW%" "%COL_PY%" --log-level INFO

echo Collector launch requested (detached, silent, singleton-protected).
echo   Script:    %COL_PY%
echo   Log:       %COL_DIR%\collector.log
echo   Status:    D:\CLAUDE\almaware-cockpit\status.json
echo   Status:    %COL_DIR%\status.json
echo   PID file:  %COL_DIR%\collector.pid
endlocal
