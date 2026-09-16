@echo off
rem KESHEV 5000 -- one click. The WINDOW owns the mic (Iddo's law 2026-08-24):
rem gui.py starts app\main.py itself, records state\mic.pid, and kills the
rem engine when the window closes. This launcher starts ONLY the window.
rem
rem History: the old version started the engine here too, with ">> trial.log".
rem That redirect held trial.log locked, gui.py then crashed on PermissionError
rem BEFORE the window opened -- the 2026-08-25 "i cant load keshev" bug.
rem One lifecycle owner now, forever. If the window ever fails, look in
rem state\gui-crash.log -- it can no longer die silently.
setlocal
set PY=C:\Program Files\Python312\python.exe
set ROOT=D:\CLAUDE\keshev-next
set PYTHONIOENCODING=utf-8
rem 2026-08-30: measured 1240 of 2252 segments thrown away as "too quiet" in one night --
rem 55% of everything Iddo said. Skipped segments had a MEDIAN peak_rms of 278 against a
rem floor of 600, so it was not silence being dropped, it was him. That is why sentences
rem arrived in fragments all night. 250 keeps the bottom quarter out and rescues ~60%.
rem 08:54 -- Iddo raised the Windows input level to 100%. Speech went from peak_rms
rem 213-382 to 17,080. The whole 'mic is broken' was a slider, not the code. With a
rem 45x stronger signal the lowered gates only let breathing through, so both are
rem back at their original values. Tunable now, so this is a number, never an edit.
rem 2026-09-03 23:12 (Iddo: 'maybe better to put keshev on one of the DGX'): the decode goes to eran1
rem FIRST (same models incl. iddo-lora, measured p50 176 ms on 08-20, GPU idle there) and the PC's own
rem :8737 is the fallback. The mic and the typer cannot move: the BRIO and his chat window live here.
rem Tonight the PC was at 100% CPU and its decoder timed out 57 times; eran1 was idle.
set KESHEV_STT_URL=http://<lan-ip>:8737/v1/transcribe
set KESHEV_STT_FALLBACK_URL=http://127.0.0.1:8737/v1/transcribe
set KESHEV_RMS_FLOOR=600
rem 2026-08-31 18:56 -- measured on the live log while Iddo said "keshev again":
rem the room hum (peak_rms ~1200, never under the 300 gate) scores voiced_ratio
rem 0.47-0.56, his real speech 0.66-0.85. At 0.40 the hum PASSED and was decoded
rem every ~4 s all day (1196 "תודה" drops). 0.60 sits between the two measured
rem bands with ~0.05 margin each side. If his quiet speech ever gets eaten,
rem lower this before touching any code.
set KESHEV_VAD_MIN=0.60
cd /d "%ROOT%"
rem 2026-09-03 VAADA-MIC: ABSOLUTE path on purpose. The old KESHEV (mic-rebuild) refuses to start
rem only if it sees "keshev-next" in a live python command line; with the relative app\gui.py the
rem window was invisible to it, and on 2026-09-02 17:40-18:23 both mics ran and typed at once.
start "" "%PY%" "%ROOT%\app\gui.py"
endlocal
