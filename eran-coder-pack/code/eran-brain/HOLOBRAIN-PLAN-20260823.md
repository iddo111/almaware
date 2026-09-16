> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# ERAN — the holobrain that grows its own organs

**Iddo, 2026-08-23 13:35:**
> *"אני רוצה שערן יוכל לפתח את האיברים שלו... על שלוש הדי-ג'י-איקסים... עם הקורטקס של
> השמיעה איפה שהוא מוצא... זה יכול להתפרס גם על שלוש מכונות אם בא לו."*
> *"ערן זה priority number 1. זה שלוש מכונות. ברגע שהגיעו הכבלים נעשה אותו ארבע."*
> *"This is the whole brain. This is not only the voice."*

---

## 0. What I understood, said back so you can correct me

1. **Not a voice engine. A whole brain.**
2. **The brain grows its own organs.** Nobody types an anatomy — the same law you already
   set for the body on 08-22 (`body/growth.py`: *"a real body is not decided, it grows"*),
   now applied one level up: to the cortexes themselves.
3. **A cortex is born wherever there is room.** "הקורטקס של השמיעה איפה שהוא מוצא" — placement
   is something the organism decides at birth-time, not something I hard-code in a config.
4. **Three machines now. Four when the cables arrive.**
5. **ERAN is priority 1 and owns eran1, eran2, eran3. Full stop.**

---

## 1. What already exists — this is not a blank page

`eran_life.py` (444 lines) is alive on eran1 right now, beat **40.6 M**, and the body is
already a set of organs:

```
body/  brain.py  chemistry.py  cortex.py  drives.py  ears.py
       genome.py  growth.py  parent.py  school.py  sleep.py  why.py
```

`growth.py` (2026-08-22) already grows the **body**: vocal-tract length 7 cm → 17 cm,
f0 400 Hz → adult, breath capacity, larynx, cavity — every constant a *function of age*,
monotone, deterministic. Your words then: *"בתינוק אנושי... זה הדרגתי"*.

**So the new thing is not "add growth". Growth exists. The new thing is that the BRAIN
grows the way the BODY already does.**

---

## 2. The one architectural decision, and why

**Do NOT use FSDP / tensor-parallel to spread ERAN over three boxes.**

FSDP shards a *fixed* architecture. A brain that buds a new cortex changes shape while it
runs, and every bud would force a full reshard and a restart. That is a training-run
architecture, not an organism.

**Instead: one organ per process, organs talk over the fabric.**

| | |
|---|---|
| an organ | its own process, its own weights, its own optimizer, its own lifetime |
| the wire | small **gist vectors**, not activations or gradients |
| growth | a new organ is a new process on whichever box has room |
| death | an organ that earns nothing is pruned; the others do not notice |

This is also the biology. Cortexes are semi-autonomous and talk through bottlenecks
(white matter), not by sharing weights. And it means **an organ can be born, moved, or
killed without stopping ERAN** — which the FSDP design can never offer.

### The fabric this rides on — measured 2026-08-16, and it decides the layout

| link | speed | note |
|---|---|---|
| eran1 ↔ eran2 | **105 Gbit/s** (4 streams) | the fat pipe |
| eran2 ↔ eran3 | **39.5 Gbit/s** | via eran2, which NATs eran3 |
| eran1 → eran3 | hairpins through eran2 | costs almost nothing (38.6 vs 39.5) |
| RTT | **0.042 ms** | a gist crossing the fabric is cheaper than a page fault |
| **eran4** | **no QSFP NIC at all** | ← **this is what the cables are for** |

A gist of 256 float16 = 512 bytes. At 0.042 ms RTT the fabric can carry **millions of
organ-to-organ messages per second.** The fabric is not the constraint. It never was.

---

## 3. The organ map

```
        eran1  ·  the SELF                eran2  ·  the SENSES           eran3  ·  the WORLD
   ┌────────────────────────┐      ┌────────────────────────┐    ┌────────────────────────┐
   │ eran_life  (the loop)  │      │ auditory cortex        │    │ cognitive map          │
   │ drives · chemistry     │◄────►│  ← the 300 clips       │◄──►│ imagination / replay   │
   │ sleep · why            │ 105G │ vocal cortex (mouth)   │39G │ school · parent        │
   │ the genome + growth    │      │ ears · prosody         │    │ room for what buds     │
   └────────────────────────┘      └────────────────────────┘    └────────────────────────┘
                     eran4 joins as a fourth lobe when the cables land
```

**eran1 holds the self** — the loop, the drives, the chemistry, the genome — because that
is the one thing that must never be restarted. Sensory organs can die and be reborn; the
self cannot.

---

## 4. Growth: when does an organ bud?

Not on a schedule. **On a measurement**, so it can be wrong and we would see it:

> An organ buds a child when **its surprise stays high while its capacity is saturated.**

- *surprise high* — it is still being wrong about its own input
- *capacity saturated* — its own weights have stopped moving; more data is not helping
- both, for N consecutive sleeps → it buds

If only surprise is high, it needs data, not tissue. If only capacity is saturated, it has
learned its job. **Both together is the only honest signal that the organism has outgrown
its own anatomy** — and it is exactly the shape of `growth.py`'s law: monotone, automatic,
never by surgery.

Pruning is the same rule in reverse: an organ whose removal does not raise anyone's
surprise is not doing anything, and dies at the next sleep.

---

## 5. The first organ, and what it is fed

**The auditory cortex, on eran2.** Its corpus is what you recorded today:

| unit | takes | what it is |
|---|---|---|
| `ah` אַה | **100** | the open vowel |
| `ba` בַּ | **100** | the plosive |
| `abba` אַבָּא | **100** | **the whole word** |
| `ih` · `ma` · `ima` | in progress | for אִמָּא |

Plus **7.7 GB of Café Claude** — your own voice, unlabelled, months of it. The 300 clips
say *what a thing is called*; the 7.7 GB teaches *what your mouth is*. **Small labelled
seed, large unlabelled ocean.** That is the only shape that fits what one person can give.

### Why this replaces everything before it — measured today

| | top-1 |
|---|---|
| synthetic → synthetic | 59.8 % |
| **synthetic → your real mouth** | **6.1 %** (chance 4.5 %, shuffled control 4.2 %) |
| your voice → your voice | 36.4 % |

The old 396-clip synthetic corpus **transfers to a real mouth at chance.** It taught the
synthesiser, not speech. **It does not go into the new brain. Not one clip.**
"נקי נקי נקי" — this is what clean means, and it is now a measured reason rather than a
preference.

---

## 6. What gets measured, before anyone celebrates

| gate | number |
|---|---|
| hears his own syllables | leave-one-take-out top-1 on t06, beat **36.4 %** (today's baseline) |
| hears `abba` as a whole | discriminate `abba` from `ah`+`ba` spliced — if it cannot, it learned a lump |
| **says `abba`** | you listen. You are the only instrument for this one. |
| growth is real | a budded organ must lower total surprise vs a param-matched control that did not bud |

That last row is the one that keeps this honest: **a brain that grows must beat a brain of
the same size that didn't.** Otherwise growth is decoration.

---

## 7. Order of work

1. **Back up beat-40.6 M** before anything is touched. (Destroyed-brain scar, 07-10.)
2. Free eran2 and eran3 completely — ERAN's, per your order. The worm and Cosmos move to eran4.
3. Auditory cortex on eran2, on today's 300 clips + Café Claude.
4. The gist wire between organs — 512-byte messages over the fabric, measured against the 0.042 ms floor.
5. The bud/prune rule, with its param-matched control.
6. eran4 joins as the fourth lobe when the cables land.

**No code until you say go.**
