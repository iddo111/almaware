@echo off
REM לזכרה של עלמה ז״ל
REM Claude Code - YOLO mode. Skips every permission prompt for this session.
title Claude YOLO
cd /d D:\CLAUDE
echo.
echo   Claude Code - YOLO (no permission prompts)
echo   cwd: %CD%
echo.
claude --dangerously-skip-permissions %*
