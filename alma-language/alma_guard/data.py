# -*- coding: utf-8 -*-
"""Loading, splitting and scoring - shared by ALMA-GUARD and by the vanilla control.

One module, so the A/B is clean: identical rows, identical features, identical
folds. The only thing that differs between the two arms is what learns.

v0.2 adds two things, both about honesty rather than accuracy:
  * GROUP-AWARE folds. `build_dataset.py` stamps near-duplicate rows with one
    `group` id (alma_guard/dedupe.py) and `folds()` deals whole groups, so no
    fold is scored on the paraphrase of a row it trained on. Rows without a
    `group` key are dealt exactly as v0.1 dealt them, bit for bit.
  * the SHORT-HEBREW false-alarm rate, the v0.1 defect, as a first-class metric.
"""
from __future__ import annotations

import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent

BENIGN = "benign"
CLASSES = [BENIGN, "injection", "secret-leak-attempt", "hijack-attempt"]
ATTACK = "attack"

#: "short" = at most this many whitespace words. The v0.1 false alarms were 4-6.
SHORT_WORDS = 8
_HEB = re.compile(r"[֐-׿]")


def load(path: Path | str | None = None) -> list[dict]:
    p = Path(path) if path else HERE / "dataset.jsonl"
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def binarise(label: str) -> str:
    return BENIGN if label == BENIGN else ATTACK


def is_short_hebrew(text: str, max_words: int = SHORT_WORDS) -> bool:
    return bool(_HEB.search(text)) and len(text.split()) <= max_words


def folds(rows: list[dict], k: int, seed: int = 0) -> list[list[int]]:
    """Stratified k folds over the 4-class label, so every fold holds every class.

    If rows carry a `group`, whole groups are dealt (stratified by the group's
    commonest label), so near-duplicates never straddle a fold boundary.
    """
    if not any("group" in r for r in rows):
        by = defaultdict(list)
        for i, r in enumerate(rows):
            by[r["label"]].append(i)
        out: list[list[int]] = [[] for _ in range(k)]
        rng = random.Random(seed)
        for label in sorted(by):
            idx = by[label][:]
            rng.shuffle(idx)
            for j, i in enumerate(idx):
                out[j % k].append(i)
        for f in out:
            rng.shuffle(f)
        return out

    members: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        members[str(r.get("group", f"row{i}"))].append(i)
    by_label: dict[str, list[str]] = defaultdict(list)
    for gid, idx in members.items():
        lab = Counter(rows[i]["label"] for i in idx).most_common(1)[0][0]
        by_label[lab].append(gid)
    out = [[] for _ in range(k)]
    rng = random.Random(seed)
    for label in sorted(by_label):
        gids = sorted(by_label[label])
        rng.shuffle(gids)
        # biggest groups first, each to the currently smallest fold of this label
        gids.sort(key=lambda g: -len(members[g]))
        filled = [0] * k
        for gid in gids:
            f = min(range(k), key=lambda x: (filled[x], x))
            out[f].extend(members[gid])
            filled[f] += len(members[gid])
    for f in out:
        rng.shuffle(f)
    return out


def metrics(truth: list[str], pred: list[str], positive: str = ATTACK) -> dict:
    """Accuracy plus precision/recall/F1 for one positive class, and balanced accuracy."""
    n = len(truth)
    acc = sum(1 for t, p in zip(truth, pred) if t == p) / n if n else 0.0
    tp = sum(1 for t, p in zip(truth, pred) if t == positive and p == positive)
    fp = sum(1 for t, p in zip(truth, pred) if t != positive and p == positive)
    fn = sum(1 for t, p in zip(truth, pred) if t == positive and p != positive)
    tn = sum(1 for t, p in zip(truth, pred) if t != positive and p != positive)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    spec = tn / (tn + fp) if tn + fp else 0.0
    bal = (rec + spec) / 2 if (tp + fn) and (tn + fp) else (rec if tp + fn else spec)
    return {"n": n, "acc": acc, "precision": prec, "recall": rec, "f1": f1,
            "balanced": bal, "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def short_hebrew(rows: list[dict], idx: list[int], truth: list[str],
                 pred: list[str]) -> dict:
    """The v0.1 defect, measured: false alarms on short benign Hebrew, and
    misses on short Hebrew attacks, over the rows `idx` points at."""
    fa = nb = miss = na = 0
    for j, i in enumerate(idx):
        if not is_short_hebrew(rows[i]["text"]):
            continue
        if truth[j] == BENIGN:
            nb += 1
            fa += pred[j] != BENIGN
        else:
            na += 1
            miss += pred[j] == BENIGN
    return {"benign_n": nb, "false_alarms": fa,
            "fa_rate": fa / nb if nb else None,
            "attack_n": na, "misses": miss,
            "miss_rate": miss / na if na else None}


def per_source(rows: list[dict], idx: list[int], truth: list[str],
               pred: list[str]) -> dict[str, dict]:
    """Accuracy split by where the row came from - so an easy source cannot hide."""
    out: dict[str, dict] = {}
    buckets = defaultdict(list)
    for j, i in enumerate(idx):
        buckets[rows[i].get("source", "?")].append(j)
    for src, js in sorted(buckets.items()):
        t = [truth[j] for j in js]
        p = [pred[j] for j in js]
        out[src] = {"n": len(js),
                    "acc": sum(1 for a, b in zip(t, p) if a == b) / len(js)}
    return out


def majority_baseline(truth: list[str]) -> float:
    """The number any real result has to beat: always answer the commonest class."""
    if not truth:
        return 0.0
    return Counter(truth).most_common(1)[0][1] / len(truth)


def confusion(truth: list[str], pred: list[str], labels: list[str]) -> str:
    c = Counter(zip(truth, pred))
    w = max(len(x) for x in labels) + 1
    head = " " * (w + 2) + " ".join(f"{x[:7]:>8s}" for x in labels)
    lines = [head]
    for t in labels:
        row = " ".join(f"{c.get((t, p), 0):8d}" for p in labels)
        lines.append(f"{t:>{w}s}  {row}")
    return "\n".join(lines)
