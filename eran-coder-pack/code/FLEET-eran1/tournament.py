"""tournament.py — queen-and-cochlea self-form. Nightly, inside the fence.

The one intervention that ever produced a large real gain in this lineage was
EVOLVING THE ORGAN, not scaling the diet (ant farm: 42.4% -> 75.8% by swapping
the cochlea). So every night the organism proposes 2-3 ear-config variants
(N_BANDS in {18,24,32} x pooling in {loudest60, mean, loudest40}) against the
current champion, re-embeds a FIXED dev set (never the heldout), grows a
deterministic fresh prototype memory per variant, and scores dev top1 through
the examiner. A challenger is crowned only if it beats the champion beyond a
bootstrap confidence margin — the judge is FIXED; only the body evolves.

Crowning = writing state/crown.json (ears read it at wake). Either way the
night is logged to results/tournament-<date>.json. Losing is a result.
"""
import datetime
import itertools
import json
import os
import random
import sys

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "body"))
sys.path.insert(0, os.path.join(ROOT, "proof"))

import genome                                     # noqa: E402
from brain import Brain                           # noqa: E402
from chemistry import Chemistry                   # noqa: E402
from ears import Ears, load_crown                 # noqa: E402
import measure                                    # noqa: E402

N_BANDS_SPACE = (18, 24, 32)
POOL_SPACE = ("loudest60", "mean", "loudest40")
N_CHALLENGERS = 3
BOOTSTRAP = 1000
CI_PCT = 5.0          # crown only if the 5th percentile of the diff > 0


def _ear_is_frozen():
    """THE FROZEN ANATOMY (genome.py, Iddo 2026-08-21): "THE EAR IS NOW
    FROZEN. The tournament may never change it again."

    While the freeze holds the night still measures every contender honestly
    and logs it — it simply may not crown. It was a bare NameError on line
    117 until 2026-08-21, i.e. the guard protecting the ear would itself have
    killed the nightly job the first night a challenger actually won.
    """
    return bool(genome.EAR_FROZEN)


def _grow_mini_brain(cfg, fit_paths):
    """Deterministic fresh prototype memory: hear each fit wav once,
    chemistry frozen at baseline. Same rule for every contender — fair."""
    ears = Ears(exam=True, n_bands=cfg["n_bands"], pooling=cfg["pooling"])
    chem = Chemistry()
    chem.frozen = True
    brain = Brain(ears.dim)
    for i, p in enumerate(sorted(fit_paths)):
        try:
            brain.hear(measure._vec(ears, p), chem, beat=i)
        except (OSError, ValueError):
            continue
    return brain, ears


def _dev_correct(cfg, fit_paths, dev_paths):
    """Per-dev-item 0/1 correctness vector for one ear config."""
    brain, ears = _grow_mini_brain(cfg, fit_paths)
    proto_label = measure.fit_proto_labels(brain, ears, fit_paths)
    out = []
    for p in dev_paths:
        y = measure.classify(brain, proto_label, measure._vec(ears, p))
        out.append(1.0 if y == measure.label_of(p) else 0.0)
    return np.asarray(out), len(brain.protos)


