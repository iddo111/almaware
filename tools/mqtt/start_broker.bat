@echo off
REM Start the amqtt MQTT broker on 1883 (TCP) + 8080 (WebSockets)
cd /d "%~dp0"
title MQTT Broker (amqtt)
".venv\Scripts\amqtt.exe" -c broker.yaml
