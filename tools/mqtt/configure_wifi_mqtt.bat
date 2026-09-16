@echo off
REM ──────────────────────────────────────────────────────────────────────────
REM  Phase 2 — flip the node firmware's built-in MQTT client on, point it at
REM  the PC's broker, and join your WiFi.  This is CONFIG ONLY — it does NOT
REM  re-flash the firmware.  Settings are written to NVS and persist reboots.
REM
REM  Usage:
REM    configure_wifi_mqtt.bat COMx WIFI_SSID WIFI_PASSWORD [MQTT_HOST]
REM
REM  Example:
REM    configure_wifi_mqtt.bat COM5 MyHomeWiFi MySecret <lan-ip>
REM
REM  Default MQTT_HOST is <lan-ip> (this PC's current LAN IP).
REM ──────────────────────────────────────────────────────────────────────────
setlocal
if "%1"=="" goto usage
if "%2"=="" goto usage
if "%3"=="" goto usage

set PORT=%1
set SSID=%2
set PSK=%3
set MQHOST=%4
if "%MQHOST%"=="" set MQHOST=<lan-ip>

echo === Configuring %PORT% — WiFi=%SSID%, MQTT=%MQHOST% ===
echo (this rewrites NVS and reboots the node — no firmware flash)
echo.

python -m meshtastic --port %PORT% ^
  --set network.wifi_enabled true ^
  --set network.wifi_ssid "%SSID%" ^
  --set network.wifi_psk  "%PSK%" ^
  --set mqtt.enabled true ^
  --set mqtt.address "%MQHOST%" ^
  --set mqtt.username "" ^
  --set mqtt.password "" ^
  --set mqtt.encryption_enabled false ^
  --set mqtt.json_enabled true ^
  --set mqtt.tls_enabled false ^
  --set mqtt.proxy_to_client_enabled false ^
  --ch-set uplink_enabled true --ch-index 0 ^
  --ch-set downlink_enabled true --ch-index 0

echo.
echo === Done. Node will reboot, join WiFi, and start publishing to MQTT. ===
echo Watch:   amqtt_sub -t "msh/#" --url mqtt://localhost:1883
exit /b 0

:usage
echo Usage: %~nx0 COMx WIFI_SSID WIFI_PASSWORD [MQTT_HOST]
echo Example: %~nx0 COM5 MyHomeWiFi MySecret <lan-ip>
exit /b 1
