> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# THROAT SEARCH — 48h articulatory search for /ba/ and /abba/ (launched 2026-08-25 02:19 UTC+3)

**חיפוש הגרון — 48 שעות על הצי, לקראת "אבא".** עידו הורה (02:00): "lets use them for the throat search and do a thorough job — take your time — even 48 hours search."

## What is running / מה רץ

A population search (CMA-ES with restarts) over **time-varying vocal-tract trajectories** —
keyframes over the 34 Kelly-Lochbaum tube areas, rendered by the verbatim `mouth34.say_sequence`
(the moving tube, ladder state carried through the closure, never a splice) — judged by an
**EXTENDED copy of ERAN's own frozen ear**: the 192 frozen cochlea dims, bit-identical to
`body/ears.py`, plus **8 appended log-RMS energy-contour numbers** sliced over the same speech
span. Targets are **Iddo's own recorded voice only** (t06 corpus: 100 real takes each of
/ah/, /ba/, /abba/, /ima/, /ih(×100)/, /ma/ — 657 clips, found at `~/eran-cortex/data/t06` on eran2).
No TTS, no synthetic clip, anywhere.

The frozen anatomy is untouched: this judge lives only in `~/throat-search/` (a separate copy on
each box), the live organs (`eranb-life` on eran1, `eran-senses` on eran2, `dmidi-*` on eran4)
were never modified or restarted, and **eran1 runs no search worker at all**.

## Where / איפה

| box | workers | nice | arms | measured before launch | measured after launch |
|---|---|---|---|---|---|
| eran2 | **12** | 5 | ba:0-3, abba:0-3, abba-free:0-1, control-ba:0, control-abba:0 | 115G avail, 20 cores, load 0.12 | load ~6-12/20, RSS ~110 MB/worker, 114G still avail |
| eran3 | **13** | 5 | ba:4-7, abba:4-7, abba-free:2-4, control-ba:1, control-abba:1 | 115G avail, load 0.29, disk 84% (573G free) | 13 procs up, 114G avail |
| eran4 | **8** | **10** | ba:8-9, abba:8-10, abba-free:5-6, control-abba:2 | 99G avail, load 0.03, Darwish untouched | 8 procs up at nice 10, 99G avail |
| eran1 | **0** | — | ERAN HIMSELF. Look, don't load. | — | — |

**33 workers total.** Each is a single-threaded process (`OMP_NUM_THREADS=1`), ~110 MB RSS,
~27 evals/sec (verbatim reference renderer, 36 ms per candidate + 0.5 ms ear). Every box keeps
≥35% of its cores and >90 GB RAM free. Deadline: **47 h** from launch (exit code 99), so it ends
before the 48h word. Disk footprint per worker: heartbeat.jsonl (rotated at 4 MB), best.json,
best.wav (~20 KB), state.json — eran3's 84%-full disk gains only a few MB.

### Capacity numbers (Iddo asked "how many can we run comfortably")
Per worker measured: **~110 MB RSS, 1 core, ~27 evals/s.** A GB10 box could comfortably hold
~14 such workers (70% of cores) and >500 of them by RAM alone — CPU is the binding constraint,
RAM is nearly irrelevant for this workload. Chosen: 12/13/8 to honor the live organs.

## The arms / הזרועות

- **ba** (37 dims): 34 vowel areas + closure-length + vowel-length + closure-area.
  Keyframes: lips-closed → vowel. Stage 1: one closure + one vowel = /ba/.
- **abba** (38 dims): shared vowel + t1/tc/t2 + closure-area. Keyframes: vowel → lips-closed → vowel.
- **abba-free** (140 dims): 4 free keyframes × 34 areas + 4 durations. No imposed gesture —
  can free articulation beat the structured arm?
- **control-***: uniform random search over the SAME space, same bookkeeping. If CMA-ES does not
  clearly beat this, nothing was learned and the numbers will say so.
