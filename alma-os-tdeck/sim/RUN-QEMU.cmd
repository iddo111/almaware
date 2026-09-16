@echo off
title ALMA-OS - real firmware in QEMU
REM Boots the ACTUAL ESP32-S3 flash image in Espressif QEMU. Serial only:
REM QEMU models no ST7789 and no SX1262, so there is no picture here by design.
REM לזכרה של עלמה ז"ל - ALMAWARE
cd /d "%~dp0"
echo Rebuilding the emulator flash image from .pio\build\qemu ...
set ALMA_FW_DIR=%~dp0..\.pio\build\qemu
python build_flash.py
echo.
echo   ALMA-OS booting on a virtual ESP32-S3. Ctrl-C to stop.
echo.
tools\qemu\bin\qemu-system-xtensa.exe -machine esp32s3 -display none -serial stdio -drive file=flash.bin,if=mtd,format=raw
pause
