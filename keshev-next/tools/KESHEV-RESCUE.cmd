@echo off
rem KESHEV RESCUE -- the 3 a.m. button. Double-click it when the mic is dead.
rem
rem It NEVER opens the microphone. It reads state, asks the decoders /health,
rem and repairs only what you pick from a numbered menu.
rem
rem chcp 65001 so the Hebrew renders. Every line also carries an English tag,
rem so even if the console font eats Hebrew the answer is still readable.
chcp 65001 >nul 2>&1
title KESHEV RESCUE - bedika
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set PY=C:\Program Files\Python312\python.exe
if not exist "%PY%" set PY=C:\Users\<user>\AppData\Local\Programs\Python\Python313\python.exe
if not exist "%PY%" set PY=python
"%PY%" "D:\CLAUDE\keshev-next\tools\rescue.py"
echo.
pause
