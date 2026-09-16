@echo off
chcp 65001 >nul
rem ==========================================================================
rem  KESHEV 6 / קשב 6  --  one click.
rem
rem  The WINDOW owns the mic (Iddo's law 2026-08-24): app\gui6.py starts
rem  app\main.py itself, records state\mic.pid, and kills the engine when the
rem  window closes. This launcher starts ONLY the window -- never the engine.
rem  (History: the old launcher started the engine here too, with
rem  ">> trial.log". That redirect held the log locked, gui.py crashed on
rem  PermissionError BEFORE the window opened, and Iddo got "i cant load
rem  keshev" for a morning. One lifecycle owner, forever.)
rem
rem  If the window ever fails, look in state\gui6-crash.log -- it cannot die
rem  silently. Running this file again while KESHEV 6 is already open does NOT
rem  start a second window: it tells the running one to come back and show
rem  itself. That is also the way home if the badge is ever lost.
rem ==========================================================================
setlocal
set PY=C:\Program Files\Python312\python.exe
set PYW=C:\Program Files\Python312\pythonw.exe
set ROOT=D:\CLAUDE\keshev-next
set PYTHONIOENCODING=utf-8

rem --------------------------------------------------------------------------
rem  THE DECODER. 2026-09-04: RUN-KESHEV.cmd set these two INLINE, and a `set`
rem  inside a .cmd beats the user-level `setx`, so Iddo was decoding on eran1's
rem  old model all day while his own environment said :8738. That bug is why
rem  the numbers below were never actually in his hands.
rem
rem  Measured overnight on 209 of HIS OWN speech segments (see
rem  _status-reports-archive\KESHEV-6-20260904.md):
rem      :8738  13 correct project names,  CER 18.0%,  p50 202 ms,  818 MiB
rem      :8737   0 correct project names,  CER 28.5%,  p50 216 ms,  3.2 GB
rem  So :8738 WAS the primary, and it was chosen HERE rather than left to the
rem  environment, because decoder.py's own default is the PC's :8737 -- the
rem  server that timed out 57 times that night at 100% CPU.
rem
rem  ------------------------------------------------------------------------
rem  2026-09-05, 19:12 -- THE PRIMARY IS NOW eran1:8739, NOT :8738.
rem  Iddo, 18:45: "מה הבעיה לשים מודל חדש וטוב על ערן" -- and he was right.
rem  The choice had been "the good model on his own GPU" or "the old model on
rem  the DGX". It is now the GOOD MODEL ON THE DGX: eran1:8739 loads exactly
rem  the weights :8738 loaded (model.bin md5 45393d05..., int8_float16, beam 5,
rem  the same lexicon prompt and the same repair map), as the user unit
rem  keshev6-stt.service -- beside :8737, and never touching eranb-life.
rem
rem  Re-measured on the SAME 209 segments, all three servers, same audio,
rem  209/209 HTTP 200 each. Names = Chinchilla/Sonnet/OpenClaw/Hermes/psytrance
rem  counted by eye; CER on the 109 real sentences:
rem      eran1:8739  13 names,  0 garbled,  CER 18.5%,  wall p50 250 ms
rem      PC   :8738  13 names,  0 garbled,  CER 18.5%,  wall p50 375 ms
rem      eran1:8737   0 names, 14 garbled,  CER 43.0%,  wall p50 235 ms
rem  They are NOT byte-identical (170/209 same text - a beam search on GB10 is
rem  not the same search as on Ampere), so the honest test is who is closer to
rem  the reference where they DIFFER: DGX 6, PC 4, tie 99. A dead heat.
rem  Latency split honestly: the DGX decodes in 185 ms and the LAN round trip
rem  adds 57 ms. The PC's 375 ms above is its real contended number (it was
rem  serving the live mic); idle on 09-04 it was 202 ms. So the DGX is ~50 ms
rem  slower than an idle PC, ~125 ms faster than the PC he actually has.
rem  The PC's 818 MiB and its GPU contention are GONE: :8738 is now stopped and
rem  survives only as the rescue path inside tools\preflight6.py.
rem  ------------------------------------------------------------------------
rem
rem  THE FALLBACK IS eran1:8737, and that is a deliberate trade, not a default:
rem
rem   * With no fallback, ONE :8738 restart mid-session hangs the mic forever.
rem     decoder.wait_until_ready() blocks with no timeout and probes only the
rem     primary, so a dead primary means the microphone never opens -- and the
rem     window looks perfectly healthy while it doesn't. That is the worst
rem     outcome on this list.
rem   * With eran1 as the fallback, two consecutive primary failures on ONE
rem     segment silently drop him onto the measurably worse model.
rem
rem  So: keep the fallback, and REMOVE THE SILENCE. app\gui6.py reads the live
rem  decoder out of the ENGINE PROCESS'S OWN environment block, health-checks it
rem  with the server's real canary, and the moment a segment is answered by the
rem  fallback it turns the badge amber, writes "גיבוי!" on it, and raises a
rem  banner naming the server and the count. A downgrade he can see is a
rem  trade-off; a downgrade he cannot see is the bug we are fixing.
rem
rem  tools\preflight6.py decides the final URLs -- eran1:8739 first, and it
rem  starts the PC's :8738 ONLY if the DGX does not answer -- so this file
rem  states the intent and the probe states the truth.
rem --------------------------------------------------------------------------
cd /d "%ROOT%"
if exist "%ROOT%\state\keshev6-env.cmd" del "%ROOT%\state\keshev6-env.cmd"
"%PY%" -X utf8 "%ROOT%\tools\preflight6.py"
if errorlevel 1 goto :refused
if not exist "%ROOT%\state\keshev6-env.cmd" goto :refused
call "%ROOT%\state\keshev6-env.cmd"
if not defined KESHEV_STT_URL goto :refused
goto :gates

:refused
echo.
echo   המיקרופון לא נפתח - אין מפענח שעונה.
echo   The mic was NOT opened: no decoder answered. Nothing is listening.
echo.
pause
exit /b 1

:gates

rem --------------------------------------------------------------------------
rem  2026-08-30: 1240 of 2252 segments were thrown away as "too quiet" in one
rem  night -- 55%% of everything Iddo said, median peak_rms 278 against a floor
rem  of 600. Then at 08:54 he raised the Windows input level to 100%% and speech
rem  went from peak_rms 213-382 to 17,080. The whole "the mic is broken" was a
rem  slider, not the code, so both gates went back to their original values.
rem  They live here so they stay a NUMBER and never become an edit.
rem --------------------------------------------------------------------------
set KESHEV_RMS_FLOOR=600
rem  2026-08-31: the room hum (peak_rms ~1200) scores voiced_ratio 0.47-0.56 and
rem  his real speech 0.66-0.85. At 0.40 the hum passed and was decoded every ~4 s
rem  all day (1196 "תודה" drops). 0.60 sits between the two measured bands with
rem  ~0.05 margin each side. If his quiet speech ever gets eaten, LOWER THIS
rem  before touching any code.
set KESHEV_VAD_MIN=0.60

rem  2026-09-04: confidence floor on the decoder's mean logprob. The committee
rem  (MIC-HALLUCINATION-20260904.md) measured this session's 33 decodes split
rem  cleanly 33/33 with an empty gap: hallucinated junk from -0.93 to -0.42
rem  ('יאללה!', 'איי!', 'אממ'x2, 'אה...'), his real speech from -0.29 to -0.02.
rem  The old floor -0.95 let the whole junk band through. -0.40 sits in the gap:
rem  catches 9/9 of today's phantoms, drops 0 of the 24 genuine utterances
rem  (margin 0.11). If a real quiet word ever gets eaten, LOWER THIS before code.
rem  2026-09-04 18:40, MEASURED ON A LIVE HOUR (17:30-18:40, 14 real sentences,
rem  19 phantoms blocked, ZERO phantoms reached him): his real speech reached
rem  **-0.36**, not -0.29. So the margin above this floor is 0.04, not the 0.11
rem  the committee measured. Still holding, but thinner than recorded. If a real
rem  quiet word is ever eaten, LOWER this toward -0.60 before touching code.
rem  (A -0.95 floor was tried this evening and is WRONG: it sits below the whole
rem  junk band -0.93..-0.42 and lets every phantom through.)
set KESHEV_LOGPROB_FLOOR=-0.40

rem --------------------------------------------------------------------------
rem  ABSOLUTE path, on purpose, and pythonw so there is no black console box.
rem  The old KESHEV (mic-rebuild) refuses to start only if it sees the literal
rem  substring "keshev-next" in a live python command line. With a relative
rem  "app\gui6.py" this window would be invisible to it, and on 2026-09-02
rem  17:40-18:23 both mics ran and typed into his chat at once. gui6.py starts
rem  the engine with console python.exe (CREATE_NO_WINDOW) so main.py's stderr
rem  timeline still reaches trial.log.
rem --------------------------------------------------------------------------
start "" "%PYW%" "%ROOT%\app\gui6.py"
endlocal
