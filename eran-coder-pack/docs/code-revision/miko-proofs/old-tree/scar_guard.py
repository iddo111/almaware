"""MIKO v1 -- the scar guard.  לזכרה של עלמה ז"ל.

2026-08-29's real finding: `nn.LayerNorm(1)` normalises over a ONE-element axis and is
therefore IDENTICALLY ZERO for every input, forever. Any scalar head that ends in
LayerNorm is a constant, no matter how much biology/kabbalah/logic sits underneath it.

This guard runs against MikoBiEncoder before any number from it is trusted:
  1. static check   -- no nn.LayerNorm module anywhere has normalized_shape == (1,)
  2. dynamic check   -- the score head (cosine sim of two encoded texts) actually
                         varies across different random-ish inputs, i.e. it is not a
                         constant function
"""
from __future__ import annotations

import torch
import torch.nn as nn

from model import MikoBiEncoder


def static_no_layernorm1(model: nn.Module) -> dict:
    bad = []
    for name, m in model.named_modules():
        if isinstance(m, nn.LayerNorm):
            shape = tuple(m.normalized_shape)
            if shape == (1,):
                bad.append(name)
    return {"layernorm1_modules": bad, "PASS": len(bad) == 0}


def dynamic_score_varies(model: MikoBiEncoder) -> dict:
    model.eval()
    texts_a = ["the mint sends roots into the reservoir", "ערן חי על eran1"]
    texts_b = ["a totally different sentence about 3D printers", "מדפס֪ ֪ל֪ מימד קריאליטי"]
    texts_c = ["yet another sentence, nothing like the first two", "משפט שלישי לא קשור לכלום"]
    with torch.no_grad():
        s1 = model.score(texts_a, texts_b)
        s2 = model.score(texts_a, texts_c)
        s3 = model.score(texts_b, texts_c)
    spread = float(torch.cat([s1, s2, s3]).std())
    varies = spread > 1e-4
    return {"scores_ab": s1.tolist(), "scores_ac": s2.tolist(), "scores_bc": s3.tolist(),
            "std_across_pairs": spread, "PASS": varies}


def run(model: MikoBiEncoder | None = None) -> dict:
    if model is None:
        model = MikoBiEncoder(d=64, depth=2)
    stat = static_no_layernorm1(model)
    dyn = dynamic_score_varies(model)
    result = {"static": stat, "dynamic": dyn, "PASS": bool(stat["PASS"] and dyn["PASS"])}
    return result


if __name__ == "__main__":
    import json
    r = run()
    print(json.dumps(r, ensure_ascii=False, indent=2))
    assert r["PASS"], "SCAR GUARD FAILED -- do not trust any number from this model"
    print("\nSCAR GUARD: PASS -- no LayerNorm(1), score head is not constant.")
