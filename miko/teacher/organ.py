# -*- coding: utf-8 -*-
"""organ.py -- the thing being taught. An ALMA weave that judges (question, page).

REUSED, NOT REBUILT: the feature hasher and the weave are alma-language/alma_guard,
exactly as GUARD uses them. Only one thing is new here, and it is the thing MIKO needs
that GUARD did not: GUARD has ONE text, MIKO has TWO that must MEET.

THE MEETING
-----------
`encoding.features` turns a text into a set of hashed n-gram buckets, each seeded with
a presence spark of 1.0; an absent feature is NOT seeded, so its knot stays SILENT, and
in ALMA silence is what carries credit. For a pair we build two banks:

    bank A (bucket b)        : b present in the question AND in the page  -> the MATCH
    bank B (bucket b + W)    : b present in the question and NOT in the page -> the MISS

That is `prod` over a shared bucket written as an encoding instead of as a knot, and it
is the whole of the pair representation. Note what is deliberately ABSENT: the page's
own buckets are never fed alone, and page LENGTH is never a feature. Both omissions are
so that evaluate.py's length-only and overlap-only controls stay honest controls.

ABSTENTION IS FREE HERE. A weave whose head never fires has said "not found" -- it did
not return a low number, it returned silence. score() gives back None for that, and
evaluate.py counts it as an abstention rather than quietly ranking it last.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

_ALMA = Path(r"D:\CLAUDE\alma-language")
if str(_ALMA) not in sys.path:
    sys.path.insert(0, str(_ALMA))

from alma_guard import encoding as E          # noqa: E402
from alma_guard.weave import GuardWeave, Hyper  # noqa: E402

RELEVANT, IRRELEVANT = "relevant", "irrelevant"


def meeting_features(question: str, page: str, width: int = 1024) -> dict[int, float]:
    """The two banks. Width of the weave must be 2*width."""
    q = E.features(question, width)
    p = E.features(page, width)
    pk = set(p)
    feats: dict[int, float] = {}
    for b in q:
        if b in pk:
            feats[b] = 1.0            # bank A: they met
        else:
            feats[b + width] = 1.0    # bank B: the question asked, the page was silent
    return feats


class MikoOrgan:
    """Thin wrapper so train_loop and evaluate speak about the organ the same way."""

    def __init__(self, width: int = 1024, **hyper):
        self.width = width
        h = dict(width=2 * width, epochs=hyper.pop("epochs", 6),
                 seed=hyper.pop("seed", 0), drift=hyper.pop("drift", 0.05),
                 init=hyper.pop("init", 0.02), r_ok=hyper.pop("r_ok", 0.10),
                 r_miss=hyper.pop("r_miss", 4.0), r_fa=hyper.pop("r_fa", 1.0))
        h.update(hyper)
        self.hyper = Hyper(**h)
        self.weave = GuardWeave([RELEVANT], self.hyper, default=IRRELEVANT)

    # ------------------------------------------------------------------ learn
    def train(self, examples, epochs=None, seed=0, verbose=False):
        """examples = [(feats, label_int)] with 1 = relevant. Returns n presentations."""
        rng = random.Random(seed + 7)
        order = list(range(len(examples)))
        n = 0
        for ep in range(epochs or self.hyper.epochs):
            rng.shuffle(order)
            for i in order:
                feats, y = examples[i]
                self.weave.present(feats, RELEVANT if y else IRRELEVANT, learn=True)
                n += 1
            if verbose:
                print("    epoch %d/%d done (%d presentations)"
                      % (ep + 1, epochs or self.hyper.epochs, n))
        return n

    # ------------------------------------------------------------------ speak
    def score(self, feats) -> float | None:
        """The head's margin, or None when the organ stayed silent = 'not found'."""
        pred, margin = self.weave.predict(feats)
        return margin.get(0) if margin else None

    # ------------------------------------------------------------------ disk
    def save(self, path, meta=None):
        blob = {"width": self.width, "hyper": vars(self.hyper),
                "weights": self.weave.weights(), "meta": meta or {}}
        Path(path).write_text(json.dumps(blob), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path):
        blob = json.loads(Path(path).read_text(encoding="utf-8"))
        h = dict(blob["hyper"])
        h.pop("width", None)
        o = cls(width=blob["width"], **h)
        o.weave.load(blob["weights"])
        o.meta = blob.get("meta", {})
        return o
