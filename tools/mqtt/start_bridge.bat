@echo off
REM Start the LoRa USB-serial ⇄ MQTT bridge.
REM Usage: start_bridge.bat [COMx] [MQTT_HOST] [MQTT_PORT]
cd /d "%~dp0"
set COMPORT=%1
if "%COMPORT%"=="" set COMPORT=COM5
set MQHOST=%2
if "%MQHOST%"=="" set MQHOST=localhost
set MQPORT=%3
if "%MQPORT%"=="" set MQPORT=1883
title LoRa Bridge %COMPORT% to %MQHOST%:%MQPORT%
".venv\Scripts\python.exe" usb_bridge.py %COMPORT% %MQHOST% %MQPORT%
