"""Segment-level acoustic units for the Hebrew Voice Ant Farm (pure numpy).

Why this module exists
----------------------
The colony quantises every 25 ms frame independently.  A syllable is not a bag
of frames, it is a trajectory: /ba/ is a closure, a burst, a formant transition
and a steady vowel, in that order, with those durations.  The frame-wise learner
throws the ordering away twice over -- once by scoring each frame against the
codebook alone, and once by run-length collapsing, which deletes duration.

This module quantises SEGMENTS.  Three stages, no labels anywhere:

  1. boundaries    an unsupervised spectral-change detector with a Schmitt
                   trigger (`Segmenter`).  Two thresholds and a refractory
                   floor, so a noisy novelty curve cannot fragment a vowel into
                   six units.
  2. descriptors   each segment becomes ONE vector: `parts` equal-time means of
                   the static cepstrum (mean + slope + curvature for parts=3),
                   the mean delta block, and log duration.  Duration is a
                   feature here; in the frame-wise design it is discarded.
  3. codebook      k-means over segment descriptors, one private codebook per
                   ant, plus one real waveform exemplar per unit so synthesis
                   still works.

`encode` still returns one unit id per 10 ms frame, constant inside a segment.
That is deliberate: it is the interface the rest of the system already speaks,
and it means `sequence_probes.collapse` recovers the segment string exactly
while the unit histogram stays duration-weighted.

Founding rule: nothing in here lets two ants touch the same fitted number.  Each
ant fits its own scaler, its own centres, its own exemplars, on its own seeded
bootstrap of the segment pool.  `Segmenter` holds no fitted parameters at all --
it is a pure function of one waveform, like the feature extractor.

Frame features come from `feature_space.frame_features` (recommended26: c1..c20
of a 26-band log-mel DCT plus 6 deltas, level-invariant by construction).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import numpy as np

import feature_space as F
import sequence_probes as sp
from acoustic_units import EXEMPLAR_RATE, load_wav, resample_samples

RATE = F.RATE
FRAME = F.FRAME          # 400 samples, 25 ms
HOP = F.HOP              # 160 samples, 10 ms
STATIC = 20              # c1..c20 of recommended26; the rest is the delta block
CHECKPOINT_FORMAT = 1
ARCHITECTURE = "segmental-vector-quantizer-with-waveform-exemplars"


# ---------------------------------------------------------------------------
# stage 1: unsupervised boundaries
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Segmenter:
    """Spectral-change boundary detector.  No fitted parameters, no labels.

    The novelty at frame t is the Euclidean distance between the mean static
    cepstrum of the `window` frames before t and the `window` frames after it.
    A single-frame difference is far too noisy at 10 ms; contrasting two 30 ms
    neighbourhoods is the cheapest thing that is not.

    Hysteresis is a Schmitt trigger on that curve: the detector must be *armed*
    to fire, it arms only after the novelty falls back below `low`, and it fires
    only on a local maximum at or above `high`.  Without it a broad transition
    (a diphthong, a released stop) emits a boundary on every frame of its own
    rising edge and the vowel shatters.  `min_frames` is a hard refractory floor
    on top of that; `max_frames` splits a segment that never changes.

    Thresholds are quoted in robust sigmas above the median of this file's own
    novelty curve.  That is an utterance statistic, and it is used ONLY to place
    boundaries -- never to build a feature vector, which is why the per-utterance
    normalisation that was catastrophic for classification is harmless here.
    """
    window: int = 3          # frames contrasted either side of a candidate
    smooth: int = 1          # moving average half-width on the novelty curve
    high: float = 1.0        # fire threshold, robust sigmas above the median
    low: float = 0.3         # re-arm threshold; must be below `high`
    min_frames: int = 4      # refractory floor, 40 ms
    max_frames: int = 30     # 300 ms; longer runs are split evenly

    def __post_init__(self) -> None:
        if self.low > self.high:
            raise ValueError("hysteresis needs low <= high")
        if self.min_frames < 1 or self.window < 1:
            raise ValueError("window and min_frames must be positive")
        if self.max_frames < 2 * self.min_frames:
            raise ValueError("max_frames must admit at least two minimal segments")

    # -- novelty ------------------------------------------------------------
    def novelty(self, x: np.ndarray) -> np.ndarray:
        """(n,) spectral change curve; zero inside `window` of either edge."""
        s = np.asarray(x, dtype=np.float64)[:, :STATIC]
        n = len(s)
        out = np.zeros(n, dtype=np.float64)
        if n < 2 * self.window + 1:
            return out
        c = np.zeros((n + 1, s.shape[1]), dtype=np.float64)
        np.cumsum(s, axis=0, out=c[1:])
        t = np.arange(n)
        lo = np.maximum(t - self.window, 0)
        hi = np.minimum(t + self.window, n)
        left = (c[t] - c[lo]) / np.maximum(t - lo, 1)[:, None]
        right = (c[hi] - c[t]) / np.maximum(hi - t, 1)[:, None]
        out = np.sqrt(((right - left) ** 2).sum(axis=1))
        out[:self.window] = 0.0
        out[n - self.window:] = 0.0
        if self.smooth > 0:
            width = 2 * self.smooth + 1
            pad = np.concatenate([np.full(self.smooth, out[0]), out,
                                  np.full(self.smooth, out[-1])])
            kernel = np.ones(width) / width
            out = np.convolve(pad, kernel, mode="valid")
        return out

    # -- Schmitt trigger ----------------------------------------------------
    def edges(self, x: np.ndarray) -> np.ndarray:
        """Segment edges as frame indices, always starting at 0 and ending at n."""
        n = len(x)
        if n <= max(2 * self.min_frames, 2):
            return np.asarray([0, n], dtype=np.int64)
        nov = self.novelty(x)
        median = float(np.median(nov))
        mad = float(np.median(np.abs(nov - median)))
        scale = max(1.4826 * mad, 1e-9)
        fire = median + self.high * scale
        arm = median + self.low * scale
        picks: list[int] = []
        armed = True
        last = 0
        for t in range(1, n - 1):
            if nov[t] < arm:
                armed = True
                continue
            if (armed and nov[t] >= fire
                    and nov[t] >= nov[t - 1] and nov[t] > nov[t + 1]
                    and t - last >= self.min_frames
                    and n - t >= self.min_frames):
                picks.append(t)
                last = t
                armed = False
        out = [0]
        for a, b in zip([0] + picks, picks + [n]):
            length = b - a
            if length > self.max_frames:
                parts = int(np.ceil(length / self.max_frames))
                cuts = a + np.round(np.arange(1, parts) * length / parts).astype(np.int64)
                out.extend(int(c) for c in cuts)
            out.append(int(b))
        return np.asarray(out, dtype=np.int64)


# ---------------------------------------------------------------------------
# stage 2: one vector per segment
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Descriptor:
    """Segment -> vector.  `parts` equal-time means, deltas, log duration."""
    parts: int = 3
    use_delta: bool = True
    use_duration: bool = True
    duration_weight: float = 1.0   # applied AFTER z-scoring, so it is not a no-op

    @property
    def dim(self) -> int:
        return (self.parts * STATIC + (26 - STATIC) * int(self.use_delta)
                + int(self.use_duration))

    def __call__(self, x: np.ndarray, edges: np.ndarray) -> np.ndarray:
        """(m, dim) for the m segments delimited by `edges` (length m + 1)."""
        x = np.asarray(x, dtype=np.float64)
        n = len(x)
        c = np.zeros((n + 1, x.shape[1]), dtype=np.float64)
        np.cumsum(x, axis=0, out=c[1:])
        a, b = edges[:-1], edges[1:]
        length = (b - a).astype(np.int64)
        cols = []
        for p in range(self.parts):
            s = a + (p * length) // self.parts
            e = a + ((p + 1) * length) // self.parts
            e = np.minimum(np.maximum(e, s + 1), b)
            s = np.minimum(s, e - 1)
            cols.append((c[e, :STATIC] - c[s, :STATIC]) / (e - s)[:, None])
        if self.use_delta:
            cols.append((c[b, STATIC:] - c[a, STATIC:]) / length[:, None])
        if self.use_duration:
            cols.append(np.log(length.astype(np.float64))[:, None])
        return np.concatenate(cols, axis=1)


# ---------------------------------------------------------------------------
# stage 3: k-means over segments
# ---------------------------------------------------------------------------

def assign(x: np.ndarray, centers: np.ndarray, chunk: int = 20_000
           ) -> tuple[np.ndarray, np.ndarray]:
    """Nearest centre id and its squared distance, chunked so memory stays flat."""
    norms = (centers ** 2).sum(axis=1)
    ids = np.empty(len(x), dtype=np.int64)
    dist = np.empty(len(x), dtype=np.float64)
    for start in range(0, len(x), chunk):
        block = x[start:start + chunk]
        d = (block ** 2).sum(axis=1)[:, None] - 2.0 * block @ centers.T + norms[None, :]
        j = d.argmin(axis=1)
        ids[start:start + chunk] = j
        dist[start:start + chunk] = np.maximum(d[np.arange(len(block)), j], 0.0)
    return ids, dist


def _plus_plus(x: np.ndarray, k: int, rng: np.random.Generator) -> np.ndarray:
    """k-means++ seeding.  Fewer dead units than uniform seeding, same cost class."""
    centers = np.empty((k, x.shape[1]), dtype=np.float64)
    centers[0] = x[rng.integers(len(x))]
    closest = ((x - centers[0]) ** 2).sum(axis=1)
    for j in range(1, k):
        total = float(closest.sum())
        if total <= 0.0:
            centers[j] = x[rng.integers(len(x))]
        else:
            centers[j] = x[int(rng.choice(len(x), p=closest / total))]
        closest = np.minimum(closest, ((x - centers[j]) ** 2).sum(axis=1))
    return centers


def kmeans(x: np.ndarray, k: int, seed: int, rounds: int = 40,
           tolerance: float = 1e-6) -> tuple[np.ndarray, np.ndarray]:
    """Lloyd with k-means++ seeding and farthest-point revival of empty cells."""
    x = np.asarray(x, dtype=np.float64)
    if len(x) < k:
        raise ValueError(f"need at least {k} segments, got {len(x)}")
    rng = np.random.default_rng(seed)
    centers = _plus_plus(x, k, rng)
    ids = np.zeros(len(x), dtype=np.int64)
    for _ in range(rounds):
        ids, dist = assign(x, centers)
        counts = np.bincount(ids, minlength=k)
        order = np.argsort(ids, kind="stable")
        cumulative = np.zeros((len(x) + 1, x.shape[1]), dtype=np.float64)
        np.cumsum(x[order], axis=0, out=cumulative[1:])
        starts = np.searchsorted(ids[order], np.arange(k), side="left")
        ends = np.searchsorted(ids[order], np.arange(k), side="right")
        updated = (cumulative[ends] - cumulative[starts]) / np.maximum(counts, 1)[:, None]
        empty = np.flatnonzero(counts == 0)
        if len(empty):
            far = np.argsort(-dist, kind="stable")[:len(empty)]
            updated[empty] = x[far]
        shift = float(np.abs(updated - centers).max())
        centers = updated
        if shift < tolerance and not len(empty):
            break
    ids, _ = assign(x, centers)
    return centers, ids


# ---------------------------------------------------------------------------
# the ant
# ---------------------------------------------------------------------------

def speech_span(samples: np.ndarray) -> tuple[int, int]:
    """The colony's own span rule, driven by the legacy log-energy column."""
    return sp.speech_span(F.log_energy(samples)[:, None])


