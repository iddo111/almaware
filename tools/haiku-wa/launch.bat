@echo off
title Claude - Haiku-WA
cd /d D:\CLAUDE\tools\haiku-wa
echo Claude - Haiku-WA starting...
echo  - Reads ANTHROPIC_API_KEY from env
echo  - Auth state persisted in .\auth\
echo  - Escalations go to .\inbox.jsonl (Opus reads it)
echo.
:loop
node index.js
echo.
echo === crashed/exited, restart in 5s (Ctrl+C twice to abort) ===
timeout /t 5 >nul
goto loop
