@echo off
rem ALMAWARE hidden wrapper - launched by run_hidden.vbs so no console is ever
rem shown. Task ALMA-Brain2-Maintain used to run python.exe (a console exe)
rem directly, which opens a terminal window at 04:30 every day (popup hunt
rem 2026-09-15). Edit brain2_maintain.py, not this file.
set PYTHONIOENCODING=utf-8
cd /d "D:\CLAUDE\alma-brain2"
"C:\Program Files\Python312\python.exe" D:\CLAUDE\alma-brain2\brain2_maintain.py --all --apply-proposals
