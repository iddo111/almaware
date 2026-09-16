@echo off
REM ALMA MASTER - one page over the whole fleet
title ALMA MASTER
cd /d "%~dp0"

REM keep the council RAM warm so the feed is not empty
tasklist /FI "IMAGENAME eq python.exe" /V 2>nul | find /I "ramlink.py hold" >nul
if errorlevel 1 (
  echo   starting ramlink holder...
  start "ramlink hold" /MIN /D "D:\CLAUDE\RAMCHAT" pythonw ramlink.py hold
)

echo   ALMA MASTER on http://127.0.0.1:8795/
start "" "http://127.0.0.1:8795/"
python server.py
