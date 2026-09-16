@echo off
REM KESHEV INTAKE - the PC end of the phone microphone.
REM Iddo, 2026-09-06: "the phone as the mic is top priority - even more than the PC".
REM The phone decodes Hebrew on eran1 (keshev6 :8739) and POSTs the text here; this
REM process types it into the window he locked. Without it the phone leg is dead.
REM
REM BELOW_NORMAL on purpose: nothing on this PC may outrank his live microphone.
REM Binds loopback + this PC's Tailscale address ONLY - never 0.0.0.0.
REM Undo autostart: delete the shortcut in shell:startup ("KESHEV Intake.lnk").
cd /d "%~dp0"
start "KESHEV intake" /belownormal /min "C:\Program Files\Python312\python.exe" "%~dp0keshev_intake.py"
REM ALMA CATCH -- the safe landing place. Without a locked window the intake types
REM into whatever is in the foreground: his open Notepad file, or the desktop, where
REM auto-enter launches icons. Measured 2026-09-06. So the catch window comes up too.
start "ALMA catch" /belownormal "C:\Program Files\Python312\pythonw.exe" "%~dp0alma_catch.py"
