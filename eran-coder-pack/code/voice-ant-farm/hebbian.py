"""Competitive Hebbian acoustic-unit learning (pure numpy, no torch, no GPU).

What this replaces
------------------
The colony's learner was batch k-means over a 14-dim frame vector.  Two things
were measured about it and both are bad:

  * the optimiser contributed nothing -- 256 *random real frames* scored 40.3%
    on the 22-way held-out syllable probe against the trained codebook's 41.9%
    (p = 0.54), so Lloyd iteration bought no linguistic structure;
  * 84 of its 256 units were dead on held-out audio (172 used), so a quarter of
    the codebook was paying rent and doing nothing.

This module is the Hebbian answer to both: units that fire together wire
together, units that win too often are taxed, and the map has a topology so
neighbouring units are forced to stay related instead of collapsing.


Why plain Hebbian is unstable, and what is used instead
-------------------------------------------------------
Plain Hebb is  dw = eta * y * x  with y = w . x.  Take the expectation:

    E[dw] = eta * E[x x^T] w = eta * C w

C is a covariance matrix, so it is positive semi-definite; the update is a
power iteration with no normaliser and ||w|| grows like exp(eta * lambda_1 * t).
It diverges.  Every unit also converges to the *same* leading eigenvector, so a
population of plain-Hebbian units carries one dimension of information no matter
how many units you buy.  `unstable_hebbian_demo` below measures the divergence
rather than asserting it; it is never called during training.

Oja's fix is to subtract a decay proportional to the unit's own output:

    dw = eta * y * (x - y * w)

The -eta*y^2*w term is a self-normaliser: at the fixed point ||w|| = 1 and w is
the principal eigenvector.  For a *competitive* unit the output is not a linear
projection but an activation in [0, 1] -- 1 for the winner, h_j < 1 for its
neighbours on the map, 0 elsewhere -- and with that y, Oja's rule collapses to
the instar / Kohonen form used here:

    dw_j = eta * h_j * (x - w_j)

The decay term is still there (it is the -eta*h_j*w_j half), it still bounds the
weight, and now the fixed point is

    w_j = E[h_j x] / E[h_j]

the neighbourhood-weighted mean of the inputs that activate unit j: a prototype,
which is what a codebook needs, rather than an eigenvector, which is not.

The batched form in `HebbianMap._step` is an explicit convex combination of the
old weight and a weighted mean of real frames, with a coefficient in [0, 1).
So the weights provably stay inside the convex hull of the data the map has
seen.  Divergence is impossible by construction, not by tuning.  (Test:
`test_hebbian.TestStability`.)


The three things the brief asked for, and where they are
--------------------------------------------------------
  normalised Hebbian     `HebbianMap._step`, derived above.
  soft-neighbourhood WTA `HebbianMap._neighbourhood` -- a Gaussian over a 2-D
                         rectangular map grid, radius annealed from half the map
                         down to sub-unit.  This is what stops every unit
                         collapsing onto the same prototype: while sigma is
                         large a win drags a whole neighbourhood, so units are
                         spread over the data before they are allowed to
                         specialise.  It also makes the *topology* readable --
                         see `topology_report`.
  homeostasis            DeSieno conscience, `HebbianMap._bias`.  Each unit
                         keeps a leaky estimate p_j of how often it wins; the
                         competition is run on d^2 + gamma * scale * (k p_j - 1),
                         so a unit winning three times its fair share is pushed
                         away and a unit that never wins is pulled in.  The
                         conscience is a *training-time* term only: `encode` is
                         a plain nearest-prototype argmin, so the interface the
                         rest of the colony sees is unchanged and comparable.

Online and incremental: `partial_fit` takes any chunk of frames and folds it in.
The learning rate and radius decay with total frames seen and then *stay at a
floor*, so an ant left running for a week keeps adapting instead of freezing.
`fit` is only a loop over `partial_fit`.

Founding rule: nothing in here reads another ant's weights, scaler, or frames.
Every ant is constructed from its own seed and fitted on its own sample of its
own corpus.  `variance_scaler` is fitted per ant, per the feature-space note.

Feature space: `feature_space.frame_features` (recommended26), the level-free
26-dim vector selected in the previous phase.  The exemplar stored per unit is
still one real 400-sample waveform frame, so `acoustic_units.synthesize_units`
works on these checkpoints unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path

import numpy as np

import feature_space as F
from acoustic_units import (
    EXEMPLAR_RATE,
    FRAME_SECONDS,
    HOP_SECONDS,
    checkpoint_digest,
    load_checkpoint,
    load_wav,
    resample_samples,
    write_json_atomic,
)

FRAME = round(EXEMPLAR_RATE * FRAME_SECONDS)   # 400
HOP = round(EXEMPLAR_RATE * HOP_SECONDS)       # 160
ARCHITECTURE = "competitive-hebbian-self-organising-acoustic-units"
FEATURE_SET = "recommended26"
# Annealing horizon used when frames are streamed in with `partial_fit` and
# there is no `fit` call to size the schedule from.  About 2.8 hours of audio.
STREAM_HORIZON = 1_000_000

FEATURE_SPEC = {
    "version": 2,
    "canonical_sample_rate": EXEMPLAR_RATE,
    "frame_seconds": FRAME_SECONDS,
    "hop_seconds": HOP_SECONDS,
    "feature_set": FEATURE_SET,
    "features": [
        "c1..c20 of DCT-II of 26-band log-mel (50-8000 Hz, pre-emphasis 0.97, "
        "per-frame 80 dB relative floor)",
        "first difference of c1..c6 over a +/-40 ms regression window",
    ],
}


# ---------------------------------------------------------------------------
# the map grid
# ---------------------------------------------------------------------------

def grid_shape(units: int) -> tuple[int, int]:
    """Near-square factorisation of `units`.  256 -> (16, 16), 512 -> (16, 32)."""
    rows = int(round(math.sqrt(units)))
    while rows > 1 and units % rows:
        rows -= 1
    return rows, units // rows


def grid_sqdist(rows: int, cols: int) -> np.ndarray:
    """(k, k) squared Euclidean distance between map positions."""
    r, c = np.divmod(np.arange(rows * cols), cols)
    return ((r[:, None] - r[None, :]) ** 2 + (c[:, None] - c[None, :]) ** 2).astype(np.float64)


def sqdist(x: np.ndarray, w: np.ndarray) -> np.ndarray:
    """(n, k) squared Euclidean distance, clipped at zero for round-off."""
    d = (x * x).sum(axis=1)[:, None] + (w * w).sum(axis=1)[None, :] - 2.0 * (x @ w.T)
    return np.maximum(d, 0.0)


# ---------------------------------------------------------------------------
# the learner
# ---------------------------------------------------------------------------

class HebbianMap:
    """Self-organising competitive Hebbian codebook over frame features.

    One ant owns exactly one of these.  Nothing is shared: the seed picks the
    initial prototypes, the frame order, and every random decision afterwards.
    """

    def __init__(
        self,
        units: int,
        dim: int,
        seed: int,
        eta0: float = 0.30,
        eta_min: float = 0.02,
        sigma0: float | None = None,
        sigma_min: float = 0.50,
        conscience: float = 0.15,
        conscience_tau: float = 10_000.0,
        horizon: int | None = None,
        batch: int = 256,
    ) -> None:
        if units < 2:
            raise ValueError("a competitive map needs at least two units")
        self.units = int(units)
        self.dim = int(dim)
        self.seed = int(seed)
        self.rows, self.cols = grid_shape(self.units)
        self.eta0, self.eta_min = float(eta0), float(eta_min)
        self.sigma0 = float(max(self.rows, self.cols) / 2.0 if sigma0 is None else sigma0)
        self.sigma_min = float(sigma_min)
        self.conscience = float(conscience)
        self.conscience_tau = float(conscience_tau)
        # `None` means "anneal over whatever the first fit() is given".  A fixed
        # default here is a trap: a horizon longer than the run leaves sigma
        # stuck near sigma0 for the whole of it, and a map whose neighbourhood
        # never shrinks is a map whose units never specialise.  That bug cost
        # this module a full round of results; it is pinned by
        # `test_hebbian.TestSchedule`.
        self.horizon = None if horizon is None else int(horizon)
        self.batch = int(batch)

        self.rng = np.random.default_rng(self.seed)
        self._grid_d2 = grid_sqdist(self.rows, self.cols)
        self.w = np.zeros((self.units, self.dim), dtype=np.float64)
        # p_j: leaky estimate of how often unit j wins.  Starts at the fair
        # share so a fresh map carries no conscience bias in either direction.
        self.p = np.full(self.units, 1.0 / self.units, dtype=np.float64)
        self.win_counts = np.zeros(self.units, dtype=np.int64)
        self.seen = 0                  # frames folded in, ever
        self.initialised = False
        self._dscale = 1.0             # running mean squared quantisation error
        self.scale = np.ones(self.dim, dtype=np.float64)

    # -- schedule ----------------------------------------------------------
    # Both anneal on total frames seen and then hold at a floor, so the map is
    # still plastic after the nominal horizon.  A learner that freezes cannot
    # be the learner for ants that run continuously.

    def _progress(self) -> float:
        return min(1.0, self.seen / max(self.horizon or STREAM_HORIZON, 1))

    def eta(self) -> float:
        return float(self.eta0 * (self.eta_min / self.eta0) ** self._progress())

    def sigma(self) -> float:
        return float(self.sigma0 * (self.sigma_min / self.sigma0) ** self._progress())

    # -- pieces ------------------------------------------------------------

    def _bias(self) -> np.ndarray:
        """DeSieno conscience: a distance penalty proportional to over-winning.

        `k * p_j - 1` is zero at the fair share, positive for a unit hogging the
        input, negative for a starving one.  Scaling by the running mean squared
        quantisation error keeps `conscience` dimensionless, so the same value
        works on any feature space.
        """
        if self.conscience <= 0.0:
            return np.zeros(self.units)
        return self.conscience * self._dscale * (self.units * self.p - 1.0)

    def _neighbourhood(self, winners: np.ndarray, sigma: float) -> np.ndarray:
        """(n, k) Gaussian over map distance from each sample's winner."""
        h = np.exp(-self._grid_d2[winners] / (2.0 * sigma * sigma))
        h[h < 1e-4] = 0.0
        return h

    def initialise(self, x: np.ndarray) -> None:
        """Seed the prototypes with random REAL frames, never with Gaussians.

        The geometry note from the previous phase: the speech manifold is
        curved, so a random real frame sits ON it and a random Gaussian draw
        sits in a region no speech occupies.  Starting from real frames also
        makes the controlled claim available -- this map at step zero *is* the
        random-real-frames baseline with the same seed, so anything it gains
        later is attributable to the learning rule and nothing else.
        """
        x = np.asarray(x, dtype=np.float64)
        if len(x) < self.units:
            raise ValueError(f"need at least {self.units} frames to initialise, got {len(x)}")
        self.w = x[self.rng.choice(len(x), self.units, replace=False)].copy()
        # a random sample, not the first 2048 rows: those are one corpus file
        # and would set the conscience's distance scale from one speaker
        probe = x[self.rng.choice(len(x), min(2048, len(x)), replace=False)]
        self._dscale = float(np.mean(sqdist(probe, self.w).min(axis=1))) or 1.0
        self.initialised = True

    def _step(self, x: np.ndarray, eta: float, sigma: float) -> None:
        """One batched normalised-Hebbian update.  See the module docstring.

        The per-unit coefficient `1 - (1 - eta)**h_total` is exactly what
        `h_total` successive online steps of size eta would compound to, so the
        batch is a vectorisation of the online rule and not a different rule.
        It lies in [0, 1), which makes the assignment below a convex
        combination: the weights cannot leave the convex hull of the data.
        """
        d2 = sqdist(x, self.w) + self._bias()[None, :]
        winners = d2.argmin(axis=1)
        h = self._neighbourhood(winners, sigma)
        mass = h.sum(axis=0)
        moving = mass > 1e-9
        if moving.any():
            target = (h.T @ x)[moving] / mass[moving, None]
            rate = 1.0 - (1.0 - eta) ** mass[moving]
            self.w[moving] += rate[:, None] * (target - self.w[moving])
        # homeostasis: leaky win-frequency estimate, DeSieno's beta expressed
        # as a time constant in frames so the batch size cannot change it.
        freq = np.bincount(winners, minlength=self.units) / len(x)
        beta = 1.0 - (1.0 - 1.0 / self.conscience_tau) ** len(x)
        self.p += beta * (freq - self.p)
        self.win_counts += np.bincount(winners, minlength=self.units)
        # running quantisation scale, only ever used to make `conscience`
        # dimensionless.  It is NOT an objective and is never reported.
        quant = float(np.mean(sqdist(x, self.w).min(axis=1)))
        self._dscale += 0.05 * (quant - self._dscale)
        self.seen += len(x)

    # -- public API --------------------------------------------------------

    def partial_fit(self, x: np.ndarray, shuffle: bool = True) -> "HebbianMap":
        """Fold a chunk of frames in.  This is the incremental entry point."""
        x = np.asarray(x, dtype=np.float64)
        if x.ndim != 2 or x.shape[1] != self.dim:
            raise ValueError(f"expected (n, {self.dim}) frames, got {x.shape}")
        if not self.initialised:
            self.initialise(x)
        if self.horizon is None:
            # streamed in with no fit() to size the schedule from
            self.horizon = STREAM_HORIZON
        order = self.rng.permutation(len(x)) if shuffle else np.arange(len(x))
        for start in range(0, len(x), self.batch):
            chunk = x[order[start:start + self.batch]]
            if len(chunk):
                self._step(chunk, self.eta(), self.sigma())
        return self

    def fit(self, x: np.ndarray, epochs: int = 1, progress: bool = False) -> "HebbianMap":
        if self.horizon is None:
            self.horizon = max(1, epochs * len(np.asarray(x)))
        for epoch in range(epochs):
            self.partial_fit(x)
            if progress:
                print(f"    epoch {epoch + 1}/{epochs}  seen={self.seen}  "
                      f"eta={self.eta():.3f} sigma={self.sigma():.2f}  "
                      f"dead={int((self.win_counts == 0).sum())}", flush=True)
        return self

    def fit_scaler(self, x: np.ndarray) -> "HebbianMap":
        """Per-ant isotropy scaler, fitted on THIS ant's own frames only."""
        self.scale = F.variance_scaler(np.asarray(x, dtype=np.float64))
        return self

    def encode(self, x: np.ndarray) -> np.ndarray:
        """Nearest prototype.  No conscience: the interface must be a pure argmin."""
        return sqdist(np.asarray(x, dtype=np.float64), self.w).argmin(axis=1)

    def encode_samples(self, samples: np.ndarray) -> np.ndarray:
        """16 kHz mono float32 -> one unit id per 10 ms frame."""
        return self.encode(F.frame_features(samples) / self.scale)

    def snap_to_frames(self, x: np.ndarray, block: int = 4096) -> int:
        """Project every prototype onto the nearest real frame it has seen.

        The diagnosis says a mean of frames sits OFF the speech manifold.  This
        is the cheap on-manifold projection; whether it helps is measured, not
        assumed (the `hebbian-snap` row of `hebbian_eval.py --cv`).  Returns how
        many prototypes actually moved.
        """
        x = np.asarray(x, dtype=np.float64)
        best_d = np.full(self.units, np.inf)
        best_i = np.zeros(self.units, dtype=np.int64)
        for start in range(0, len(x), block):
            piece = x[start:start + block]
            d = sqdist(piece, self.w)
            idx = d.argmin(axis=0)
            val = d[idx, np.arange(self.units)]
            take = val < best_d
            best_d[take] = val[take]
            best_i[take] = start + idx[take]
        moved = int(np.sum(np.any(self.w != x[best_i], axis=1)))
        self.w = x[best_i].copy()
        return moved

    # -- diagnostics -------------------------------------------------------

    def dead_units(self, x: np.ndarray) -> int:
        """Units that win for no frame of `x`."""
        used = np.unique(self.encode(x))
        return int(self.units - len(used))

    def state(self) -> dict:
        return {
            "units": self.units, "feature_dim": self.dim, "seed": self.seed,
            "grid_rows": self.rows, "grid_cols": self.cols,
            "eta0": self.eta0, "eta_min": self.eta_min,
            "sigma0": self.sigma0, "sigma_min": self.sigma_min,
            "conscience": self.conscience, "conscience_tau": self.conscience_tau,
            "horizon": int(self.horizon or STREAM_HORIZON), "batch": self.batch,
            "frames_seen": int(self.seen),
            "final_eta": self.eta(), "final_sigma": self.sigma(),
            "win_counts": self.win_counts.tolist(),
            "win_frequency_gini": gini(self.win_counts.astype(np.float64)),
            "feature_scale": self.scale.tolist(),
        }


