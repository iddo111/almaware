@echo off
rem =====================================================================
rem  ALMA ENHANCER launcher (100%% ALMAWARE, pure stdlib)
rem  1. makes sure the hidden RAM holder ("hold") is alive
rem  2. launches the GUI (alma_enhancer_gui.py)
rem  Relative to its own folder, so it works from any install location.
rem =====================================================================
setlocal
set "HERE=%~dp0"
pushd "%HERE%"

rem --- pick interpreter: hidden pythonw if available, else python ------
set "PYW="
for /f "delims=" %%i in ('where pythonw.exe 2^>nul') do if not defined PYW set "PYW=%%i"
if not defined PYW set "PYW=python"

rem --- ensure the holder (life-support for the RAM sections) -----------
python "%HERE%alma_enhancer.py" status >nul 2>&1
if errorlevel 2 (
    echo [ALMA] RAM sections DOWN - starting hidden holder...
    start "" /min "%PYW%" "%HERE%alma_enhancer.py" hold
    rem give it a moment to initialize the sections
    ping -n 3 127.0.0.1 >nul
)

rem --- launch the GUI ---------------------------------------------------
if exist "%HERE%alma_enhancer_gui.py" (
    start "" /min "%PYW%" "%HERE%alma_enhancer_gui.py"
) else (
    echo [ALMA] GUI not installed yet ^(alma_enhancer_gui.py missing^).
    echo [ALMA] Core status:
    python "%HERE%alma_enhancer.py" status
    pause
)

popd
endlocal
