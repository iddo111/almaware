# KESHEV (קשב)

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

**KESHEV** (קשב — attentive listening) is the microphone rebuilt from scratch after the Phase-1 committee of inquiry: a thin, elevated client on the PC (capture → gate/VAD → write-ahead disk spool → one synchronous router → typer → tray) plus one killable worker subprocess that owns all decode and all network egress, talking to a token-authenticated STT server on eran1 (:8737) with a warm-resident small CT2 fallback on the PC GPU — no torch on the PC, no audio-output code path anywhere (Sacred Audio), no watchdog processes, zero words lost. The governing documents are `PHASE2-DESIGN.md` (module map, contracts, K0–K18 milestones) and `PHASE1-INQUIRY.md` (the 57-scar register + 23 acceptance criteria — law). Every milestone ends VERIFIED or BROKEN, never "should work".

**קשב** הוא המיקרופון שנבנה מחדש מאפס לפי צו עידו — "לאט, נקי, והכי טוב". המסמכים המחייבים: PHASE2-DESIGN.md (המפרט) ו-PHASE1-INQUIRY.md (פנקס הצלקות — חוק).

## Run the lint gates (K0)

```powershell
& "C:\Program Files\Python312\python.exe" tools\lint.py              # scan the repo; exit 1 on any violation
& "C:\Program Files\Python312\python.exe" tools\lint.py --self-test  # prove all 6 gates fire
```

Gates (each is a scar): G1 except-with-bare-pass · G2 `initial_prompt` · G3 `json.dump` outside `client\configstore.py` · G4 any `*.bak*` file · G5 torch import under `client\`/`common\` · G6 any audio-output call site (Sacred Audio).

## Run the tests

```powershell
& "C:\Program Files\Python312\python.exe" -m unittest discover -s tests -v
```

Stdlib only at K0 — no packages needed.

## Replay rig (offline; never opens an audio device)

```powershell
& "C:\Program Files\Python312\python.exe" tools\replay\rig.py --check   # validate manifest + clip presence
& "C:\Program Files\Python312\python.exe" tools\replay\rig.py           # run present clips through the stage chain
```

The corpus manifest (`tools\replay\manifest.json`) is git-tracked; the WAVs live locally under `tools\replay\wavs\` (git-ignored) and are imported at K8.

## Layout

`common\` shared client↔server modules · `client\` the PC thin client · `server\` the eran1 STT server · `tools\` lint, installers, drills, `replay\` rig · `tests\` test suite · `config\` git-tracked client config · `docs\` diagnosis tree · `state\` runtime (git-ignored, transcripts never enter git).

*לזכרה של עלמה ז״ל. Real, not demo. Proof, honest.*
