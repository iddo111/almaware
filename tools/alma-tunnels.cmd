@echo off
REM לזכרה של עלמה ז״ל
REM Opens the SSH tunnels that make the fleet's tooled web pages reachable
REM from this PC as clickable 127.0.0.1 links.
REM
REM Both daemons bind loopback ON THEIR OWN NODE on purpose - an agent that can
REM write files and run shell commands should not be listening on a LAN port.
REM The tunnel is the only door, and it closes when this window closes.
title ALMA tunnels
echo.
echo   Opening tunnels...
echo     127.0.0.1:4170  -^>  eran1  Qwen Code Web  (chat with tools)
echo     127.0.0.1:8098  -^>  eran4  Coder Harness  (write/read/test loop)
echo.
start "" /B ssh -N -L 4170:127.0.0.1:4170 -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes eran1
start "" /B ssh -N -L 8098:127.0.0.1:8098 -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes eran4
timeout /t 6 /nobreak >nul
echo   --- health ---
curl -s -m 10 http://127.0.0.1:4170/health & echo.
curl -s -m 10 http://127.0.0.1:8098/health & echo.
echo.
echo   Leave this window OPEN. Closing it closes the tunnels.
echo.
pause