- Even seeds start from the found /ah/ posture (stage-on-stage); odd seeds start random.
- f0 FENCED at 220 Hz (the frog scar; a baby is 200-500 Hz). Areas fenced [0.15, 4.0].
- Objective: spread-weighted distance (babble.py's convention — each of the 200 dims scaled by
  1/its spread across Iddo's own takes) to the target unit's centroid. `plain192` (gym.py's exact
  legacy metric) recorded alongside for continuity. **The bar: a REAL Iddo clip averages
  wdist ≈ 13.9 from its own centroid.** A wdist near 14 = as close as Iddo's own takes are to
  each other, in ERAN's own (extended) ear.

## Stage-0 sanity — run BEFORE launch on eran2, all gates green (SANITY0-20260824T231836Z.json, copy in this folder)

| gate | expected | measured | verdict |
|---|---|---|---|
| CMA-ES on 39-d sphere | < 1e-6 | 9.7e-07 @ gen 292 | ✅ |
| fast renderer == verbatim reference | float noise | max diff 9.1e-13, but 0.6x SPEED → **reference loop used** | ✅ (honest: "fast" was slower) |
| reproduce gym.py ah-best distance | 0.43120789968882467 | 0.43120793470697288 (Δ3.5e-8 = eran1↔eran2 float noise; 7 sig figs) | ✅ |
| frozen-ear LOO ah-vs-abba (probe replication) | 92.5% / sep 0.2330 / gaps +0.0599 −0.0469 | **exact** | ✅ |
| extended-ear LOO ah-vs-abba | ≥ frozen | **93.5%** vs 92.5% | ✅ |
| closure gesture direction | toward abba | toward abba at 40/60/80/120/160 ms, monotone | ✅ |
| silence (an ABSENCE) visibility | frozen ear nearly blind | 6.2% → **13.9%** of class separation (**2.3x gain**) | ✅ |
| **the "~30x" claim from the 08-24 brief** | gesture moves ~30x further | **NOT REPRODUCED: measured 1.1x** (displacement ÷ class-separation, per space) | ⚠️ honest miss — see below |

**On the 30x:** the frozen ear already SEES a closure's spectral shape (the 08-24 probe's own
part 3 showed the gesture moving the frozen percept), so *relative total displacement* barely
grows when the contour is appended. What the 8 numbers actually buy, measured: (1) a pure energy
dip — invisible by construction to a level-free ear — becomes clearly audible (2.3x relative);
(2) LOO separation improves; (3) the objective can no longer be satisfied by a spectral trick
with no real closure. That is what the search needs. No file implementing the claimed 08-24
extension measurement was found on eran1, eran2, or the PC (searched); the extension was
re-derived and re-measured here, and the honest number is 1.1x/2.3x, not 30x.

## How to check progress / איך בודקים

```bash
# one-screen summary per box (worker, last beat, evals, best, real-clip bar):
ssh eran2 "cd ~/throat-search && bash check.sh"
ssh eran3 "cd ~/throat-search && bash check.sh"
ssh eran4@<lan-ip> "cd ~/throat-search && bash check.sh"

# live heartbeat of one worker:
ssh eran2 "tail -3 ~/throat-search/run/abba-0/heartbeat.jsonl"

# the current best trajectory of one worker (params, keyframes, all distances,
# nearest-unit table, multi-glottis-seed score):
ssh eran2 "python3 -m json.tool ~/throat-search/run/abba-0/best.json | head -40"

# listen to the current best (copy to PC first; SACRED AUDIO — nothing plays on its own):
scp eran2:~/throat-search/run/abba-0/best.wav .

# watch the tmux session itself:
ssh -t eran2 "tmux attach -t throat"        # Ctrl-b d to detach
```

## How to stop / איך עוצרים

```bash
# graceful (workers finish their generation, checkpoint, and exit; supervisors stop):
ssh eran2 "touch ~/throat-search/STOP && tmux kill-session -t throat"
ssh eran3 "touch ~/throat-search/STOP && tmux kill-session -t throat"
ssh eran4@<lan-ip> "touch ~/throat-search/STOP && tmux kill-session -t throat"
# (tmux kill-session alone also works — state.json checkpoints every <=10 min,
#  and bash launch.sh <box> resumes every worker from its own state.json.)
```