def gini(counts: np.ndarray) -> float:
    """0 = every unit wins equally often, 1 = one unit takes everything."""
    v = np.sort(np.asarray(counts, dtype=np.float64))
    n = len(v)
    total = v.sum()
    if total <= 0:
        return 0.0
    return float((2.0 * np.arange(1, n + 1) - n - 1) @ v / (n * total))


def unstable_hebbian_demo(x: np.ndarray, eta: float = 0.05, steps: int = 2000,
                          seed: int = 7007) -> dict:
    """Measure the divergence that motivates the normalisation.  Never trained.

    Runs plain Hebb (dw = eta*y*x, y = w.x) and Oja (dw = eta*y*(x - y*w)) on
    the same shuffled stream from the same start, and reports the weight norms.
    Plain Hebb grows without bound; Oja settles at ||w|| = 1.  This exists so the
    claim in the module docstring is a measurement and not an assertion.

    The data is centred and scaled to E||x||^2 = 1 first, so that the largest
    covariance eigenvalue is at most 1 and `eta` is inside the stable range for
    *both* rules.  Without that, Oja would overflow too and the comparison would
    be about step size rather than about the rule -- which would prove nothing.
    """
    x = np.asarray(x, dtype=np.float64)
    x = x - x.mean(axis=0)
    x = x / max(math.sqrt(float(np.mean(np.sum(x * x, axis=1)))), 1e-12)
    rng = np.random.default_rng(seed)
    order = rng.integers(0, len(x), steps)
    w0 = rng.standard_normal(x.shape[1])
    w0 /= np.linalg.norm(w0)
    plain, oja = w0.copy(), w0.copy()
    plain_norms, oja_norms = [], []
    with np.errstate(over="ignore", invalid="ignore"):
        for index in order:
            sample = x[index]
            y = float(plain @ sample)
            plain = plain + eta * y * sample
            y2 = float(oja @ sample)
            oja = oja + eta * y2 * (sample - y2 * oja)
            plain_norms.append(float(np.linalg.norm(plain)))
            oja_norms.append(float(np.linalg.norm(oja)))
    return {
        "steps": steps,
        "eta": eta,
        "plain_hebbian_norm_start": plain_norms[0],
        "plain_hebbian_norm_end": plain_norms[-1],
        "plain_hebbian_norm_growth": plain_norms[-1] / max(plain_norms[0], 1e-12),
        "oja_norm_end": oja_norms[-1],
    }


