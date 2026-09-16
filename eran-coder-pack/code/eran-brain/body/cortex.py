"""cortex.py — DEPTH. A stack of prototype layers that BIRTHS its own depth.

Until today ERAN's brain was one flat layer of prototypes with no connections
between them, and the consequence was measured, not guessed: he can recognise
a syllable (62.88% on the 132-item heldout, chance 4.545%) but has never once
beaten chance at decomposing a word into its syllables. A flat memory has
exactly one answer for a whole sound. Decomposition needs a unit that is ABOUT
a sequence of other units — that is what a second layer is.

WHAT A LAYER IS
---------------
Layer 0 is ``brain.Brain`` unchanged — the same object, reused, not forked.
Layer k>0 is ALSO ``brain.Brain``: same growth-on-surprise, same per-prototype
tolerance/tuning curve, same Hebbian pull at the same chemistry-set rate, same
scars, same eligibility traces, same sleep. Only its INPUT differs. This is
greedy layer-wise unsupervised learning — the Deep Belief Network idea (Hinton
2006), on a living organism instead of a training script. There is no backprop
here, anywhere, ever: no layer ever sends an error signal down to the layer
below it. Each layer learns from what the layer below happens to do.

WHAT LAYER k SEES  (the percept, and why THIS percept)
------------------------------------------------------
Layer k-1 emits, per utterance, an ordered TRACE of firings: for each moment
of the sound, (winning prototype index, similarity). Layer k's percept is an
ORDERED CONCATENATION over ``genome.LAYER_SLOTS`` consecutive slots of that
trace: slot j holds the winning prototype's own vector, scaled by how strongly
it won, and the whole concatenation is L2-normalised (Brain's cosine maths
assumes unit vectors). So one layer-1 unit literally IS "this shape, then this
shape, then this shape" — legible, and you can name its three parts by looking
at them (proof/measure_depth.py does exactly that).

The alternative the brief offered — a normalised bag-of-TRANSITIONS over
prototype INDICES — was rejected for one concrete reason: ``sleep.py`` prunes
prototypes and RE-INDEXES the survivors. A percept keyed on index would have
its meaning silently scrambled every night, and its width would have to change
every time the layer below grew. Keying on the prototype's VECTOR is immune to
both: it is fixed-width (LAYER_SLOTS x dim of the layer below) no matter how
many prototypes live below, and pruning cannot rewrite history that is already
stored as geometry.

WHERE THE TRACE COMES FROM  (and why this is not touching the frozen ear)
-------------------------------------------------------------------------
THE EAR IS FROZEN (genome.py, Iddo 2026-08-21) and nothing here changes it.
``ears.frames(path)`` produces exactly the frames it always did, and
``ears.pool(feats, rms)`` over the FULL span returns the byte-identical vector
``ears.utterance(path)`` returns — proof/test_organism.py asserts that
equality. The cortex simply also looks at the same cochlea output through a
SHORTER window (genome.CORTEX_WINDOW_MS, hopping by CORTEX_HOP_MS) so that a
sound has an inside and not only an identity. That is the brain choosing where
to look, which is the brain's business; the anatomy is untouched.

Layer 0 still LEARNS only from the whole utterance, exactly as before. The
windowed trace is READ-ONLY (``nearest``, never ``hear``) — so wiring the
cortex in cannot change what layer 0 becomes.

BIRTH, NOT CONFIGURATION  (Iddo's two laws)
--------------------------------------------
"MAX NEURONS FROM BIRTH": the capacity for ``genome.MAX_LAYERS`` exists from
the first beat. "לתת למוח גבולות ולתת לו לשלוט בגודל שלו ובצורה שלו בתוך
הגבולות": inside that fence the brain decides its own depth. So no human ever
switches a layer on. Layer k is BORN, at a sleep, only when

  (a) layer k-1 has SETTLED — across each of the last LAYER_SETTLE_SLEEPS
      sleeps its prototype count moved by no more than LAYER_SETTLE_TOL, or
      LAYER_SETTLE_FRAC of its own size, whichever is larger (a layer still
      churning has not finished being itself), and
  (b) at least genome.LAYER_BIRTH_MIN_EVENTS DISTINCT sequences went past IN
      ONE EPOCH — one stretch between two sleeps. Distinct, because the scar
      is a 272M-parameter run whose heldout came out 2x worse than chance:
      depth without data is memorisation, and a child who hears one sound
      100,000 times has heard one sequence. In one epoch, because a sequence
      key is a tuple of prototype INDICES and sleep renumbers those — see
      _key, where counting them across a prune was found to inflate the gate
      18-fold on real state.

Both numbers live in the genome. A birth is logged loudly, to the journal and
to the metrics line, because it is the organism changing shape.

SPACE
-----
Every prototype has a 3D position. Layer index sets the z plane; inside a
plane a newborn lands among the prototypes it already resembles and is pushed
out along a deterministic direction in proportion to how UNLIKE them it is,
then relaxed apart so nothing piles up. Same history in, same coordinates out.
Whether that actually produces a topographic map — neighbours similar, the way
tonotopy is laid out in real auditory cortex — is a CLAIM, so it is measured
(proof/measure_depth.py) and written to results, never asserted.
"""
import gzip
import hashlib
import json
import math
import os
import struct

