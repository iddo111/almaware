@echo off
rem Register KESHEV-6 to start with Windows. NOT RUN AUTOMATICALLY - Iddo runs it,
rem or tells Claude to, after he has approved the switch.
rem
rem WHY THIS EXISTS AND WHY IT MATTERS MORE THAN IT LOOKS:
rem keshev-next/app/main.py calls decoder.wait_until_ready(), which blocks FOREVER
rem by default - deliberately, because a mic listening into a server that cannot
rem answer is a shredder (see the comment in decoder.py). So if KESHEV_STT_URL
rem points at :8738 and :8738 is not running after a reboot, the mic never opens.
rem It logs "waiting for the decoder: UNREACHABLE" and waits.
rem
rem THEREFORE: switch and register TOGETHER, or do neither.
rem   1) this script          (so :8738 comes back after a reboot)
rem   2) setx KESHEV_STT_URL http://127.0.0.1:8738/v1/transcribe
rem
rem To undo: delete the shortcut this creates from the Startup folder, and
rem   setx KESHEV_STT_URL ""
setlocal
set LNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\KESHEV-6-server.lnk
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%LNK%');" ^
  "$s.TargetPath='wscript.exe';" ^
  "$s.Arguments='\"D:\CLAUDE\keshev-6\run_hidden.vbs\"';" ^
  "$s.WorkingDirectory='D:\CLAUDE\keshev-6';" ^
  "$s.Description='KESHEV-6 STT server on 127.0.0.1:8738';" ^
  "$s.Save()"
if exist "%LNK%" (
  echo OK - KESHEV-6 will start with Windows.
  echo Shortcut: "%LNK%"
) else (
  echo FAILED - the shortcut was not created. Do NOT switch KESHEV_STT_URL yet.
)
endlocal
