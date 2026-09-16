# -*- coding: utf-8 -*-
"""CODER-04 -- the act that never returns.

Nothing the coder training produces ever comes back:
  - save-hf-every 0, so no usable model is ever exported;
  - the fp32 masters live only inside a 50 GB optim.pt;
  - a recursive grep of /home/eran3 for 'ckpt2' finds only the 4 unit files --
    no process on any box loads a checkpoint;
  - ~/coder-base-logs holds one number, taken 2026-09-04 07:30 on the BASE model,
    twelve hours BEFORE training began, by a script that can only load an HF repo
    by name and therefore cannot score a checkpoint at all.

So the held-out set that the four-guard contract exists to protect (400 files,
its own exit code 5, a self-test at every boot) has never been re-scored, and
"is the coder better than base on code it has never seen" has no answer after
430 hours of planned GB10 time.

This proof takes a DIRECTORY (orig/ or new/) and checks the whole return path:
export exists -> an evaluator can read it -> the watchdog surfaces the number.

Run:  python proof_CODER-04.py ../orig    -> FAIL
      python proof_CODER-04.py ../new     -> PASS
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _proofkit import Proof, extract, load_module, target_from_argv  # noqa: E402

d = target_from_argv("new")
p = Proof("CODER-04", d)

# ---- 1. an export is actually produced -------------------------------------
cfgp = d / "train.config.json"
cfg = json.loads(cfgp.read_text(encoding="utf-8")) if cfgp.exists() else {}
hf = cfg.get("save-hf-every")
se = cfg.get("save-every")
p.check(isinstance(hf, int) and hf > 0,
        "save-hf-every > 0 (an export is produced at all)",
        "save-hf-every=%r -- with 0 the masters never leave optim.pt and nothing "
        "can load them" % (hf,))
if isinstance(hf, int) and hf > 0 and isinstance(se, int) and se > 0:
    p.check(hf % se == 0,
            "save-hf-every is a multiple of save-every",
            "%d %% %d = %d -- an export that never lands on a checkpoint step "
            "cannot be tied back to one" % (hf, se, hf % se))

# ---- 2. exports are pruned (8.4 GB each on an 84%-full disk) ---------------
tp = d / "train.py"
ns, missing = extract(tp, ["prune_export_dirs"])
if missing:
    p.fail("train.py prunes old HF exports",
           "prune_export_dirs() missing -- exports would grow without bound at "
           "8.4 GB each while ckpt/ + ckpt2/ + ckpt-keep/ already hold 238 GB")
else:
    import tempfile
    import os
    with tempfile.TemporaryDirectory() as t:
        for n in ("step_00000200", "step_00000400", "step_00000600"):
            os.makedirs(os.path.join(t, n))
        gone = ns["prune_export_dirs"](t, 2)
        left = sorted(os.listdir(t))
        p.check(gone == ["step_00000200"] and left == ["step_00000400", "step_00000600"],
                "prune keeps the newest 2 exports", "removed=%r left=%r" % (gone, left))
    src = tp.read_text(encoding="utf-8")
    p.check("prune_export_dirs(" in src.split("HF export ->")[-1][:400],
            "the prune is actually called after an export is written")

# ---- 3. an evaluator that can read an export -------------------------------
ev = d / "eval_ckpt.py"
if not ev.exists():
    p.fail("eval_ckpt.py exists",
           "baseline.py loads the HF repo BY NAME (AutoModelForCausalLM."
           "from_pretrained(REPO)) -- there is no tool on the box that can score "
           "a trained checkpoint, so no held-out number can exist")
else:
    ens, emiss = extract(ev, ["summarise", "delta_vs_baseline", "step_of", "SEQ"])
    p.check(not emiss, "eval_ckpt.py exposes its pure scoring helpers", repr(emiss))
    if not emiss:
        p.check(ens["SEQ"] == 2048,
                "SEQ cap matches baseline.py (2048)",
                "a different cap makes the new number incomparable to the only "
                "baseline that exists")
        res = ens["summarise"](900.0, 1000, 800, {"py": [400.0, 500, 420]})
        p.check(abs(res["MEAN_CE_NATS"] - 0.9) < 1e-6 and res["TOP1_ACCURACY"] == 0.8,
                "summarise() computes token-weighted CE and top-1", json.dumps(res)[:120])
        dv = ens["delta_vs_baseline"]({"MEAN_CE_NATS": 0.80, "TOP1_ACCURACY": 0.81},
                                      {"MEAN_CE_NATS": 0.9386, "TOP1_ACCURACY": 0.7893})
        p.check(dv and dv["improved"] is True and dv["delta_ce_nats_negative_is_better"] < 0,
                "a lower CE than the 0.9386-nat baseline reads as improved", repr(dv))
        dv2 = ens["delta_vs_baseline"]({"MEAN_CE_NATS": 1.10, "TOP1_ACCURACY": 0.70},
                                       {"MEAN_CE_NATS": 0.9386, "TOP1_ACCURACY": 0.7893})
        p.check(dv2 and dv2["improved"] is False,
                "a HIGHER CE reads as not improved (the sign is not fudged)")
        p.check(ens["step_of"]("/x/export/step_00000200") == 200,
                "the eval line carries the training step it belongs to")
        try:
            ens["summarise"](0.0, 0, 0, {})
            p.fail("scoring zero tokens refuses to write a result",
                   "an empty eval must raise, not report CE 0 -- that is the "
                   "'empty batch that does not raise' shape")
        except SystemExit:
            p.check(True, "scoring zero tokens refuses to write a result")
        except ZeroDivisionError:
            p.check(True, "scoring zero tokens refuses to write a result",
                    "raises ZeroDivisionError")

# ---- 4. the watchdog surfaces the number (or its absence) ------------------
wp = d / "watchdog.py"
w = load_module(wp)
if not hasattr(w, "eval_lag_problem"):
    p.fail("the watchdog reports the held-out score",
           "a watchdog that reports a falling training loss and never mentions "
           "that the held-out set has not been scored is reporting the easy half")
else:
    p.check(bool(w.eval_lag_problem(None, 53)),
            "'never scored' is reported as a problem",
            repr(w.eval_lag_problem(None, 53)))
    p.check(bool(w.eval_lag_problem({"step": 200}, 1600)),
            "a stale eval (step 200 vs 1600) is reported")
    p.check(w.eval_lag_problem({"step": 1500}, 1600) is None,
            "a current eval is not nagged about")

p.done()
