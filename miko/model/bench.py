"""BENCH — the three metrics, decided BEFORE any training.  לזכרה של עלמה ז״ל.

> 🪟 BROKEN WINDOWS LAW — if it is not working, fix it immediately. Test the REAL output.

A model is not "good"; it is good *at a stated thing*. MIKO's three, from `miko/PLAN.md`,
in order, every one reported next to a vanilla control of matched parameter count:

    1  RELEVANCE    reproduce the fleet's 0–1 judgement from raw bytes
    2  CALIBRATION  does DISSENT PREDICT ERROR?  — the court's own central claim
    3  ROBUSTNESS   corrupt one seat: the ruling should barely move

Speed is not a criterion. Parameter counts are matched within 1 %. Seeds >= 3. Every
number is printed next to its control, **including the ones that lose.**

────────────────────────────────────────────────────────────────────────────────────
WHAT CAN RUN TODAY, AND WHAT IS BLOCKED — stated plainly
────────────────────────────────────────────────────────────────────────────────────
RUNS NOW (no labels needed — these are properties of the wiring):
    3  robustness           corrupt a seat: bloc vs mean vs the rejected median
    –  the LayerNorm scar   a regression test so that bug can never come back

BLOCKED ON DATA:
    1  relevance   `miko/PLAN.md` says "156 fleet-scored pairs in the archive
                   (data/pairs.jsonl)". **That file does not exist.** The archive at
                   `_genizah/almido-search-20260820/` has no `data/` directory at all —
                   only two `findings/` files. Memory recorded "295 teacher-scored pairs
                   and climbing" on eran4 on 2026-08-19; if they survive, they are there,
                   not here. Until real pairs are in hand this metric does not run, and
                   NO synthetic substitute will be used — synthetic corpora transfer at
                   chance in this project and that scar is already paid for.
    2  calibration  needs the same labels.

Nothing is written up as working until its number exists.
"""
from __future__ import annotations

import json
import pathlib

import torch
import torch.nn as nn
import torch.nn.functional as F

from alma import encode_batch
from miko import Miko, Vanilla, matched_vanilla
from sefirot import ColumnTriad

HERE = pathlib.Path(__file__).resolve().parent
PAIRS = HERE.parent / "data" / "pairs.jsonl"


# ═════════════════════════════════════════════════ 3. ROBUSTNESS — never run until now

def corrupt(seat: torch.Tensor, how: str) -> torch.Tensor:
    """The three ways a witness goes bad."""
    if how == "zero":
        return torch.zeros_like(seat)
    if how == "invert":
        return -seat
    if how == "saturate":
        return torch.full_like(seat, 50.0)
    raise ValueError(how)


def robustness(d: int = 64, n: int = 512, seeds: int = 3) -> dict:
    """THE CLAIM: one corrupted seat should not be able to drag the verdict.

    `miko/PLAN.md`: *"This is a one-hour experiment and it has never been run."*
    It is run here, on the same three seat opinions ruled THREE ways:

        bloc    אחרי רבים להטות — MIKO's actual ruling, the majority that agrees
        mean    the control: one loud seat drags everyone
        median  the REJECTED rule — Iddo, 2026-08-29: "בית דין אמיתי עם הכרעה, לא חציון"
                — kept here only so the rejection is MEASURED, not assumed
    """
    out: dict[str, dict[str, float]] = {}
    for how in ("zero", "invert", "saturate"):
        bags = {"bloc": [], "mean": [], "median": []}
        for s in range(seeds):
            torch.manual_seed(s)
            t = ColumnTriad(d, d, bump=False)
            x = torch.randn(n, d)
            t(x)
            seats = t.last_seats.detach()                        # (3, n, d)
            rules = {
                "bloc": lambda st: t.rule(st)[0],
                "mean": lambda st: st.mean(0),
                "median": lambda st: st.median(dim=0).values,
            }
            for name, rule in rules.items():
                clean = rule(seats)
                for victim in range(3):
                    bad = seats.clone()
                    bad[victim] = corrupt(bad[victim], how)
                    shift = (rule(bad) - clean).norm() / (clean.norm() + 1e-8)
                    bags[name].append(float(shift))
        res = {k: sum(v) / len(v) for k, v in bags.items()}
        out[how] = {**res, "best": min(res, key=res.get),
                    "bloc_vs_mean": res["mean"] / res["bloc"] if res["bloc"] > 0 else float("inf")}
    return out


# ═════════════════════════════════════════════════ the scar, as a regression test

