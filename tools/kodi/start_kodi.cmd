@echo off
REM Kodi Media Center Launcher
REM Launches Kodi from portable directory (single instance)
REM For: iddoperez.ai

setlocal enabledelayedexpansion

REM Get the directory where this script is located
set SCRIPT_DIR=%~dp0
set KODI_DIR=%SCRIPT_DIR%Kodi-portable

REM Verify Kodi executable exists
if not exist "%KODI_DIR%\kodi.exe" (
    echo ERROR: Kodi executable not found at %KODI_DIR%\kodi.exe
    echo Please extract the Kodi portable ZIP to: %KODI_DIR%
    pause
    exit /b 1
)

REM Check if Kodi is already running (single instance)
tasklist /fi "ImageName eq kodi.exe" /fo csv /nh | find /i "kodi.exe" >nul
if not errorlevel 1 (
    echo Kodi is already running. Bringing to foreground...
    REM If you want to force kill and restart, uncomment below:
    REM taskkill /im kodi.exe /f
    REM timeout /t 2 /nobreak
    REM goto LAUNCH
    exit /b 0
)

:LAUNCH
REM Launch Kodi from portable directory
echo Starting Kodi Media Center...
start "" "%KODI_DIR%\kodi.exe"

REM Wait briefly for process to start
timeout /t 3 /nobreak

REM Verify it started
tasklist /fi "ImageName eq kodi.exe" /fo csv /nh | find /i "kodi.exe" >nul
if errorlevel 1 (
    echo WARNING: Kodi may have failed to start. Check Event Viewer.
    pause
    exit /b 1
) else (
    echo SUCCESS: Kodi is now running
    echo.
    echo Web Interface: http://localhost:8090 (after Kodi fully loads)
    echo.
)

exit /b 0