def segment_waveform(samples: np.ndarray, first: int, last: int) -> np.ndarray:
    """Samples covered by frames [first, last) of `samples`."""
    start = first * HOP
    stop = min(len(samples), (last - 1) * HOP + FRAME)
    return samples[start:max(stop, start + 1)].astype(np.float32, copy=True)


def resample_to(wave: np.ndarray, length: int) -> np.ndarray:
    if len(wave) == length:
        return wave.astype(np.float32, copy=True)
    src = np.linspace(0.0, 1.0, len(wave), endpoint=False)
    dst = np.linspace(0.0, 1.0, max(length, 1), endpoint=False)
    return np.interp(dst, src, wave).astype(np.float32)


def runs_of(ids: np.ndarray) -> list[tuple[int, int]]:
    """[(unit, frame_count), ...] for a per-frame id sequence."""
    ids = np.asarray(ids, dtype=np.int64)
    if len(ids) == 0:
        return []
    change = np.flatnonzero(np.concatenate([[True], ids[1:] != ids[:-1], [True]]))
    return [(int(ids[change[i]]), int(change[i + 1] - change[i]))
            for i in range(len(change) - 1)]


class SegmentalAnt:
    """One independent learner.  Its centres and exemplars are private to it."""

    def __init__(self, ant: str, seed: int, units: int = 128,
                 segmenter: Segmenter | None = None,
                 descriptor: Descriptor | None = None,
                 bootstrap: bool = True, max_segments: int = 400_000,
                 rounds: int = 40, whiten: bool = False) -> None:
        self.ant = ant
        self.seed = int(seed)
        self.units = int(units)
        self.segmenter = segmenter or Segmenter()
        self.descriptor = descriptor or Descriptor()
        self.bootstrap = bootstrap
        self.max_segments = int(max_segments)
        self.rounds = int(rounds)
        self.whiten = bool(whiten)
        self.mean_: np.ndarray | None = None
        self.std_: np.ndarray | None = None
        self.rotation_: np.ndarray | None = None
        self.centers_: np.ndarray | None = None
        self.exemplars_: list[np.ndarray] = []
        self.train_counts_: np.ndarray | None = None
        self.provenance_: list[dict] = []

    # -- feature plumbing ---------------------------------------------------
    def frames(self, samples: np.ndarray) -> np.ndarray:
        return F.frame_features(samples)

    def describe_features(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        edges = self.segmenter.edges(x)
        return self.descriptor(x, edges), edges

    def scale(self, d: np.ndarray) -> np.ndarray:
        if self.mean_ is None or self.std_ is None:
            raise ValueError(f"{self.ant} is not fitted")
        out = (np.asarray(d, dtype=np.float64) - self.mean_) / self.std_
        if self.rotation_ is not None:
            out = out @ self.rotation_
        if self.descriptor.use_duration and self.descriptor.duration_weight != 1.0:
            out[:, -1] *= self.descriptor.duration_weight
        return out

    def _fit_rotation(self, draw: np.ndarray) -> None:
        """PCA whitening of the segment space, fitted on this ant's own draw.

        `parts` block means of one trajectory are heavily correlated -- part 1
        and part 2 of a 60 ms segment overlap in everything but the transition.
        Unwhitened Euclidean k-means therefore spends its centres on the mean
        spectrum and almost none on the trajectory, which is the one thing a
        segmental model is supposed to see.  Duration is left out of the
        rotation so that `duration_weight` still means something.
        """
        keep = draw.shape[1] - int(self.descriptor.use_duration)
        z = (draw[:, :keep] - self.mean_[:keep]) / self.std_[:keep]
        covariance = np.cov(z, rowvar=False)
        values, vectors = np.linalg.eigh(covariance)
        floor = max(float(values.max()) * 1e-6, 1e-9)
        rotation = vectors / np.sqrt(np.maximum(values, floor))
        full = np.zeros((draw.shape[1], draw.shape[1]))
        full[:keep, :keep] = rotation
        if self.descriptor.use_duration:
            full[-1, -1] = 1.0
        self.rotation_ = full

    # -- fitting ------------------------------------------------------------
    def pool(self, corpus: list[dict]) -> tuple[np.ndarray, list[dict]]:
        """Every segment in `corpus` as one descriptor matrix, plus provenance."""
        blocks, provenance = [], []
        for item in corpus:
            x = item.get("frames")
            if x is None:
                x = self.frames(item["samples"])
            first, last = item.get("span", (0, len(x)))
            window = x[first:last]
            if len(window) < 2:
                continue
            d, edges = self.describe_features(window)
            blocks.append(d)
            for a, b in zip(edges[:-1], edges[1:]):
                provenance.append({"path": item.get("path"),
                                   "first": int(first + a), "last": int(first + b)})
        if not blocks:
            raise ValueError("no segments found in the training corpus")
        return np.concatenate(blocks, axis=0), provenance

    def fit(self, corpus: list[dict], exemplars: bool = True) -> "SegmentalAnt":
        """`corpus` items need `samples` (or `frames`) and, for exemplars, `path`.

        Each ant draws its own seeded bootstrap of the pooled segments, fits its
        own z-scaler on that draw, and runs its own k-means.  Nothing crosses.
        """
        pool, provenance = self.pool(corpus)
        rng = np.random.default_rng(self.seed)
        index = np.arange(len(pool))
        if self.bootstrap:
            index = rng.integers(0, len(pool), size=len(pool))
        if len(index) > self.max_segments:
            index = rng.choice(index, self.max_segments, replace=False)
        draw = pool[index]
        self.mean_ = draw.mean(axis=0)
        self.std_ = np.maximum(draw.std(axis=0), 1e-6)
        self.rotation_ = None
        if self.whiten:
            self._fit_rotation(draw)
        centers, _ = kmeans(self.scale(draw), self.units, self.seed, self.rounds)
        self.centers_ = centers
        ids, distance = assign(self.scale(pool), centers)
        self.train_counts_ = np.bincount(ids, minlength=self.units)
        if exemplars:
            self._learn_exemplars(pool, ids, distance, provenance)
        return self

    def _learn_exemplars(self, pool, ids, distance, provenance) -> None:
        """One real training waveform per unit: the segment closest to the centre."""
        best = np.full(self.units, np.inf)
        chosen: list[int | None] = [None] * self.units
        for i, (unit, d) in enumerate(zip(ids, distance)):
            if d < best[unit]:
                best[unit] = d
                chosen[unit] = i
        cache: dict[str, np.ndarray] = {}
        self.exemplars_, self.provenance_ = [], []
        for unit in range(self.units):
            i = chosen[unit]
            if i is None:                      # dead unit: 25 ms of digital silence
                self.exemplars_.append(np.zeros(FRAME, dtype=np.float32))
                self.provenance_.append({"path": None, "first": None, "last": None})
                continue
            record = provenance[i]
            path = record["path"]
            if path not in cache:
                audio = load_wav(Path(path))
                cache[path] = resample_samples(audio.samples, audio.rate, EXEMPLAR_RATE)
                if len(cache) > 64:            # keep the working set small
                    cache.pop(next(iter(cache)))
            wave = segment_waveform(cache[path], record["first"], record["last"])
            self.exemplars_.append(wave)
            self.provenance_.append(record)

    # -- encoding -----------------------------------------------------------
    def encode_features(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """(one unit id per frame, segment edges).  Constant inside a segment."""
        if self.centers_ is None:
            raise ValueError(f"{self.ant} is not fitted")
        if len(x) < 2:
            return np.zeros(len(x), dtype=np.int64), np.asarray([0, len(x)])
        d, edges = self.describe_features(x)
        units, _ = assign(self.scale(d), self.centers_)
        return np.repeat(units, np.diff(edges)), edges

    def encode(self, samples: np.ndarray) -> np.ndarray:
        """The interface the rest of the system speaks: audio -> unit sequence."""
        return self.encode_features(self.frames(samples))[0]

    def encode_span(self, samples: np.ndarray) -> np.ndarray:
        x = self.frames(samples)
        first, last = speech_span(samples)
        return self.encode_features(x[first:last])[0]

    # -- synthesis ----------------------------------------------------------
    def synthesize(self, ids: np.ndarray, crossfade: int = 80) -> np.ndarray:
        """Rebuild audio from unit ids alone, using the stored real waveforms."""
        if self.centers_ is None:
            raise ValueError(f"{self.ant} is not fitted")
        ids = np.asarray(ids, dtype=np.int64)
        if ids.ndim != 1 or len(ids) == 0:
            raise ValueError("unit sequence must be a nonempty 1-D array")
        if int(ids.min()) < 0 or int(ids.max()) >= self.units:
            raise ValueError("unit sequence contains an out-of-range id")
        pieces = [resample_to(self.exemplars_[unit], max(count * HOP, HOP))
                  for unit, count in runs_of(ids)]
        total = sum(len(p) for p in pieces) - crossfade * (len(pieces) - 1)
        out = np.zeros(max(total, 1), dtype=np.float64)
        weight = np.zeros_like(out)
        cursor = 0
        for piece in pieces:
            ramp = np.ones(len(piece))
            fade = min(crossfade, len(piece) // 2)
            if fade > 0:
                taper = 0.5 - 0.5 * np.cos(np.pi * np.arange(fade) / fade)
                ramp[:fade] = taper
                ramp[-fade:] = taper[::-1]
            stop = min(cursor + len(piece), len(out))
            out[cursor:stop] += (piece * ramp)[:stop - cursor]
            weight[cursor:stop] += ramp[:stop - cursor]
            cursor = max(stop - crossfade, cursor + 1)
        out /= np.maximum(weight, 1e-3)
        return np.clip(out, -1.0, 1.0).astype(np.float32)

    # -- persistence --------------------------------------------------------
    def to_checkpoint(self, corpus_note: str = "") -> dict:
        if self.centers_ is None:
            raise ValueError(f"{self.ant} is not fitted")
        payload = {
            "format_version": CHECKPOINT_FORMAT,
            "architecture": ARCHITECTURE,
            "ant": self.ant,
            "seed": self.seed,
            "units": self.units,
            "descriptor_dim": int(self.centers_.shape[1]),
            "corpus": corpus_note,
            "segmenter": asdict(self.segmenter),
            "descriptor": asdict(self.descriptor),
            "bootstrap": self.bootstrap,
            "whiten": self.whiten,
            "rotation": None if self.rotation_ is None else self.rotation_.tolist(),
            "frame_seconds": F.FRAME_SECONDS,
            "hop_seconds": F.HOP_SECONDS,
            "exemplar_rate": EXEMPLAR_RATE,
            "feature_set": F.CANONICAL,
            "scaler_mean": self.mean_.tolist(),
            "scaler_std": self.std_.tolist(),
            "centers": self.centers_.tolist(),
            "train_segment_counts": self.train_counts_.tolist(),
            "dead_units_train": int(np.sum(self.train_counts_ == 0)),
            "exemplars_pcm16": [
                np.clip(np.rint(w * 32767), -32768, 32767).astype("<i2").tolist()
                for w in self.exemplars_],
            "exemplar_provenance": self.provenance_,
        }
        payload["checkpoint_sha256"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return payload

    @classmethod
    def from_checkpoint(cls, payload: dict) -> "SegmentalAnt":
        ant = cls(payload["ant"], payload["seed"], payload["units"],
                  Segmenter(**payload["segmenter"]),
                  Descriptor(**payload["descriptor"]),
                  bool(payload.get("bootstrap", True)),
                  whiten=bool(payload.get("whiten", False)))
        ant.mean_ = np.asarray(payload["scaler_mean"], dtype=np.float64)
        ant.std_ = np.asarray(payload["scaler_std"], dtype=np.float64)
        ant.rotation_ = (None if payload.get("rotation") is None
                         else np.asarray(payload["rotation"], dtype=np.float64))
        ant.centers_ = np.asarray(payload["centers"], dtype=np.float64)
        ant.train_counts_ = np.asarray(payload["train_segment_counts"], dtype=np.int64)
        ant.exemplars_ = [np.asarray(w, dtype=np.float32) / 32768.0
                          for w in payload["exemplars_pcm16"]]
        ant.provenance_ = payload["exemplar_provenance"]
        return ant


def write_checkpoint(path: Path, payload: dict) -> None:
    """Compact, not indented: the exemplar block is a million integers."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    temporary.replace(path)


def load_checkpoint(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("format_version") != CHECKPOINT_FORMAT:
        raise ValueError(f"{path}: unsupported segmental checkpoint format")
    expected = payload.get("checkpoint_sha256")
    body = {k: v for k, v in payload.items() if k != "checkpoint_sha256"}
    actual = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if not expected or expected != actual:
        raise ValueError(f"{path}: checkpoint hash mismatch")
    return payload


# ---------------------------------------------------------------------------
# controls
# ---------------------------------------------------------------------------

def random_real_segments(ant: SegmentalAnt, corpus: list[dict], seed: int,
                         exemplars: bool = True) -> SegmentalAnt:
    """The control that matters: k real segments as centres, no Lloyd iterations.

    Random real FRAMES tied trained k-means in the frame-wise design (40.3% vs
    41.9%, p = 0.54).  If segment k-means does not beat the same control at the
    segment level, the optimiser is still contributing nothing and the win --
    if there is one -- belongs to the representation, not to the learning.
    """
    control = SegmentalAnt(ant.ant, seed, ant.units, ant.segmenter, ant.descriptor,
                           bootstrap=False, max_segments=ant.max_segments,
                           whiten=ant.whiten)
    pool, provenance = control.pool(corpus)
    control.mean_ = pool.mean(axis=0)
    control.std_ = np.maximum(pool.std(axis=0), 1e-6)
    if control.whiten:
        control._fit_rotation(pool)
    rng = np.random.default_rng(seed)
    picked = rng.choice(len(pool), control.units, replace=False)
    control.centers_ = control.scale(pool[picked])
    ids, distance = assign(control.scale(pool), control.centers_)
    control.train_counts_ = np.bincount(ids, minlength=control.units)
    if exemplars:
        control._learn_exemplars(pool, ids, distance, provenance)
    return control


def with_units(ant: SegmentalAnt, units: int) -> SegmentalAnt:
    return SegmentalAnt(ant.ant, ant.seed, units, ant.segmenter, ant.descriptor,
                        ant.bootstrap, ant.max_segments, ant.rounds, ant.whiten)


def tuned(segmenter: Segmenter, **kwargs) -> Segmenter:
    return replace(segmenter, **kwargs)


# ---------------------------------------------------------------------------
# the same command line acoustic_units.py offers, so the rest of the system can
# drive a segmental checkpoint without knowing it is one
# ---------------------------------------------------------------------------

def _cli_encode(args) -> None:
    ant = SegmentalAnt.from_checkpoint(load_checkpoint(Path(args.checkpoint)))
    audio = load_wav(Path(args.wav))
    samples = resample_samples(audio.samples, audio.rate, EXEMPLAR_RATE)
    ids, edges = ant.encode_features(ant.frames(samples))
    print(json.dumps({
        "audio_pcm_sha256": audio.pcm_sha256,
        "unit_namespace": f"{load_checkpoint(Path(args.checkpoint))['checkpoint_sha256']}"
                          f":segment_unit_id",
        "frames": int(len(ids)),
        "segments": [{"unit": int(ids[int(a)]),
                      "start_s": round(float(a) * HOP / RATE, 3),
                      "end_s": round(float(b) * HOP / RATE, 3)}
                     for a, b in zip(edges[:-1], edges[1:])],
    }))


def _cli_synthesize(args) -> None:
    from acoustic_units import write_wav_atomic
    payload = load_checkpoint(Path(args.checkpoint))
    ant = SegmentalAnt.from_checkpoint(payload)
    audio = load_wav(Path(args.wav))
    samples = resample_samples(audio.samples, audio.rate, EXEMPLAR_RATE)
    ids = ant.encode(samples)
    output = ant.synthesize(ids)
    digest = write_wav_atomic(Path(args.output), output, EXEMPLAR_RATE)
    print(json.dumps({
        "checkpoint_sha256": payload["checkpoint_sha256"],
        "source_audio_pcm_sha256": audio.pcm_sha256,
        "output_audio_sha256": digest,
        "output": args.output,
        "segments": len(runs_of(ids)),
        "duration_seconds": len(output) / EXEMPLAR_RATE,
        "claim_limit": "learned-exemplar reconstruction from segment ids alone; "
                       "not speech or conversation acceptance",
    }))


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(required=True)
    e = sub.add_parser("encode")
    e.add_argument("--checkpoint", required=True)
    e.add_argument("--wav", required=True)
    e.set_defaults(fn=_cli_encode)
    s = sub.add_parser("synthesize")
    s.add_argument("--checkpoint", required=True)
    s.add_argument("--wav", required=True)
    s.add_argument("--output", required=True)
    s.set_defaults(fn=_cli_synthesize)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