## First scores — 3 minutes after launch, reported honestly

Weighted distance to the target centroid in the extended ear (lower = closer; **a real Iddo
clip averages ≈ 13.9 from its own centroid** — that is the bar). Random starts began at 19-55.

| box | best guided ba | best guided abba | best abba-free | best CONTROL (random) |
|---|---|---|---|---|
| eran2 | 23.31 (ba-3) | **18.54** (abba-3) | 43.55 | **17.14** (control-ba), 18.67 (control-abba) |
| eran3 | 27.24 | 35.99 | 41.33 | 18.67 / 19.48 |
| eran4 | 23.00 | 26.32 | 42.59 | 19.38 |

**At minute 3 the random-search CONTROLS LEAD the guided arms.** That is exactly what a fair
control looks like early: uniform sampling covers the box broadly while CMA-ES starts from one
point and must adapt before it overtakes. If after the 47 h guided still does not clearly beat
the controls, then per [[feedback_clean_experiments]] nothing was learned and this file must say
so. The heartbeats will tell.

All 33 workers verified alive (ps on each box), all writing heartbeats, evals flowing at
~600-1400/worker in the first 3 minutes (eran3's were launched last). First checkpoint
(best.json + best.wav + state.json) lands ≤10 min after launch per worker.

### First checkpoint verified (02:29, 10 minutes in) — the machinery is real, not a proxy

`run/abba-0/` on eran2 wrote best.json + **best.wav (23 KB, ERAN's actual current best sound)**
+ state.json exactly on the 10-min mark. The honest read at 12,628 evals:

- **wdist 14.27** vs the real-clip bar **13.91** — a hair outside the cloud of Iddo's own takes.
- **plain192 = 0.414** vs real-clip mean **0.467** — in the frozen legacy metric he is already
  *closer than an average real clip* (the legacy metric is exactly what it could always game;
  the contour dims are what still hold him honest).
- Multi-glottis-seed rescore: 14.87 ± 0.36 over 5 seeds — the score is not one lucky noise draw.
- **The embarrassment control: nearest unit is /ma/ (13.82), then /ba/ (13.96), then /abba/
  (14.27, aimed).** Ten minutes in he sits in the CV-syllable neighbourhood but has NOT yet
  found what makes abba abba — and his best closure duration sits at the 0.03 s search minimum,
  i.e. the closure gesture is not yet doing work. That is what 47 more hours are for.

### Crash-resume proven live (02:30)

Killed `control-ba-0` mid-run (SIGTERM, rc=143) → supervisor relaunched it 15 s later →
`RESUMED control-ba-0 at evals=19856 best=16.3330` from state.json → 12/12 workers on eran2
again. Only the ~1k evals since the last checkpoint were lost, by design. A box reboot is
recovered the same way: `cd ~/throat-search && bash launch.sh <box>` resumes every worker.

Measured after settling: eran2 load ~12/20, eran3 13.8/20 (13 workers, 107 MB RSS mean),
eran4 8.0/20 (8 workers at nice 10, 105 MB RSS mean).

## Do-no-harm verification (after launch, 02:22)

- eran1: `eranb-life` + `eranb-serve` **active** (user services), `eran_life.py --live` PID 120630
  running, observation window :8820 answering. Nothing was ever executed on eran1 beyond reads.
- eran2: `eran-senses` **active**, `ping` over the organ wire answers `{"pong": true}` in 0.002 ms
  with 12 workers running beside it.
- eran4: `dmidi` processes untouched; workers run at nice 10.

## Files

- Search dir on each box: `~/throat-search/` (code + `data/t06` corpus copy + `run/<arm-seed>/`)
- This folder: `SANITY0-20260824T231836Z.json` (the full stage-0 record), `STATUS.md` (this file)
- RAMCHAT: claim + result posted as `claude-cli-FABLE-throat`