# ---------------------------------------------------------------------------
# topology -- the thing k-means cannot have
# ---------------------------------------------------------------------------

def topology_report(w: np.ndarray, rows: int, cols: int) -> dict:
    """Is the map ordered?  Grid distance vs feature distance, and folding.

    `neighbour_ratio` is the mean feature distance between grid neighbours over
    the mean distance between random unit pairs.  1.0 means the map is no more
    ordered than a shuffled codebook; a self-organised map should be well under.
    `topographic_error` needs data and is computed in `hebbian_eval`.
    """
    k = rows * cols
    gd = np.sqrt(grid_sqdist(rows, cols))
    fd = np.sqrt(sqdist(w, w))
    iu = np.triu_indices(k, 1)
    g, f = gd[iu], fd[iu]
    adjacent = g == 1.0
    gm, fm = g - g.mean(), f - f.mean()
    pearson = float((gm @ fm) / max(math.sqrt((gm @ gm) * (fm @ fm)), 1e-12))
    return {
        "grid": [int(rows), int(cols)],
        "pearson_grid_vs_feature_distance": pearson,
        "mean_neighbour_feature_distance": float(f[adjacent].mean()),
        "mean_pair_feature_distance": float(f.mean()),
        "neighbour_ratio": float(f[adjacent].mean() / max(f.mean(), 1e-12)),
    }


