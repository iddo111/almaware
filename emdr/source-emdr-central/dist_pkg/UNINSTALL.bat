@echo off
setlocal
title EMDR Widget - Uninstaller

set "TARGET=%LOCALAPPDATA%\EMDR_Widget"
set "STARTMENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs"
set "DESKTOP=%USERPROFILE%\Desktop"

echo  Removing shortcuts ...
if exist "%STARTMENU%\EMDR Widget.lnk" del /F /Q "%STARTMENU%\EMDR Widget.lnk"
if exist "%DESKTOP%\EMDR Widget.lnk" del /F /Q "%DESKTOP%\EMDR Widget.lnk"

echo  Removing install folder %TARGET% ...
if exist "%TARGET%" rmdir /S /Q "%TARGET%"

echo  DONE.
timeout /t 2 >nul
exit /b 0
