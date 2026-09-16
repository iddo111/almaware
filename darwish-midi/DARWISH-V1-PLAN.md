> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# DARWISH v1 — start fresh, properly

**Iddo's order, 2026-08-23 09:42:** *"kill and delete both darwish — prepare plan and proper corpus — start fresh with better midi output."*

*לזכרו של לאור ז״ל. This is a memorial, not a training run.*

---

## 0. Why v0 died — measured, not felt

Iddo listened and said *"סאקס"*. He was right, and the numbers say exactly why. All three
findings below are measurements taken on 2026-08-23, not opinions.

### 0.1 The sampler was throwing away the kick — FIXED, and it was not enough

Decoded straight from the model's own token list:

| sampling | kick | corpus |
|---|---|---|
| `temp .95, top_k 32` (what shipped) | **0.1 %** | 35.1 % |
| `temp 1.0, top_k 0` | 21.5 % | 35.1 % |
| `temp .85, top_k 0` | **39.1 %** | 35.1 % |

`top_k=32` truncates a 108-token vocabulary in which kick-bearing tokens are *scattered*
(token = `drums*13 + bass`, so kick lives in tokens 13–25, 39–51, 65–77, 91–103). The top 32
by probability clustered in the no-kick region, and the longer the generation ran the deeper
it drifted — 7.9 % kick over 720 tokens, 0.1 % over 4096. **A death spiral, not a model flaw.**

**Standing rule for v1: never truncate this vocabulary with `top_k`.** Composite tokens and
top-k truncation do not mix.

### 0.2 The renderer had no instruments and the MIDI had no instruments either

`voice/psy_synth.py` is hand-written oscillators; its own docstring says *"No sample packs or
soundfonts are used here."* And the emitted MIDI carried **zero program-change events** —
measured 4149 note-ons on ch9, 3810 on ch0, not one `0xCn` — so any real synth played the
whole bassline as Acoustic Grand Piano.

Fixed on the PC: FluidSynth 2.6.0 (LGPL) + FluidR3_GM (MIT) in `vendor/`, and
`voice/gm_dress.py` assigns a real TR-808 kit, Synth Bass, lead and pad. **Keep both.** They
are the loudspeaker for v1 and they are no longer the bottleneck.

### 0.3 The real ceiling: the corpus and the alphabet

Sonic scan against a real Darwish track from the corpus (`voice/sonic_scan.py`):

| | real Darwish | v0 render |
|---|---|---|
| variety between 8 s blocks (self-sim std) | **0.080** | **0.016** |
| high 4k–16k energy | 10.3 % | 1.7 % |

*(the kick-grid column of that scan is unreliable — the peak-picker confuses bass notes with
kicks and reported 633 BPM for the real track. Do not quote it. Fix or drop it in v1.)*

**5× less variety than the real thing.** The model loops without developing. That is not the
synth and not the sampler. It is what it was fed and what it was allowed to say.

---

## 1. The corpus is the biggest problem, and nobody had looked at it

From `midi_tokenize.log` on eran4 — 191 logged files, 3.40 M tokens, 94.7 hours:

### 1.1 82 % of the corpus is DJ sets, not tracks

**58 files are longer than 20 minutes and account for 2,778,876 tokens = 81.8 % of everything
the model learned from.** The top of the list:

| share | length | file |
|---|---|---|
| 3.29 % | 182.6 min | Darwish 3HRS LIVE @ Desert Adventure #20 |
| 3.27 % | 181.3 min | Darwish @ Desert Adventure 2025 — 3 Hours Sunrise Set |
| 3.12 % | 173.2 min | Darwish — Desert Adventure 2019 (Full Set) |
| 2.11 % | 123.7 min | Progressive Mix 2013 By D.J. Darwish |

A DJ set is **other people's tracks, beatmatched end to end, with no song boundary**. A model
fed 82 % DJ sets cannot learn a build, a drop or a breakdown, because at the scale it sees
there aren't any — there is one continuous 4/4 pulse for three hours. *That is precisely the
"loops without developing" number in §0.3.*

### 1.2 The corpus is a YouTube title search, not a discography

Present in the corpus and definitely not Darwish psytrance tracks:
- `The Little Palestine Logo Scandal: Laila vs. Rush Darwish` — a talk video
- `D.J. Darwish on German TV` — a TV segment
- `Bassel Darwish | Crobar Club`, `House Calls: Live with Bassel Darwish` — **a different
  artist**, a house DJ who happens to share the surname
- `OZORA FESTIVAL 2026 — Vegas, Captain Hook…` — appears **three times**, and is not Darwish
- `Stomping Ground • Compiled by Darwish Vol.1` — a 65-minute compilation of other artists

### 1.3 The tempo grid is snapping, so every token may be on the wrong beat

**191 files → only 10 distinct BPM values**, and 116 of them are *exactly* 143.6.

| BPM | files |
|---|---|
| 143.6 | 116 |
| 139.7 | 40 |
| 126.0 | 10 |
| 136.0 | 6 |
| 147.7 | 5 |

