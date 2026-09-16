@echo off
REM ERAN A70 room-ear audio receiver. Listens on 0.0.0.0:18190 for audio chunks
REM from the A70 phone, transcodes to 16k mono wav into heard_a70\.
REM Uses the SAME Python the mic uses, run with -s (no user site-packages).
REM Separate from dispatch-fix\pc-listener.py (18180) and the Hebrew mic.
setlocal
set PY=C:\Users\<user>\AppData\Local\Programs\Python\Python312\python.exe
cd /d D:\CLAUDE\eran-audio
"%PY%" -s "D:\CLAUDE\eran-audio\a70_receiver.py"
endlocal
