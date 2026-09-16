> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# כמה גרונות, כמה פיות, כמה אזניים / The organ census

**Iddo asked, 2026-08-24 04:07:** *"יש לך בעיות וכפילויות בפרויקט — כמה גרונות כמה פיות כמה אזניים"*
He was right to ask. Counted across all of `D:\CLAUDE` (archives and worktrees excluded).

## The count

| organ | copies on disk | what the LIVE organism actually wears |
|---|---|---|
| 👂 **ears** | **6** | **one** — `eran-brain/body/ears.py` (the frozen cochlea, 79.55%) |
| 👄 **mouths / throats** | **5** | **one** — `eran-brain/voice/mouth.py` |
| 🗣️ **babble loops** | **8** | **one** — `eran-brain/organs/babble.py` |
| 👁️ **eyes** | **4** | **none. All four are in `archive/`.** |

**In one line: ERAN wears one ear, one mouth, one babbling chassis, and no eyes.
Everything else is an old copy or an experiment nobody wears.**

## Which is which

**EARS (6).** Live: `eran-brain/body/ears.py` (289 lines, imported by `eran_life.py:45`
and `voice/babble.py`). Deliberate port: `snn-lab/cochlea.py` — a faithful copy so the
spiking net is judged on the *same* ear, which is correct and should stay. Different
jobs, not duplicates: `keshev-next/app/ear.py` and `keshev-fable/app/ear.py` are the
mic's capture front-ends (resampling, RMS segmentation), and `darwish-midi/body/ears.py`
is a MIDI token feeder that only shares the word. Actually dead: `eran-audio/cochlea.py`
(EnCodec tokens, June, another modality).

**MOUTHS (5).** Live: `eran-brain/voice/mouth.py`, 7 motors, **numpy only** — the scipy
filter was hand-written out so the mouth can run anywhere. It is a port of
`voice-ant-farm/mouth_v1.py`, which is the real predecessor and still on disk.
`voice-ant-farm/mouth.py` is a 9-motor fork nobody wears. `yigal-alma/alma_yigal/vocal.py`
belongs to another project. `alma-larynx/make_larynx.py` is **not a synthesiser at all** —
it generates STL for a *physically printed* larynx.

**BABBLE (8).** Live: `organs/babble.py` — the (1+1) hill-climb **with a blind control
arm**, which is the version that produced the 2026-08-23 20:29 measurement.
`voice/babble.py` is the evolution-strategy trainer used by `voice/say.py`. The other six
are dead dashboards and daemons from June/July (`eran-dashboard`, `eran-live`,
`eran-audio`, `voice-ant-farm`).

**EYES (4).** All in `archive/`: `eran-third-eye/` (1394 lines, June), `eran-room`,
`eina-pkicha`. **ERAN has no vision loop.**

## The honest read

The duplication is real but it is mostly **history, not confusion** — the live organism
imports exactly one of each, and the copies are predecessors, deliberate ports, or other
projects that reuse the word. The two worth a decision:

1. **`voice-ant-farm/mouth_v1.py` vs `eran-brain/voice/mouth.py`** — the same mouth in two
   places. If `mouth_v1` is ever edited, the live one silently drifts. One should become
   the source and the other should import it or say in its header that it is frozen.
2. **The six dead babble scripts** — they cost nothing but they are what makes the tree
   look like it has eight mouths. They belong in `archive/`.

Nothing here is on fire. Nothing here needed changing tonight.
