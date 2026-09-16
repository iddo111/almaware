"""brain.py — the synaptic sequence memory. No tensors; dicts you can read aloud.

Cells = contexts (last k tokens, k=1..4) + 16 bar-phase bump cells.
Synapses = w[cell][next_token], with per-cell count n and eligibility traces.
Learning = the three-factor rule (surprise x chemistry gate), never backprop.
"""
import gzip
import json
import math
import os

import genome


def _ctx_key(order, toks):
    return str(order) + "|" + ",".join(map(str, toks))


def _phase_key(phase):
    return "P|" + str(phase)


_BUMP = [[math.exp(-genome.K_BUMP * min(abs(p - mu), genome.STEPS_PER_BAR - abs(p - mu)) ** 2 / 4.0)
          for mu in range(genome.STEPS_PER_BAR)] for p in range(genome.STEPS_PER_BAR)]


class Brain:
    def __init__(self):
        self.w = {}               # cell -> {token(str): weight}
        self.n = {}               # cell -> times seen
        self.uni = [1.0] * genome.VOCAB   # unigram floor (add-one)
        self.uni_total = float(genome.VOCAB)
        self.elig = {}            # cell -> {token: trace}
        self.mass = 0             # live synapse count
        self.history = []         # last ORDER_MAX tokens
        self.beats = 0

    # ------------------------------------------------------------------ cells
    def _active_cells(self, phase):
        cells = []
        h = self.history
        for k in range(1, genome.ORDER_MAX + 1):
            if len(h) >= k:
                cells.append((_ctx_key(k, h[-k:]), 1.0))
        pk = _phase_key(phase)
        for mu in range(genome.STEPS_PER_BAR):
            pass  # bump cells vote via their tuned key below
        cells.append((pk, genome.PHASE_GAIN * _BUMP[phase][phase]))
        return cells

    # -------------------------------------------------------------- predict
    def predict(self, phase):
        """Full 108-way distribution (generation). Reliability-mixed backoff."""
        p = [u / self.uni_total for u in self.uni]
        for cell, gain in self._active_cells(phase):
            cw = self.w.get(cell)
            if not cw:
                continue
            n = self.n.get(cell, 0)
            lam = gain * (n / (n + genome.LAMBDA_C))
            if lam <= 0:
                continue
            tot = sum(cw.values())
            if tot <= 0:          # a fully-depressed cell (e.g. after a strong tap)
                continue
            for t_str, wt in cw.items():
                t = int(t_str)
                p[t] = (1 - lam) * p[t] + lam * (wt / tot)
            s = sum(p)
            p = [x / s for x in p]
        return p

    def p_of(self, target, phase):
        """O(cells) probability of one target token (for digestion / CE eval)."""
        p = self.uni[target] / self.uni_total
        for cell, gain in self._active_cells(phase):
            cw = self.w.get(cell)
            if not cw:
                continue
            n = self.n.get(cell, 0)
            lam = gain * (n / (n + genome.LAMBDA_C))
            if lam <= 0:
                continue
            tot = sum(cw.values())
            if tot <= 0:          # a fully-depressed cell (e.g. after a strong tap)
                continue
            p = (1 - lam) * p + lam * (cw.get(str(target), 0.0) / tot)
        return max(p, 1e-12)

    # --------------------------------------------------------------- digest
    def digest(self, tok, phase, chem, learn=True):
        """Observe token in current context; the three-factor online update."""
        p = self.p_of(tok, phase)
        bits = -math.log2(p)
        if learn:
            chem.observe_surprise(bits)
            gate = genome.ETA0 * chem.plasticity_gain()
            if gate > 0:
                delta = gate * (1.0 - p)
                for cell, _gain in self._active_cells(phase):
                    self._bump_syn(cell, tok, delta)
                    self._tag(cell, tok)
                self._grow(tok, phase, bits)
            self.uni[tok] += 1.0
            self.uni_total += 1.0
        self.history.append(tok)
        if len(self.history) > genome.ORDER_MAX:
            self.history.pop(0)
        self.beats += 1
        if self.beats % 64 == 0:
            self._decay_traces()
        return bits

    def _bump_syn(self, cell, tok, delta):
        cw = self.w.setdefault(cell, {})
        t = str(tok)
        was = t in cw
        cw[t] = cw.get(t, 0.0) + delta
        if not was:
            self.mass += 1
        self.n[cell] = self.n.get(cell, 0) + 1
        if cw[t] > genome.W_MAX:                       # synaptic scaling
            f = genome.W_MAX / cw[t]
            for k in cw:
                cw[k] *= f
        if self.mass > genome.MASS_MAX:
            self._prune_weakest()

    def _grow(self, tok, phase, bits):
        """Order-(k+1) cell born where its order-k parent is reliable but surprised."""
        h = self.history
        for k in range(1, genome.ORDER_MAX):
            if len(h) < k + 1:
                break
            parent = _ctx_key(k, h[-k:])
            child = _ctx_key(k + 1, h[-(k + 1):])
            if (child not in self.w and self.n.get(parent, 0) >= genome.GROW_MIN
                    and bits > genome.GROW_SURPRISE):
                self.w[child] = {}

    # ------------------------------------------------------------ eligibility
    def _tag(self, cell, tok):
        self.elig.setdefault(cell, {})[str(tok)] = 1.0

    def tag_only(self, tok, phase):
        """Performance mode (ACh=0): tag pathways used, learn nothing."""
        for cell, _g in self._active_cells(phase):
            self._tag(cell, tok)
        self.history.append(tok)
        if len(self.history) > genome.ORDER_MAX:
            self.history.pop(0)

    def _decay_traces(self):
        f = math.exp(-64.0 / genome.TRACE_TAU)
        dead = []
        for cell, toks in self.elig.items():
            for t in list(toks):
                toks[t] *= f
                if toks[t] < 0.01:
                    del toks[t]
            if not toks:
                dead.append(cell)
        for c in dead:
            del self.elig[c]

    def snapshot_trace(self):
        """The song's fingerprint: which synapses sang it (for distal payout)."""
        return {c: dict(t) for c, t in self.elig.items() if t}

    def pay_trace(self, trace, valence, eta, chem):
        """Distal payout: Dw = eta * ACh * V * e. Pain depresses (unlearning)."""
        paid = missing = 0
        for cell, toks in trace.items():
            cw = self.w.get(cell)
            for t, e in toks.items():
                if cw is not None and t in cw:
                    cw[t] = max(0.0, cw[t] + eta * chem.ach * valence * e)
                    paid += 1
                else:
                    missing += 1
        return paid, missing

    # ------------------------------------------------------------- housekeeping
    def _prune_weakest(self, target_mass=None):
        """Cut the weakest synapses until mass <= target (default: the mass cap).

        DW-12: save() used to call this to enforce the FILE cap, but the loop
        only ran while mass > 0.95*MASS_MAX — an oversized file with mass under
        that line was a silent no-op. It now takes an explicit target so the file
        guard can prune toward a SIZE, and it can no longer spin forever when
        there is nothing left to cut.
        """
        limit = genome.MASS_MAX * 0.95 if target_mass is None else max(0, target_mass)
        cut = genome.W_MIN
        while self.mass > limit:
            removed = 0
            for cell in list(self.w):
                cw = self.w[cell]
                for t in [t for t, v in cw.items() if v < cut]:
                    del cw[t]
                    removed += 1
                if not cw:
                    del self.w[cell]
                    self.n.pop(cell, None)
            self.mass -= removed
            if removed == 0:
                if not self.w:
                    break
                cut *= 2.0
        return self.mass

    def top_synapses(self, k=10):
        out = []
        for cell, cw in self.w.items():
            for t, v in cw.items():
                out.append((v, cell, t))
        out.sort(reverse=True)
        return out[:k]

    # ------------------------------------------------------------- persistence
    def _write(self, path):
        state = {"w": self.w, "n": self.n, "uni": self.uni,
                 "uni_total": self.uni_total, "mass": self.mass}
        raw = json.dumps(state).encode("utf-8")
        with gzip.open(path, "wb") as f:
            f.write(raw)
        return os.path.getsize(path) / 1e6

    def save(self, path, log=None):
        """Persist, then ENFORCE the file cap — prune toward the size, out loud.

        DW-12: the old guard was `if mb > FILE_MAX_MB: self._prune_weakest()`,
        and _prune_weakest only looped while mass > 0.95*MASS_MAX. Whenever the
        file was over the cap while mass sat under that line the guard did
        nothing at all, silently, and the file stayed over the cap. Now the
        target is derived from the measured bytes and every prune is logged with
        before/after mass and size.
        """
        log = log or (lambda m: print(m, flush=True))
        mb = self._write(path)
        if mb <= genome.FILE_MAX_MB:
            return mb
        for _ in range(8):
            before_mass, before_mb = self.mass, mb
            target = int(self.mass * (genome.FILE_MAX_MB / mb) * 0.95)
            self._prune_weakest(target_mass=target)
            mb = self._write(path)
            log(f"[brain] file {before_mb:.2f} MB > cap {genome.FILE_MAX_MB} MB: "
                f"pruned {before_mass - self.mass} synapses "
                f"({before_mass} -> {self.mass}); file now {mb:.2f} MB")
            if mb <= genome.FILE_MAX_MB or self.mass >= before_mass:
                break
        if mb > genome.FILE_MAX_MB:
            log(f"[brain] WARNING: still {mb:.2f} MB after pruning to "
                f"{self.mass} synapses — the cap is not holdable by pruning")
        return mb

    @classmethod
    def load(cls, path):
        b = cls()
        with gzip.open(path, "rb") as f:
            state = json.loads(f.read().decode("utf-8"))
        b.w, b.n = state["w"], state["n"]
        b.uni, b.uni_total = state["uni"], state["uni_total"]
        b.mass = state["mass"]
        return b