import numpy as np

import genome
from brain import Brain


# --------------------------------------------------------------- determinism
def _rng_for(*parts):
    """A deterministic little RNG from a stable hash of its arguments.

    Not random.Random(hash(...)): CPython's str hash is salted per process, so
    that would place the same prototype somewhere else tomorrow. sha1 of the
    joined parts is stable across processes, machines and Python versions.
    """
    h = hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).digest()
    seed = struct.unpack("<Q", h[:8])[0]
    return np.random.default_rng(seed)


class Cortex:
    """The layered brain. ``layers[0]`` is the ordinary Brain, untouched."""

    def __init__(self, dim0, layers=None, log=None):
        self.dim0 = int(dim0)
        self.log = log or (lambda msg: None)
        self.layers = list(layers) if layers else [Brain(self.dim0)]
        self.layers[0].max_protos = genome.MAX_PROTOTYPES
        for k in range(1, len(self.layers)):
            self.layers[k].max_protos = genome.LAYER_MAX_PROTOTYPES
        # bookkeeping the fence reads
        self.sleep_counts = [[] for _ in range(genome.MAX_LAYERS)]
        self.distinct = [set() for _ in range(genome.MAX_LAYERS)]     # THIS epoch
        self.distinct_best = [0 for _ in range(genome.MAX_LAYERS)]    # best epoch
        self.distinct_total = [0 for _ in range(genome.MAX_LAYERS)]   # cumulative
        self.births = []                # [{layer, beat, dim, why}]
        self.backfilled = [0 for _ in range(genome.MAX_LAYERS)]
        self.beat = self.layers[0].beat
        self.place_all()

    # ------------------------------------------------------------- geometry
    def percept_dim(self, k):
        """Width of layer k's percept: fixed at LAYER_SLOTS x the width below."""
        d = self.dim0
        for _ in range(k):
            d *= genome.LAYER_SLOTS
        return d

    def n_layers(self):
        return len(self.layers)

    def counts(self):
        return [len(b.protos) for b in self.layers]

    # ---------------------------------------------------------------- space
    def place_all(self):
        """Give a body to every prototype that arrived without one.

        An old single-layer state/brain.json.gz has no positions at all — it
        was written before this file existed, so its prototypes are backfilled
        in birth order.

        A BACKFILLED MAP IS NOT THE MAP THE ORGANISM WOULD HAVE GROWN, and
        this docstring used to claim it was. Two reasons it cannot be: the
        backfill sees each prototype's vector as it is TODAY, after however
        much Hebbian drift, not as it was at spawn; and it sees only the
        prototypes that SURVIVED pruning, not the neighbours that were there
        at the time and have since died. It is a faithful application of the
        same rule to the history that is left, which is the best that can be
        done for a brain that predates positions — and it is counted
        (``backfilled``) so any measurement over those positions can say so.
        """
        for k, brain in enumerate(self.layers):
            missing = [i for i, p in enumerate(brain.protos)
                       if p.get("pos") is None]
            if k < len(self.backfilled):
                self.backfilled[k] += len(missing)
            for i in sorted(missing, key=lambda j: (brain.protos[j]["birth_step"], j)):
                self.place(k, i)

    def place(self, k, idx):
        """Place prototype ``idx`` of layer ``k``. Cheap, incremental, exact.

        Weighted mean of its k nearest already-placed neighbours' positions,
        pushed outward in proportion to how unlike them it is, plus a
        deterministic jitter, then a few steps of light repulsion so nothing
        piles up. Only the newborn moves: history keeps its coordinates.
        """
        brain = self.layers[k]
        p = brain.protos[idx]
        z = k * genome.POS_Z_SPACING
        placed = [(j, q) for j, q in enumerate(brain.protos)
                  if j != idx and q.get("pos") is not None]
        rng = _rng_for(genome.SEED, "pos", k, len(placed), p["birth_step"])
        jit = rng.uniform(-genome.POS_JITTER, genome.POS_JITTER, size=2)

        # Rounded to 4 places on assignment, which is exactly what the state
        # file stores — so a prototype's position in memory and its position
        # after a save/load are the SAME number, not almost the same one.
        if not placed:
            p["pos"] = [round(float(jit[0]), 4), round(float(jit[1]), 4),
                        round(float(z), 4)]
            return p["pos"]

        vec = np.asarray(p["vec"], dtype=np.float64)
        sims = np.array([float(np.asarray(q["vec"], dtype=np.float64) @ vec)
                         for _, q in placed])
        order = np.argsort(-sims)[:genome.POS_K_NEIGHBOURS]
        w = np.clip(sims[order], 0.0, None) + 1e-6
        near = np.array([placed[o][1]["pos"][:2] for o in order],
                        dtype=np.float64)
        base = (w[:, None] * near).sum(axis=0) / w.sum()

        # how far out: an unrelated newborn must not sit on top of whatever
        # happened to be its "nearest" neighbour.
        dissim = float(np.clip(1.0 - sims[order].max(), 0.0, 2.0))
        ang = float(rng.uniform(0.0, 2.0 * math.pi))
        out = genome.POS_SPREAD * dissim * np.array([math.cos(ang),
                                                     math.sin(ang)])
        xy = base + out + jit

        others = np.array([q["pos"][:2] for _, q in placed], dtype=np.float64)
        for _ in range(genome.POS_REPULSION_STEPS):
            d = xy - others
            dist = np.linalg.norm(d, axis=1)
            close = dist < genome.POS_MIN_DIST
            if not close.any():
                break
            push = np.zeros(2)
            for j in np.where(close)[0]:
                n = dist[j]
                unit = (d[j] / n) if n > 1e-9 else np.array(
                    [math.cos(ang), math.sin(ang)])
                push += unit * (genome.POS_MIN_DIST - n)
            xy = xy + 0.5 * push
        p["pos"] = [round(float(xy[0]), 4), round(float(xy[1]), 4),
                    round(float(z), 4)]
        return p["pos"]

    def positions(self, k=None):
        """[(layer, index, (x,y,z))] for every placed prototype."""
        out = []
        for li, brain in enumerate(self.layers):
            if k is not None and li != k:
                continue
            for i, p in enumerate(brain.protos):
                if p.get("pos") is not None:
                    out.append((li, i, tuple(float(x) for x in p["pos"])))
        return out

    # ------------------------------------------------------ the windowed read
    def window_bounds(self, rms):
        """[(start, stop)] frame windows the cortex reads the cochlea through.

        Windows live INSIDE the speech span, found with the ear's own rule and
        the ear's own constant (rms above EAR_SPEECH_FRAC of the peak — the
        exact test ears.pool uses for the cochlea). Without this the trace
        spends most of its steps on the silence around a 0.87 s recording, and
        a silent window is not quiet to the cochlea: level is normalised away
        frame by frame, so silence arrives as loud, confident noise. No new ear
        parameter is invented here; it is the ear's own boundary, reused.

        Never shorter than genome.EAR_SLICES frames — the cochlea splits what
        it is given into EAR_SLICES pieces, and a piece with no frames in it
        would be a NaN, not a percept.
        """
        rms = np.asarray(rms, dtype=np.float64)
        n_all = len(rms)
        win = max(genome.EAR_SLICES,
                  int(round(genome.CORTEX_WINDOW_MS / genome.HOP_MS)))
        hop = max(1, int(round(genome.CORTEX_HOP_MS / genome.HOP_MS)))
        if n_all < genome.EAR_SLICES:
            return []
        peak = float(np.max(rms)) if n_all else 0.0
        live = np.where(rms > peak * genome.EAR_SPEECH_FRAC)[0]
        # The fallback is on the COUNT of live frames, not the width of their
        # span — character for character the test ears.pool makes for the
        # cochlea. A different fallback here would be a second, divergent
        # speech-span rule living outside the frozen ear, which is exactly what
        # the freeze forbids.
        if len(live) < genome.EAR_SLICES:
            lo, hi = 0, n_all
        else:
            lo, hi = int(live[0]), int(live[-1]) + 1
        n = hi - lo
        if n <= win:
            return [(lo, hi)]
        out = [(lo + s, lo + s + win) for s in range(0, n - win + 1, hop)]
        if out[-1][1] < hi:                       # never drop the tail
            out.append((hi - win, hi))
        return out

    def trace0(self, ears, feats, rms):
        """Layer 0's firing trace over one sound: [(idx, sim)], in time order.

        READ-ONLY — ``nearest``, never ``hear``. Layer 0 learns from the whole
        utterance exactly as it always has; this only asks it what each moment
        most resembles.
        """
        out = []
        for a, b in self.window_bounds(rms):
            v = ears.pool(feats[a:b], rms[a:b])
            if not np.isfinite(v).all():
                continue
            idx, sim, _ = self.layers[0].nearest(v)
            if idx is None:
                continue
            out.append((int(idx), float(sim)))
        return out

    # ----------------------------------------------------------- the percept
    def percepts_from(self, k, below_trace):
        """Layer k's percepts, from the trace layer k-1 emitted.

        One percept per sliding group of LAYER_SLOTS consecutive firings —
        so a layer above always has a sequence of its own to be about.
        """
        below = self.layers[k - 1]
        s = genome.LAYER_SLOTS
        if len(below_trace) < s:
            return []
        out = []
        for t in range(len(below_trace) - s + 1):
            parts = []
            ok = True
            for idx, sim in below_trace[t:t + s]:
                if idx >= len(below.protos):      # pruned since; skip the group
                    ok = False
                    break
                parts.append(np.asarray(below.protos[idx]["vec"],
                                        dtype=np.float64) * max(sim, 0.0))
            if not ok:
                continue
            v = np.concatenate(parts)
            n = float(np.linalg.norm(v))
            if n <= 0:
                continue
            out.append(v / n)
        return out

    @staticmethod
    def _key(below_trace, s):
        """The distinct-sequence keys in one trace: tuples of winner indices.

        A PROTOTYPE INDEX IS ONLY MEANINGFUL BETWEEN TWO SLEEPS. sleep.py's
        _prune rebuilds the prototype list and renumbers every survivor (it
        remaps brain.elig through kept_idx and nothing else). So a set of these
        keys accumulated across a prune is nonsense in both directions: the
        same sound recorded on either side of the night becomes two keys, and
        two different sounds can collapse onto one. Left running, the birth
        gate would have been satisfiable by re-indexing churn alone — measured
        on 2026-08-21: 3,625 "distinct" sequences against a gate of 200, on a
        layer 0 that had been pruned six times.

        The fix is in the accounting, not here: ``distinct`` is an EPOCH set,
        cleared at every sleep (see reset_distinct), so every key in it was
        made in one index space. The gate therefore asks a stronger and
        cleaner question — N distinct sequences BETWEEN two sleeps.
        """
        return {tuple(i for i, _ in below_trace[t:t + s])
                for t in range(len(below_trace) - s + 1)}

    # -------------------------------------------------------------- hearing
    def hear_path(self, ears, path, chem, beat, learn=True, learn0=None):
        """One sound arrives. Every layer hears it, each from the one below.

        Returns the layer-0 record (so every existing caller keeps working)
        with two additions: ``layers`` (one record per layer) and
        ``layer_protos``.

        ``learn0`` exists for the EXAMINER only. Setting it False while
        ``learn`` stays True exposes the layers ABOVE to new audio while
        holding layer 0 exactly as the organism grew it — so a depth
        comparison is about depth, and not about layer 0 quietly getting extra
        training the flat arm never had. Life never passes it.
        """
        feats, rms = ears.frames(path)            # the heldout guard lives here
        vec0 = ears.pool(feats, rms)              # == ears.utterance(path)
        return self.hear_frames(ears, feats, rms, vec0, chem, beat, learn,
                                learn0)

    def hear_frames(self, ears, feats, rms, vec0, chem, beat, learn=True,
                    learn0=None):
        self.beat = int(beat)
        learn0 = learn if learn0 is None else bool(learn0)
        rec0 = self.layers[0].hear(vec0, chem, beat, learn=learn0)
        if learn0 and rec0.get("spawned"):
            self.place(0, rec0["idx"])

        below_trace = self.trace0(ears, feats, rms)
        records = [dict(rec0, layer=0)]
        for k in range(1, len(self.layers) + 1):
            # Evidence is only gathered for the ONE layer that could be born
            # next — the layer above the top. Counting it for layers that
            # already exist would grow a set nobody will ever read again.
            if k == len(self.layers) and k < genome.MAX_LAYERS:
                keys = self._key(below_trace, genome.LAYER_SLOTS)
                self.distinct_total[k] += len(keys)
                if len(self.distinct[k]) < genome.LAYER_DISTINCT_CAP:
                    self.distinct[k] |= keys
            if k >= len(self.layers):
                break
            percepts = self.percepts_from(k, below_trace)
            trace_k, best = [], None
            # Every layer's own clock ticks. Without this a layer above 0 keeps
            # the beat it was born at forever, so Brain.strictness() freezes —
            # a layer born late would be born already adult and barely able to
            # spawn (found in review, 2026-08-21).
            self.layers[k].beat = int(beat)
            for v in percepts:
                r = self.layers[k].hear(v, chem, beat, learn=learn)
                if learn and r.get("spawned"):
                    self.place(k, r["idx"])
                if r["idx"] is None:
                    continue
                trace_k.append((int(r["idx"]), float(r["sim"])))
                if best is None or r["sim"] > best["sim"]:
                    best = dict(r, layer=k)
            records.append(best or {"layer": k, "idx": None, "sim": 0.0,
                                    "attraction": 0.0, "surprise": 1.0,
                                    "spawned": False})
            below_trace = trace_k

        out = dict(rec0)
        out["layers"] = records
        out["layer_protos"] = self.counts()
        return out

    def read_path(self, ears, path):
        """Hear WITHOUT learning: the full percept stack for one sound.

        The examiner's way in. Returns {vec0, trace0, per-layer traces and the
        most confident percept/winner of each layer}.
        """
        feats, rms = ears.frames(path)
        vec0 = ears.pool(feats, rms)
        return self.read_frames(ears, feats, rms, vec0)

    def read_frames(self, ears, feats, rms, vec0):
        idx0, sim0, _ = self.layers[0].nearest(vec0)
        trace = self.trace0(ears, feats, rms)
        out = {"vec0": vec0, "top0": (idx0, sim0), "traces": [trace],
               "percepts": [None], "best": [(idx0, sim0)]}
        below_trace = trace
        for k in range(1, len(self.layers)):
            percepts = self.percepts_from(k, below_trace)
            trace_k, best_v, best = [], None, (None, 0.0)
            for v in percepts:
                idx, sim, _ = self.layers[k].nearest(v)
                if idx is None:
                    continue
                trace_k.append((int(idx), float(sim)))
                if best_v is None or sim > best[1]:
                    best_v, best = v, (int(idx), float(sim))
            out["traces"].append(trace_k)
            out["percepts"].append(best_v)
            out["best"].append(best)
            below_trace = trace_k
        return out

    # ------------------------------------------------------------ the fence
    def settle_tolerance(self, count):
        """How much a layer of this size may still move and still count as
        settled: LAYER_SETTLE_TOL prototypes, or LAYER_SETTLE_FRAC of itself."""
        return max(genome.LAYER_SETTLE_TOL,
                   genome.LAYER_SETTLE_FRAC * float(count))

    def settle_trend(self, k):
        """(older window mean, recent window mean) or None if too little sleep."""
        h = self.sleep_counts[k]
        w = genome.LAYER_SETTLE_SLEEPS
        if len(h) < 2 * w:
            return None
        older = h[-2 * w:-w]
        recent = h[-w:]
        return (sum(older) / w, sum(recent) / w)

    def settled(self, k):
        """Has layer k stopped GROWING? (a) of the birth preconditions.

        The trend, not the nightly churn. This was first written sleep-to-
        sleep — every one of the last N deltas within tolerance — and it could
        not fire on this organism at all, for a reason worth writing down:
        genome.PRUNE_UNUSED_BEATS (4000) is twice genome.SLEEP_EVERY (2000),
        so a prototype born in one epoch comes up for attrition two epochs
        later and the count runs a period-2 saw. Measured over 15 sleeps on
        2026-08-21, layer 0 gave deltas
            +24 -8 +26 +15 -21 +23 +7 -23 +21 +7 -7 -27 +34 -4
        — an amplitude near 30 on a base of ~120 that never damps — while the
        3-sleep rolling mean went
            74 -> 88 -> 99 -> 106 -> 112 -> 115 -> 117 -> 119 -> 120 -> 127
            -> 118 -> 118 -> 119
        and plainly flattened. The layer HAD stopped growing; only its
        membership kept turning over. A rule that reads the churn instead of
        the trend measures the sleep cadence, not development, and would have
        held depth shut forever on a brain that was ready.

        So: compare the mean of the last LAYER_SETTLE_SLEEPS sleeps with the
        mean of the LAYER_SETTLE_SLEEPS before them, and call the layer
        settled when the two agree inside settle_tolerance. Slow steady growth
        still fails it (a drift of 2 prototypes a night moves the means apart
        by more than the tolerance); a saw that goes nowhere passes.
        """
        t = self.settle_trend(k)
        if t is None:
            return False
        older, recent = t
        return abs(recent - older) <= self.settle_tolerance(older)

    def birth_status(self, k=None):
        """Why the next layer is or is not being born. Honest, printable."""
        k = k if k is not None else len(self.layers)
        if k >= genome.MAX_LAYERS:
            return {"layer": k, "born": False, "why": "MAX_LAYERS reached",
                    "max_layers": genome.MAX_LAYERS}
        return {
            "layer": k,
            "born": False,
            "settled_below": self.settled(k - 1),
            "sleep_counts_below": list(self.sleep_counts[k - 1][-8:]),
            "settle_trend_below": self.settle_trend(k - 1),
            "settle_tolerance_now": self.settle_tolerance(
                len(self.layers[k - 1].protos)),
            "distinct_sequences_this_epoch": len(self.distinct[k]),
            "distinct_sequences_best_epoch": self.distinct_best[k],
            "distinct_sequences_total": self.distinct_total[k],
            "distinct_needed": genome.LAYER_BIRTH_MIN_EVENTS,
        }

    def after_sleep(self, beat):
        """Called by sleep.py once per sleep, AFTER pruning. May birth a layer.

        The birth decision is made FIRST, on the epoch that just ended, and
        only then is the epoch's evidence cleared — because pruning has just
        renumbered the prototypes those keys refer to (see _key).
        """
        for k, brain in enumerate(self.layers):
            self.sleep_counts[k].append(len(brain.protos))
            if len(self.sleep_counts[k]) > 64:
                del self.sleep_counts[k][:-64]
        born = self.maybe_birth(beat)
        self.reset_distinct()
        return born

    def reset_distinct(self):
        """End the epoch: remember how big it got, then forget the keys."""
        for k in range(genome.MAX_LAYERS):
            self.distinct_best[k] = max(self.distinct_best[k],
                                        len(self.distinct[k]))
            self.distinct[k] = set()

    def maybe_birth(self, beat):
        """The birth itself. Nothing here can be forced by a human."""
        k = len(self.layers)
        if k >= genome.MAX_LAYERS:
            return None
        if not self.settled(k - 1):
            return None
        if len(self.distinct[k]) < genome.LAYER_BIRTH_MIN_EVENTS:
            return None
        dim = self.percept_dim(k)
        layer = Brain(dim, max_protos=genome.LAYER_MAX_PROTOTYPES,
                      age_offset=int(beat))       # its own childhood starts now
        layer.beat = int(beat)
        self.layers.append(layer)
        rec = {"layer": k, "beat": int(beat), "dim": dim,
               "distinct_sequences": len(self.distinct[k]),
               "below_protos": len(self.layers[k - 1].protos),
               "settle_history": list(self.sleep_counts[k - 1][-8:]),
               "settle_trend": self.settle_trend(k - 1)}
        self.births.append(rec)
        self.log(f"[cortex] *** LAYER {k} IS BORN *** at beat {beat}: "
                 f"dim {dim} ({genome.LAYER_SLOTS} slots x "
                 f"{self.percept_dim(k - 1)}), after "
                 f"{rec['distinct_sequences']} distinct sequences and a "
                 f"settled layer {k - 1} ({rec['settle_history']}). "
                 f"Nobody switched it on.")
        return rec

    # ---------------------------------------------------------- persistence
    def to_state(self):
        return {
            "version": 1,
            "beat": int(self.beat),
            "dim0": self.dim0,
            "n_layers": len(self.layers),
            "max_layers": genome.MAX_LAYERS,
            "slots": genome.LAYER_SLOTS,
            "sleep_counts": [list(h) for h in self.sleep_counts],
            # The epoch set is deliberately NOT persisted: its keys are
            # prototype indices, which are only meaningful between two sleeps
            # (see _key), and a restart is not a sleep. What survives is what
            # is index-free — how big the best epoch got, and the running
            # total — so history is reported without being reused.
            "distinct_this_epoch": [len(d) for d in self.distinct],
            "distinct_best": list(self.distinct_best),
            "distinct_total": list(self.distinct_total),
            "backfilled": list(self.backfilled),
            "births": list(self.births),
            # layer 0 lives in its own file (BRAIN_FILE) and is NOT duplicated
            "layers": [b.to_state() for b in self.layers[1:]],
        }

    def save(self, brain_path=None, cortex_path=None):
        """Layer 0 first (the file every existing tool reads), then the rest.

        Each file is written tmp + os.replace, so neither can ever be torn.
        They are two files on purpose: state/brain.json.gz keeps its exact old
        shape, so measure.py, serve.py, tournament.py and an eran1 that has
        not been updated yet all keep working unchanged. A crash between the
        two writes leaves layer 0 one checkpoint ahead of the layers above it
        — recoverable and logged, never corrupt.
        """
        brain_path = brain_path or genome.BRAIN_FILE
        cortex_path = cortex_path or genome.CORTEX_FILE
        self.layers[0].beat = int(self.beat)
        self.layers[0].save(brain_path)
        os.makedirs(os.path.dirname(cortex_path), exist_ok=True)
        raw = json.dumps(self.to_state()).encode("utf-8")
        tmp = cortex_path + ".tmp"
        with gzip.open(tmp, "wb") as f:
            f.write(raw)
        os.replace(tmp, cortex_path)

    @classmethod
    def load(cls, dim0, brain_path=None, cortex_path=None, log=None):
        """Wake the whole stack.

        BACKWARDS COMPATIBILITY IS MANDATORY. An existing single-layer
        state/brain.json.gz — ERAN is alive on eran1 right now with a real
        history — must load and BECOME layer 0 with no rebirth, no archive, no
        loss. Losing it would repeat the worst scar in this project (11.9M
        steps destroyed). proof/test_organism.py tests exactly this.
        """
        brain_path = brain_path or genome.BRAIN_FILE
        cortex_path = cortex_path or genome.CORTEX_FILE
        log = log or (lambda msg: None)
        layers = []
        if os.path.exists(brain_path):
            layers.append(Brain.load(brain_path))
        else:
            layers.append(Brain(dim0))
        state = {}
        if os.path.exists(cortex_path):
            try:
                with gzip.open(cortex_path, "rb") as f:
                    state = json.loads(f.read().decode("utf-8"))
            except (OSError, ValueError) as e:
                log(f"[cortex] cortex file unreadable ({e}); the layers above "
                    f"0 start over. Layer 0 is untouched.")
                state = {}
        # A layer above 0 is only meaningful against the exact geometry it grew
        # in: its width is LAYER_SLOTS x the width below. If genome.LAYER_SLOTS
        # or the ear moved since it was written, that layer is looking at a
        # shape that no longer exists. Say so at WAKE and drop it — the
        # alternative is a dimension mismatch exploding inside a live beat, and
        # this codebase already has that scar (the onset ear, 2026-08-21).
        # Layer 0 is never dropped: it is the history.
        for k, s in enumerate(state.get("layers", []), start=1):
            expect = layers[0].dim * (genome.LAYER_SLOTS ** k)
            if int(s.get("dim", -1)) != expect:
                log(f"[cortex] layer {k} on disk is dim {s.get('dim')} but "
                    f"this genome makes it {expect} "
                    f"(LAYER_SLOTS={genome.LAYER_SLOTS}, layer 0 dim "
                    f"{layers[0].dim}). Layer {k} and everything above it are "
                    f"DROPPED and will have to be born again. Layer 0 is "
                    f"untouched.")
                break
            layers.append(_brain_from_state(s))
        c = cls(layers[0].dim, layers=layers, log=log)

        def _fit(name, default, cast=list):
            """Restore a per-layer list, padded or trimmed to MAX_LAYERS.

            Trimming matters: MAX_LAYERS is the fence and Iddo may lower it.
            Without this, a lowered fence left these lists shorter than the
            layer list and after_sleep's append blew up with IndexError inside
            sleep — in a live beat, unguarded.
            """
            v = list(state.get(name, default))
            v = v[:genome.MAX_LAYERS]
            while len(v) < genome.MAX_LAYERS:
                v.append(cast())
            return v

        c.sleep_counts = _fit("sleep_counts", c.sleep_counts, list)
        c.distinct = [set() for _ in range(genome.MAX_LAYERS)]   # a new epoch
        c.distinct_best = _fit("distinct_best", c.distinct_best, int)
        c.distinct_total = _fit("distinct_total", c.distinct_total, int)
        c.backfilled = _fit("backfilled", c.backfilled, int)
        c.births = list(state.get("births", []))
        if state and int(state.get("slots", genome.LAYER_SLOTS)) != \
                genome.LAYER_SLOTS:
            log(f"[cortex] this file was written with LAYER_SLOTS="
                f"{state.get('slots')} and the genome now says "
                f"{genome.LAYER_SLOTS}. The layers above 0 were dropped above; "
                f"the epoch evidence is not reused across a slot change.")
        if state and int(state.get("beat", c.layers[0].beat)) != c.layers[0].beat:
            log(f"[cortex] layer 0 is at beat {c.layers[0].beat}, the layers "
                f"above at {state.get('beat')}: one checkpoint apart after a "
                f"crash. Kept, not discarded — the layers above learn on.")
        c.beat = c.layers[0].beat
        c.place_all()
        return c


def _brain_from_state(state):
    b = Brain(int(state["dim"]), max_protos=genome.LAYER_MAX_PROTOTYPES,
              age_offset=int(state.get("age_offset", 0)))
    b.beat = int(state.get("beat", 0))
    b.heard = int(state.get("heard", 0))
    b.sim_hist = [float(s) for s in state.get("sim_hist", [])]
    b.bar = (float(state["bar"]) if state.get("bar") is not None else None)
    for p in state["protos"]:
        b.protos.append({
            "vec": np.asarray(p["vec"], dtype=np.float64),
            "mass": float(p["mass"]),
            "birth_step": int(p["birth_step"]),
            "last_used": int(p["last_used"]),
            "scar": float(p["scar"]),
            "n_abs": int(p.get("n_abs", 0)),
            "s_sum": float(p.get("s_sum", 0.0)),
            "s_sq": float(p.get("s_sq", 0.0)),
            "pos": ([float(x) for x in p["pos"]]
                    if p.get("pos") is not None else None),
        })
    b._dirty()
    return b