# ---------------------------------------------------------------------------
# corpus -> frames
# ---------------------------------------------------------------------------

def wav_frames(path: Path) -> tuple[np.ndarray, np.ndarray, str]:
    """(features, canonical samples, pcm hash) for one WAV."""
    audio = load_wav(path)
    samples = resample_samples(audio.samples, audio.rate, EXEMPLAR_RATE)
    return F.frame_features(samples), samples, audio.pcm_sha256


def folder_frames(
    folder: Path, limit: int | None = None, stride: int = 1, seed: int = 0,
    verbose: bool = False,
) -> tuple[np.ndarray, list[str]]:
    """Featurise a folder.  `limit` samples files, `stride` subsamples frames.

    Both are honest subsampling knobs for the 40.6 h corpus: whatever is used is
    written into the checkpoint as `corpus_provenance`, so a run is never
    quietly smaller than it claims.  File choice is seeded per ant, so two ants
    do not even see the same slice of the corpus.
    """
    paths = sorted(folder.glob("*.wav"))
    if not paths:
        raise ValueError(f"no WAV recordings in {folder}")
    if limit is not None and limit < len(paths):
        rng = np.random.default_rng(seed)
        paths = [paths[i] for i in sorted(rng.choice(len(paths), limit, replace=False))]
    frames, hashes, seen = [], [], set()
    t0 = time.time()
    for n, path in enumerate(paths):
        try:
            x, _, pcm = wav_frames(path)
        except ValueError:
            continue
        if pcm in seen:
            continue
        seen.add(pcm)
        hashes.append(pcm)
        frames.append(x[::stride].astype(np.float32))
        if verbose and (n + 1) % 2000 == 0:
            print(f"    featurised {n + 1}/{len(paths)} files "
                  f"({time.time() - t0:.0f}s)", flush=True)
    if not frames:
        raise ValueError(f"no usable WAV recordings in {folder}")
    return np.concatenate(frames), hashes


