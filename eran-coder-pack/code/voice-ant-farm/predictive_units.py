"""Predictive-coding acoustic units (pure numpy, no torch, no GPU).

Why
---
k-means optimises reconstruction of one frame.  That objective is gameable by
noise -- the controlled experiment in this project showed phase-randomised noise
*beating* structured speech on quantisation error -- and the measured
consequence is that a trained k=256 codebook (41.9% held-out 22-way top-1) is
statistically indistinguishable from picking 256 random real frames (40.3%,
p=0.54).  The optimiser contributes nothing.

Predicting the FUTURE cannot be gamed the same way, because noise is
unpredictable by construction.  This module is the smallest honest version of
that idea: one linear predictor per unit, trained by contrast (InfoNCE), with a
closed-form ridge M-step.  No neural net, no autodiff, one `np.linalg.solve`.

The learner
-----------
Frames are `feature_space.frame_features` (recommended26, level-invariant by
construction).  Each ant z-scores them with statistics fitted on its OWN
subsample -- ants never see each other's scaler, centroids, predictors or
exemplars.

State per unit u:
    m_u   centroid in z-space                    (encode() uses only this)
    W_u   linear map z_t -> predicted z_{t+delta}
    b_u   bias

Score of unit u for frame t against a candidate future y:
    s_u(t, y) = -||W_u z_t + b_u - y||^2 / (2 tau)

InfoNCE for the true future y_t against M negatives drawn from the ant's own
targets:
    nce_u(t) = s_u(t, y_t) - logsumexp([s_u(t, y_t), s_u(t, Y_1..Y_M)])
    chance   = -log(M + 1)

Training alternates:
  E-step  assign t to the unit minimising
              ||z_t - m_u||^2 / q_scale + beta * nll_u(t) / log(M+1)
          over the R centroids nearest z_t.  beta = 0 is exactly k-means in
          z-space, which is the control this file also runs.
  M-step  m_u <- mean of assigned z_t   (keeps the partition Voronoi-consistent,
                                          so encode() needs no future)
          W_u, b_u <- ridge solve on the (z_t, y_t) pairs assigned to u.

The restriction to the R nearest centroids is not an optimisation detail: it is
what keeps the train-time partition close to the Voronoi partition that
`encode` will actually use at test time.  Centroids still migrate, because they
are re-averaged over predictively-chosen members -- that is the mechanism by
which the predictive objective reshapes the cells.

Interface
---------
`PredictiveCodebook.encode(samples) -> unit ids`, one id per 10 ms frame, from
the current frame alone.  One real 400-sample waveform exemplar per unit, so
`fire.py` synthesis still works.  Checkpoints are JSON, hashed like the legacy
ones.

Quantisation error is not computed anywhere in this file, on purpose.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import feature_space as F
from acoustic_units import EXEMPLAR_RATE, FRAME_SECONDS, HOP_SECONDS, load_wav, resample_samples

CHECKPOINT_FORMAT = 1
ARCHITECTURE = "predictive-coding-vector-quantiser-infonce"
FRAME_SAMPLES = round(FRAME_SECONDS * EXEMPLAR_RATE)   # 400
HOP_SAMPLES = round(HOP_SECONDS * EXEMPLAR_RATE)       # 160


# --------------------------------------------------------------------------
# corpus -> frames
# --------------------------------------------------------------------------

@dataclass
class FrameCorpus:
    """Frames from many files, with file boundaries kept so that a (context,
    future) pair can never straddle two recordings."""

    x: np.ndarray            # (n_frames, d) float64, the ant's feature space
    starts: np.ndarray       # (n_files + 1,) index of each file's first frame
    paths: list[Path]
    seconds: float
    feature_set: str = F.CANONICAL

    @property
    def n(self) -> int:
        return len(self.x)

    def pair_index(self, delta: int) -> np.ndarray:
        """Indices t such that t and t+delta live in the same file."""
        keep = np.ones(len(self.x), dtype=bool)
        for a, b in zip(self.starts[:-1], self.starts[1:]):
            keep[max(a, b - delta):b] = False
        return np.flatnonzero(keep)


def load_frames(
    folders: list[Path], feature_set: str = F.CANONICAL, limit_files: int | None = None,
    seed: int = 0, max_frames: int | None = None, progress: bool = False,
) -> FrameCorpus:
    """Featurise WAV folders once.  `limit_files` subsamples FILES (not frames)
    with a seeded shuffle, so a subsample is still whole recordings and the
    pair structure survives."""
    paths: list[Path] = []
    for folder in folders:
        paths.extend(sorted(Path(folder).glob("*.wav")))
    if not paths:
        raise ValueError(f"no WAV files under {folders}")
    if limit_files is not None and limit_files < len(paths):
        order = np.random.default_rng(seed).permutation(len(paths))[:limit_files]
        paths = [paths[i] for i in sorted(order)]
    blocks, starts, kept, total_samples = [], [0], [], 0
    t0 = time.time()
    for i, path in enumerate(paths):
        audio = load_wav(path)
        samples = resample_samples(audio.samples, audio.rate, EXEMPLAR_RATE)
        if len(samples) < FRAME_SAMPLES + HOP_SAMPLES:
            continue
        block = F.extract(feature_set, samples)
        blocks.append(np.asarray(block, dtype=np.float64))
        starts.append(starts[-1] + len(block))
        kept.append(path)
        total_samples += len(samples)
        if max_frames is not None and starts[-1] >= max_frames:
            break
        if progress and (i + 1) % 2000 == 0:
            print(f"    {i + 1}/{len(paths)} files, {starts[-1]} frames, "
                  f"{time.time() - t0:.0f}s", flush=True)
    if not blocks:
        raise ValueError("no usable audio")
    return FrameCorpus(np.concatenate(blocks), np.asarray(starts, dtype=np.int64),
                       kept, total_samples / EXEMPLAR_RATE, feature_set)


# --------------------------------------------------------------------------
# the codebook
# --------------------------------------------------------------------------

@dataclass
class PredictiveCodebook:
    mean: np.ndarray          # (d,)  ant-private z-scoring
    scale: np.ndarray         # (d,)
    centers: np.ndarray       # (k, d) in z-space
    weights: np.ndarray       # (k, d, d + 1) linear predictors (last column = bias)
    feature_set: str
    delta: int
    exemplars: np.ndarray | None = None       # (k, FRAME_SAMPLES) float32
    exemplar_sources: list | None = None
    history: list | None = None

    @property
    def k(self) -> int:
        return len(self.centers)

    def normalise(self, x: np.ndarray) -> np.ndarray:
        return (np.asarray(x, dtype=np.float64) - self.mean) / self.scale

    def assign(self, x: np.ndarray) -> np.ndarray:
        """Unit id per frame from the frame alone -- no future, no file context."""
        return nearest(self.normalise(x), self.centers)

    def encode(self, samples: np.ndarray) -> np.ndarray:
        """Waveform -> unit sequence, one id per 10 ms hop."""
        return self.assign(F.extract(self.feature_set, np.asarray(samples)))

    def predict(self, z: np.ndarray, ids: np.ndarray) -> np.ndarray:
        w = self.weights[ids]
        return np.einsum("nij,nj->ni", w[:, :, :-1], z) + w[:, :, -1]


def nearest(z: np.ndarray, centers: np.ndarray, chunk: int = 20_000) -> np.ndarray:
    """argmin_u ||z - centers[u]||^2, chunked so the (n, k) matrix stays small."""
    out = np.empty(len(z), dtype=np.int64)
    cn = (centers ** 2).sum(axis=1)
    for a in range(0, len(z), chunk):
        block = z[a:a + chunk]
        d = cn[None, :] - 2.0 * (block @ centers.T)
        out[a:a + chunk] = d.argmin(axis=1)
    return out


def n_nearest(z: np.ndarray, centers: np.ndarray, r: int,
              chunk: int = 20_000) -> tuple[np.ndarray, np.ndarray]:
    """The r nearest centroids per frame and their squared distances.

    Returns (ids, dist), both (n, r), nearest first.  The distances come back
    with the caller so the (n, r, d) difference tensor is never materialised --
    at 40 h that array alone would be gigabytes.
    """
    r = min(r, len(centers))
    ids = np.empty((len(z), r), dtype=np.int64)
    dist = np.empty((len(z), r), dtype=np.float64)
    cn = (centers ** 2).sum(axis=1)
    for a in range(0, len(z), chunk):
        block = z[a:a + chunk]
        d = cn[None, :] - 2.0 * (block @ centers.T)
        part = np.argpartition(d, r - 1, axis=1)[:, :r]
        taken = np.take_along_axis(d, part, axis=1)
        order = taken.argsort(axis=1, kind="stable")
        ids[a:a + chunk] = np.take_along_axis(part, order, axis=1)
        dist[a:a + chunk] = (np.take_along_axis(taken, order, axis=1)
                             + (block ** 2).sum(axis=1)[:, None])
    return ids, np.maximum(dist, 0.0)


def ridge_fit(z: np.ndarray, y: np.ndarray, ids: np.ndarray, k: int,
              lam: float, min_members: int, predictor: str = "linear") -> np.ndarray:
    """One ridge-regularised linear predictor per unit, closed form.

    Units with too few members inherit the global predictor rather than a
    degenerate one; that is a fallback, not a shared parameter -- the global
    predictor is fitted on this ant's own frames only.

    `predictor="constant"` drops the linear part and keeps only the bias, so the
    predicted future is the unit's mean future and nothing else.  That is the
    stricter reading of "the current UNIT predicts the next frame": with a full
    linear map the unit only chooses *which* map to apply to a frame that is
    itself informative, so a good score need not mean the discrete symbol
    carries anything.  Both are measured.
    """
    d = z.shape[1]
    if predictor == "constant":
        out = np.zeros((k, y.shape[1], d + 1))
        counts = np.bincount(ids, minlength=k).astype(np.float64)
        sums = np.zeros((k, y.shape[1]))
        np.add.at(sums, ids, y)
        global_mean = y.mean(axis=0)
        enough = counts >= max(min_members, 1)
        out[:, :, d] = global_mean
        out[enough, :, d] = sums[enough] / counts[enough, None]
        return out
    if predictor != "linear":
        raise ValueError(f"unknown predictor {predictor!r}")
    aug = np.concatenate([z, np.ones((len(z), 1))], axis=1)   # (n, d+1)
    reg = lam * np.eye(d + 1)
    reg[-1, -1] = 0.0                                          # never shrink the bias
    gram_all = aug.T @ aug
    rhs_all = aug.T @ y
    global_w = np.linalg.solve(gram_all + reg, rhs_all).T      # (d, d+1)

    out = np.repeat(global_w[None, :, :], k, axis=0)
    order = np.argsort(ids, kind="stable")
    ids_sorted = ids[order]
    bounds = np.searchsorted(ids_sorted, np.arange(k + 1))
    for u in range(k):
        rows = order[bounds[u]:bounds[u + 1]]
        if len(rows) < min_members:
            continue
        a = aug[rows]
        out[u] = np.linalg.solve(a.T @ a + reg, a.T @ y[rows]).T
    return out


def infonce(z: np.ndarray, y: np.ndarray, cand: np.ndarray, weights: np.ndarray,
            negatives: np.ndarray, tau: float, chunk: int = 65_536,
            dtype: type = np.float64) -> np.ndarray:
    """InfoNCE score of every candidate unit for every frame.

    Returns (n, r): nce[t, j] = s_u(t, y_t) - logsumexp over {y_t} u negatives,
    with u = cand[t, j].  Always <= 0; -log(M + 1) is chance.

    Grouped by unit rather than by frame, because within one unit the predictor
    is a single matrix and the whole group is one real (m, d+1) @ (d+1, d)
    gemm -- a per-frame gather of (n, r, d, d+1) weights would be gigabytes and
    is memory-bound.  ||p - y||^2 is expanded as ||p||^2 - 2 p.y + ||y||^2, so
    all M negatives arrive in one further (m, d) @ (d, M) gemm.

    The (m, M) score block is then reduced entirely in place.  It is the only
    large array here and every extra pass over it costs more than the matmuls
    do; `dtype=np.float32` halves that traffic and is what `fit` uses, since the
    result is consumed by an argmin over r candidates.  The default stays
    float64 so the exactness test compares like with like.
    """
    n, r = cand.shape
    k = len(weights)
    aug = np.concatenate([z, np.ones((n, 1))], axis=1).astype(dtype)
    negatives = np.asarray(negatives, dtype=dtype)
    neg_sq = (negatives ** 2).sum(axis=1)                     # (M,)
    y = np.asarray(y, dtype=dtype)
    y_sq = (y ** 2).sum(axis=1)                               # (n,)
    scale = dtype(1.0 / (2.0 * tau))
    flat = cand.ravel()
    frame = np.repeat(np.arange(n), r)
    order = np.argsort(flat, kind="stable")
    bounds = np.searchsorted(flat[order], np.arange(k + 1))
    out = np.empty(n * r, dtype=np.float64)
    for u in range(k):
        sel = order[bounds[u]:bounds[u + 1]]
        if not len(sel):
            continue
        wu = weights[u].T.astype(dtype)
        for a in range(0, len(sel), chunk):
            piece = sel[a:a + chunk]
            f = frame[piece]
            p = aug[f] @ wu                                    # (m, d)
            p_sq = (p ** 2).sum(axis=1)
            s_pos = -(p_sq - 2.0 * (p * y[f]).sum(axis=1) + y_sq[f]) * scale
            s = p @ negatives.T                                # (m, M)
            s *= 2.0
            s -= p_sq[:, None]
            s -= neg_sq[None, :]
            s *= scale                                         # now s_neg
            mx = np.maximum(s_pos, s.max(axis=1))
            s -= mx[:, None]
            np.exp(s, out=s)
            total = s.sum(axis=1) + np.exp(s_pos - mx)
            out[piece] = s_pos - (mx + np.log(total))
    return out.reshape(n, r)


def kmeanspp_init(z: np.ndarray, k: int, rng: np.random.Generator) -> np.ndarray:
    """Seeded k-means++ over a capped subsample; the same init for beta=0 and
    beta>0, so any difference between them is the objective and not the seed."""
    cap = min(len(z), 60_000)
    pool = z if len(z) <= cap else z[rng.choice(len(z), cap, replace=False)]
    centers = np.empty((k, z.shape[1]))
    centers[0] = pool[rng.integers(len(pool))]
    closest = ((pool - centers[0]) ** 2).sum(axis=1)
    for i in range(1, k):
        total = closest.sum()
        if total <= 0:
            centers[i] = pool[rng.integers(len(pool))]
        else:
            centers[i] = pool[rng.choice(len(pool), p=closest / total)]
        closest = np.minimum(closest, ((pool - centers[i]) ** 2).sum(axis=1))
    return centers


def _reseed_dead(centers: np.ndarray, counts: np.ndarray, z: np.ndarray,
                 worst: np.ndarray, rng: np.random.Generator) -> int:
    """Re-seed empty units onto the frames the current model predicts worst."""
    dead = np.flatnonzero(counts == 0)
    if not len(dead):
        return 0
    order = np.argsort(-worst, kind="stable")[:max(len(dead) * 20, 100)]
    picks = rng.choice(order, size=len(dead), replace=len(order) < len(dead))
    centers[dead] = z[picks] + rng.normal(0.0, 1e-3, size=(len(dead), z.shape[1]))
    return len(dead)


def fit(corpus: FrameCorpus, k: int, seed: int, *, beta: float = 1.0,
        delta: int = 3, rounds: int = 12, candidates: int = 8,
        negatives: int = 256, tau: float = 1.0, ridge: float = 1.0,
        min_members: int = 40, max_pairs: int | None = None,
        shuffle_targets: bool = False, predictor: str = "linear",
        verbose: bool = False) -> PredictiveCodebook:
    """Train one ant.  Every fitted quantity here is private to this ant.

    `shuffle_targets` is the control that decides whether any of this is about
    prediction: it permutes the futures across the corpus, destroying the
    temporal pairing and nothing else -- same features, same k, same rounds,
    same contrastive machinery, same negatives, same reseeding.  If the learner
    scores the same with the futures shuffled, the gain was never predictive.
    """
    rng = np.random.default_rng(seed)
    idx = corpus.pair_index(delta)
    if max_pairs is not None and len(idx) > max_pairs:
        idx = np.sort(rng.choice(idx, max_pairs, replace=False))
    if len(idx) < 10 * k:
        raise ValueError(f"need at least {10 * k} usable frame pairs, got {len(idx)}")

    raw = corpus.x[idx]
    mean = raw.mean(axis=0)
    scale = np.maximum(raw.std(axis=0), 1e-6)
    z = (raw - mean) / scale
    y = (corpus.x[idx + delta] - mean) / scale
    if shuffle_targets:
        # a separate generator, so the shuffled control keeps the identical
        # k-means++ initialisation and the identical negative draws
        y = y[np.random.default_rng(seed + 999_983).permutation(len(y))]

    centers = kmeanspp_init(z, k, rng)
    neg_pool = y[rng.choice(len(y), min(negatives, len(y)), replace=False)]
    weights = ridge_fit(z, y, np.zeros(len(z), dtype=np.int64), k, ridge,
                        len(z) + 1, predictor)
    chance = np.log(len(neg_pool) + 1)
    history = []

    for it in range(rounds):
        t0 = time.time()
        cand, q = n_nearest(z, centers, candidates)                  # (n, r) each
        q_scale = float(q[:, 0].mean()) or 1.0
        if beta > 0.0:
            nce = infonce(z, y, cand, weights, neg_pool, tau, dtype=np.float32)
            cost = q / q_scale + beta * (-nce) / chance
        else:
            nce = np.zeros_like(q)
            cost = q
        choice = cost.argmin(axis=1)
        ids = np.take_along_axis(cand, choice[:, None], axis=1).ravel()
        chosen_nce = np.take_along_axis(nce, choice[:, None], axis=1).ravel()

        counts = np.bincount(ids, minlength=k)
        sums = np.zeros_like(centers)
        np.add.at(sums, ids, z)
        alive = counts > 0
        centers[alive] = sums[alive] / counts[alive, None]
        reseeded = _reseed_dead(centers, counts, z, -chosen_nce, rng)

        weights = ridge_fit(z, y, ids, k, ridge, min_members, predictor)
        # honest re-measurement of the objective under the new predictors
        rec = float(np.mean(np.take_along_axis(q, choice[:, None], axis=1)))
        history.append({
            "round": it,
            "mean_infonce_nats": float(chosen_nce.mean()),
            "chance_infonce_nats": float(-chance),
            "mean_quantisation": rec,
            "dead_units": int((counts == 0).sum()),
            "reseeded": int(reseeded),
            "seconds": round(time.time() - t0, 1),
        })
        if verbose:
            h = history[-1]
            print(f"    round {it:2d}  nce {h['mean_infonce_nats']:+.4f} "
                  f"(chance {h['chance_infonce_nats']:+.3f})  "
                  f"q {h['mean_quantisation']:.4f}  dead {h['dead_units']:3d}  "
                  f"{h['seconds']}s", flush=True)
        neg_pool = y[rng.choice(len(y), min(negatives, len(y)), replace=False)]

    return PredictiveCodebook(mean=mean, scale=scale, centers=centers,
                              weights=weights, feature_set=corpus.feature_set,
                              delta=delta, history=history)


def fit_kmeans(corpus: FrameCorpus, k: int, seed: int, *, rounds: int = 12,
               delta: int = 3, max_pairs: int | None = None,
               verbose: bool = False) -> PredictiveCodebook:
    """beta = 0 control: identical code path, identical init, no predictive term."""
    return fit(corpus, k, seed, beta=0.0, delta=delta, rounds=rounds,
               max_pairs=max_pairs, verbose=verbose)


def fit_random_frames(corpus: FrameCorpus, k: int, seed: int, *, delta: int = 3,
                      max_pairs: int | None = None) -> PredictiveCodebook:
    """The baseline that actually matters: k random REAL frames, never fitted."""
    rng = np.random.default_rng(seed)
    idx = corpus.pair_index(delta)
    if max_pairs is not None and len(idx) > max_pairs:
        idx = np.sort(rng.choice(idx, max_pairs, replace=False))
    raw = corpus.x[idx]
    mean, scale = raw.mean(axis=0), np.maximum(raw.std(axis=0), 1e-6)
    z = (raw - mean) / scale
    centers = z[rng.choice(len(z), k, replace=False)].copy()
    y = (corpus.x[idx + delta] - mean) / scale
    weights = ridge_fit(z, y, nearest(z, centers), k, 1.0, 40)
    return PredictiveCodebook(mean=mean, scale=scale, centers=centers,
                              weights=weights, feature_set=corpus.feature_set,
                              delta=delta, history=[])


# --------------------------------------------------------------------------
# waveform exemplars -- synthesis must keep working
# --------------------------------------------------------------------------

def learn_exemplars(book: PredictiveCodebook, folders: list[Path],
                    limit_files: int | None = None, seed: int = 0) -> None:
    """One real 400-sample waveform per unit: the training frame closest to it."""
    paths: list[Path] = []
    for folder in folders:
        paths.extend(sorted(Path(folder).glob("*.wav")))
    if limit_files is not None and limit_files < len(paths):
        order = np.random.default_rng(seed).permutation(len(paths))[:limit_files]
        paths = [paths[i] for i in sorted(order)]
    best = np.full(book.k, np.inf)
    frames = np.zeros((book.k, FRAME_SAMPLES), dtype=np.float32)
    sources: list = [None] * book.k
    cn = (book.centers ** 2).sum(axis=1)
    for path in paths:
        audio = load_wav(path)
        samples = resample_samples(audio.samples, audio.rate, EXEMPLAR_RATE)
        if len(samples) < FRAME_SAMPLES:
            continue
        z = book.normalise(F.extract(book.feature_set, samples))
        d = (z ** 2).sum(axis=1)[:, None] + cn[None, :] - 2.0 * (z @ book.centers.T)
        index = d.argmin(axis=0)
        value = d[index, np.arange(book.k)]
        better = np.flatnonzero(value < best)
        for u in better:
            start = int(index[u]) * HOP_SAMPLES
            window = samples[start:start + FRAME_SAMPLES]
            if len(window) < FRAME_SAMPLES:
                continue
            best[u] = value[u]
            frames[u] = window
            sources[u] = {"file": path.name, "frame": int(index[u]),
                          "pcm_sha256": audio.pcm_sha256}
    if any(s is None for s in sources):
        missing = [i for i, s in enumerate(sources) if s is None]
        raise ValueError(f"no waveform exemplar for units {missing[:8]}")
    book.exemplars = frames
    book.exemplar_sources = sources


# --------------------------------------------------------------------------
# checkpoints
# --------------------------------------------------------------------------

def checkpoint_digest(checkpoint: dict) -> str:
    payload = {k: v for k, v in checkpoint.items() if k != "checkpoint_sha256"}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def save(book: PredictiveCodebook, path: Path, extra: dict | None = None) -> dict:
    checkpoint = {
        "format_version": CHECKPOINT_FORMAT,
        "architecture": ARCHITECTURE,
        "feature_set": book.feature_set,
        "feature_dim": int(book.centers.shape[1]),
        "units": int(book.k),
        "delta_frames": int(book.delta),
        "exemplar_rate": EXEMPLAR_RATE,
        "exemplar_frame_samples": FRAME_SAMPLES,
        "exemplar_hop_samples": HOP_SAMPLES,
        "mean": book.mean.tolist(),
        "scale": book.scale.tolist(),
        "centers": book.centers.tolist(),
        "weights": book.weights.tolist(),
        "history": book.history,
    }
    if book.exemplars is not None:
        checkpoint["exemplars_pcm16"] = [
            np.clip(np.rint(f * 32767), -32768, 32767).astype("<i2").tolist()
            for f in book.exemplars
        ]
        checkpoint["exemplar_sources"] = book.exemplar_sources
    if extra:
        checkpoint.update(extra)
    checkpoint["checkpoint_sha256"] = checkpoint_digest(checkpoint)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(checkpoint), encoding="utf-8")
    tmp.replace(path)
    return checkpoint


def load(path: Path) -> PredictiveCodebook:
    checkpoint = json.loads(Path(path).read_text(encoding="utf-8"))
    if checkpoint.get("format_version") != CHECKPOINT_FORMAT:
        raise ValueError(f"{path}: unsupported checkpoint format")
    if checkpoint.get("checkpoint_sha256") != checkpoint_digest(checkpoint):
        raise ValueError(f"{path}: checkpoint hash mismatch")
    exemplars = None
    if "exemplars_pcm16" in checkpoint:
        exemplars = (np.asarray(checkpoint["exemplars_pcm16"], dtype=np.float32)
                     / 32768.0)
    return PredictiveCodebook(
        mean=np.asarray(checkpoint["mean"], dtype=np.float64),
        scale=np.asarray(checkpoint["scale"], dtype=np.float64),
        centers=np.asarray(checkpoint["centers"], dtype=np.float64),
        weights=np.asarray(checkpoint["weights"], dtype=np.float64),
        feature_set=checkpoint["feature_set"],
        delta=int(checkpoint["delta_frames"]),
        exemplars=exemplars,
        exemplar_sources=checkpoint.get("exemplar_sources"),
        history=checkpoint.get("history"),
    )
