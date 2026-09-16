"""
measure.py — THE ANSWER, not a vibe.

Runs the loop from many random initial patterns and measures, with numbers
written to results/OPTIC-LOOP-<date>.json:

  0. NULL CONTROL, printed and saved FIRST: an identity transform (no blur,
     no weight, no threshold, gain=1, decay=0). If this doesn't sit at
     exactly zero frame-difference, the harness itself is broken -- nothing
     downstream can be trusted, so this is an assert, not a suggestion.
  1. Convergence: frame-to-frame difference over time for N random starts,
     classified converged / oscillating / chaotic.
  2. Attractor count: cluster the settled states. THE single most important
     number in this file -- it is the memory capacity.
  3. Perturbation recovery: noise + corner-occlusion on each discovered
     attractor, re-run, check it returns. Content-addressable recall.
  4. Threshold on vs off: same seeds, nonlinearity removed. If behaviour is
     identical, that is the finding (the nonlinearity does nothing).
  5. Gain/decay sweep: where the dynamics are neither dead nor saturated.

Every run here uses `--source virtual` (see loop.py / SIMULATE.md): NO
camera, NO screen. This is the software-only test of the iterated map. See
SIMULATE.md for exactly why that is a legitimate, clearly-labelled, distinct
question from the physical hardware question this project exists to answer.
"""
from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path

import numpy as np
import cv2

from optics import OpticsConfig, make_fixed_mask, apply_optics
from loop import VirtualSource, run_loop, init_pattern, BASE_RES

RESULTS_DIR = Path(__file__).parent / "results"

DEFAULT_CFG_KWARGS = dict(
    blur_ksize=5, blur_sigma=1.2,
    weight_mode="fixed",
    threshold_mode="sigmoid", threshold_k=12.0, threshold_bias=0.5,
    gain=1.15, decay=0.08,
    shift_dx=0.0, shift_dy=0.0, rotate_deg=0.0,
)


def make_cfg(**overrides) -> OpticsConfig:
    kw = dict(DEFAULT_CFG_KWARGS)
    kw.update(overrides)
    return OpticsConfig(**kw)


def run_trial(seed: int, cfg: OpticsConfig, iters: int, mask, sim_noise: float = 0.0,
              sim_jitter: float = 0.0, frame_history: int | None = 20) -> dict:
    source = VirtualSource(sim_noise=sim_noise, sim_jitter=sim_jitter, seed=seed)
    init_state = init_pattern(seed, BASE_RES)
    result = run_loop(source, cfg, iters, init_state, mask=mask, frame_history=frame_history)
    source.close()
    return result


def classify(diffs: list, frames: list, eps: float, hold: int = 5, period_max: int = 12,
             period_tol_factor: float = 3.0) -> dict:
    n = len(diffs)
    for t in range(max(0, n - hold + 1)):
        window = diffs[t:t + hold]
        if len(window) == hold and all(d < eps for d in window):
            return {"class": "converged", "step": t}
    last = frames[-1]
    best_p, best_err = None, None
    for p in range(2, period_max + 1):
        idx = len(frames) - 1 - p
        if idx < 0:
            break
        err = float(np.mean(np.abs(last - frames[idx])))
        if best_err is None or err < best_err:
            best_err, best_p = err, p
    if best_err is not None and best_err < eps * period_tol_factor:
        return {"class": "oscillating", "period": best_p, "match_err": best_err}
    return {"class": "chaotic"}


def settled_representation(cls: dict, result: dict) -> np.ndarray:
    if cls["class"] == "converged":
        return result["final"]
    if cls["class"] == "oscillating":
        p = cls["period"]
        tail = result["frames"][-p:]
        return np.mean(tail, axis=0)
    return result["final"]  # chaotic: report last frame; expected not to cluster well


