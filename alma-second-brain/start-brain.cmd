@echo off
REM ALMA Second Brain — loopback only by design. See README before adding --host.
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
py -3.12 brain.py --port 8960 --host 127.0.0.1
