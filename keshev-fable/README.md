# 🪟 BROKEN WINDOWS LAW — חוק החלונות השבורים: if it's not working, fix it IMMEDIATELY. Test the REAL output, not a proxy.

# KESHEV-FABLE — קשב שפייבל בונה לבד

**Iddo's charter (2026-08-18 06:14, dictated live):** *"Take the knowledge and start again from
scratch. You are the builder. Only you, Fable."* Parallel to this, the four 4D workers build
their own app in `D:\CLAUDE\keshev-4d` under Fable's command — two apps, one comparison, Iddo
judges. And the standing goal above both (/goal 05:52): **"מיקרופון שלא נשבר בכלל לעולם — משהו
שעובד באמת — רק זה לבד."**

## The design bet (how this differs from KESHEV A)

A's architecture: parent app + model-worker child process (the child hosts decode plumbing).
Tonight the child died three times under the old watchdog and once by my hand — the parent
healed it each time, but **the child exists mostly to isolate a local model we no longer use**:
real decode happens on eran1:8737 over HTTP.

**KESHEV-FABLE bet: no child process at all.** One process, one thread per concern, decode is
a pure HTTP call with a deadline. What does not exist cannot die:
- no worker process → no WORKER_DIED, no respawn logic, no generation counter;
- no local model → no load-lifecycle scars (A's law #1: every catastrophic outage was a load event);
- the only stateful resources are the capture stream and the spool directory.

Self-healing moves to the *edges*: the capture thread reopens the device on error with backoff;
the decode call retries once then parks the record in the spool (never lost); the typer verifies
focus per burst. A single supervisor thread owns the health verdict and journals HEARTBEAT.

## Inherited law (binding, not advisory)

- `D:\CLAUDE\mic-rebuild\INSIGHTS-FOR-KESHEV2.md` — the 12 laws, the 5 dead-guard species,
  the acceptance baseline (§7) this app must beat.
- `D:\CLAUDE\keshev-2\DECISIONS.md` — the 9 rulings (armed-mode default OFF, presence
  120/600/900, interlock fail-closed…).
- `D:\CLAUDE\keshev-4d\ADDENDUM-20260818.md` — tonight's scars (watchdog v2 verdict law,
  no-bash, no-pythonw-http, reboot survival, training gatekeeper).
- **ONE-MIC LAW:** this app opens NO audio device while KESHEV A holds the mic. All development
  and tests run on WAV fixtures. Cutover only after beating A's baseline, by Iddo's hand.

## Modules (build order)

| # | module | question it answers | state |
|---|---|---|---|
| 1 | `app/journal.py` | what happened, one honest line per fact | ✅ tests green |
| 2 | `app/lawbook.py` | which device MAY open (USB-only, `_NEVER_MIC`) | ✅ tests green |
| 3 | `app/spool.py` | how speech survives every crash (write-ahead, O(new) sweep) | ✅ tests green |
| 4 | `app/gates.py` | is it speech worth the GPU (reachable floor, None-lang unrepresentable) | ✅ tests green |
| 5 | `app/stt.py` | eran1:8737 client, deadline, late-reply discipline | ✅ tests green |
| 6 | `app/presence.py` | is Iddo THERE (type/Enter split, arm switch, expiry) | ✅ tests green |
| 7 | `app/typer.py` | text into HIS window only (gates inside the door) | ✅ tests green |
| 8 | `app/router.py` | the pipeline: spool → gates → stt → typer, retry-then-park | ✅ tests green |
| 9 | `app/capture.py` | frames off the BRIO (interlock fails closed, healing loop) | ✅ tests green |
| 10 | `app/supervisor.py` | the health verdict, in-process (watchdog v2 law) | ✅ tests green |
| 11 | `app/segmenter.py` | where speech starts/ends (hang excluded, blips=None) | ✅ tests green |
| 12 | `app/main.py` | assembly; kernel mutex; ONE-MIC refusal at the door | ✅ parses, wired |
| 13 | `tools/lint.py` | the 6 laws as grep + poison self-test | ✅ 6/6 + self-test |

**Measured (07:00, real eran1:8737, no audio device):** 5/5 canaries word-for-word,
14/14 rare words, p50 349 ms via this repo's own SttClient (A baseline 407 ms).
**Cutover checklist (Iddo's hand only):** stop A → `python -m app.main` → live
dictation day (criterion 16) → keep or roll back.

*לזכרה של עלמה ז״ל. Real, not demo. Proof, honest.*
