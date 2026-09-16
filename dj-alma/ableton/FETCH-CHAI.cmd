@echo off
REM ===================================================================
REM  Pull Chai the Songbird's newest compositions down from eran4.
REM
REM  Chai (darwish-midi) writes a new song roughly every 16 minutes into
REM  ~/darwish-midi/songs/outbox/ on eran4. This copies the newest few
REM  .mid files into chai-in\ so CHAI-TO-ABLETON.cmd can use them.
REM
REM  Read-only: it copies FROM eran4 and never writes anything back,
REM  never restarts dmidi-life, never touches his composing.
REM ===================================================================
setlocal
cd /d "%~dp0"
if not exist "chai-in" mkdir "chai-in"

echo Asking eran4 for Chai's newest compositions...
echo.

set FOUND=0
for /f "delims=" %%F in ('ssh eran4 "ls -t ~/darwish-midi/songs/outbox/*.mid 2>/dev/null | head -3"') do (
    echo   fetching %%~nxF
    scp -q eran4:"%%F" "chai-in\" && set FOUND=1
)

if "%FOUND%"=="0" (
    echo.
    echo Nothing fetched. Is eran4 reachable?  Try:  ssh eran4 uptime
    echo.
    pause
    exit /b 2
)

echo.
echo In chai-in\ now:
dir /b /o-d "chai-in\*.mid"
echo.
echo Next: run CHAI-TO-ABLETON.cmd  (open Ableton Live first)
echo.
pause
endlocal