# ---------------------------------------------------------------------------
# exemplars -- one real waveform frame per unit, so synthesis still works
# ---------------------------------------------------------------------------

def learn_exemplars(folders: list[Path], centers: np.ndarray, scale: np.ndarray,
                    limit: int | None = None, seed: int = 0) -> dict:
    """Nearest real 400-sample training frame to every prototype.

    Same contract as `acoustic_units.learn_exemplars`, in the new feature space,
    so `acoustic_units.synthesize_units` runs on these checkpoints unchanged.
    """
    k = len(centers)
    best_distance = np.full(k, np.inf)
    best_frames: list[np.ndarray | None] = [None] * k
    best_hashes: list[str | None] = [None] * k
    best_indexes: list[int | None] = [None] * k
    paths: list[Path] = []
    for folder in folders:
        paths.extend(sorted(folder.glob("*.wav")))
    if limit is not None and limit < len(paths):
        rng = np.random.default_rng(seed)
        paths = [paths[i] for i in sorted(rng.choice(len(paths), limit, replace=False))]
    for path in paths:
        try:
            x, samples, pcm = wav_frames(path)
        except ValueError:
            continue
        d = sqdist(x / scale, centers)
        index = d.argmin(axis=0)
        value = d[index, np.arange(k)]
        take = value < best_distance
        for unit in np.flatnonzero(take):
            i = int(index[unit])
            start = i * HOP
            raw = samples[start:start + FRAME]
            if len(raw) < FRAME:
                raw = np.pad(raw, (0, FRAME - len(raw)))
            best_distance[unit] = float(value[unit])
            best_frames[unit] = raw.astype(np.float32, copy=True)
            best_hashes[unit] = pcm
            best_indexes[unit] = i
    if any(f is None for f in best_frames):
        raise ValueError("could not learn a waveform exemplar for every unit")
    pcm16 = [
        np.clip(np.rint(f * 32767), -32768, 32767).astype("<i2").tolist()
        for f in best_frames if f is not None
    ]
    return {
        "exemplar_rate": EXEMPLAR_RATE,
        "exemplar_frame_samples": FRAME,
        "exemplar_hop_samples": HOP,
        "exemplars_pcm16": pcm16,
        "exemplar_source_hashes": best_hashes,
        "exemplar_source_frame_indexes": [int(i) for i in best_indexes if i is not None],
    }


