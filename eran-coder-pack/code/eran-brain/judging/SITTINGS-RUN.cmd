@echo off
rem ERAN sittings for Iddo - all six pages, hidden, survive a reboot (logon task ERAN-Sittings, claude-cli-FABLE 2026-09-03).
rem   8855 school (blind A/B)   8856 school2 (second sitting)   8857 judge Claude (blind grid)
rem   8858 MAKOM (his one place) 8859 hear the teacher (labelled, he presses play)
rem   8862 sitting3 (na + corpus, added claude-cli-FABLE-SITTING3 2026-09-03)
rem Launched hidden via: wscript.exe "D:\CLAUDE\run_hidden.vbs" "D:\CLAUDE\eran-brain\judging\SITTINGS-RUN.cmd"
set PYTHONIOENCODING=utf-8
for %%c in (makom-RUN.cmd hear-claude-RUN.cmd galeria-RUN.cmd school-RUN.cmd school2-RUN.cmd claude-sitting-RUN.cmd sitting3-RUN.cmd) do (
  wscript.exe "D:\CLAUDE\run_hidden.vbs" "D:\CLAUDE\eran-brain\judging\%%c"
)