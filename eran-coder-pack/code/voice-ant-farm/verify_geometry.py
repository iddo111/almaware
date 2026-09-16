"""Is the colony's 14-dim feature space geometrically broken by loudness?

GLM-5.2's diagnosis, in full:

    "The features are extracted from the Fourier MAGNITUDE spectrum and are
     strictly positive.  This creates a funnel effect in Euclidean space: as
     overall energy rises, the L2 distance between a loud frame and a quiet
     frame is artificially inflated.  k-means is fundamentally biased to group
     by ENERGY regardless of linguistic content."

That is a mechanism plus a consequence, and they are separable.  This script
tests both, on real frames, and does not take either on faith.

  1  How much of the total frame variance does each dimension hold?
  2  Across many random frame pairs, how well does |delta log-energy| predict
     Euclidean distance?  How much does deleting the energy column change the
     ranking of neighbours?
  3  A controlled gain sweep: the SAME frame of the SAME utterance, only
     quieter.  If the space is level-dominated, a phone at -18 dB is further
     from itself than from a different phone at the same level.

Every number is measured.  Run:
    py -3.13 verify_geometry.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

import feature_space as F
from acoustic_units import EXEMPLAR_RATE, load_wav, resample_samples

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "state-hebbian" / "geometry-verification.json"
SEED = 7007


def samples_of(path: Path) -> np.ndarray:
    a = load_wav(path)
    return resample_samples(a.samples, a.rate, EXEMPLAR_RATE)


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    def rank(v):
        order = np.argsort(v, kind="stable")
        r = np.empty(len(v), dtype=np.float64)
        r[order] = np.arange(len(v), dtype=np.float64)
        return r
    ra, rb = rank(a), rank(b)
    ra -= ra.mean(); rb -= rb.mean()
    return float(ra @ rb / max(np.sqrt((ra @ ra) * (rb @ rb)), 1e-12))


def pearson(a: np.ndarray, b: np.ndarray) -> float:
    a = a - a.mean(); b = b - b.mean()
    return float(a @ b / max(np.sqrt((a @ a) * (b @ b)), 1e-12))


def speech_mask(samples: np.ndarray) -> np.ndarray:
    """Same rule sequence_probes.speech_span uses, as a boolean mask."""
    e = F.log_energy(samples)
    k = max(1, int(round(0.30 * len(e))))
    floor = float(np.median(np.sort(e)[:k]))
    hit = np.flatnonzero(e >= floor + 1.5)
    if hit.size < 3:
        return np.ones(len(e), dtype=bool)
    m = np.zeros(len(e), dtype=bool)
    m[hit[0]:hit[-1] + 1] = True
    return m


# --------------------------------------------------------------------------

def gather_frames(paths: list[Path], speech_only: bool) -> np.ndarray:
    out = []
    for p in paths:
        s = samples_of(p)
        x = F.extract("legacy14", s)
        out.append(x[speech_mask(s)] if speech_only else x)
    return np.concatenate(out)


def variance_share(x: np.ndarray) -> dict:
    var = x.var(axis=0)
    total = float(var.sum())
    names = ["log_energy", "zcr"] + [f"band{i:02d}" for i in range(12)]
    return {
        "total_variance": total,
        "per_dimension": {n: {"variance": float(v), "share": float(v / total)}
                          for n, v in zip(names, var)},
        "log_energy_share": float(var[0] / total),
        "zcr_share": float(var[1] / total),
        "twelve_bands_share": float(var[2:].sum() / total),
    }


def pair_correlations(x: np.ndarray, n_pairs: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    i = rng.integers(0, len(x), n_pairs)
    j = rng.integers(0, len(x), n_pairs)
    keep = i != j
    i, j = i[keep], j[keep]
    d_full = np.sqrt(((x[i] - x[j]) ** 2).sum(axis=1))
    d_noe = np.sqrt(((x[i, 1:] - x[j, 1:]) ** 2).sum(axis=1))
    d_e = np.abs(x[i, 0] - x[j, 0])
    share = np.mean((d_e ** 2) / np.maximum(d_full ** 2, 1e-12))
    return {
        "pairs": int(len(i)),
        "pearson_distance_vs_abs_energy_gap": pearson(d_full, d_e),
        "spearman_distance_vs_abs_energy_gap": spearman(d_full, d_e),
        "mean_fraction_of_squared_distance_from_energy_column": float(share),
        "median_fraction_of_squared_distance_from_energy_column":
            float(np.median((d_e ** 2) / np.maximum(d_full ** 2, 1e-12))),
        "pearson_distance_vs_abs_energy_gap_energy_column_removed":
            pearson(d_noe, d_e),
        "spearman_full_vs_energyless_distance": spearman(d_full, d_noe),
    }


def neighbour_agreement(x: np.ndarray, n_probe: int, seed: int) -> dict:
    """Does deleting the energy column change who each frame's neighbours are?"""
    rng = np.random.default_rng(seed + 1)
    sub = x[rng.choice(len(x), min(4000, len(x)), replace=False)]
    probe = sub[rng.choice(len(sub), n_probe, replace=False)]
    d_full = ((probe[:, None, :] - sub[None, :, :]) ** 2).sum(axis=2)
    d_noe = ((probe[:, None, 1:] - sub[None, :, 1:]) ** 2).sum(axis=2)
    np.fill_diagonal(d_full[:, :n_probe], np.inf)
    top_full = np.argsort(d_full, axis=1)[:, :10]
    top_noe = np.argsort(d_noe, axis=1)[:, :10]
    overlap = [len(set(a.tolist()) & set(b.tolist())) / 10.0
               for a, b in zip(top_full, top_noe)]
    return {
        "probe_frames": int(n_probe),
        "bank_frames": int(len(sub)),
        "mean_top10_neighbour_overlap_with_vs_without_energy": float(np.mean(overlap)),
    }


