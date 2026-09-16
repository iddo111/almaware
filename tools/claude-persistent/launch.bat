@echo off
title Claude — Persistent
cd /d D:\CLAUDE
echo Claude — Persistent (auto-launched at logon)
echo Bridge: http://<tailnet-ip>:8765/  (A70 can paste in here)
echo.
claude --dangerously-skip-permissions
