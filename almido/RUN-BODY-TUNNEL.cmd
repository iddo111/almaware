@echo off
REM ALMA BODY TUNNEL -- cloudflared, the only way in from the internet.
REM Started by the logon task ALMA-Body-Tunnel. Hidden, BELOW_NORMAL.
REM
REM The tunnel token is a SECRET and is NOT in this file and NOT in the task arguments
REM (Task Scheduler shows those to anyone who opens it). It lives in
REM   D:\CLAUDE\iddo-harness\state\body_tunnel_token.txt   (ACL'd to iddo1 alone)
REM and is read here, into a variable, one line before it is used.
REM
REM To revoke everything: delete the tunnel in the Cloudflare dashboard. To stop it here:
REM   Stop-ScheduledTask -TaskName ALMA-Body-Tunnel ; Get-Process cloudflared | Stop-Process
setlocal enabledelayedexpansion
set "TOKENFILE=D:\CLAUDE\iddo-harness\state\body_tunnel_token.txt"
set "LOG=D:\CLAUDE\almido\workspace\body-tunnel.log"
if not exist "%TOKENFILE%" (
  echo [%DATE% %TIME%] NO TUNNEL TOKEN at %TOKENFILE% -- not starting. >> "%LOG%"
  exit /b 2
)
set "TUNTOKEN="
for /f "usebackq delims=" %%T in ("%TOKENFILE%") do if not defined TUNTOKEN set "TUNTOKEN=%%T"
if not defined TUNTOKEN (
  echo [%DATE% %TIME%] TUNNEL TOKEN FILE IS EMPTY -- not starting. >> "%LOG%"
  exit /b 3
)
echo [%DATE% %TIME%] starting cloudflared for the body >> "%LOG%"
start "" /B /BELOWNORMAL "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --no-autoupdate run --token !TUNTOKEN! >> "%LOG%" 2>&1
endlocal
