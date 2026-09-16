@echo off
start "" "C:\Program Files\Python312\pythonw.exe" -X utf8 "D:\CLAUDE\second-brain\wiki_server.py"
timeout /t 2 >nul
start "" "http://127.0.0.1:8811/"
