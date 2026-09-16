"""proof_SNN-2 — the dev split must hold back BASE RENDERINGS, not files.

  FAILS on sweep.py.bak-rev-20260906  (85 of 88 dev items had a sibling in train)
  PASSES on the fixed sweep.py        (0 shared base renderings)

  ./venv/bin/python proof_SNN-2.py --src sweep.py.bak-rev-20260906
"""
import argparse
import importlib.machinery
import importlib.util
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cochlea                                                   # noqa: E402

CORPUS = os.path.join(HERE, "corpus-syllables")


def load(path, name="sweep_under_test"):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_file_location(name, path, loader=loader)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(HERE, "sweep.py"))
    a = ap.parse_args()
    mod = load(a.src)

    files = cochlea.split_files(CORPUS, "train")
    groups = np.array([cochlea.base_id_of(f) for f in files])
    y = np.array([cochlea.CLASSES.index(cochlea.label_of(f)) for f in files])
    x = np.arange(len(files)).reshape(-1, 1)      # carries the row index
    print(f"corpus: {len(files)} training wavs, {len(set(groups))} base renderings")

    grouped = getattr(mod, "grouped_dev", None)
    if grouped is not None:
        xa, ya, xd, yd = grouped(x, y, groups, frac=0.25, seed=0)
        how = "grouped_dev (by base rendering)"
    else:
        xa, ya, xd, yd = mod.stratified_dev(x, y, frac=0.25, seed=0)
        how = "stratified_dev (by file)"

    tr_idx, dev_idx = xa.ravel(), xd.ravel()
    tr_groups = set(groups[tr_idx].tolist())
    leaked = [i for i in dev_idx if groups[i] in tr_groups]
    frac = len(leaked) / max(1, len(dev_idx))
    print(f"{how}: train {len(tr_idx)}  dev {len(dev_idx)}")
    print(f"dev items whose OWN base rendering is also in train: "
          f"{len(leaked)}/{len(dev_idx)} = {frac:.1%}")

    ok = (len(dev_idx) > 0 and len(tr_idx) > 0 and not leaked
          and len(set(y[dev_idx].tolist())) == len(cochlea.CLASSES))
    print("PASS" if ok else "FAIL", "— a dev split that shares base renderings "
          "with train measures memorisation, not generalisation")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
