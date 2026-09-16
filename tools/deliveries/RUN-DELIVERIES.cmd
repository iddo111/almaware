@echo off
rem המשלוחים -- the clickable page. Starts the server if it is not up, then opens it.
setlocal
set PY=C:\Program Files\Python312\pythonw.exe
tasklist /FI "IMAGENAME eq pythonw.exe" | find /I "pythonw" >nul
start "" "%PY%" "D:\CLAUDE\tools\deliveries\deliveries.py"
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8848/"
endlocal
