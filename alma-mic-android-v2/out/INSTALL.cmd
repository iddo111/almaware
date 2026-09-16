@echo off
REM ALMA Mic v2 - install to the S26 (serial R5GL65F495X), 2026-09-06 build.
REM Piece 3 of Iddo's phone-mic order: input-device picker (incl. USB) +
REM delivery target (this phone / a locked window on the PC).
REM
REM -r = reinstall, KEEPS existing app data (transcripts, saved server/token,
REM      mic device choice, target choice). Enabling the ALMA keyboard as the
REM      active input method still needs Iddo's own tap in Settings - this
REM      script does not and must not do that for him.
adb -s R5GL65F495X install -r "%~dp0alma-mic-v2-20260906-1222.apk"
if %ERRORLEVEL% NEQ 0 (
    echo INSTALL FAILED - see adb output above.
    exit /b %ERRORLEVEL%
)
echo.
echo Installed. Verify with:
echo   adb -s R5GL65F495X shell pm list packages ^| findstr alma
echo   adb -s R5GL65F495X shell ime list -s
echo.
echo To ACTIVATE the ALMA keyboard, Iddo must still do this himself on the phone:
echo   Settings - System - Languages ^&input - On-screen keyboard - Manage keyboards - enable "ALMA"
echo   then long-press the keyboard-switch key (globe icon) - choose ALMA
echo.
echo REVERSE (uninstall this app, keeps nothing - all local transcripts/settings are lost):
echo   adb -s R5GL65F495X uninstall com.almaware.almamic2
