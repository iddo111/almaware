@echo off
REM לזכרה של עלמה ז״ל
REM Qwen3-Coder-480B across eran1+eran2+eran3. Start / stop / status.
REM
REM Normally you never need this: all three units are systemd-enabled with
REM Restart=always and linger, so they come up on their own after a reboot.
REM This is the manual handle for when you want one.
title Qwen 3xDGX
setlocal

if /I "%~1"=="stop"   goto STOP
if /I "%~1"=="status" goto STATUS
goto START

:START
echo   starting RPC workers on eran2 + eran3 ...
ssh eran2 "systemctl --user start qwen-rpc"
ssh eran3 "systemctl --user start qwen-rpc"
echo   starting head on eran1 ...
ssh eran1 "systemctl --user start qwen-head"
echo.
echo   The head loads 271 GB across three nodes. This takes ~16 minutes.
echo   Until then /health answers 503 "Loading model" - that is correct, not broken.
echo.
goto STATUS

:STOP
echo   stopping head, then workers ...
ssh eran1 "systemctl --user stop qwen-head"
ssh eran2 "systemctl --user stop qwen-rpc"
ssh eran3 "systemctl --user stop qwen-rpc"
goto END

:STATUS
echo.
echo   ---- units ----
ssh eran1 "printf 'eran1 head   %%s\n' $(systemctl --user is-active qwen-head)"
ssh eran2 "printf 'eran2 worker %%s\n' $(systemctl --user is-active qwen-rpc)"
ssh eran3 "printf 'eran3 worker %%s\n' $(systemctl --user is-active qwen-rpc)"
echo.
echo   ---- ready? ----
curl -s -m 15 http://<tailnet-ip>:8080/health
echo.
echo.
echo   Web UI:  http://<tailnet-ip>:8080/
echo.

:END
endlocal
pause