def run(train_dir=None, seed=None):
    train_dir = train_dir or genome.FOOD_TRAIN
    date = datetime.date.today().isoformat()
    rng = random.Random(seed if seed is not None else genome.SEED + hash(date) % 10000)
    measure.print_baselines_first()

    all_train = measure.wavs_in(train_dir)
    fit = [p for p in all_train if not measure.is_dev(p)]
    dev = [p for p in all_train if measure.is_dev(p)]
    if not fit or not dev:
        print("[tournament] no food to judge on — night skipped, honestly.")
        return None

    crown = load_crown()
    champion = {"n_bands": int(crown.get("n_bands", genome.N_BANDS)),
                "pooling": str(crown.get("pooling", genome.POOLING))}
    space = [{"n_bands": nb, "pooling": pl}
             for nb, pl in itertools.product(N_BANDS_SPACE, POOL_SPACE)
             if not (nb == champion["n_bands"] and pl == champion["pooling"])]
    challengers = rng.sample(space, min(N_CHALLENGERS, len(space)))

    results = []
    champ_vec, champ_protos = _dev_correct(champion, fit, dev)
    results.append({"config": champion, "role": "champion",
                    "dev_top1": float(champ_vec.mean()),
                    "protos": champ_protos})
    print(f"[tournament] champion {champion}: dev top1 "
          f"{champ_vec.mean():.2%} ({champ_protos} protos)")

    best, best_vec = None, None
    for cfg in challengers:
        vec, n_protos = _dev_correct(cfg, fit, dev)
        results.append({"config": cfg, "role": "challenger",
                        "dev_top1": float(vec.mean()), "protos": n_protos})
        print(f"[tournament] challenger {cfg}: dev top1 {vec.mean():.2%} "
              f"({n_protos} protos)")
        if best_vec is None or vec.mean() > best_vec.mean():
            best, best_vec = cfg, vec

    crowned = False
    ci_lo = None
    if best is not None and best_vec.mean() > champ_vec.mean():
        # bootstrap the paired difference over dev items — the noise margin
        boot_rng = np.random.default_rng(genome.SEED)
        n = len(dev)
        diffs = []
        for _ in range(BOOTSTRAP):
            idx = boot_rng.integers(0, n, n)
            diffs.append(best_vec[idx].mean() - champ_vec[idx].mean())
        ci_lo = float(np.percentile(diffs, CI_PCT))
        if ci_lo > 0 and _ear_is_frozen():
            print(f"[tournament] challenger {best} led (CI {ci_lo:+.3f}) but "
                  f"THE EAR IS FROZEN — measuring only, no crown. Anatomy "
                  f"changes are Iddo's word, not a nightly job's.")
        elif ci_lo > 0:
            crowned = True
            os.makedirs(genome.STATE_DIR, exist_ok=True)
            crown_doc = {"n_bands": best["n_bands"],
                         "pooling": best["pooling"],
                         "crowned": date, "ci_lo": ci_lo}
            # The night may crown a WIDTH, never an ANATOMY. If a later edit
            # ever puts a repr in here it dies at 03:30 on the box, loudly,
            # instead of at wake inside the child. A real raise, not an
            # assert: asserts vanish under python -O.
            if "repr" in crown_doc:
                raise RuntimeError(
                    "tournament tried to crown an ear repr — the anatomy is "
                    "Iddo's word, not a nightly job's (genome.EAR_FROZEN). "
                    f"offending crown: {crown_doc}")
            tmp = genome.CROWN_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(crown_doc, f, indent=1)
            os.replace(tmp, genome.CROWN_FILE)
            print(f"[tournament] CROWNED {best} (CI lower bound "
                  f"{ci_lo:+.3f} > 0). Ears change at next wake; the brain "
                  f"will be reborn to see through them.")
        else:
            print(f"[tournament] challenger led but inside noise "
                  f"(CI lower {ci_lo:+.3f} <= 0) — an empty throne is "
                  f"preferred. Champion stands.")
    else:
        print("[tournament] no challenger beat the champion. That is a "
              "result too.")

    os.makedirs(genome.RESULTS_DIR, exist_ok=True)
    log_path = os.path.join(genome.RESULTS_DIR, f"tournament-{date}.json")
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump({"date": date, "dev_items": len(dev),
                   "fit_items": len(fit), "contenders": results,
                   "crowned": crowned, "ci_lower": ci_lo,
                   "judge": "FIXED: sha-dev split + majority-vote prototype "
                            "purity; only the body evolves"},
                  f, indent=1)
    print(f"[tournament] logged {log_path}")
    return crowned


if __name__ == "__main__":
    run()