def gain_sweep(paths: list[Path], gains_db: list[float], sets: list[str]) -> dict:
    """The clean test.  Identical audio, only quieter.  Nothing else changes."""
    results = {}
    reference = [samples_of(p) for p in paths]
    masks = [speech_mask(s) for s in reference]
    for name in sets:
        base = [F.extract(name, s, m) for s, m in zip(reference, masks)]
        rows = []
        for db in gains_db:
            g = 10.0 ** (db / 20.0)
            quiet = [F.extract(name, s * g, m) for s, m in zip(reference, masks)]
            # self distance: same file, same frame index, different level
            self_d, other_d = [], []
            for a, b, m in zip(base, quiet, masks):
                self_d.append(np.sqrt(((a[m] - b[m]) ** 2).sum(axis=1)))
            for k in range(len(base)):
                for l in range(len(base)):
                    if k == l:
                        continue
                    n = min(masks[k].sum(), masks[l].sum())
                    if n < 5:
                        continue
                    p = base[k][masks[k]][:n]
                    q = base[l][masks[l]][:n]
                    other_d.append(np.sqrt(((p - q) ** 2).sum(axis=1)))
            s_all = np.concatenate(self_d)
            o_all = np.concatenate(other_d)
            rows.append({
                "gain_db": db,
                "mean_distance_same_frame_different_level": float(s_all.mean()),
                "mean_distance_different_file_same_level": float(o_all.mean()),
                "ratio_self_over_other": float(s_all.mean() / max(o_all.mean(), 1e-12)),
                "fraction_self_farther_than_median_other":
                    float(np.mean(s_all > np.median(o_all))),
            })
        results[name] = rows
    return results


