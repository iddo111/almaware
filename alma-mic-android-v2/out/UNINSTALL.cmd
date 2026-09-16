@echo off
REM Reverse of INSTALL.cmd. Removes ALMA Mic v2 entirely from the S26
REM (serial R5GL65F495X) - ALL local data (transcripts, saved server/token,
REM mic device choice, target choice) is lost with it. adb uninstall alone
REM does not touch anything else on the phone (no other app, no system setting).
adb -s R5GL65F495X uninstall com.almaware.almamic2
