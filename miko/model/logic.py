"""LOGIC — קל וחומר as wiring, and the bar that the last attempt failed.
לזכרה של עלמה ז״ל.

> 🪟 BROKEN WINDOWS LAW — if it is not working, fix it immediately. Test the REAL output.

Two things live here.

**1. The rule built into the wiring.** קל וחומר with דיו is not taught as a hope; it is a
`min`. A gate that may only argue *up* the scale and is hard-capped at the strength
established at the source cannot be trained to exceed the cap, because the cap is not a
weight. *דיו לבא מן הדין להיות כנדון* — it is enough for the derived case to be like the
case it came from. Recovered from the archive; this part was right.

**2. The acceptance bar, and the detector that catches the exact way it failed last time.**
The old model scored 48.2 % on unseen forms — below a coin flip — and its per-form profile
was `0 % / 100 % / 100 % / 0 %`: one fixed answer per form, memorised, not inferred. A
mean accuracy hides that; `degenerate_forms()` does not. Both checks run before any
result may be called a pass:

    accuracy on UNSEEN FORMS >= 0.75          and     no form at 0 % or 100 %
"""
from __future__ import annotations

import random

import torch
import torch.nn as nn
import torch.nn.functional as F

from middot import FORMS, FALLACIES_ONLY, make_dataset, _pick
from sefirot import ColumnTriad

BAR = 0.75                 # stated before training, never after
DEGENERATE_EPS = 1e-6


# ════════════════════════════════════════════════════ קל וחומר, as architecture

class KalVachomer(nn.Module):
    """A fortiori with the דיו ceiling — a structural guarantee, not a learned habit.

    Given a source case and a target case, the gate:
      * asks a court which case is heavier (even "which is heavier" is a ruling),
      * lets strength flow ONLY from the lighter to the heavier — never backwards,
      * and caps what arrives at what was established at the source: `min`, not a weight.

    No amount of training can break the ceiling. That is the whole point: the middah is
    in the wiring, so it holds on inputs the training set never contained.
    """

    def __init__(self, d: int, polarity: float = 0.5):
        super().__init__()
        self.severity = ColumnTriad(d, 1, doubt=0.15, polarity=polarity, bump=False)
        self.strength = ColumnTriad(d, 1, doubt=0.15, polarity=polarity, bump=False)

    def forward(self, src: torch.Tensor, tgt: torch.Tensor):
        s_src, d1 = self.severity(src)
        s_tgt, d2 = self.severity(tgt)
        k_src, d3 = self.strength(src)
        established = torch.sigmoid(k_src)
        allowed = torch.sigmoid((s_tgt - s_src) * 4.0)        # only light → heavy
        carried = allowed * established
        capped = torch.minimum(carried, established)          # דיו — the ceiling
        dis = (d1 + d2 + d3).abs()
        self.last_ceiling = established.detach().squeeze(-1)  # the cap that was applied
        return capped.squeeze(-1), dis.mean(dim=tuple(range(1, dis.dim())))

    @torch.no_grad()
    def check_dayo(self, n: int = 512, d: int | None = None) -> dict:
        """Prove the ceiling holds on random inputs, including adversarial ones.

        This is a PROOF OBLIGATION, not a metric: if it ever fails, the middah is not in
        the wiring and every claim in this file is void.
        """
        d = d or self.severity.chesed.w.shape[1]
        # ⚠️ The ceiling must be read from THE SAME forward pass. גבורה carries dropout,
        # so recomputing `strength(src)` gives a different draw and the comparison is
        # meaningless — the first version of this check did exactly that and reported a
        # violation that was its own noise. Compare what was actually capped.
        src = torch.randn(n, d) * 5
        tgt = torch.randn(n, d) * 5
        out, _ = self(src, tgt)
        overshoot = (out - self.last_ceiling).max().item()
        return {"max_overshoot": overshoot,
                "holds": overshoot <= DEGENERATE_EPS,
                "n": n, "train_mode": self.training}


