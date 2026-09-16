"""Pick one feature vector from the cross-validation runs, by mean rank.

Taking the single highest CV top-1 would be fitting the fold noise: the
neighbourhood sweep showed 72 configurations inside a 71-79% band.  This ranks
every configuration on all six cross-validated columns, averages the ranks, and
then prefers the lower-dimensional and more fold-stable of the leaders.

The held-out split is not read here, and was not read by any run this reads.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
COLUMNS = [
    ("span", "top1", 1.0), ("loud60", "top1", 1.0),
    ("span", "all_pairs_pooled", 1.0), ("loud60", "all_pairs_pooled", 1.0),
    ("span", "ba/pa", 1.0), ("span", "da/ta", 1.0),
    ("loud60", "ba/pa", 1.0), ("loud60", "da/ta", 1.0),
]


def value(row: dict, pooling: str, key: str) -> float:
    block = row["poolings"][pooling]
    if key in block:
        return float(block[key])
    return float(block["minimal_pairs"].get(key, float("nan")))


def main() -> None:
    rows: dict[str, dict] = {}
    for path in sorted(HERE.glob("feature-cv*.json")):
        for row in json.loads(path.read_text(encoding="utf-8"))["results"]:
            rows[row["feature_set"]] = row
    names = sorted(rows)
    matrix = np.array([[value(rows[n], p, k) for p, k, _ in COLUMNS] for n in names])
    ranks = np.empty_like(matrix)
    for j in range(matrix.shape[1]):
        order = np.argsort(-matrix[:, j], kind="stable")
        r = np.empty(len(names))
        r[order] = np.arange(1, len(names) + 1)
        ranks[:, j] = r
    mean_rank = ranks.mean(axis=1)
    sd = np.array([rows[n]["poolings"]["span"]["top1_std_over_folds"] for n in names])
    dim = np.array([rows[n]["dim"] for n in names])
    order = np.lexsort((dim, sd, mean_rank))
    print(f"{len(names)} configurations, ranked on {len(COLUMNS)} "
          f"cross-validated columns\n")
    print(f"{'rank':>4}  {'feature set':<26}{'dim':>4}{'meanrank':>10}"
          f"{'span top1':>11}{'sd':>6}{'loud60':>9}{'span 8pair':>12}"
          f"{'ba/pa':>8}{'da/ta':>8}")
    for i in order[:15]:
        r = rows[names[i]]
        print(f"{list(order).index(i) + 1:>4}  {names[i]:<26}{dim[i]:>4}"
              f"{mean_rank[i]:>10.1f}"
              f"{r['poolings']['span']['top1'] * 100:>10.1f}%{sd[i] * 100:>6.1f}"
              f"{r['poolings']['loud60']['top1'] * 100:>8.1f}%"
              f"{r['poolings']['span']['all_pairs_pooled'] * 100:>11.1f}%"
              f"{r['poolings']['span']['minimal_pairs']['ba/pa'] * 100:>7.1f}%"
              f"{r['poolings']['span']['minimal_pairs']['da/ta'] * 100:>7.1f}%")
    print("\nreference rows:")
    for name in ("legacy14", "legacy14_noenergy", "logmel26", "mfcc12", "mfcc13"):
        if name not in rows:
            continue
        i = names.index(name)
        r = rows[name]
        print(f"{list(order).index(i) + 1:>4}  {name:<26}{dim[i]:>4}"
              f"{mean_rank[i]:>10.1f}"
              f"{r['poolings']['span']['top1'] * 100:>10.1f}%{sd[i] * 100:>6.1f}"
              f"{r['poolings']['loud60']['top1'] * 100:>8.1f}%"
              f"{r['poolings']['span']['all_pairs_pooled'] * 100:>11.1f}%"
              f"{r['poolings']['span']['minimal_pairs']['ba/pa'] * 100:>7.1f}%"
              f"{r['poolings']['span']['minimal_pairs']['da/ta'] * 100:>7.1f}%")
    (HERE / "feature-selection.json").write_text(json.dumps({
        "protocol": "mean rank over 8 cross-validated columns, ties broken by "
                    "fold standard deviation then dimensionality",
        "columns": [f"{p}:{k}" for p, k, _ in COLUMNS],
        "ranking": [{"feature_set": names[i], "dim": int(dim[i]),
                     "mean_rank": float(mean_rank[i]),
                     "cv_span_top1": rows[names[i]]["poolings"]["span"]["top1"],
                     "cv_loud60_top1": rows[names[i]]["poolings"]["loud60"]["top1"]}
                    for i in order],
    }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
