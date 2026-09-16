@echo off
REM ALMA-BRAIN — shared second brain for Claude / Qwen / gpt-oss.
REM Reads ALMA-RECALL's index. No torch, no outbound network.
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
python brain.py >> brain.log 2>&1
