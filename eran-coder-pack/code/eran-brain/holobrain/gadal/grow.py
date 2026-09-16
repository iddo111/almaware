"""GADAL / גָּדַל — THE POLICY: when a model is allowed to get bigger, and when it is not.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

This is the contribution. net.py is a replaceable body; this file is the rule.

THE INSTRUMENT
--------------
"Underfit" cannot be a feeling. It has to be a number, and the number has to have a
floor under it, or "the loss is still high" means nothing at all.

When the data contains the SAME input more than once with different answers -- ERAN's 3
clips of one syllable, MOREH's 14 verified variants of one letter, any corpus with
repeats -- the spread WITHIN a repeated input is error no function of the input can ever
remove. That within-group variance is the irreducible floor, and it is measured, not
assumed:

    floor = sum over outputs and groups of (y - group mean)^2  /  number of live entries

A model whose train loss sits at the floor has extracted everything the inputs allow.
A model whose train loss sits above the floor has not, and only THAT is underfit.

If a dataset has no repeated inputs the floor is 0 and the caller is told, because then
condition B below is vacuous and the rule is running on three legs, not four.

THE RULE, EXACTLY AS IMPLEMENTED
--------------------------------
GROW (widen) when ALL FOUR hold at a checkpoint:

  A  TRAIN PLATEAU        best train MSE improved by less than `tol` (relative) over the
                          last `patience` checks. A model still descending is not stuck
                          and does not need more room.
  B  UNDERFIT             train MSE > floor * (1 + `slack`). The model has NOT yet
                          reached what the data itself allows.
  C  NOT ALREADY MEMORISING   (val - train) / max(train, eps) <= `gap_max`.
                          A wide train-to-val gap means the capacity it already has is
                          being spent on memorising. More capacity makes that worse.
  D  GROWTH IS STILL PAYING   the BEST val seen anywhere in the run has improved since
                          the previous growth step. After `grow_patience` consecutive
                          growth steps that bought no new best, growth halts for good.
                          (Comparing consecutive checkpoints instead of the running best
                          was measured on 2026-09-05 to halt at width 1 in 20 of 22 folds
                          -- a coarse val set makes consecutive readings jump around, and
                          the halt fired on noise. The running best is monotone and does
                          not have that failure mode.)

NEVER GROW because the model is doing well. That is the road that produced ERAN's
3-clips-per-syllable, MIKO's 39 memorised questions and WINSTON's 93 indexed photos.
Conditions A and B are the trigger and both are about failure to fit; C and D are
brakes. There is no path in this file where success causes growth.

PRUNE after a growth phase halts: drop the hidden units whose utility
(||outgoing|| * std(activation)) is below `prune_frac` of the largest, having first
folded their mean contribution into the next bias. The prune is KEPT only if val does
not worsen by more than `prune_tol`; otherwise it is reverted and logged as refused.
Then, if the rule fires again, grow again. A brain adds and prunes; adding only is not
the mechanism.

WHAT IS RETURNED is the best-val snapshot, with the size it had at that moment -- not
the last size reached. Growing past the right size and keeping the overgrown model would
be the same mistake in a new coat.

EVERY step is logged with the numbers that justified it: size before and after, train
and val at the decision point, the floor, the gap, which condition failed, and the
measured output delta of the function-preserving operation. Without that record it is
intuition wearing a lab coat.
"""
from __future__ import annotations

import json
import math
import os

import numpy as np

from net import Net


# ---------------------------------------------------------------------------- the floor
def noise_floor(Y, M, groups) -> dict:
    """Irreducible masked MSE: the spread that survives inside a repeated input.

    Y (n, k) targets, M (n, k) 0/1 live mask, groups (n,) an id per row -- rows sharing an
    id have the SAME input. Returns the floor and the evidence for it.
    """
    Y = np.asarray(Y, float)
    M = np.asarray(M, float) if M is not None else np.ones_like(Y)
    g = np.asarray(groups)
    uniq = np.unique(g)
    ss, n_live = 0.0, float(M.sum())
    repeated = 0
    for u in uniq:
        rows = g == u
        if rows.sum() < 2:
            continue
        repeated += 1
        for j in range(Y.shape[1]):
            m = rows & (M[:, j] > 0)
            if m.sum() < 2:
                continue
            v = Y[m, j]
            ss += float(((v - v.mean()) ** 2).sum())
    return {"floor": ss / max(n_live, 1.0), "n_live": n_live, "n_groups": int(len(uniq)),
            "n_groups_repeated": repeated,
            "usable": repeated > 0}


