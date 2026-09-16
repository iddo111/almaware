@echo off
rem Kills any running mic then starts a fresh one (elevated when run via the ALMA-MIC-Admin task)
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | Where-Object { $_.CommandLine -match 'gui.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
cd /d D:\CLAUDE\alma-mic
start "" "C:\Users\<user>\AppData\Local\Programs\Python\Python313\pythonw.exe" gui.py
