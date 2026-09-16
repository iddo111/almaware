# ALMA-MIC LKG — 5 bugs fixed

1. audio.py  `avoid` was a HARD filter applied BEFORE probing → rejected working mics
   on their name. Now a soft demotion; live signal decides.
2. pipeline.py  a pinned `config.mic` was honoured forever, even pinned to a device
   passing 0.00001 rms. Now probed, falls through to auto if dead.
3. typer.py  typing was hardcoded to ChatGPT/Claude/Codex. Now config-driven, and it
   remembers the last real window when ALMA-MIC's own window has focus.
4. stt.py  on a language-detection exception it returned None, and language=None tells
   Whisper "pick ANY language" → room noise came back as Icelandic and Arabic with the
   Hebrew lock ON. Now falls back inside the whitelist + a clamp before decode.
5. typer.py `_same_target()` compared the window TITLE. A terminal running a Braille
   spinner rewrites its caption every tick, so dictation was refused mid-sentence:
      expected '⠂ security-fix-fleet-plan'  hwnd=527370 pid=3532
      actual   '⠐ security-fix-fleet-plan'  hwnd=527370 pid=3532
   Identical window. Now compares HWND + PID + exe only; the caption is decoration.

Settings: mic=auto · auto_enter=true · type_anywhere=true · speech_rms_gate=0.012
          lang_lock=true [he,en]
Restore: copy every .py and config.json here back over D:\CLAUDE\alma-mic\
