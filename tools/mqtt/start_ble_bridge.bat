@echo off
REM Start the LoRa BLE ⇄ MQTT bridge.
REM Usage: start_ble_bridge.bat [BLE_ADDRESS_OR_NAME] [MQTT_HOST] [MQTT_PORT]
REM Example: start_ble_bridge.bat 8e18 localhost 1883
REM Pre-req: pair the node first via Settings -> Bluetooth -> Add device.
cd /d "%~dp0"
title LoRa BLE Bridge %1
".venv\Scripts\python.exe" ble_bridge.py %1 %2 %3
