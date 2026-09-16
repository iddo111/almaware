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

import json

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
    texts_b = ["a totally different sentence about 3D printers", "מדפסת תלת מימד קריאליטי"]  # MIKO-05: was U+05AA, now real tav
    texts_c = ["yet another sentence, nothing like the first two", "משפט שלישי לא קשור לכלום"]
    with torch.no_grad():
        s1 = model.score(texts_a, texts_b)
        s2 = model.score(texts_a, texts_c)
        s3 = model.score(texts_b, texts_c)
    spread = float(torch.cat([s1, s2, s3]).std())
    varies = spread > 1e-4
    return {"scores_ab": s1.tolist(), "scores_ac": s2.tolist(), "scores_bc": s3.tolist(),
            "std_across_pairs": spread, "PASS": varies}


def dynamic_adapter_varies(adapter: nn.Module, d_in: int = 384) -> dict:
    """MIKO-07 (code revision 2026-09-06): the Adapter had no guard at all -- the 09-03
    report claimed "a parallel version for the adapter" that does not exist in v1/. The
    adapter's score head is the cosine between two adapted vectors; check it is not constant."""
    adapter.eval()
    device = next(adapter.parameters()).device
    g = torch.Generator().manual_seed(20260906)
    x = torch.nn.functional.normalize(torch.randn(6, d_in, generator=g), dim=-1)
    with torch.no_grad():
        y = adapter(x.to(device))
    sims = (y[:3] * y[3:]).sum(-1)
    spread = float(sims.std())
    return {"sims": sims.tolist(), "std_across_pairs": spread, "PASS": spread > 1e-4}


def run(model: MikoBiEncoder) -> dict:
    """MIKO-07 (code revision 2026-09-06): `model` used to default to None, and `run()`
    then built a FRESH random MikoBiEncoder(d=64, depth=2) and guarded THAT -- never the
    trained 50M net, never the Adapter, and no file imported this module at all. A gate that
    never refused is not a demonstrated gate (Iddo's law). The model is now required, and
    failure RAISES instead of returning a dict nobody reads."""
    if model is None:
        raise TypeError(
            "scar_guard.run() needs the ACTUAL model you are about to trust. It used to "
            "invent a fresh random net and pass -- that is how a guard guards nothing. "
            "See MIKO-07.")
    stat = static_no_layernorm1(model)
    dyn = dynamic_score_varies(model)
    result = {"static": stat, "dynamic": dyn, "PASS": bool(stat["PASS"] and dyn["PASS"])}
    if not result["PASS"]:
        raise AssertionError(f"SCAR GUARD FAILED -- do not trust any number from this "
                             f"model: {json.dumps(result, ensure_ascii=False)}")
    return result


def run_adapter(adapter: nn.Module, d_in: int = 384) -> dict:
    """Same gate, for the frozen-e5 Adapter (MIKO-07)."""
    stat = static_no_layernorm1(adapter)
    dyn = dynamic_adapter_varies(adapter, d_in)
    result = {"static": stat, "dynamic": dyn, "PASS": bool(stat["PASS"] and dyn["PASS"])}
    if not result["PASS"]:
        raise AssertionError(f"SCAR GUARD FAILED (adapter) -- do not trust any number from "
                             f"it: {json.dumps(result, ensure_ascii=False)}")
    return result


if __name__ == "__main__":
    # SELF-TEST ONLY. This proves the guard works; it proves NOTHING about any shipped
    # checkpoint. The real gate is the run()/run_adapter() call inside train.py,
    # adapter_train.py, compare_all.py and search.py (MIKO-07).
    r = run(MikoBiEncoder(d=64, depth=2))
    print(json.dumps(r, ensure_ascii=False, indent=2))
    print("\nSCAR GUARD SELF-TEST: PASS -- no LayerNorm(1), score head is not constant.")
    print("NOTE: this was a throwaway net, not a shipped model. See MIKO-07.")