Seventeen years of goa, progressive and psytrance do not share six tempos. The detector is
snapping to a lattice. **If the BPM is wrong the 16th-note grid is wrong, and every single
token is quantised onto the wrong beat** — the "score" is smeared before the model ever sees
it. This must be proven or disproven before anything is retrained.

---

## 2. The plan

### Phase 1 — a proper corpus (do this first; nothing else matters until it is done)

1. **Split or drop the sets.** Anything > 20 min is either dropped or cut at detected track
   boundaries (long crossfade / key change / energy trough). Dropping is the honest default;
   splitting is a research task, not a given.
2. **Filter to the actual artist.** Manual pass over 323 titles. Remove Bassel Darwish, talk
   videos, other-artist compilations and festival sets. Keep remixes *by* Darwish.
3. **De-duplicate** by audio fingerprint, not filename — the OZORA set is in there three times
   and `Retro Goa set` twice under two years.
4. **Fix or verify BPM per file.** Measure the onset-interval histogram directly and compare
   against the detector. If it is snapping, replace it. Report the real BPM distribution.
5. **Publish the resulting corpus card**: n tracks, hours, BPM histogram, year spread, what was
   removed and why. Iddo signs it off before a single training step runs.

**Expected outcome, stated in advance so it can be wrong:** ~120–180 real single tracks,
12–20 hours, far less than the 94.7 h claimed — and *better*, because 82 % of those hours were
teaching the model the wrong thing.

### Phase 2 — climb to rung (b): a MIDI the music survives

`midi_lean.py` is honest rung (a): percussion grid + bass degree + tempo/key, ~9–10 tok/s, and
it says outright that leads, FX and velocity are *"not approximated — never encoded."* v1 adds
what a psytrance track actually is:

| lane | v0 | v1 |
|---|---|---|
| drums | 3 on/off bits | kick / snare / clap / open hat / closed hat / ride, **each with velocity** |
| bass | 12 scale degrees, mono | degree **+ octave + note length + accent/slide** |
| **lead** | **absent** | **monophonic lead f0 lane** (rung b, the whole point) |
| structure | BAR / PHRASE | + section marks (intro / build / drop / break) |
| header | tempo, key | tempo, key, **and per-bar energy** |

Keep separate lanes as separate tokens; **do not multiply them into one composite id again** —
that composite is what made §0.1 possible.

Expected: ~40–70 tok/s instead of 9–10 → roughly **25–45 M tokens** from the cleaned corpus.

### Phase 3 — size the model to the corpus, which is what Iddo asked for

Current: **1.36 M params on 5.36 M tokens = 3.9 tokens/param.** Healthy is ~20. **The v0 model
is roughly 5× oversized for its data** — Iddo's instinct was correct.

- If Phase 1+2 yield 30 M tokens → optimal ≈ **1.5 M params**.
- If they yield 15 M → optimal ≈ **750 K params**.

**Size is decided after Phase 2 reports the real token count, never before.**

### Phase 4 — train from scratch, and hold out by TRACK

From scratch, as Iddo said: *"עדיף לאמן מודל מההתחלה כמו שצריך, כי נורא קשה לתקן לו טעויות."*

Held-out split **by track, never by segment** — the same scar that cost ERAN ~14 points
(`project_eran_session_leak_scar`). Two segments of one track in different splits is leakage.

### Phase 5 — acceptance, measured, before Iddo is asked to listen

`voice/sonic_scan.py` runs on every candidate against real Darwish tracks. A render is shown
to Iddo **only** if:

| axis | gate |
|---|---|
| kick share of steps | within ±10 pts of corpus | 
| variety (self-sim std over 8 s blocks) | ≥ 0.06 (real ≈ 0.080, v0 = 0.016) |
| high 4k–16k energy | ≥ 5 % (real 10.3 %, v0 1.7 %) |
| stereo width | ≥ 0.20 (real 0.306) |
| lead lane | non-empty for ≥ 30 % of bars |

Fix the kick-grid metric first or drop it — §0.3.

---

## 3. Hardware — there is room

Measured on eran4 (<lan-ip>), 2026-08-23:

| | |
|---|---|
| disk free | **988 GB** (72 % used of 3.6 T) |
| RAM | 120 GB total, **67 GB free** |
| GPU | NVIDIA GB10, **idle** |
| corpus on disk | 8.6 GB of mp3, 21 MB of tokens |

A 1.5 M-param model on 30 M tokens is nothing for this box. **The constraint was never the
hardware.**

---

## 4. What was deleted and what was kept

Iddo ordered both renders killed. Deleted: the two WAV files (280 MB of proof that v0 does not
work). **Kept** in `songs/outbox/`: the MIDI and the sidecar JSON for each — ~80 KB total, and
they are the evidence behind §0.1. Kept: `vendor/` (FluidSynth + soundfont),
`voice/gm_dress.py`, `voice/sonic_scan.py`. Those are v1's loudspeaker and v1's ears.
