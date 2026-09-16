# THROAT-SEARCH v3 — Stage A harness, PREPPED, NOT LAUNCHED (2026-08-26)

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — test the REAL output, not a proxy.

**עברית בקצרה:** מכונת החיפוש המוכחת של v1 הורכבה מחדש עם האיברים החדשים —
פה v2 (עם אף!) ואוזן v3 — על שלוש המכונות. כל בדיקות הקדם עברו (ALL_OK
בשלושתן), האף נשמע (6.9x מהרעש), הסגר נראה, והמערכת דטרמיניסטית ביט-אחד-ביט
בין המכונות. **שום worker לא הופעל — ממתינים למילה של עידו.**

## What exists (this box + eran3 + eran4, identical trees)

| file | what |
|---|---|
| `cma.py` | v1's CMA-ES, VERBATIM (md5 identical to the archive) |
| `run_worker.py` | v1's proven worker loop, organs swapped: mouth2 (C backend, parity 0.0) + ear3 (996d) + gates_v3. Refuses without ORGANS.lock verify + sanity ALL_OK. best.json now carries organ hashes, gate detail, 5-glottis-seed rescore, review flag |
| `ORGANS.lock` | ear3 spec 4a6864faab1a + carfac 4cdb95ee + patch 0001 + calib + targets-cache + per-file shas; cortex "none-v0 (Judge B pending)"; mouth2 file shas + per-host libvoc sha (all three hosts: 149e324c, byte-identical); geometry story-bunton-child-60mo. Any mismatch = refusal (CORTEX-FREEZE LAW) |
| `targets_v3.py` | REUSES ~/ear-v3/targets-cache/ear3-t06.json (spec-hash-guarded); wdist = ear3.judge convention; wrote `calib/real-clip-bars.json` |
| `gates_v3.py` | ear3-calib.json gates as-is (NOT retuned), GATE_PENALTY 50 + distance-sanity: wdist ≤ 1.3x real mean → review/ folder, never auto-celebrated (the splice lesson) |
| `arms_v3.py` | Stage A: ah-1kf/ih-1kf 16d · ba-cv 31d · **ma-nasal 32d (FIRST NASAL ARM EVER)** · ah/ba/ma-free 45d · 5 control twins. F0_LO/F0_HI=200/500 module constants — NOTE: Iddo's real abba f0 dips to 60–80 Hz and he called flat 220 "too high"; the fence may need lowering after his listen (mouth2.F0_MIN must move with it) |
| `sup.sh / launch.sh / check.sh` | v1 supervisor pattern; tmux session **throat3**; eran1 line COMMENTED OUT — "Iddo's word only" |
| `regression/v1cheat/` | the 6 archived v1 cheat wavs — permanent negative tests |
| `sanity0_v3.py` | the pre-launch suite below |

## SANITY0-V3 — ALL_OK=true on eran2, eran3, eran4 (identical numbers)

| item | result |
|---|---|
| A CMA sphere 31d | 8.5e-07 after 248 gens — PASS |
| B mouth C determinism + parity | bit-identical; C-vs-ref max\|diff\| **0.0** — PASS |
| C ORGANS.lock | VERIFIED all 3 boxes, backend=c |
| D Ear-v3 LOO | stored EAR3-ACCEPT re-asserted: 0.695 six-way ≥ 0.687; spec accept==live==cache — PASS |
| E real-clip bars | mean 3.80–3.96 per unit (the new "13.9"; DIFFERENT EAR from v1, never compare raw) |
| F gates | joint real pass .95–.97 all units; **6/6 v1 cheats CAUGHT** (1.50–1.94x mean; 2 also fail gates) |
| G **nasal audibility** | velum open vs sealed separates in the ma-vs-ba direction: **0.6545 = 6.9x** the 5-seed noise — the nose is AUDIBLE |
| H closure visibility | d(abba)−d(ah): 0.7345 → 0.0172 (toward abba); dip 0.020 → 0.987 — PASS |
| I evals/s (1 core pinned) | **eran2 16.55 · eran3 15.49 · eran4 16.80** (plan expected 9–13; measured better) |

Cross-box determinism: features sha256 for ah/abba/ma_t06_1 **bit-identical
on all three boxes** and equal to the EAR3-ACCEPT recorded prefixes. Every
sanity number identical across boxes. venvs pinned: numpy 2.5.2 / scipy
1.18.1 / jax 0.11.1 + vendored patched carfac (patch verified in each
installed copy).

## What launch WILL do (when — and only when — Iddo says go)

33 workers, 47 h deadline, tmux session `throat3`:
eran2 12 (nice 5) · eran3 13 (nice 5, run-state only — disk 84%) ·
eran4 8 (nice 10) · eran1 **0** (commented out, Iddo's word only).
At the measured ~15.5–16.8 evals/s/worker: **~510–550 evals/s fleet-wide,
~44 M evals/day** (measured on random ba-cv candidates; CMA-concentrated
populations may differ). Guided must beat its control twin AND come ≤1.3x
the real-clip bar AND pass gates AND survive Iddo's listen — else the
report says "nothing was learned" in those words.

## The one command (run all three, any order)

    ssh eran2 "cd ~/throat-search-v3 && ./launch.sh eran2"
    ssh eran3 "cd ~/throat-search-v3 && ./launch.sh eran3"
    ssh eran4@<lan-ip> "cd ~/throat-search-v3 && ./launch.sh eran4"

Stop everything: `touch ~/throat-search-v3/STOP` on each box (workers
finish their generation and exit; supervisors do not relaunch).
Progress: `./check.sh`. Review folder: `review/` — flagged would-be
winners wait for Iddo's ears there.

## Untouched, verified untouched

eran1 (the organism) · `~/eran-organs/sense_organ.py` :8830 on eran2 ·
`~/throat-search-v1-20260826/` (read-only archive; cma.py copied out,
nothing written in).