# ---------------------------------------------------------------------------- the gardener
class Gardener:
    """Trains a net that is allowed to change size. All decisions are logged."""

    DEFAULTS = dict(
        lr=0.03, wd=0.0,
        check_every=25,          # epochs between decision points
        patience=6,              # checks of train plateau before a growth decision
        max_epochs=6000,
        tol=0.002,               # relative train improvement that still counts as descent
        slack=0.10,              # train must be >10% above the floor to count as underfit
        gap_max=0.60,            # relative train/val gap above which we refuse to grow
        grow_frac=0.5,           # units added = ceil(grow_frac * current width), min 1
        max_width=512,
        grow_patience=3,         # growth steps buying no new best-val before halting
        val_tol=0.0,             # relative best-val improvement that counts as "paid off"
        prune_frac=0.05,         # utility below this fraction of the max is prunable
        prune_tol=0.02,          # relative val worsening a prune may cost before refusal
        max_cycles=8,
        widen_eps=1e-2,
        widen_mode="zero",   # "zero" (new random unit, zero fan-out) or "split" (Net2Net copy)
        start_width=1,
    )

    def __init__(self, n_in, n_out, seed=0, log_path=None, **cfg):
        self.cfg = dict(self.DEFAULTS)
        bad = set(cfg) - set(self.DEFAULTS)
        if bad:
            raise ValueError("unknown config keys: %s" % sorted(bad))
        self.cfg.update(cfg)
        self.net = Net(n_in, n_out, widths=(self.cfg["start_width"],), seed=seed, act="relu")
        self.seed = seed
        self.log: list[dict] = []
        self.log_path = log_path

    # ------------------------------------------------------------------ logging
    def _say(self, kind, **kw):
        rec = {"i": len(self.log), "kind": kind, **kw}
        self.log.append(rec)
        if self.log_path:
            os.makedirs(os.path.dirname(os.path.abspath(self.log_path)), exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec

    # ------------------------------------------------------------------ the run
    def fit(self, Xtr, Ytr, Mtr, Xva, Yva, Mva, groups_tr=None, verbose=False):
        c = self.cfg
        fl = (noise_floor(Ytr, Mtr, groups_tr) if groups_tr is not None
              else {"floor": 0.0, "usable": False, "n_groups_repeated": 0})
        self._say("floor", **{k: (float(v) if isinstance(v, (int, float, np.floating)) else v)
                              for k, v in fl.items()})
        floor = float(fl["floor"])

        best = {"val": math.inf, "state": None, "widths": None, "epoch": -1, "params": None}
        hist_tr: list[float] = []
        epoch = 0
        grow_fails = 0
        grown_halted = False
        cycles = 0
        val_at_last_grow = math.inf

        def snap(ep):
            tr = self.net.loss(Xtr, Ytr, Mtr)
            va = self.net.loss(Xva, Yva, Mva)
            if va < best["val"]:
                best.update(val=va, state=self.net.state(), widths=self.net.widths,
                            epoch=ep, params=self.net.n_params,
                            mae_va=self.net.mae(Xva, Yva, Mva))
            return tr, va

        while epoch < c["max_epochs"] and cycles < c["max_cycles"]:
            # ---- train until the train loss plateaus (or we run out of epochs)
            plateau = False
            while epoch < c["max_epochs"]:
                for _ in range(c["check_every"]):
                    self.net.step(Xtr, Ytr, Mtr, lr=c["lr"], wd=c["wd"])
                epoch += c["check_every"]
                tr, va = snap(epoch)
                hist_tr.append(tr)
                if len(hist_tr) > 2 * c["patience"]:
                    recent = min(hist_tr[-c["patience"]:])
                    prev = min(hist_tr[-2 * c["patience"]: -c["patience"]])
                    if prev - recent < c["tol"] * max(prev, 1e-12):
                        plateau = True
                        break
            tr = self.net.loss(Xtr, Ytr, Mtr)
            va = self.net.loss(Xva, Yva, Mva)
            gap = (va - tr) / max(tr, 1e-12)

            # ---- the decision
            cond = {
                "A_train_plateau": bool(plateau),
                "B_underfit": bool(tr > floor * (1.0 + c["slack"])) if fl["usable"] else None,
                "C_not_memorising": bool(gap <= c["gap_max"]),
                "D_growth_paying": bool(grow_fails < c["grow_patience"]),
            }
            room = self.net.widths[-1] < c["max_width"]
            fires = (cond["A_train_plateau"] and (cond["B_underfit"] is not False)
                     and cond["C_not_memorising"] and cond["D_growth_paying"] and room
                     and not grown_halted)

            if fires:
                k = max(1, int(math.ceil(c["grow_frac"] * self.net.widths[-1])))
                k = min(k, c["max_width"] - self.net.widths[-1])
                y_before = self.net.forward(Xtr)
                before = self.net.widths
                p_before = self.net.n_params
                self.net.widen(k, eps=c["widen_eps"], mode=c["widen_mode"])
                delta = float(np.max(np.abs(self.net.forward(Xtr) - y_before)))
                # D: did the RUNNING BEST val improve since the previous growth step?
                paid = (math.isinf(val_at_last_grow) or
                        (val_at_last_grow - best["val"]) > c["val_tol"] * max(val_at_last_grow, 1e-12))
                grow_fails = 0 if paid else grow_fails + 1
                val_at_last_grow = best["val"]
                self._say("grow", epoch=epoch, width_before=before, width_after=self.net.widths,
                          params_before=p_before, params_after=self.net.n_params, added=k,
                          train_mse=tr, val_mse=va, gap=gap, floor=floor,
                          conditions=cond, preserve_max_abs_delta=delta, mode=c["widen_mode"],
                          previous_step_paid=bool(paid), grow_fails=grow_fails)
                if verbose:
                    print(f"  grow {before}->{self.net.widths} ep{epoch} tr {tr:.5f} va {va:.5f} "
                          f"gap {gap:+.3f} floor {floor:.5f} delta {delta:.2e}")
                hist_tr.clear()      # a new size gets a fresh plateau history, or the stale
                cycles += 1          # one re-fires 25 epochs later and it grows without learning
                continue

            # ---- growth refused: say exactly which leg failed, then prune
            if not grown_halted:
                self._say("halt_growth", epoch=epoch, width=self.net.widths, train_mse=tr,
                          val_mse=va, gap=gap, floor=floor, conditions=cond,
                          reason=("max_width" if not room else
                                  ",".join(k for k, v in cond.items() if v is False) or "none"))
                grown_halted = True

            pruned = self._prune_pass(Xtr, Ytr, Mtr, Xva, Yva, Mva, epoch)
            if pruned:
                grown_halted = False                 # a smaller model may underfit again
                grow_fails = 0
                val_at_last_grow = math.inf
                hist_tr.clear()
                cycles += 1
                continue
            break

        # the model we keep is the best-val snapshot, not the last size reached
        if best["state"] is not None:
            self.net.restore(best["state"])
        self._say("done", epoch=epoch, kept_widths=best["widths"], kept_epoch=best["epoch"],
                  kept_val_mse=best["val"], kept_params=best["params"],
                  final_widths=self.net.widths)
        return self.net, best

    # ------------------------------------------------------------------ pruning
    def _prune_pass(self, Xtr, Ytr, Mtr, Xva, Yva, Mva, epoch) -> int:
        c = self.cfg
        u = self.net.utility(Xtr)
        if len(u) <= 1:
            return 0
        thr = c["prune_frac"] * float(u.max())
        keep = u > thr
        if keep.all() or not keep.any():
            return 0
        va0 = self.net.loss(Xva, Yva, Mva)
        state = self.net.state()
        self.net.fold_constant(Xtr, keep)
        n = self.net.prune(keep)
        va1 = self.net.loss(Xva, Yva, Mva)
        ok = va1 <= va0 * (1.0 + c["prune_tol"])
        if not ok:
            self.net.restore(state)
        self._say("prune", epoch=epoch, removed=n, kept=int(keep.sum()),
                  width_after=self.net.widths, utility_max=float(u.max()),
                  utility_threshold=thr, val_before=va0, val_after=va1,
                  accepted=bool(ok))
        return n if ok else 0
