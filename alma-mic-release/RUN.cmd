@echo off
rem Almaware Voice Typer — start the app. / הפעלת האפליקציה.
chcp 65001 >nul
cd /d "%~dp0"
if not exist "venv\Scripts\pythonw.exe" (
  echo Please run INSTALL.cmd first. / קודם הריצו INSTALL.cmd
  pause
  exit /b 1
)
start "" "venv\Scripts\pythonw.exe" gui.py
