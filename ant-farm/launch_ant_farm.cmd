@echo off
setlocal
set "ANT_FARM_ROOT=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%ANT_FARM_ROOT%start_ant_farm.ps1"

if errorlevel 1 (
  echo Ant Farm failed to start.
  pause
  exit /b 1
)
