@echo off
REM ===================================================================
REM  DJ ALMIDO -- put Chai's newest composition into Ableton Live.
REM
REM  Iddo: open Ableton first, then double-click this.
REM  If Ableton is not open it will tell you so and change nothing.
REM
REM  Pass anything as an argument to do a DRY RUN instead (prints the
REM  plan, opens no socket, touches nothing):   CHAI-TO-ABLETON.cmd dry
REM ===================================================================
setlocal
set PYTHONIOENCODING=utf-8
set PY="C:\Program Files\Python312\python.exe"
cd /d "%~dp0"

REM Newest .mid sitting in chai-in\ (fetch more with FETCH-CHAI.cmd).
set NEWEST=
for /f "delims=" %%F in ('dir /b /o-d "chai-in\*.mid" 2^>nul') do (
    if not defined NEWEST set NEWEST=chai-in\%%F
)

if not defined NEWEST (
    echo.
    echo No .mid files in chai-in\ -- run FETCH-CHAI.cmd first to pull
    echo Chai's latest compositions from eran4.
    echo.
    pause
    exit /b 2
)

echo Using: %NEWEST%
echo.

if "%~1"=="" (
    %PY% mid_to_live.py "%NEWEST%"
) else (
    %PY% mid_to_live.py --dry-run "%NEWEST%"
)

echo.
pause
endlocal
