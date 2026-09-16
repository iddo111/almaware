#!/usr/bin/env python3
"""patch_arm.py — install the closed loop into the PARALLEL ARM copy only.

Refuses to run anywhere except ~/eran-brain-pc. The living organism at
~/eran-brain is never touched by this script, by construction: it checks the
absolute path of its own tree before it writes a byte.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.basename(ROOT) != "eran-brain-pc":
    sys.exit(f"REFUSED: this patcher only runs inside ~/eran-brain-pc, not {ROOT}")

BODY = os.path.join(ROOT, "body")

GENOME_ADD = '''

# =============================================================================
# --- THE CLOSED LOOP (predictive coding) — THE FENCE, third wall -------------
# =============================================================================
# Added 2026-09-06 on Iddo's order "תסגור את הלולאה בערן". body/predict.py holds
# the mechanism and the reasoning; these are the only numbers it may read, per
# the law of this file: every constant lives here and nowhere else.
#
# THE REDUCTION IS EXACT. At PC_FEEDBACK_GAIN = 0.0 every closed-loop quantity
# collapses algebraically to the open loop — same surprise, same spawn test,
# same eta — so the two arms differ in exactly one number. This is checked in
# code (pc/run_arms.py --selftest), not asserted here.
PC_FEEDBACK_GAIN = 1.0    # 0.0 = the open loop, exactly. 1.0 = full predictive
                          # coding at baseline chemistry.
PC_TOPK = 8               # prototypes the expectation is mixed from. The
                          # mixture is the point: a single winner would be
                          # 1 - cos with extra steps.
PC_BETA = 12.0            # softmax sharpness over partial-evidence similarity.
                          # Cosines here live in a narrow band near 1, so a
                          # low beta makes the mixture a flat average of the
                          # top-k and predicts the corpus mean.
PC_ERR_GAIN = 1.0         # eta scales by (1 + PC_ERR_GAIN * prediction error):
                          # the child learns most from what it got wrong. At 0
                          # the pull is the plain Hebbian rate.
PC_PE_MIN_SD = 0.02       # twin of TOLERANCE_MIN_SD, in error space: no
                          # prototype's error distribution is infinitely sharp,
                          # or a repeated sound clones itself forever.
PC_PE_WARMUP_CEIL = 2.0   # a young prototype's error tolerance before it has a
                          # distribution — 2.0 is the maximum 1-cos can be, so
                          # it absorbs anything, exactly as TOLERANCE_WARMUP
                          # does on the similarity side.
'''

CHEM_ADD = '''
    # ------------------------------------------- the gate on the top-down path
    def feedback(self):
        """How far the child leans on what it EXPECTS, versus what it hears.

        Added 2026-09-06 with the closed loop. It is the same shape as
        plasticity() — a multiplier built from chemicals that already existed,
        never a new knob bolted on:

            ACh  up  -> attending -> the expectation is worth trusting
            NE   up  -> a jolt    -> the expectation just failed; trust the ears

        which is Yu & Dayan (2005): ACh signals expected uncertainty, NE
        unexpected uncertainty. At baseline (ach=1, ne=0) this is exactly 1.0,
        so genome.PC_FEEDBACK_GAIN means what it says and the chemistry only
        modulates around it.
        """
        if self.frozen:
            return 1.0
        return self.ach / (1.0 + self.ne)
'''

BRAIN_ADD = '''
    # -------------------------------------------------------------- hear_pc
    def pe_tolerance(self, idx):
        """The twin of tolerance(), in PREDICTION-ERROR space.

        tolerance() asks "did this match me worse than my members usually do".
        This asks "did I fail to PREDICT this worse than I usually fail" — and
        the sign flips, because in error space bigger is worse. Same running
        mean, same running spread, same strictness k that grows with the
        child's age, same minimum spread so a repeated sound cannot clone
        itself. Nothing new about the shape of the test; only the quantity.
        """
        p = self.protos[idx]
        n = p.get("pe_n", 0)
        if n < genome.TOLERANCE_WARMUP:
            return genome.PC_PE_WARMUP_CEIL
        mean = p["pe_sum"] / n
        var = max(0.0, p["pe_sq"] / n - mean * mean)
        sd = max(var ** 0.5, genome.PC_PE_MIN_SD)
        return mean + self.strictness() * sd

    def _absorb_pe(self, idx, pe):
        p = self.protos[idx]
        p["pe_n"] = p.get("pe_n", 0) + 1
        p["pe_sum"] = p.get("pe_sum", 0.0) + float(pe)
        p["pe_sq"] = p.get("pe_sq", 0.0) + float(pe) * float(pe)

    def hear_pc(self, vec, chem, beat, predictor, learn=True):
        """hear(), with the arrow that goes back down.

        Everything is a blend `(1-g)*open + g*closed` on g = the chemistry-gated
        feedback gain, so g=0 is the open loop ALGEBRAICALLY, not nearly:

            surprise :  (1-g)(1-sim)          + g * pe
            spawn    :  (1-g)(1-tolerance)    + g * pe_tolerance   as the bar,
                        and the same blend of (1-sim) and pe as the score
            eta      :  ETA0 * plasticity * (1 + g * PC_ERR_GAIN * pe)

        The prototype is still pulled toward the RAW percept and still stored
        in raw signal space — see the header of body/predict.py for why an
        error cannot be a generative model. The error decides *whether* and
        *how hard*, never *toward what*.
        """
        g = float(np.clip(genome.PC_FEEDBACK_GAIN * chem.feedback(), 0.0, 1.0))
        pred = predictor.predict(vec, self._matrix())
        pe = float(pred["pe"])

        idx, sim, att = self.nearest(vec)
        open_bad = 1.0 - sim if idx is not None else 1.0
        bad = (1.0 - g) * open_bad + g * pe
        spawned = False
        if learn:
            if idx is None:
                bar = -1.0                      # empty brain: always spawn
            else:
                bar = ((1.0 - g) * (1.0 - self.tolerance(idx))
                       + g * self.pe_tolerance(idx))
            if (idx is None or bad > bar) and len(self.protos) < self.max_protos:
                self.protos.append({
                    "vec": np.asarray(vec, dtype=np.float64).copy(),
                    "mass": 1.0, "birth_step": beat,
                    "last_used": beat, "scar": 0.0,
                    "n_abs": 0, "s_sum": 0.0, "s_sq": 0.0,
                    "pe_n": 0, "pe_sum": 0.0, "pe_sq": 0.0,
                })
                idx = len(self.protos) - 1
                spawned = True
                self._dirty()
            elif idx is not None:
                eta = (genome.ETA0 * chem.plasticity()
                       * (1.0 + g * genome.PC_ERR_GAIN * pe))
                p = self.protos[idx]
                v = p["vec"] + eta * (np.asarray(vec) - p["vec"])
                n = np.linalg.norm(v)
                p["vec"] = v / n if n > 0 else v
                p["mass"] += 1.0
                p["last_used"] = beat
                self._absorb_stat(idx, sim)
                self._absorb_pe(idx, pe)
                self._dirty()
            if idx is not None:
                self.elig[idx] = 1.0
                self.sim_hist.append(float(sim))
                if len(self.sim_hist) > genome.NOVELTY_WINDOW:
                    del self.sim_hist[:-genome.NOVELTY_WINDOW]
            self.heard += 1
        return {"idx": idx, "sim": sim, "attraction": att,
                "surprise": bad, "spawned": spawned,
                "pe": pe, "open_surprise": open_bad, "g": g,
                "resid_norm": float(pred["resid_norm"]),
                "n_used": int(pred["n_used"])}
'''


def append_once(path, text, marker):
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    if marker in src:
        print(f"  {os.path.basename(path)}: already patched")
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write(src.rstrip("\n") + "\n" + text)
    print(f"  {os.path.basename(path)}: +{len(text)} bytes")


def insert_before(path, text, anchor, marker):
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    if marker in src:
        print(f"  {os.path.basename(path)}: already patched")
        return
    if anchor not in src:
        sys.exit(f"anchor not found in {path}: {anchor!r}")
    src = src.replace(anchor, text + "\n" + anchor, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"  {os.path.basename(path)}: +{len(text)} bytes")


print(f"patching the PARALLEL ARM at {ROOT}")
append_once(os.path.join(BODY, "genome.py"), GENOME_ADD, "PC_FEEDBACK_GAIN")
append_once(os.path.join(BODY, "chemistry.py"), CHEM_ADD, "def feedback(")
insert_before(os.path.join(BODY, "brain.py"), BRAIN_ADD,
              "    # ---------------------------------------------------------- eligibility",
              "def hear_pc(")
print("done. ~/eran-brain (the living organism) was not opened.")
