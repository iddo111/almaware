@echo off
REM Carries the sibling's alarms from eran3 into RAMCHAT, and refreshes
REM SIBLING-STATUS.txt for the morning report. Reads only; changes nothing.
set PYTHONIOENCODING=utf-8
"C:\Program Files\Python312\python.exe" "%~dp0watch_relay.py" %*