def kmeans_partition_test(x: np.ndarray, k: int, seed: int, rounds: int = 25) -> dict:
    """Does the fitted partition explain energy better than it explains timbre?

    eta^2 per dimension = 1 - within-cluster variance / total variance.  If
    k-means is "biased to group by ENERGY regardless of linguistic content",
    eta^2 for the log-energy column will sit well above eta^2 for the bands.
    """
    rng = np.random.default_rng(seed)
    sub = x[rng.choice(len(x), min(20_000, len(x)), replace=False)]
    centers = sub[rng.choice(len(sub), k, replace=False)].copy()
    for _ in range(rounds):
        ids = ((sub[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2).argmin(axis=1)
        new = centers.copy()
        for j in range(k):
            m = sub[ids == j]
            if len(m):
                new[j] = m.mean(axis=0)
        if np.allclose(new, centers, atol=1e-5):
            centers = new
            break
        centers = new
    ids = ((sub[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2).argmin(axis=1)
    within = np.zeros(sub.shape[1])
    for j in range(k):
        m = sub[ids == j]
        if len(m) > 1:
            within += len(m) * m.var(axis=0)
    within /= len(sub)
    eta = 1.0 - within / np.maximum(sub.var(axis=0), 1e-12)
    names = ["log_energy", "zcr"] + [f"band{i:02d}" for i in range(12)]
    return {
        "k": k, "frames": int(len(sub)),
        "eta_squared_per_dimension": {n: float(v) for n, v in zip(names, eta)},
        "eta_squared_log_energy": float(eta[0]),
        "eta_squared_bands_mean": float(eta[2:].mean()),
        "eta_squared_zcr": float(eta[1]),
    }


def main() -> None:
    t0 = time.time()
    rng = np.random.default_rng(SEED)
    syll = sorted((ROOT / "corpus-combined" / "train").glob("*.wav"))
    big = sorted((ROOT / "corpus-big" / "human" ).rglob("*.wav"))
    big_sample = [big[i] for i in rng.choice(len(big), min(180, len(big)),
                                             replace=False)] if big else []
    print(f"syllable files={len(syll)}  human corpus files={len(big)} "
          f"(sampling {len(big_sample)})", flush=True)

    report = {
        "question": "is the 14-dim feature space dominated by loudness",
        "claim_under_test": "GLM-5.2: magnitude-spectrum features are strictly "
                            "positive, so L2 distance is inflated by energy and "
                            "k-means groups by loudness, not by phone",
        "seed": SEED,
    }

    for tag, paths in (("syllable_corpus", syll[:200]),
                       ("human_corpus_40h_sample", big_sample)):
        if not paths:
            continue
        for span in ("all_frames", "speech_frames_only"):
            x = gather_frames(paths, span == "speech_frames_only")
            key = f"{tag}::{span}"
            report[key] = {
                "files": len(paths),
                "frames": int(len(x)),
                "variance": variance_share(x),
                "pair_correlations": pair_correlations(x, 400_000, SEED),
                "neighbours": neighbour_agreement(x, 400, SEED),
            }
            v = report[key]["variance"]
            c = report[key]["pair_correlations"]
            print(f"{key:<44} frames={len(x):>7}  "
                  f"energy var share={v['log_energy_share']:.3f}  "
                  f"zcr={v['zcr_share']:.5f}  "
                  f"r(dist,|dE|)={c['pearson_distance_vs_abs_energy_gap']:.3f}  "
                  f"rho={c['spearman_distance_vs_abs_energy_gap']:.3f}  "
                  f"sq-dist from energy={c['mean_fraction_of_squared_distance_from_energy_column']:.3f}",
                  flush=True)

    print("\n-- does k-means actually partition by energy --", flush=True)
    x = gather_frames(syll[:200], True)
    report["kmeans_partition"] = {str(k): kmeans_partition_test(x, k, SEED)
                                  for k in (64, 256)}
    for k, d in report["kmeans_partition"].items():
        print(f"k={k:<4} eta^2(log_energy)={d['eta_squared_log_energy']:.3f}  "
              f"eta^2(12 bands, mean)={d['eta_squared_bands_mean']:.3f}  "
              f"eta^2(zcr)={d['eta_squared_zcr']:.3f}", flush=True)

    print("\n-- controlled gain sweep (identical audio, level only) --", flush=True)
    gain_files = syll[:24]
    sweep_sets = ["legacy14", "legacy14_noenergy", "logmel26", "mfcc13",
                  "mfcc12", "mfcc13_cmvn", "recommended51"]
    report["gain_sweep"] = gain_sweep(gain_files, [-6.0, -12.0, -18.0], sweep_sets)
    report["gain_sweep_note"] = (
        "self = same file, same frame index, only quieter. other = a different "
        "syllable file at the ORIGINAL level. ratio > 1 means a phone is "
        "further from itself-turned-down than from a different phone."
    )
    for name, rows in report["gain_sweep"].items():
        line = "  ".join(f"{r['gain_db']:+.0f}dB ratio={r['ratio_self_over_other']:.3f}"
                         for r in rows)
        print(f"{name:<20} {line}", flush=True)

    report["seconds"] = round(time.time() - t0, 1)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT}  ({report['seconds']}s)")


if __name__ == "__main__":
    sys.exit(main())
