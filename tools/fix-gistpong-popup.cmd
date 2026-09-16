@echo off
REM ============================================================
REM  Fix the every-3-minute "Clod popup" (GistPong heartbeat).
REM  Repoints the Highest-privilege task to a hidden VBS launcher
REM  so no console window ever flashes. Fully reversible.
REM  Self-elevates (one UAC click).
REM ============================================================
net session >nul 2>&1
if %errorlevel% NEQ 0 (
  powershell -NoProfile -Command "Start-Process '%~f0' -Verb RunAs"
  exit /b
)
echo Applying hidden-launcher fix to GistPongWatchdogHeartbeat...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$a = New-ScheduledTaskAction -Execute 'wscript.exe' -Argument '//nologo \"D:\CLAUDE\tools\run-hidden-gistpong-hb.vbs\"'; Set-ScheduledTask -TaskName 'GistPongWatchdogHeartbeat' -Action $a; (Get-ScheduledTask -TaskName 'GistPongWatchdogHeartbeat').Actions | ForEach-Object { Write-Host ('NOW -> ' + $_.Execute + ' ' + $_.Arguments) }"
echo.
echo Done. The 3-minute window flash should now be gone.
echo (Revert: point the task action back to powershell.exe -File ...Ensure-GistPongWatchdog.ps1)
pause