# ---------------------------------------------------------------------------
# checkpoints
# ---------------------------------------------------------------------------

def build_checkpoint(learner: HebbianMap, ant: str, train_hashes: list[str],
                     exemplars: dict, provenance: dict, extra: dict | None = None) -> dict:
    checkpoint = {
        "format_version": 3,
        "architecture": ARCHITECTURE,
        "audio_hash_kind": "sha256(sample_rate_le32+decoded_pcm16le)",
        "feature_spec": FEATURE_SPEC,
        "experiment_namespace": hashlib.sha256(json.dumps(
            {"feature_spec": FEATURE_SPEC, "units": learner.units,
             "architecture": ARCHITECTURE}, sort_keys=True).encode()).hexdigest(),
        "ant": ant,
        "seed": learner.seed,
        "units": learner.units,
        "feature_dim": learner.dim,
        "learner": learner.state(),
        "topology": topology_report(learner.w, learner.rows, learner.cols),
        "corpus_provenance": provenance,
        "train_audio_hashes": sorted(set(train_hashes)),
        "heldout_audio_hashes": [],
        "centers": learner.w.tolist(),
        "centers_are_in_scaled_feature_space": True,
        "codebooks_merged": False,
        "claim_limit": "acoustic candidates and learned-exemplar reconstruction only",
    }
    checkpoint.update(exemplars)
    if extra:
        checkpoint.update(extra)
    checkpoint["checkpoint_sha256"] = checkpoint_digest(checkpoint)
    return checkpoint


