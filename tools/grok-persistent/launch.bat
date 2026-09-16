@echo off
title Grok - Persistent
cd /d D:\CLAUDE
echo Grok - Always-on session
echo Bridge will type into this window from your phone (clod-bridge title-matches "Grok")
echo.
:loop
"C:\Users\<user>\.grok\bin\grok.exe"
echo.
echo === Grok exited - restarting in 5s, Ctrl+C twice to kill ===
timeout /t 5 >nul
goto loop
