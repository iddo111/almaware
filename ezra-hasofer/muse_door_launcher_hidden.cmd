@echo off
netstat -ano | findstr ":8900 " | findstr "LISTENING" >nul 2>&1
if %ERRORLEVEL%==0 goto :eof
set PYTHONIOENCODING=utf-8
powershell.exe -NoProfile -WindowStyle Hidden -Command "Start-Process -FilePath 'C:\Program Files\Python312\pythonw.exe' -ArgumentList '\"D:\CLAUDE\ezra-hasofer\muse_door.py\"' -WorkingDirectory 'D:\CLAUDE\ezra-hasofer' -WindowStyle Hidden"