def layernorm_scar() -> dict:
    """`nn.LayerNorm(1)` is identically zero. This is the measured cause of the archived
    worm's 48.2 % logic result — its verdict head and GIST attention were CONSTANT.

    This test exists so the bug can never come back silently.
    """
    ln = nn.LayerNorm(1)
    x = torch.randn(8, 1) * 10
    dead = float(ln(x).abs().max())
    t = ColumnTriad(32, 1, bump=False)
    a = t(torch.randn(4, 32))[0]
    b = t(torch.randn(4, 32) * 7)[0]
    live = float((a - b).abs().max())
    return {"layernorm1_max_output": dead,
            "columntriad_d_out_1_varies_with_input": live,
            "PASS": dead < 1e-6 and live > 1e-3}


# ═════════════════════════════════════════════════ 1+2. relevance and calibration

def load_pairs(path: pathlib.Path = PAIRS):
    if not path.exists():
        return None
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return rows


def relevance_and_calibration(rows, d: int = 96, depth: int = 4, max_len: int = 512,
                              steps: int = 400, seeds: int = 3) -> dict:
    """Fit the fleet's 0–1 judgement; then ask whether dissent predicts error.

    Both arms trained identically, parameter counts matched within 1 %.
    Returns numbers whether they win or lose.
    """
    if not rows:
        return {"blocked": "no fleet-scored pairs on disk — see the header of this file"}
    q = encode_batch([r["question"] for r in rows], max_len)
    p = encode_batch([r["page"] for r in rows], max_len)
    y = torch.tensor([float(r["score"]) for r in rows])
    cut = int(0.8 * len(rows))
    res = {}
    for name in ("miko", "vanilla"):
        losses, calib = [], []
        for s in range(seeds):
            torch.manual_seed(s)
            m = Miko(d=d, depth=depth, max_len=max_len)
            model = m if name == "miko" else matched_vanilla(m, max_len)
            opt = torch.optim.Adam(model.parameters(), lr=3e-4)
            for _ in range(steps):
                opt.zero_grad()
                o = model(q[:cut], p[:cut])
                loss = F.mse_loss(o["score"], y[:cut]) + 0.02 * o["dissent"].mean()
                loss.backward()
                opt.step()
            model.eval()
            with torch.no_grad():
                o = model(q[cut:], p[cut:])
                err = (o["score"] - y[cut:]).abs()
                losses.append(float(err.mean()))
                dis = o["dissent"]
                if float(dis.std()) > 1e-6:
                    hi = dis > dis.median()
                    calib.append(float(err[hi].mean() - err[~hi].mean()))
        res[name] = {
            "heldout_abs_err": sum(losses) / len(losses),
            "dissent_predicts_error": (sum(calib) / len(calib)) if calib else None,
        }
    res["winner"] = min(("miko", "vanilla"), key=lambda k: res[k]["heldout_abs_err"])
    return res


if __name__ == "__main__":
    print("═" * 78)
    print("MIKO BENCH — every number next to its control, including the ones that lose")
    print("═" * 78)

    print("\n[scar] nn.LayerNorm(1) regression test")
    r = layernorm_scar()
    print(f"  LayerNorm(1) max output          = {r['layernorm1_max_output']:.3e}  (is zero)")
    print(f"  ColumnTriad(d,1) input-dependent = {r['columntriad_d_out_1_varies_with_input']:.4f}")
    print(f"  PASS = {r['PASS']}")

    print("\n[3] ROBUSTNESS — corrupt ONE of three seats. Never run before today.")
    print("     verdict shift, relative (lower = the court held). 3 seeds x 3 victims.")
    rob = robustness()
    print(f"     {'corruption':<11} {'BLOC (ours)':>12} {'MEAN (ctrl)':>12} "
          f"{'MEDIAN (rejected)':>18}   best")
    for how, v in rob.items():
        print(f"     {how:<11} {v['bloc']:>12.4f} {v['mean']:>12.4f} {v['median']:>18.4f}"
              f"   {v['best']}")

    print("\n[1+2] RELEVANCE + CALIBRATION")
    rows = load_pairs()
    out = relevance_and_calibration(rows)
    if "blocked" in out:
        print(f"     BLOCKED — {out['blocked']}")
        print(f"     expected at: {PAIRS}")
        print("     next step: recover the fleet-scored pairs from eran4, or re-collect.")
    else:
        print(f"     {json.dumps(out, indent=2)}")

    print("\n" + "═" * 78)
