# -*- coding: utf-8 -*-
"""proof_DW-04.py — the bird's own verdict must move its mood.

THE DEFECT (measured over 1,678 samples, one per 1,000 beats):
    serotonin was written by exactly one caller — body/parent.py's pay_taps() —
    and no human has ever tapped (feedback/inbox is empty, 'taps_paid' appears in
    0 of 1,678,809 metrics lines). So sht was 0.5 in 1,678 of 1,678 samples,
    stdev 0.0, one distinct value, and chem.temperature() was a constant 1.0 for
    the whole life. The critic's valence went to the synapses and never to the
    mood.

WHAT THIS PROVES, through the REAL Life._sing_and_audition:
    one judged song with the real Chemistry. Old: serotonin does not move, and
    the sampling temperature is unchanged. Fixed: a good verdict lifts the mood,
    a bad verdict lowers it, and the temperature follows.

    python3 proof_DW-04.py --mode old   -> FAIL
    python3 proof_DW-04.py              -> PASS
"""
import os
import sys
import tempfile
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _rev20260906 as rev  # noqa: E402

MODE = rev.mode_from_argv()
TREE, SWAPPED = rev.enter(MODE)

sys.modules.setdefault("psy_synth", types.ModuleType("psy_synth"))
import genome                      # noqa: E402
from chemistry import Chemistry    # noqa: E402
from drives import Drives          # noqa: E402
import darwish_life as dl          # noqa: E402

VALENCE_GOOD = 0.954     # the valence of the ONE song this bird ever sang
VALENCE_BAD = -0.800

c = rev.Checks(__doc__.strip().splitlines()[0], MODE)
print("  tree=%s  swapped=%s" % (TREE, SWAPPED or "(none: this IS the tree)"))

SANDBOX = tempfile.mkdtemp(prefix="dw-rev-song-")
dl.ROOT = SANDBOX
dl.OUTBOX_DIR = os.path.join(SANDBOX, "songs", "outbox")
dl.psy_synth = None                                  # no numpy in the proof


class _Voice(types.ModuleType):
    @staticmethod
    def sing(brain, chem, bars=32):
        return list(range(64)), {"1|0": {"7": 1.0}}

    @staticmethod
    def save_song(song_id, tokens, trace, outbox):
        open(os.path.join(outbox, song_id + ".json"), "w").write("{}")


class _MidiOut(types.ModuleType):
    @staticmethod
    def write(path, tokens):
        open(path, "wb").write(b"MThd")


class _Synth(types.ModuleType):
    @staticmethod
    def render(path, tokens, bpm=None):
        open(path, "wb").write(b"RIFF")
        return 32.0


dl.voice = _Voice("voice")
dl.midi_out = _MidiOut("midi_out")
dl.synth = _Synth("synth")


def sing_once(valence):
    """One trip through the real _sing_and_audition with a stub body."""
    life = dl.Life.__new__(dl.Life)
    life.ablate = []
    life.beat = 1
    life.chem = Chemistry()
    life.drives = Drives()
    life.drives.E = 0.85
    life.brain = types.SimpleNamespace(
        digest=lambda tok, phase, chem, learn=True: 1.0,
        pay_trace=lambda trace, v, eta, chem: (10, 0),
        mass=1000)
    life.ears = types.SimpleNamespace(audition=lambda tokens: [])
    life.critic = types.SimpleNamespace(
        judge=lambda tokens: (valence, {"kick_downbeat": 0.25}))
    life._song_gate = {}
    life._songs = 0
    os.makedirs(dl.OUTBOX_DIR, exist_ok=True)
    before = life.chem.sht, life.chem.temperature()
    extra = life._sing_and_audition()
    after = life.chem.sht, life.chem.temperature()
    return before, after, extra


(sht0, t0), (sht1, t1), extra = sing_once(VALENCE_GOOD)
print("  good verdict %.3f: sht %.4f -> %.4f   temperature %.4f -> %.4f"
      % (VALENCE_GOOD, sht0, sht1, t0, t1))
c.check("a judged song moves serotonin", sht1 != sht0,
        "sht %.4f -> %.4f" % (sht0, sht1))
c.check("a GOOD verdict raises the mood", sht1 > sht0)
c.check("the sampling temperature is no longer a constant", t1 != t0,
        "%.4f -> %.4f" % (t0, t1))
c.check("the song still happened", "sang" in extra and "critic_valence" in extra,
        str(sorted(extra))[:120])

(bsht0, _), (bsht1, _), _ = sing_once(VALENCE_BAD)
print("  bad verdict  %.3f: sht %.4f -> %.4f" % (VALENCE_BAD, bsht0, bsht1))
c.check("a BAD verdict lowers the mood", bsht1 < bsht0,
        "sht %.4f -> %.4f" % (bsht0, bsht1))

c.check("Chemistry.critic_valence exists", hasattr(Chemistry, "critic_valence"))
c.check("the bird's own verdict is weaker than the father's thumb",
        0.0 < getattr(genome, "CRITIC_VALENCE_GAIN", 0.0) < 1.0,
        "CRITIC_VALENCE_GAIN=%s" % getattr(genome, "CRITIC_VALENCE_GAIN", None))
c.check("Life._liveness_checks exists (flat-mood warning)",
        hasattr(dl.Life, "_liveness_checks"))

c.done()
