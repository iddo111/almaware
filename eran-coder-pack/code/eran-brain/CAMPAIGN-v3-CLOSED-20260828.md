> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# throat-search v3 — BOOKS CLOSED, 2026-08-28 01:45 JDT

**Closed under the CORTEX-FREEZE LAW**, whose only escape is Iddo's explicit order. He
gave it (*"תעשה מה שנכון לגבי ה-BA"*, then *"אני משאיר לך את הבחירה"*), and the choice
made was to close v3 honestly rather than bump the hash and keep counting.

## Why it closed
The mouth was edited. `mouth2.py` and `fastcore.py` now let a gesture override the burst
constants, because Iddo heard what no metric had flagged: **"חסר המון פיצוץ בהתחלה"** —
his burst measured **8.4 dB against real human 23.5 and 26.3**. `ORGANS.lock` refused
every worker on the next start, exactly as designed. **The guard was right.**

## v3's final record — measured on the OLD mouth, and comparable only to itself

| | wdist |
|---|---|
| best ear-confirmed `ba` | **3.931** |
| real human `ba`, mean of 100 clips | 3.911 |
| where v3 started, 2026-08-27 morning | 4.353 (and that one was a nasal) |

`ba` classification rose **23% → 94%** across the campaign. Two fixes did it: the
**velum fence** (a nasalised /ba/ IS /ma/, and no pressure accumulates while the velum
is open, so a burst was impossible) and the **release-speed dial** (`ma` had one, `ba`
did not; 16.6 dB → 35.1 dB burst sharpness).

**Iddo never accepted 3.931.** His verdict: *"יש לו פיצוץ אבל לא שם עדיין"*. The number
reached the human band; his ear did not.

## v4 — opened the same minute
New `ORGANS.lock` built on eran2, distributed, each host's own compiled core added,
**VERIFIED on all three**. Arms restarted clean: **28 ba workers, 0 crashes, 0 refusals,
dims 34 (`ba-cv`) and 48 (`ba-free`)**. `ma-nasal` (32) and `ah-free` (45) untouched and
bit-identical — they pass no burst overrides.

**What v4 adds:** burst **gain** [1.0, 12.0] (was fixed 2.2) and burst **vent time**
[2, 20] ms (was fixed 3 ms, while tract_core's own comment says real bursts run 5–25 ms).
Also the `ba-cv` seal keyframe is fenced to 0.04, under the 0.05 threshold above which
the synth accumulates **no pressure at all** — 109 of 256 v3 candidates were leaking
there and could not burst by construction.

## ⛔ The rule this file exists to enforce
**No v4 number may be compared to 3.931.** Different instrument, different scale. v3's
archive is `run-archive-*` on each box and `ORGANS.lock.v3-CLOSED-20260828`.
