@echo off
setlocal
title EMDR Widget - Installer

echo.
echo  EMDR Widget - One-click installer
echo  ---------------------------------
echo.

set "TARGET=%LOCALAPPDATA%\EMDR_Widget"
set "STARTMENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs"
set "DESKTOP=%USERPROFILE%\Desktop"

if not exist "%TARGET%" mkdir "%TARGET%"

echo  Copying EMDR_Widget.exe to %TARGET% ...
copy /Y "%~dp0EMDR_Widget.exe" "%TARGET%\EMDR_Widget.exe" >nul
if errorlevel 1 (
    echo  ERROR: copy failed.
    pause
    exit /b 1
)

if exist "%~dp0emdr.ico" copy /Y "%~dp0emdr.ico" "%TARGET%\emdr.ico" >nul
if exist "%~dp0README.txt" copy /Y "%~dp0README.txt" "%TARGET%\README.txt" >nul

echo  Creating Start Menu shortcut ...
powershell -NoProfile -Command ^
  "$s=(New-Object -COM WScript.Shell).CreateShortcut('%STARTMENU%\EMDR Widget.lnk'); $s.TargetPath='%TARGET%\EMDR_Widget.exe'; $s.IconLocation='%TARGET%\emdr.ico'; $s.WorkingDirectory='%TARGET%'; $s.Save()"

echo  Creating Desktop shortcut ...
powershell -NoProfile -Command ^
  "$s=(New-Object -COM WScript.Shell).CreateShortcut('%DESKTOP%\EMDR Widget.lnk'); $s.TargetPath='%TARGET%\EMDR_Widget.exe'; $s.IconLocation='%TARGET%\emdr.ico'; $s.WorkingDirectory='%TARGET%'; $s.Save()"

echo.
echo  DONE. EMDR Widget is now installed.
echo   - Start Menu: "EMDR Widget"
echo   - Desktop:    "EMDR Widget"
echo.
echo  Launching now ...
start "" "%TARGET%\EMDR_Widget.exe"
timeout /t 3 >nul
exit /b 0
