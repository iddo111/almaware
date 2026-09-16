@echo off
REM Kill all system LEDs via OpenRGB CLI (motherboard + GPU, skip keyboard/mouse)
REM Run this after OpenRGB is installed. Add to startup or Scheduled Task.

set OPENRGB="C:\Program Files\OpenRGB\OpenRGB.exe"
if not exist %OPENRGB% set OPENRGB="C:\Program Files (x86)\OpenRGB\OpenRGB.exe"

REM List all detected devices (run once to see device indices)
REM %OPENRGB% --list-devices

REM Set all devices to black (off)
REM --device 0 = first device, etc. Adjust if keyboard/mouse are at certain indices.
REM Using --alldevices sets everything — if keyboard/mouse should be skipped,
REM use specific device indices after running --list-devices.

%OPENRGB% --noautoconnect --alldevices --color 000000

echo LEDs off.
