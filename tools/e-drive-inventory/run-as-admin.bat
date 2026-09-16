@echo off
title Claude - E: Drive Inventory (Admin)
:: This .bat asks for UAC, then runs the read-only ext4 scan of E:
:: Output: %USERPROFILE%\Desktop\E-drive-files.txt

net session >nul 2>&1
if %errorLevel% neq 0 (
  echo Re-launching as admin...
  powershell -Command "Start-Process '%~f0' -Verb RunAs"
  exit /b
)

echo Reading E: drive (PhysicalDrive2) read-only...
echo This takes 5-15 minutes depending on file count.
echo Output: %USERPROFILE%\Desktop\E-drive-files.txt
echo.

python D:\CLAUDE\tools\e-drive-inventory\inventory.py

echo.
echo === DONE - check Desktop ===
pause
