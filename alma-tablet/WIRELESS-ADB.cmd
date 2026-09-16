@echo off
setlocal
title ALMA - connect to the Tab A7 Lite over WiFi (no cable)
set ADB=%LOCALAPPDATA%\Microsoft\WinGet\Packages\Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe\platform-tools\adb.exe
if not exist "%ADB%" set ADB=D:\platform-tools\adb.exe

echo.
echo   WIRELESS ADB - no cable, no dongle needed
echo   ==========================================
echo.
echo   The tablet must be on the SAME WiFi as this PC.
echo.
echo   ON THE TABLET:
echo     Settings ^> Developer options ^> Wireless debugging  ^-^-^>  ON
echo     tap "Pair device with pairing code"
echo   It shows two things:  an IP:PORT   and a 6-digit CODE
echo.
echo   Note: the PAIRING port and the CONNECT port are DIFFERENT numbers.
echo   The pairing screen shows one; the main Wireless debugging screen shows
echo   the other. You need both. This trips everyone up once.
echo.

set /p PAIRADDR=  Pairing IP:PORT (from the pop-up)          :
set /p CODE=  6-digit pairing code                      :
echo.
"%ADB%" pair %PAIRADDR% %CODE%
echo.

set /p CONNADDR=  Connect IP:PORT (from the main WD screen)  :
echo.
"%ADB%" connect %CONNADDR%
echo.
echo   ---- devices now visible ----
"%ADB%" devices -l
echo.
echo   If that worked, run TABLET PROBE next.
echo.
pause