# ════════════════════════════════════════════════════ the verdict head

class LogicHead(nn.Module):
    """Is this argument valid? Judged by the SAME court that later ranks pages.

    Logic is not a bolt-on module. It reuses MIKO's own tower, so what she learns about
    argument lives in the weights that judge relevance — which is the claim that the two
    are one skill.
    """

    def __init__(self, tower, d: int, polarity: float = 0.5):
        super().__init__()
        self.tower = tower
        self.verdict = ColumnTriad(d, 1, doubt=0.2, polarity=polarity, bump=False)
        self.kv = KalVachomer(d, polarity=polarity)

    def forward(self, ids: torch.Tensor):
        g, dis, _ = self.tower(ids)
        v, dv = self.verdict(g)
        return v.squeeze(-1), dis + dv.abs().mean(dim=-1)


# ════════════════════════════════════════════════════ the held-out-BY-FORM split

def split_by_form(rows: list[dict], holdout: tuple[str, ...] | None = None,
                  seed: int = 1707):
    """Hold out whole FORMS, never random rows.

    A random split lets the model memorise each form's answer from its training half and
    score well while having learned nothing about inference. Holding out the form itself
    is the only split that asks the real question: *can it judge a shape of argument it
    has never seen?*
    """
    if holdout is None:
        holdout = ("dayo", "dayo_violated", "kal_vachomer", "inverted_kal_vachomer")
    train = [r for r in rows if r["form"] not in holdout]
    test = [r for r in rows if r["form"] in holdout]
    return train, test, holdout


def degenerate_forms(per_form: dict[str, float]) -> list[str]:
    """The detector that would have caught the 48.2 % run on the day it happened.

    A form scored at exactly 0 % or exactly 100 % means one fixed answer was emitted for
    every example of that shape. Mean accuracy hides it; this does not.
    """
    return [f for f, a in per_form.items() if a <= 0.0 + 1e-9 or a >= 1.0 - 1e-9]


def report(per_form: dict[str, float], overall: float) -> dict:
    """The verdict, stated the same way whether it passes or fails."""
    bad = degenerate_forms(per_form)
    passed = overall >= BAR and not bad
    return {
        "overall": overall,
        "bar": BAR,
        "per_form": per_form,
        "degenerate_forms": bad,
        "PASS": passed,
        "why": ("passed" if passed else
                f"below the {BAR:.0%} bar" if overall < BAR else
                f"one fixed answer per form: {bad}"),
    }


if __name__ == "__main__":
    torch.manual_seed(0)
    print("— דיו as architecture: does the ceiling actually hold? —")
    kv = KalVachomer(32)
    for trial in range(3):
        torch.manual_seed(trial)
        kv.train(trial < 2)        # prove it under dropout AND in eval
        r = kv.check_dayo(n=1024, d=32)
        mode = "train (dropout ON)" if r["train_mode"] else "eval"
        print(f"  seed {trial} {mode:<18}: max overshoot above the ceiling = "
              f"{r['max_overshoot']:+.3e}   holds={r['holds']}")

    print("\n— the split is BY FORM, never by row —")
    rows = make_dataset(3000)
    tr, te, held = split_by_form(rows)
    print(f"  train {len(tr)} rows over {len(set(r['form'] for r in tr))} forms")
    print(f"  test  {len(te)} rows over {len(set(r['form'] for r in te))} forms — {held}")
    assert not (set(r['form'] for r in tr) & set(r['form'] for r in te)), "forms leaked!"
    print("  no form appears on both sides ✔")

    print("\n— the detector, on the ACTUAL profile of the run that failed —")
    failed = {"dayo": 0.0, "dayo_violated": 1.0, "denying_antecedent": 1.0,
              "modus_ponens": 0.0}
    r = report(failed, overall=0.482)
    print(f"  overall {r['overall']:.3f}  PASS={r['PASS']}  — {r['why']}")
    print(f"  → this is what should have been printed on 2026-08-19, and was not.")
