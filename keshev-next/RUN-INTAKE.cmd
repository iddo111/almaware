@echo off
rem keshev-next INTAKE SIDECAR launcher.
rem Separate process from the live keshev-next mic (app\main.py) -- this
rem script never touches or restarts that process. BELOW_NORMAL priority
rem per the PC rule (nothing above BELOW_NORMAL on Iddo's machine).
setlocal
cd /d "%~dp0"
set PY=C:\Program Files\Python312\python.exe
if not exist "%PY%" set PY=python

start "KESHEV-INTAKE" /belownormal /min "%PY%" "%~dp0intake\keshev_intake.py"
endlocal
