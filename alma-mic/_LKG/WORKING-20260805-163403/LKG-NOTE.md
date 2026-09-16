# ALMA-MIC — LKG lock

Locked by Iddo's instruction, 2026-08-05: "mic working !!!! lock it as LKG".

## Verified working
- Hebrew + English dictation transcribed correctly and typed into the focused window.
- Auto-Enter sends.
- Mic selected automatically by LIVE SIGNAL, not by name.

## The four bugs this LKG fixes

1. `audio.py pick_device()` — the config `avoid` name-list was a HARD filter applied
   BEFORE probing, so a working mic was discarded on its name alone. It rejected the
   only USB mic on the machine, then the only working Bluetooth headset.
   Now: avoid is a soft demotion. Signal decides. Only true loopback devices are
   hard-blocked (they record the speakers).

2. `pipeline.py _pick_device()` — a pinned `config.mic` was honoured forever. It was
   pinned to "Microphone (USBAudio1.0)" passing 0.00001 rms (digital silence) and sat
   transcribing nothing for weeks. Now the pin is probed and falls through to auto if dead.

3. `typer.py` — typing was hard-coded to ChatGPT/Claude/Codex windows only, so every
   other window raised FocusGuardError. Now config-driven (`type_anywhere`,
   `type_targets`), and when ALMA-MIC's own window has focus it types into the LAST
   window actually dictated into instead of refusing.

4. `stt.py _auto_language()` — on a detection exception it returned None, and
   `language=None` tells Whisper "pick ANY language". That is how room noise came back
   as Icelandic and Arabic while lang_lock was ON. Now a failed detection falls back
   INSIDE the whitelist, plus a clamp before decode so no path can reopen it.

## Settings that matter
- mic: auto
- auto_enter: true
- type_anywhere: true
- speech_rms_gate: 0.012   (measured: speech ~0.19 rms, room noise 0.003-0.004;
                            the old 0.0045 gate sat ON the noise floor)
- lang_lock: true, lang_whitelist: [he, en]

## Restore
Copy every .py and config.json from this folder back over D:\CLAUDE\alma-mic\.