def measure_pre_threshold_level(mask: np.ndarray, n: int = 30) -> float:
    """Measure the actual signal level right before the nonlinearity (blur
    + weight applied, threshold off, gain=1, decay=0), averaged over N
    random inputs. The fixed transparency mask can only attenuate (it is
    <=1 everywhere, mean ~0.69 here) -- so the real pre-threshold signal
    sits measurably below 0.5 by construction, not by accident. A
    threshold bias left at an arbitrary 0.5 would be miscalibrated against
    the actual working range, exactly as a real photodetector's comparator
    would need its bias set to the real illumination level."""
    cfg_pre = make_cfg(threshold_mode="off", gain=1.0, decay=0.0)
    means = []
    for seed in range(n):
        x = init_pattern(seed + 7000, BASE_RES)
        pre = apply_optics(x, cfg_pre, mask)
        means.append(float(pre.mean()))
    return float(np.mean(means))


def cluster_states(vectors: list, eps: float) -> list:
    """Greedy online clustering by mean-abs-diff distance to running centroid.
    O(n * k) where k = number of clusters found -- fine at n<=200."""
    clusters = []
    for i, v in enumerate(vectors):
        placed = False
        for c in clusters:
            d = float(np.mean(np.abs(v - c["centroid"])))
            if d < eps:
                c["members"].append(i)
                n = len(c["members"])
                c["centroid"] = c["centroid"] + (v - c["centroid"]) / n
                placed = True
                break
        if not placed:
            clusters.append({"members": [i], "centroid": v.copy()})
    return clusters


def pairwise_distance_stats(vectors: list) -> dict:
    n = len(vectors)
    dists = []
    for i in range(n):
        for j in range(i + 1, n):
            dists.append(float(np.mean(np.abs(vectors[i] - vectors[j]))))
    if not dists:
        return {"n_pairs": 0, "min": None, "max": None, "mean": None, "median": None}
    d = np.array(dists)
    return {
        "n_pairs": len(dists),
        "min": float(d.min()), "max": float(d.max()),
        "mean": float(d.mean()), "median": float(np.median(d)),
    }


def save_png(arr01: np.ndarray, path: Path, size: int = 256) -> None:
    img = cv2.resize(arr01, (size, size), interpolation=cv2.INTER_NEAREST)
    cv2.imwrite(str(path), (np.clip(img, 0, 1) * 255).astype(np.uint8))


