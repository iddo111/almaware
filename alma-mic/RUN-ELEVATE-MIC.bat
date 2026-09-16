@echo off
REM Double-click me, then click YES on the UAC prompt.
REM This makes the ALMA mic run elevated so it can type into Grok.
net session >nul 2>&1
if %errorlevel% neq 0 (
  powershell -NoProfile -Command "Start-Process -FilePath 'powershell' -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File \"%~dp0ELEVATE-MIC.ps1\"' -Verb RunAs"
  exit /b
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ELEVATE-MIC.ps1"