def load_hebbian(path: Path) -> tuple[np.ndarray, np.ndarray, dict]:
    """(centers, feature scale, checkpoint).  Hash-verified by acoustic_units."""
    checkpoint = load_checkpoint(path)
    if checkpoint.get("architecture") != ARCHITECTURE:
        raise ValueError(f"{path}: not a Hebbian checkpoint")
    centers = np.asarray(checkpoint["centers"], dtype=np.float64)
    scale = np.asarray(checkpoint["learner"]["feature_scale"], dtype=np.float64)
    return centers, scale, checkpoint


def encode_wav(path: Path, centers: np.ndarray, scale: np.ndarray) -> np.ndarray:
    x, _, _ = wav_frames(path)
    return sqdist(x / scale, centers).argmin(axis=1)


# ---------------------------------------------------------------------------
# training one ant
# ---------------------------------------------------------------------------

def featurise_folders(folders: list[Path], file_limit: int | None, frame_stride: int,
                      seed: int, verbose: bool) -> tuple[np.ndarray, list[str]]:
    frames, hashes = [], []
    for folder in folders:
        f, h = folder_frames(folder, file_limit, frame_stride, seed, verbose)
        frames.append(f)
        hashes.extend(h)
    return np.concatenate(frames), hashes


def train_ant(
    ant: str, seed: int, folders: list[Path], state_root: Path, units: int = 256,
    epochs: int = 20, scaled: bool = True, snap: bool = False,
    file_limit: int | None = None, frame_stride: int = 1,
    exemplar_file_limit: int | None = None,
    frames: np.ndarray | None = None, hashes: list[str] | None = None,
    verbose: bool = True, **hyper,
) -> tuple[dict, Path]:
    """Train one ant.  `frames`/`hashes` let four ants share one featurisation
    pass over a 40-hour corpus; they are still four independent learners, because
    what is shared is the *audio*, which the colony has always shared, and never
    a weight, a scaler, or a random stream."""
    t0 = time.time()
    if frames is None:
        frames, hashes = featurise_folders(folders, file_limit, frame_stride,
                                           seed, verbose)
    hashes = list(hashes or [])
    featurise_seconds = time.time() - t0

    learner = HebbianMap(units, frames.shape[1], seed, **hyper)
    # float64 in place: a 40-hour corpus at stride 3 is ~0.7 GB and a second
    # copy for the scaled version is the difference between running and not.
    x = np.array(frames, dtype=np.float64)
    if scaled:
        learner.fit_scaler(x)
        x /= learner.scale
    t1 = time.time()
    learner.fit(x, epochs=epochs, progress=verbose)
    snapped = learner.snap_to_frames(x) if snap else 0
    train_seconds = time.time() - t1
    dead_on_train = learner.dead_units(x)
    frame_count = len(x)
    del x

    exemplars = learn_exemplars(folders, learner.w, learner.scale,
                                exemplar_file_limit or file_limit, seed)
    provenance = {
        "folders": [str(f) for f in folders],
        "files_used": len(set(hashes)),
        "file_limit_per_folder": file_limit,
        "exemplar_file_limit": exemplar_file_limit or file_limit,
        "frame_stride": frame_stride,
        "train_frame_count": int(frame_count),
        "train_audio_seconds": round(frame_count * frame_stride * HOP_SECONDS, 1),
        "epochs": epochs,
        "feature_scaled_per_ant": bool(scaled),
        "snapped_to_real_frames": bool(snap),
        "prototypes_snapped": snapped,
        "featurise_seconds": round(featurise_seconds, 1),
        "train_seconds": round(train_seconds, 1),
    }
    checkpoint = build_checkpoint(learner, ant, hashes, exemplars, provenance, {
        "train_frame_count": int(frame_count),
        "dead_units_on_train": int(dead_on_train),
    })
    state = state_root / ant
    state.mkdir(parents=True, exist_ok=True)
    candidate = state / f"candidate-{checkpoint['checkpoint_sha256'][:12]}.json"
    write_json_atomic(candidate, checkpoint)
    write_json_atomic(state / "current.json", checkpoint)
    return checkpoint, candidate


