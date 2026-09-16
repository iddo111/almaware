"""brain.py — the legible prototype memory. Growth-on-surprise, Hebbian pull.

Prototypes are dicts you can read: {vec, mass, birth_step, last_used, scar}.
hear(vec): nearest by cosine; a vector too far from everything it knows spawns
a NEW prototype (surprise grows the brain, inside the fence); a familiar one
pulls its prototype closer (Hebbian), at a rate the chemistry sets.

Eligibility traces remember which prototypes were recently active, so a parent
tap minutes later still pays exactly the pathways that were used.

Persistence is atomic (tmp + os.replace) and human-readable when gunzipped.
Embodies: self-sizing, never-fake (the file IS the brain, zcat and read it).
"""
import gzip
import json
import math
import os

import numpy as np

import genome


class Brain:
    """One layer of prototype memory.

    ADDITIVE, 2026-08-21 (body/cortex.py): two fields that change nothing for a
    layer-0-only organism.
      * ``max_protos`` — the fence, per instance. Defaults to
        genome.MAX_PROTOTYPES, so a bare Brain() behaves exactly as before; the
        Cortex lowers it for layers above 0 (genome.LAYER_MAX_PROTOTYPES).
      * ``p["pos"]`` — an optional 3D coordinate the Cortex assigns at spawn.
        Written only when present, read only when present: an old
        state/brain.json.gz has none and loads untouched, and a new file read
        by old code is ignored key-for-key (load() names the keys it wants).
      * ``age_offset`` — the beat this layer was BORN at, so its critical
        period starts then and not at the organism's birth. Layer 0 is born
        with the organism, so its offset is 0 and nothing changes. A layer
        born at beat 700,000 without this is a newborn wearing an adult's
        strictness (STRICTNESS_ADULT from its very first percept) and can
        barely spawn at all — measured as a bug on 2026-08-21. Every layer
        gets its own childhood.
    """

    def __init__(self, dim, max_protos=None, age_offset=0):
        self.dim = int(dim)
        self.max_protos = int(max_protos if max_protos is not None
                              else genome.MAX_PROTOTYPES)
        self.age_offset = int(age_offset)
        self.protos = []          # [{vec, mass, birth_step, last_used, scar}]
        self._mat = None          # cached (n, dim) matrix for fast cosine
        self.elig = {}            # proto index -> trace strength
        self.beat = 0             # last beat this brain lived through
        self.heard = 0            # utterances digested
        self.sim_hist = []        # recent best-match similarities (self-calibration)
        self.bar = None           # the novelty homeostat's current setting

    # -------------------------------------------------------- novelty (self-tuning)
    def spawn_target(self):
        """How open should a child this age be to a brand-new prototype?

        A critical period: wide open at birth, closing GRADUALLY with living
        (Iddo's law — a baby's ear and mouth do change, but never by surgery).
        """
        age = self.age() / genome.CRITICAL_PERIOD_BEATS
        decay = float(np.exp(-age))
        return (genome.SPAWN_RATE_ADULT
                + (genome.SPAWN_RATE_INFANT - genome.SPAWN_RATE_ADULT) * decay)

    def novelty_bar(self):
        """How different must a sound be to deserve its own prototype?

        An OUTLIER test against the child's own experience: a sound is new
        when it matches worse than it usually manages — worse than
        mean - k*sd of its recent matches. k is the child's strictness, and
        it is the thing that grows up: a newborn calls almost anything new
        (k small), a matured brain only genuinely strange things (k large),
        and the change is gradual, never surgery.

        This is deliberately NOT a spawn-RATE target. Chasing a rate is a
        trap that was measured on 2026-08-21: more prototypes -> better
        matches -> fewer "novel" sounds -> the bar climbs to keep the rate up
        -> more prototypes. It ran away to 66 blobs for 3 sounds and cost the
        child its accuracy. An outlier test converges instead: once the brain
        covers what it hears, outliers become rare on their own.
        """
        if len(self.sim_hist) < genome.NOVELTY_MIN_HISTORY:
            return genome.NOVELTY_THRESH
        h = np.asarray(self.sim_hist[-genome.NOVELTY_WINDOW:], dtype=float)
        self.bar = float(np.clip(h.mean() - self.strictness() * h.std(),
                                 0.0, 0.999))
        return self.bar

    def tolerance(self, idx):
        """How much variety THIS prototype already accepts.

        Each prototype keeps the running mean and spread of how well the
        things it absorbed matched it — its own tuning curve. A sound is new
        only if it falls outside that curve (below mean - k*sd). This is the
        local test that finally converged on 2026-08-21: a global bar chased
        itself (more prototypes -> better matches -> higher bar -> more
        prototypes) but a prototype's own tolerance simply widens until it
        covers its own variants, and then stops.

        A young prototype has no curve yet, so it accepts its first
        TOLERANCE_WARMUP members unconditionally — an infant cluster is not
        allowed to be picky.
        """
        p = self.protos[idx]
        n = p.get("n_abs", 0)
        if n < genome.TOLERANCE_WARMUP:
            # Generous, not blind: a young prototype takes anything that even
            # resembles it, but a sound pointing the other way (cosine <= 0)
            # is a different thing and gets its own prototype.
            return genome.TOLERANCE_WARMUP_FLOOR
        mean = p["s_sum"] / n
        var = max(0.0, p["s_sq"] / n - mean * mean)
        # A tuning curve is never infinitely sharp. Without this floor a
        # prototype fed identical copies gets sd=0, so its own sound lands a
        # hair below its own mean and it clones itself forever (measured
        # 2026-08-21: 3 prototypes from one repeated sound).
        sd = max(var ** 0.5, genome.TOLERANCE_MIN_SD)
        return mean - self.strictness() * sd

    def _absorb_stat(self, idx, sim):
        p = self.protos[idx]
        p["n_abs"] = p.get("n_abs", 0) + 1
        p["s_sum"] = p.get("s_sum", 0.0) + float(sim)
        p["s_sq"] = p.get("s_sq", 0.0) + float(sim) * float(sim)

    def age(self):
        """Beats THIS layer has lived, counted from its own birth.

        Layer 0's age_offset is 0, so this is exactly the old
        max(0.0, float(self.beat)) and nothing about the existing organism
        moves. A layer born later starts its critical period when it is born.
        """
        return max(0.0, float(self.beat) - float(self.age_offset))

    def strictness(self):
        """k: how many standard deviations below its own average a match must
        fall before the child calls it a new thing. Grows with living."""
        age = self.age() / genome.CRITICAL_PERIOD_BEATS
        grown = 1.0 - float(np.exp(-age))
        return (genome.STRICTNESS_INFANT
                + (genome.STRICTNESS_ADULT - genome.STRICTNESS_INFANT) * grown)

    # ------------------------------------------------------------- internals
    def _matrix(self):
        if self._mat is None or len(self._mat) != len(self.protos):
            if self.protos:
                self._mat = np.stack([p["vec"] for p in self.protos])
            else:
                self._mat = np.zeros((0, self.dim))
        return self._mat

    def _dirty(self):
        self._mat = None

    # -------------------------------------------------------------- nearest
    def nearest(self, vec):
        """(index, raw cosine sim, effective attraction) of the best prototype.

        Attraction = sim - scar: a scarred prototype pulls less (the down-tap
        did its work). Returns (None, 0, 0) on an empty brain.
        """
        m = self._matrix()
        if not len(m):
            return None, 0.0, 0.0
        sims = m @ vec                        # all vecs are L2-normalized
        scars = np.array([p["scar"] for p in self.protos])
        att = sims - scars
        i = int(np.argmax(att))
        return i, float(sims[i]), float(att[i])

    # ----------------------------------------------------------------- hear
    def hear(self, vec, chem, beat, learn=True):
        """One utterance vector arrives. Spawn on surprise, else Hebbian pull."""
        idx, sim, att = self.nearest(vec)
        surprise = 1.0 - sim if idx is not None else 1.0
        spawned = False
        if learn:
            if (idx is None or sim < self.tolerance(idx)) \
                    and len(self.protos) < self.max_protos:
                self.protos.append({
                    "vec": np.asarray(vec, dtype=np.float64).copy(),
                    "mass": 1.0, "birth_step": beat,
                    "last_used": beat, "scar": 0.0,
                    "n_abs": 0, "s_sum": 0.0, "s_sq": 0.0,
                })
                idx = len(self.protos) - 1
                spawned = True
                self._dirty()
            elif idx is not None:
                eta = genome.ETA0 * chem.plasticity()
                p = self.protos[idx]
                v = p["vec"] + eta * (np.asarray(vec) - p["vec"])
                n = np.linalg.norm(v)
                p["vec"] = v / n if n > 0 else v
                p["mass"] += 1.0
                p["last_used"] = beat
                self._absorb_stat(idx, sim)
                self._dirty()
            if idx is not None:
                self.elig[idx] = 1.0          # tag the pathway (for the parent)
                self.sim_hist.append(float(sim))
                if len(self.sim_hist) > genome.NOVELTY_WINDOW:
                    del self.sim_hist[:-genome.NOVELTY_WINDOW]
            self.heard += 1
        return {"idx": idx, "sim": sim, "attraction": att,
                "surprise": surprise, "spawned": spawned}

    # ---------------------------------------------------------- eligibility
    def decay_traces(self):
        f = math.exp(-1.0 / genome.TRACE_TAU)
        dead = []
        for i in self.elig:
            self.elig[i] *= f
            if self.elig[i] < genome.TRACE_FLOOR:
                dead.append(i)
        for i in dead:
            del self.elig[i]

    def pay_trace(self, kind, chem):
        """Parent payout through the traces. up: mass x10 under the OXT lift;
        down: valence scar (attraction drops); fire: the big bonus."""
        lift = 1.0 + chem.oxt
        paid = 0
        for i, e in list(self.elig.items()):
            if i >= len(self.protos):
                continue
            p = self.protos[i]
            if kind == "up":
                p["mass"] += genome.TAP_UP_BONUS * e * lift
            elif kind == "fire":
                p["mass"] += genome.TAP_FIRE_BONUS * e * lift
            elif kind == "down":
                p["scar"] = min(1.0, p["scar"] + genome.SCAR_HIT * e)
            paid += 1
        return paid

    # --------------------------------------------------------------- reading
    def total_mass(self):
        return float(sum(p["mass"] for p in self.protos))

    def top_protos(self, k=10):
        order = sorted(range(len(self.protos)),
                       key=lambda i: -self.protos[i]["mass"])
        return order[:k]

    # ----------------------------------------------------------- persistence
    def _proto_state(self, p):
        d = {
            "vec": [round(float(x), 6) for x in p["vec"]],
            "mass": round(float(p["mass"]), 3),
            "birth_step": int(p["birth_step"]),
            "last_used": int(p["last_used"]),
            "scar": round(float(p["scar"]), 4),
            "n_abs": int(p.get("n_abs", 0)),
            "s_sum": round(float(p.get("s_sum", 0.0)), 5),
            "s_sq": round(float(p.get("s_sq", 0.0)), 5),
        }
        if p.get("pos") is not None:          # only if the cortex placed it
            d["pos"] = [round(float(x), 4) for x in p["pos"]]
        return d

    def to_state(self):
        return {
            "dim": self.dim, "beat": self.beat, "heard": self.heard,
            "age_offset": self.age_offset,
            "sim_hist": [round(float(s), 5) for s in self.sim_hist[-genome.NOVELTY_WINDOW:]],
            "bar": (round(float(self.bar), 6) if self.bar is not None else None),
            "protos": [self._proto_state(p) for p in self.protos],
        }

    def save(self, path=None):
        """Atomic: write tmp, then os.replace. A crash mid-write can never
        leave a corrupt brain — the old file survives untouched."""
        path = path or genome.BRAIN_FILE
        os.makedirs(os.path.dirname(path), exist_ok=True)
        raw = json.dumps(self.to_state()).encode("utf-8")
        tmp = path + ".tmp"
        with gzip.open(tmp, "wb") as f:
            f.write(raw)
        os.replace(tmp, path)

    @classmethod
    def load(cls, path=None):
        path = path or genome.BRAIN_FILE
        with gzip.open(path, "rb") as f:
            state = json.loads(f.read().decode("utf-8"))
        b = cls(state["dim"], age_offset=int(state.get("age_offset", 0)))
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
                # absent in every brain file written before 2026-08-21; the
                # cortex places any prototype that arrives without a body.
                "pos": ([float(x) for x in p["pos"]]
                        if p.get("pos") is not None else None),
            })
        b._dirty()
        return b
