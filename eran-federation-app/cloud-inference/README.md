> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# ERAN in the cloud — inference while the fleet trains
# ערן בענן — הסקה בזמן שהאימון רץ בבית

**Branch / ענף:** `federation/eran-cloud-inference` · **2026-08-23** · not deployed, deploy is Iddo's call
**לא הועלה לענן. ההעלאה היא החלטה של עידו.**

---

## The idea in one line / הרעיון בשורה

**EN —** The DGX fleet is busy being ERAN's life; the cloud carries a read-only copy of
his *perception* and answers the world for free while the fleet gets on with the work.

**HE —** הצי מאמן, הענן עונה. הענן מחזיק עותק־קריאה־בלבד של **התפיסה** של ערן ומשיב לכל
העולם בחינם, בזמן שהצי ממשיך לעבוד.

Iddo, 2026-08-23: *"maybe it can be used to run inference while training is onboard"* —
this is that, built.

## Why ERAN of all projects / למה דווקא ערן

Because he is small. His whole recognising brain is **91 prototype vectors of 192
numbers** — 62 KB gzipped on disk, 167 KB sanitised on the wire — and his ear is
**frozen DSP**, not a learned network. No GPU, no torch, no weights to ship. That is
the rare project where "run it on free cloud" is a fact and not a wish.

| | measured 2026-08-23 |
|---|---|
| brain snapshot on the wire | **167 KB** (33% of the Worker's own cap) |
| cochlea + lookup, 0.94 s of audio | **2.01 ms** CPU |
| cochlea + lookup, 0.32 s (his own breath) | **0.69 ms** CPU |
| cold isolate: parse brain + build index | **3.13 ms** |
| worst case per request, cold | **~5 ms** against Cloudflare's 10 ms free-tier limit |
| parity with `eran-brain/body/ears.py` | **396/396 utterances, same prototype** |

## The two laws this obeys / שני החוקים

1. **The cloud never learns.** There is no spawn, no Hebbian pull, no scar, no
   forgetting anywhere in `brain.js` or `eran.js`. It can only look up. A second ERAN
   quietly learning in a Worker would be a second ERAN, and there is one.
   **הענן לא לומד. אף פעם.**
2. **The cloud never gets audio it may keep.** `/api/eran/hear` reads the wav, turns it
   into 192 numbers and forgets it. Nothing is stored, nothing is logged, no recording
   ever reaches KV. ([[feedback_mic_private_capture]])
   **שום הקלטה לא נשמרת ולא נרשמת.**

## What is here / מה יש כאן

| file | what it is |
|---|---|
| `ear.js` | ERAN's frozen cochlea, ported to JS. A PORT, not a redesign — if it disagrees with `ears.py`, it is wrong. |
| `brain.js` | `nearest()` and nothing else. Recognition, never learning. |
| `push_brain.py` | fleet → cloud. Sanitises the snapshot, runs the panel's **own** leak self-check, POSTs with the existing Bearer credential. |
| `parity_dump.py` | runs ERAN's real cochlea over his corpus and writes what it heard. |
| `parity_test.mjs` | **the acceptance check.** Same wavs through the JS ear, number by number. |
| `worker_test.mjs` | drives the real Worker module with a fake KV: auth, guards, ear, lookup. |
| `../worker/src/eran.js` | the routes themselves. |
| `PROJECTS.md` | **the same question asked of every project in the workspace.** |

## The lane / הצינור

```
   eran1/2/3  the organism lives and learns          <- unchanged, untouched
        |
        |  push_brain.py    91 prototypes, sanitised, 167 KB, Bearer token
        v
   federation.iddoperez.ai      KV: "eran-brain"     <- read-only copy
        |
        |  POST /api/eran/hear   (a wav, or a 192-vector)
        v
   anyone, any browser, no PC on, ~2 ms of CPU
```

## Run the checks / להריץ את הבדיקות

```bash
cd D:\CLAUDE\eran-federation-app\cloud-inference && PYTHONIOENCODING=utf-8 python parity_dump.py --n 400 --out parity-full.json && node parity_test.mjs parity-full.json && node worker_test.mjs
```

Last run, 2026-08-23 21:2x:

```
band table            OK   24 bands, identical bin ranges
utterance vectors     OK   396 wavs x 192 dims, worst drift 1.13e-7 (tol 0.000001)
nearest prototype     OK   396/396 identical, worst cosine drift 8.76e-8
PARITY OK — the cloud ear hears what ERAN hears (396 utterances).

ALL PASS — 16 passed, 0 failed
```

## The API / הממשק

```
POST /api/eran/brain        Bearer FED_PUSH_TOKEN — the fleet pushes a snapshot
GET  /api/eran/brain.json   what brain is up there, and how old (?vectors=1 for the vectors)
GET  /api/eran/health       is there a brain, is it stale
POST /api/eran/hear         Content-Type: audio/wav   -> {nearest, sim, surprise, top[]}
                            Content-Type: application/json {"vec":[192 floats]}
```

Every answer carries `age_s` and `snapshot_state`. **A stale cloud says it is stale** —
that is the point of putting the age on the wire.

## What this does NOT do / מה זה לא עושה

- **It does not name the sound.** ERAN's prototypes are unlabelled — he has never been
  told what a syllable is called. `/api/eran/hear` answers "closest to prototype 82,
  cosine 0.963", which is the truth. Labels would be a story.
- **It does not train.** Free tiers cannot and their ToS says so; the DGX is the
  trainer. That line was drawn in [[project_eran_federation]] and has not moved.
- **It is not deployed.** Everything above was measured locally. A deploy publishes to
  `federation.iddoperez.ai` and is Iddo's to approve.

## The known ceiling / התקרה הידועה

Cold-start parse costs ~0.021 ms per prototype. With ~2 ms for the ear and a 10 ms
free-tier CPU limit, the lane runs out of room at roughly **380 prototypes**. ERAN's
genome allows 4096. The fix when he gets there is not a bigger plan — it is to send the
vectors as base64 `Float32Array` instead of JSON numbers, which is a morning's work and
about 40x cheaper to parse. Written down here so it is a known ceiling and not a
surprise outage.