DEFAULT_ANTS = ("ant-a", "ant-b", "ant-c", "ant-d")
DEFAULT_SEEDS = (7007, 7019, 7039, 7057)


def train_command(args) -> None:
    folders = [Path(p) for p in args.folders.split(",")]
    state_root = Path(args.state)
    ants = DEFAULT_ANTS[:args.ants]
    seeds = DEFAULT_SEEDS[:args.ants]
    summary = []
    shared_frames = shared_hashes = None
    if args.file_limit is None:
        # every ant would featurise exactly the same files; do it once
        t0 = time.time()
        shared_frames, shared_hashes = featurise_folders(
            folders, None, args.frame_stride, 0, True)
        print(f"featurised {shared_frames.shape[0]} frames from "
              f"{len(set(shared_hashes))} files in {time.time() - t0:.0f}s", flush=True)
    for ant, seed in zip(ants, seeds):
        print(f"{ant} (seed {seed})", flush=True)
        checkpoint, path = train_ant(
            ant, seed, folders, state_root, units=args.units, epochs=args.epochs,
            scaled=not args.no_scale, snap=args.snap, file_limit=args.file_limit,
            frame_stride=args.frame_stride,
            exemplar_file_limit=args.exemplar_file_limit,
            frames=shared_frames, hashes=shared_hashes,
            eta0=args.eta0, eta_min=args.eta_min, sigma_min=args.sigma_min,
            conscience=args.conscience, horizon=args.horizon or None,
        )
        summary.append({
            "ant": ant, "seed": seed, "path": str(path),
            "checkpoint_sha256": checkpoint["checkpoint_sha256"],
            "dead_units_on_train": checkpoint["dead_units_on_train"],
            "train_seconds": checkpoint["corpus_provenance"]["train_seconds"],
            "neighbour_ratio": checkpoint["topology"]["neighbour_ratio"],
        })
        print(json.dumps(summary[-1]), flush=True)
    write_json_atomic(state_root / "train-summary.json",
                      {"architecture": ARCHITECTURE, "units": args.units,
                       "codebooks_merged": False, "ants": summary})


def encode_command(args) -> None:
    centers, scale, checkpoint = load_hebbian(Path(args.checkpoint))
    ids = encode_wav(Path(args.wav), centers, scale)
    from acoustic_units import collapse_runs
    print(json.dumps({
        "unit_namespace": f"{checkpoint['checkpoint_sha256']}:unit_id",
        "units": collapse_runs(ids, HOP_SECONDS),
    }))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(required=True)
    t = sub.add_parser("train")
    t.add_argument("--folders", default="corpus-combined/train")
    t.add_argument("--state", default="state-hebbian/hebbian")
    t.add_argument("--units", type=int, default=256)
    t.add_argument("--epochs", type=int, default=20)
    t.add_argument("--ants", type=int, default=4)
    t.add_argument("--file-limit", type=int, default=None)
    t.add_argument("--exemplar-file-limit", type=int, default=None)
    t.add_argument("--frame-stride", type=int, default=1)
    t.add_argument("--eta0", type=float, default=0.30)
    t.add_argument("--eta-min", type=float, default=0.02)
    t.add_argument("--sigma-min", type=float, default=0.50)
    t.add_argument("--conscience", type=float, default=0.15)
    t.add_argument("--horizon", type=int, default=0,
                   help="frames over which eta and sigma anneal; 0 = the whole run")
    t.add_argument("--no-scale", action="store_true")
    t.add_argument("--snap", action="store_true")
    t.set_defaults(fn=train_command)
    e = sub.add_parser("encode")
    e.add_argument("--checkpoint", required=True)
    e.add_argument("--wav", required=True)
    e.set_defaults(fn=encode_command)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
