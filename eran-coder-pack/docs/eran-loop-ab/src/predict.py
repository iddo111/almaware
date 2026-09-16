"""predict.py — THE ARROW THAT GOES BACK DOWN. Rao & Ballard (1999), in numpy.

לזכרה של עלמה ז״ל.

WHAT WAS OPEN
-------------
Until now the organism's only arrow ran one way:

    wav -> cochlea -> one 192-d vector -> brain finds the nearest prototype -> done

The matched prototype never flowed back down. Nothing the brain believed could
change what the ears delivered next, and "surprise" was measured *after* the
best match had already been found — which is not surprise at all. It is
`1 - cos(v, nearest)`: "I have never seen anything like this." A child who is
startled is not saying that. It is saying **"I expected something else."**

WHAT THIS CLOSES
----------------
The frozen cochlea already delivers TIME: EAR_SLICES=8 ordered windows across
the sound, each an N_BANDS-wide spectral shape (ears.pool, the cochlea branch).
The 192-d percept is those 8 slices laid end to end. So a prediction has
somewhere real to point: **slice t, predicted from slices 0..t-1.**

    for t = 1..7:
        the brain matches what it has heard SO FAR (slices 0..t-1)
        against every prototype's own first t slices
        -> a softmax mixture over the top-k                    (the expectation)
        -> pred_t = the mixture's slice t                      (sent DOWN)
        -> e_t = Vn[t] - pred_t                                (what it missed)
    prediction_error = mean_t (1 - cos(Vn[t], pred_t))         (sent back UP)

Slice 0 has nothing above it and is carried raw; that is also what keeps the
residual from having a trivial all-zero solution.

THE EXPECTATION IS A MIXTURE, NOT THE WINNER. That is the whole point, and it
is where the second predicted consequence comes from: two prototypes that
differ only by predictable variation both contribute, the mixture explains the
variation away, and no third prototype is spawned for it. A single-winner
prediction would be `1 - cos` again with extra steps.

    ||Vn[t] - pred_t||^2 = 2 * (1 - cos_t)

so the prediction error IS the residual energy. They are not two quantities;
the residual vector is returned as well, and its norm is recorded, but nothing
here pretends they are independent evidence.

WHY PROTOTYPES STAY IN RAW SIGNAL SPACE
---------------------------------------
The obvious-looking move — store the residual as the prototype — is wrong and
would collapse the organism. **You cannot generate a prediction from an error.**
In Rao & Ballard the higher level holds the *generative* model and the feedback
carries its prediction; only the feedforward path carries residual. So the
prototype file stays exactly what ORGANISM.md promises: something you can
`zcat` and read as a spectrum. What the closed loop changes is what the error
is allowed to DO — set surprise, decide a spawn, and scale the Hebbian pull.

THE GATE
--------
`g_eff = PC_FEEDBACK_GAIN * chem.feedback()`, clipped to [0,1], and every use
of the prediction is a blend `(1-g)*old + g*new`. At `PC_FEEDBACK_GAIN = 0`
this reduces to the open loop EXACTLY — not approximately — which is the only
honest way to run the two arms against each other.

`chem.feedback() = ach / (1 + ne)`: the child leans on what it expects while it
is attending, and abandons the expectation the instant something jolts it.
That is not decoration — it is Yu & Dayan's (2005) reading of ACh as expected
uncertainty and NE as unexpected uncertainty, and this organism already had
both chemicals. Nothing new was invented to hold a knob.

NO LABEL EVER REACHES THIS FILE. It sees float vectors and nothing else — no
path, no filename, no class. It could not read a label if one were handed to it.
"""
import numpy as np

import genome


class Predictor:
    """The top-down path. Stateless; it reads the brain and returns numbers."""

    def __init__(self, slices=None, topk=None, beta=None):
        self.slices = int(slices if slices is not None else genome.EAR_SLICES)
        self.topk = int(topk if topk is not None else genome.PC_TOPK)
        self.beta = float(beta if beta is not None else genome.PC_BETA)

    # ------------------------------------------------------------------ shape
    @staticmethod
    def _rows(mat, slices):
        """(..., dim) -> (..., slices, bands) with every slice L2-normalised.

        The cochlea already emits unit-norm slices (ears.pool), so for a fresh
        percept this is a no-op; a prototype that has been pulled by Hebbian
        learning has drifted off the unit sphere per slice and is renormalised
        here. Doing it in one place is what keeps a mixture's weights meaning
        the same thing for a newborn prototype and a heavy old one.
        """
        m = np.asarray(mat, dtype=np.float64)
        m = m.reshape(m.shape[:-1] + (slices, -1))
        n = np.linalg.norm(m, axis=-1, keepdims=True)
        return m / np.where(n > 0, n, 1.0)

    # ------------------------------------------------------------ the arrow
    def predict(self, vec, proto_mat):
        """One percept meets the brain's expectation.

        vec       : (dim,)      the frozen cochlea's percept, untouched
        proto_mat : (n, dim)    every prototype, raw signal space

        Returns dict:
          pe        mean prediction error over the predicted slices, in [0,2],
                    directly comparable to the open loop's 1 - cos
          pe_per_slice
          resid     (dim,) the residual percept, L2-normalised (what the ears
                    would send up if there were a layer above to send it to)
          resid_norm  ||v - pred|| before normalisation, the raw energy
          n_used    how many prototypes the expectation was mixed from
        """
        S = self.slices
        Vn = self._rows(vec, S)                      # (S, B)
        n = 0 if proto_mat is None else len(proto_mat)
        if n == 0:
            # No expectation exists yet. Everything is maximally surprising and
            # nothing is subtracted — a newborn is all bottom-up.
            return {"pe": 1.0,
                    "pe_per_slice": [1.0] * max(0, S - 1),
                    "resid": np.asarray(vec, dtype=np.float64).copy(),
                    "resid_norm": float(np.linalg.norm(Vn)),
                    "n_used": 0}

        Pn = self._rows(proto_mat, S)                # (n, S, B)
        # C[i, t] = cos(slice t of percept, slice t of prototype i).
        C = np.einsum("isb,sb->is", Pn, Vn)          # (n, S)
        # Evidence available BEFORE slice t: the running mean of C over u < t.
        cum = np.cumsum(C, axis=1)                   # (n, S)
        pred = np.zeros((S, Vn.shape[1]))
        pe_t = []
        k = min(self.topk, n)
        for t in range(1, S):
            sims = cum[:, t - 1] / t                 # mean cos over slices < t
            if k < n:
                top = np.argpartition(-sims, k - 1)[:k]
            else:
                top = np.arange(n)
            s = sims[top]
            w = np.exp(self.beta * (s - s.max()))
            w = w / w.sum()
            p = w @ Pn[top, t, :]                    # the mixture's slice t
            pn = np.linalg.norm(p)
            if pn > 0:
                p = p / pn
            pred[t] = p
            pe_t.append(1.0 - float(Vn[t] @ p))      # in [0, 2]
        pe = float(np.mean(pe_t)) if pe_t else 1.0

        resid = (Vn - pred).ravel()                  # slice 0: pred is zero
        rn = float(np.linalg.norm(resid))
        if rn > 0:
            resid = resid / rn
        return {"pe": pe, "pe_per_slice": [float(x) for x in pe_t],
                "resid": resid, "resid_norm": rn, "n_used": int(k)}
