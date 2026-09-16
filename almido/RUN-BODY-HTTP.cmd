@echo off
REM ALMA BODY over HTTP -- the MCP endpoint a cloud model reaches through Cloudflare Access.
REM Started by the logon task ALMA-Body-HTTP. Hidden, BELOW_NORMAL, loopback only.
REM
REM It binds 127.0.0.1 ONLY. Nothing outside this machine can reach it except through the
REM cloudflared tunnel, and nothing reaches the tunnel except through Iddo's login.
REM Kill switch: create C:\Users\<user>\.iddo-harness\STOP (or state\BODY-STOP) and this
REM door refuses everything, reads included, without being restarted.
setlocal
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
cd /d "D:\CLAUDE\almido"
if not exist "workspace" mkdir "workspace"
start "" /B /BELOWNORMAL "C:\Program Files\Python312\pythonw.exe" "D:\CLAUDE\almido\almido_body_http.py" serve >> "D:\CLAUDE\almido\workspace\body-http-task.log" 2>&1
endlocal
