@echo off
if "%~1"=="" (
  echo Usage: launch_gui ^<path-to-script.py^>
  exit /b 1
)
cmd /c start "" /B pythonw "%~1"
