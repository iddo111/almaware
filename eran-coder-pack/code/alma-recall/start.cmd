@echo off
REM ALMA-RECALL - one search box over memory + every AI chat on this PC
title ALMA-RECALL
cd /d "%~dp0"
echo.
echo   ALMA-RECALL - indexing latest chats...
echo.
python recall.py index
echo.
echo   Opening http://127.0.0.1:8794/
start "" "http://127.0.0.1:8794/"
python recall.py serve