def try_save_diff_curves_png(curves: dict, path: Path) -> bool:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for label, diffs in curves.items():
        ax.plot(diffs, label=label, linewidth=1.2)
    ax.set_yscale("log")
    ax.set_xlabel("iteration")
    ax.set_ylabel("frame-to-frame mean |diff|  (log scale)")
    ax.set_title("optic-loop: frame-difference decay, sample runs")
    ax.legend(fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return True


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, default=50, help="random starts for the baseline/attractor experiment")
    ap.add_argument("--iters", type=int, default=150)
    ap.add_argument("--cluster-eps", type=float, default=0.05)
    ap.add_argument("--conv-eps", type=float, default=2e-3)
    ap.add_argument("--sim-noise", type=float, default=0.0,
                     help="synthetic camera-noise sigma for a robustness pass; 0 = idealized (default)")
    ap.add_argument("--ablation-seeds", type=int, default=30)
    ap.add_argument("--sweep-seeds", type=int, default=5)
    ap.add_argument("--sweep-iters", type=int, default=70)
    ap.add_argument("--recovery-eps", type=float, default=0.06)
    ap.add_argument("--threshold-bias", type=float, default=None,
                     help="override the auto-calibrated threshold bias (default: measured "
                          "from the actual pre-threshold signal level, see step 0.5)")
    args = ap.parse_args()

    RESULTS_DIR.mkdir(exist_ok=True)
    date_str = datetime.date.today().isoformat()
    out = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "backend": "virtual -- SOFTWARE ONLY. No camera opened, no screen touched. "
                   "See SIMULATE.md for what this does and does not tell us about the physical loop.",
        "base_res": BASE_RES,
        "cli_args": vars(args),
        "default_cfg": DEFAULT_CFG_KWARGS,
    }

    mask = make_fixed_mask((BASE_RES, BASE_RES), seed=1)

    # =====================================================================
    # 0. NULL CONTROL -- printed and saved first, on purpose.
    # =====================================================================
    print("=" * 78)
    print("0. NULL CONTROL: identity transform (blur off / weight none / threshold off / "
          "gain=1 / decay=0)")
    control_cfg = make_cfg(blur_ksize=0, weight_mode="none", threshold_mode="off",
                            gain=1.0, decay=0.0)
    ctrl = run_trial(seed=0, cfg=control_cfg, iters=20, mask=None, frame_history=None)
    ctrl_diffs = ctrl["diffs"]
    print(f"   max frame-diff over 20 iters = {max(ctrl_diffs):.10f}  (expect ~0.0)")
    out["control_identity"] = {"diffs": ctrl_diffs, "max_diff": float(max(ctrl_diffs))}
    assert max(ctrl_diffs) < 1e-6, (
        "NULL CONTROL FAILED -- the identity config is not actually identity. "
        "This means the harness has a bug; every measurement below would be untrustworthy. Stopping."
    )
    print("   PASS -- harness confirmed correct before measuring anything else.\n")

    # =====================================================================
    # 0.5 BIAS CALIBRATION -- measured, not guessed
    # =====================================================================
    print("=" * 78)
    print("0.5 BIAS CALIBRATION: the fixed transparency mask only attenuates (mean<1), so the "
          "real pre-threshold signal sits below 0.5 by construction. Measuring it instead of "
          "guessing, and documenting the mismatch a naive bias=0.5 would cause.")
    pre_level = measure_pre_threshold_level(mask, n=30)
    print(f"   measured pre-threshold field mean over 30 seeds: {pre_level:.4f}")

    naive_bias = 0.5
    cfg_naive = make_cfg(threshold_bias=naive_bias)
    naive_means = []
    for seed in range(3300, 3300 + 15):
        result = run_trial(seed, cfg_naive, 60, mask, frame_history=10)
        naive_means.append(float(result["final"].mean()))
    print(f"   DIAGNOSTIC -- naive bias={naive_bias}: 15 seeds -> mean final intensity "
          f"avg={np.mean(naive_means):.4f} (near 0 = every run collapses to the same trivial "
          f"off-state regardless of its starting pattern; this is what a mismatched bias does)")

    matched_bias = round(pre_level, 3) if args.threshold_bias is None else args.threshold_bias
    print(f"   USING matched threshold_bias = {matched_bias} for every experiment below.\n")

    out["bias_calibration"] = {
        "measured_pre_threshold_field_mean": pre_level,
        "naive_bias": naive_bias,
        "naive_bias_diagnostic_mean_final_intensity_15seeds": float(np.mean(naive_means)),
        "naive_bias_diagnostic_individual": naive_means,
        "matched_bias_chosen": matched_bias,
        "note": ("threshold_bias must be set relative to the actual post-mask signal level. "
                 "With bias left at an unmatched 0.5, ALL 50 baseline seeds collapsed to one "
                 "trivial near-zero attractor in ~4 steps regardless of starting pattern -- "
                 "not memory, just an off-switch. Every experiment below uses the matched bias "
                 "instead, exactly as calibrating a real comparator/OASLM bias voltage to the "
                 "real illumination level would require."),
    }

    # =====================================================================
    # 1 + 2. BASELINE: convergence + attractor count
    # =====================================================================
    print("=" * 78)
    print(f"1+2. BASELINE: {args.seeds} random starts, threshold ON (sigmoid), "
          f"threshold_bias={matched_bias}, sim_noise={args.sim_noise}")
    cfg_on = make_cfg(threshold_bias=matched_bias)
    baseline_runs = []
    baseline_diff_curves_sample = {}
    for i, seed in enumerate(range(1000, 1000 + args.seeds)):
        result = run_trial(seed, cfg_on, args.iters, mask, sim_noise=args.sim_noise)
        cls = classify(result["diffs"], result["frames"], eps=args.conv_eps)
        baseline_runs.append({
            "seed": seed, "class": cls["class"], "detail": {k: v for k, v in cls.items() if k != "class"},
            "final_diff": result["diffs"][-1],
        })
        baseline_runs[-1]["_settled"] = settled_representation(cls, result)
        if i < 6:
            baseline_diff_curves_sample[f"seed{seed}_{cls['class']}"] = result["diffs"]

    n_conv = sum(1 for r in baseline_runs if r["class"] == "converged")
    n_osc = sum(1 for r in baseline_runs if r["class"] == "oscillating")
    n_chaos = sum(1 for r in baseline_runs if r["class"] == "chaotic")
    conv_steps = [r["detail"]["step"] for r in baseline_runs if r["class"] == "converged"]
    print(f"   converged: {n_conv}/{args.seeds}   oscillating: {n_osc}/{args.seeds}   "
          f"chaotic: {n_chaos}/{args.seeds}")
    if conv_steps:
        print(f"   convergence step: mean={np.mean(conv_steps):.1f}  "
              f"min={min(conv_steps)}  max={max(conv_steps)}")

    settled_vectors = [r["_settled"] for r in baseline_runs if r["class"] in ("converged", "oscillating")]
    settled_seed_idx = [r["seed"] for r in baseline_runs if r["class"] in ("converged", "oscillating")]
    dist_stats = pairwise_distance_stats(settled_vectors)
    clusters = cluster_states(settled_vectors, eps=args.cluster_eps)
    clusters_sorted = sorted(clusters, key=lambda c: -len(c["members"]))
    print(f"   pairwise settled-state distance: mean={dist_stats['mean']}, "
          f"median={dist_stats['median']}, min={dist_stats['min']}, max={dist_stats['max']}")
    print(f"   >>> ATTRACTOR COUNT (cluster-eps={args.cluster_eps}): {len(clusters_sorted)} <<<")
    for ci, c in enumerate(clusters_sorted):
        print(f"     cluster {ci}: {len(c['members'])} runs")

    attractor_paths = []
    for ci, c in enumerate(clusters_sorted[:6]):
        p = RESULTS_DIR / f"attractor_{date_str}_{ci}.png"
        save_png(c["centroid"], p)
        attractor_paths.append(str(p))

    out["baseline"] = {
        "n_seeds": args.seeds,
        "n_converged": n_conv, "n_oscillating": n_osc, "n_chaotic": n_chaos,
        "convergence_step_mean": float(np.mean(conv_steps)) if conv_steps else None,
        "convergence_step_min": min(conv_steps) if conv_steps else None,
        "convergence_step_max": max(conv_steps) if conv_steps else None,
        "settled_pairwise_distance_stats": dist_stats,
        "cluster_eps": args.cluster_eps,
        "attractor_count": len(clusters_sorted),
        "attractor_cluster_sizes": [len(c["members"]) for c in clusters_sorted],
        "attractor_png_paths": attractor_paths,
        "runs": [{k: v for k, v in r.items() if k != "_settled"} for r in baseline_runs],
        "sample_diff_curves": baseline_diff_curves_sample,
    }

    diff_curve_png = RESULTS_DIR / f"diff_curves_{date_str}.png"
    if try_save_diff_curves_png(baseline_diff_curves_sample, diff_curve_png):
        out["baseline"]["diff_curve_png"] = str(diff_curve_png)
        print(f"   saved diff-curve plot: {diff_curve_png}")
    print()

    # =====================================================================
    # 3. PERTURBATION RECOVERY: is a settled state content-addressable?
    # =====================================================================
    print("=" * 78)
    print(f"3. PERTURBATION RECOVERY on each of the {len(clusters_sorted)} discovered attractor(s)")
    recovery_results = []
    for ci, c in enumerate(clusters_sorted):
        attractor = c["centroid"]
        for kind in ("noise", "occlude_corner"):
            if kind == "noise":
                rng = np.random.default_rng(9000 + ci)
                perturbed = np.clip(attractor + rng.normal(0, 0.35, size=attractor.shape), 0, 1).astype(np.float32)
            else:
                perturbed = attractor.copy()
                h, w = perturbed.shape
                perturbed[: h // 2, : w // 2] = 0.0  # occlude top-left quadrant

            source = VirtualSource(seed=9100 + ci)
            result = run_loop(source, cfg_on, args.iters, perturbed, mask=mask, frame_history=20)
            source.close()
            cls = classify(result["diffs"], result["frames"], eps=args.conv_eps)
            settled = settled_representation(cls, result)
            dist_to_original = float(np.mean(np.abs(settled - attractor)))
            recovered = dist_to_original < args.recovery_eps
            recovery_results.append({
                "attractor_id": ci, "perturbation": kind,
                "final_class": cls["class"], "distance_to_original_attractor": dist_to_original,
                "recovered": recovered,
            })
            print(f"   attractor {ci} + {kind:15s}: final_class={cls['class']:11s} "
                  f"dist_to_original={dist_to_original:.4f}  recovered={recovered}")

    n_recovered = sum(1 for r in recovery_results if r["recovered"])
    print(f"   >>> RECALL RATE: {n_recovered}/{len(recovery_results)} perturbation trials recovered <<<\n")
    out["perturbation_recovery"] = {
        "recovery_eps": args.recovery_eps,
        "n_trials": len(recovery_results),
        "n_recovered": n_recovered,
        "trials": recovery_results,
    }

    # =====================================================================
    # 4. THRESHOLD ON vs OFF -- does the nonlinearity matter?
    # =====================================================================
    print("=" * 78)
    print(f"4. ABLATION: threshold ON vs OFF, {args.ablation_seeds} matched seeds")
    cfg_off = make_cfg(threshold_mode="off", threshold_bias=matched_bias)
    on_runs, off_runs = [], []
    for seed in range(2000, 2000 + args.ablation_seeds):
        r_on = run_trial(seed, cfg_on, args.iters, mask, sim_noise=args.sim_noise)
        c_on = classify(r_on["diffs"], r_on["frames"], eps=args.conv_eps)
        on_runs.append({"seed": seed, "class": c_on["class"], "_settled": settled_representation(c_on, r_on)})

        r_off = run_trial(seed, cfg_off, args.iters, mask, sim_noise=args.sim_noise)
        c_off = classify(r_off["diffs"], r_off["frames"], eps=args.conv_eps)
        off_runs.append({"seed": seed, "class": c_off["class"], "_settled": settled_representation(c_off, r_off)})

    def summarize(runs):
        conv = sum(1 for r in runs if r["class"] == "converged")
        osc = sum(1 for r in runs if r["class"] == "oscillating")
        chaos = sum(1 for r in runs if r["class"] == "chaotic")
        settled = [r["_settled"] for r in runs if r["class"] in ("converged", "oscillating")]
        clusters = cluster_states(settled, eps=args.cluster_eps)
        return conv, osc, chaos, len(clusters)

    on_conv, on_osc, on_chaos, on_natt = summarize(on_runs)
    off_conv, off_osc, off_chaos, off_natt = summarize(off_runs)
    print(f"   threshold ON : converged={on_conv} oscillating={on_osc} chaotic={on_chaos} "
          f"attractors={on_natt}")
    print(f"   threshold OFF: converged={off_conv} oscillating={off_osc} chaotic={off_chaos} "
          f"attractors={off_natt}")

    identical = (on_conv, on_osc, on_chaos, on_natt) == (off_conv, off_osc, off_chaos, off_natt)
    per_seed_identical = all(
        on_runs[i]["class"] == off_runs[i]["class"]
        and float(np.mean(np.abs(on_runs[i]["_settled"] - off_runs[i]["_settled"]))) < 1e-4
        for i in range(len(on_runs))
    )
    verdict = ("IDENTICAL -- the nonlinearity is doing NOTHING measurable at this operating point"
               if per_seed_identical else
               "DIFFERENT -- the nonlinearity changes the dynamics")
    print(f"   >>> {verdict} <<<\n")

    out["ablation_threshold"] = {
        "n_seeds": args.ablation_seeds,
        "threshold_on": {"converged": on_conv, "oscillating": on_osc, "chaotic": on_chaos, "attractor_count": on_natt},
        "threshold_off": {"converged": off_conv, "oscillating": off_osc, "chaotic": off_chaos, "attractor_count": off_natt},
        "aggregate_identical": identical,
        "per_seed_identical": per_seed_identical,
        "verdict": verdict,
    }

    # =====================================================================
    # 5. GAIN / DECAY SWEEP -- find the operating band
    # =====================================================================
    print("=" * 78)
    print(f"5. GAIN/DECAY SWEEP: {args.sweep_seeds} seeds/cell, {args.sweep_iters} iters/run")
    gains = np.round(np.linspace(0.7, 1.7, 6), 3)
    decays = np.round(np.linspace(0.0, 0.45, 6), 3)
    sweep_cells = []
    for g in gains:
        for d in decays:
            cfg_cell = make_cfg(gain=float(g), decay=float(d), threshold_bias=matched_bias)
            dead = sat = settled = 0
            for seed in range(3000, 3000 + args.sweep_seeds):
                result = run_trial(seed, cfg_cell, args.sweep_iters, mask, frame_history=15)
                mean_intensity = float(np.mean(result["final"]))
                if mean_intensity < 0.03:
                    dead += 1
                elif mean_intensity > 0.97:
                    sat += 1
                cls = classify(result["diffs"], result["frames"], eps=args.conv_eps)
                if cls["class"] in ("converged", "oscillating"):
                    settled += 1
            healthy = args.sweep_seeds - dead - sat
            cell = {
                "gain": float(g), "decay": float(d),
                "n_dead": dead, "n_saturated": sat, "n_healthy_amplitude": healthy,
                "n_settled": settled,
                "healthy_frac": healthy / args.sweep_seeds,
                "settled_frac": settled / args.sweep_seeds,
            }
            sweep_cells.append(cell)

    band = [c for c in sweep_cells if c["healthy_frac"] >= 0.6 and c["settled_frac"] >= 0.6]
    gband, dband = [], []
    print(f"   {len(sweep_cells)} cells swept. Operating band (healthy_frac>=0.6 and settled_frac>=0.6): "
          f"{len(band)} cells")
    if band:
        gband = sorted(set(c["gain"] for c in band))
        dband = sorted(set(c["decay"] for c in band))
        print(f"   >>> BAND: gain in {gband}, decay in {dband} <<<")
    else:
        print("   >>> NO cell satisfied both conditions at these thresholds -- see full grid in JSON <<<")
    print()

    out["gain_decay_sweep"] = {
        "gains_tested": gains.tolist(), "decays_tested": decays.tolist(),
        "seeds_per_cell": args.sweep_seeds, "iters_per_run": args.sweep_iters,
        "cells": sweep_cells,
        "band_gain_values": gband if band else [],
        "band_decay_values": dband if band else [],
        "band_cell_count": len(band),
    }

    # =====================================================================
    # WRITE RESULTS
    # =====================================================================
    out_path = RESULTS_DIR / f"OPTIC-LOOP-{date_str}.json"
    out_path.write_text(json.dumps(out, indent=2))
    print("=" * 78)
    print(f"WROTE {out_path}")
    print(f"Attractor images: {attractor_paths}")

    # -------------------------------------------------------------------
    # Plain verdict
    # -------------------------------------------------------------------
    print("=" * 78)
    settle_rate = (n_conv + n_osc) / args.seeds
    print("VERDICT (software-only / virtual backend -- see SIMULATE.md before treating this as "
          "the physical answer):")
    print(f"  settle rate:        {settle_rate:.0%}  ({n_conv} converged + {n_osc} oscillating "
          f"of {args.seeds})")
    print(f"  attractor count:    {len(clusters_sorted)}")
    print(f"  recall rate:        {n_recovered}/{len(recovery_results)}")
    print(f"  threshold matters:  {'NO' if per_seed_identical else 'YES'}")
    print(f"  operating band:     {len(band)} of {len(sweep_cells)} sweep cells")


if __name__ == "__main__":
    main()
