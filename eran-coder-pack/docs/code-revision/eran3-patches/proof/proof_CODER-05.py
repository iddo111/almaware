# -*- coding: utf-8 -*-
"""CODER-05 -- the only 'the weights improved' number is contaminated.

paired_compare.py printed a single headline: "IDENTICAL DATA: global sequences
0..6783 ... difference -0.2568 +/- 0.0160 (-16.06 sigma)". Its docstring says the
only differences between the two sides are the weights and the batch size.

That is false. The new run's weights come from init_weights_step1017.pt, taken
from the OLD run's checkpoint at step 1017 -- whose train_state.json records
seq_index 8136. Those weights had already trained on global sequences 0..8135,
which is a superset of the 0..6783 being compared. A lower loss there is real
learning PLUS first-pass memorisation, in unknown proportion, and no amount of
sigma separates them after the fact.

This proof drives the real script over a synthetic train.out where the new run
has not yet reached the first clean step, and demands that it says so.

Run:  python proof_CODER-05.py ../orig/paired_compare.py   -> FAIL
      python proof_CODER-05.py ../new/paired_compare.py    -> PASS
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _proofkit import Proof, extract, target_from_argv  # noqa: E402

target = target_from_argv("new/paired_compare.py").resolve()
p = Proof("CODER-05", target)

# ---- 1. the boundary is computable ----------------------------------------
ns, missing = extract(target, ["first_clean_step"])
if missing:
    p.fail("first_clean_step() exists",
           "the script has no notion that some of the compared data was already "
           "trained on -- it cannot tell a clean step from a contaminated one")
else:
    f = ns["first_clean_step"]
    # old run's ckpt/step_00001017/train_state.json: seq_index 8136; new block 128
    p.check(f(8136, 128) == 65,
            "seq_index 8136 at block 128 -> first clean NEW step is 65",
            "got %r; new step d covers sequences [(d-1)*128, d*128), so d=64 "
            "covers 8064..8191 and still overlaps the seen 8064..8135" % (f(8136, 128),))
    p.check(f(8192, 128) == 65, "an exact multiple boundary is handled")
    p.check(f(0, 128) == 1, "a cold start has no contaminated prefix")

# ---- 2. run the real script on a synthetic train.out ----------------------
with tempfile.TemporaryDirectory() as t:
    t = pathlib.Path(t)
    lines = []
    for s in range(1, 1018):            # old run, batch 8, max 8000
        lines.append("[00:00:00] step %d/8000 loss %.4f gnorm 0.900 lr 1e-05\n"
                     % (s, 1.40 - 0.00002 * s))
    for s in range(1, 54):              # new run, batch 128, max 1600, 53 steps
        lines.append("[00:00:00] step %d/1600 loss %.4f gnorm 0.550 lr 4e-05\n"
                     % (s, 1.15 - 0.0008 * s))
    (t / "train.out").write_text("".join(lines), encoding="utf-8")
    st = t / "step_00001017"
    st.mkdir()
    (st / "train_state.json").write_text(json.dumps({"seq_index": 8136,
                                                     "dom_cursor": 7323}),
                                         encoding="utf-8")
    r = subprocess.run([sys.executable, str(target), "train.out",
                        str(st / "train_state.json"), "128"],
                       cwd=str(t), capture_output=True, text=True)
    out = (r.stdout or "") + (r.stderr or "")
    print("  --- script output ---")
    for ln in out.splitlines():
        print("  | " + ln)
    print("  ---------------------")

    p.check("CONTAMINATED" in out.upper(),
            "the contaminated half is labelled as such",
            "the script reports a comparison without saying that one side had "
            "already trained on that text")
    p.check("IDENTICAL DATA" not in out.upper(),
            "it no longer claims the two sides saw 'identical data' unqualified",
            "the SET of sequences is identical; what the weights had already seen "
            "of it is not, and that is the whole question")
    p.check("8136" in out or "8,136" in out,
            "the warm-start seq_index is stated in the output",
            "the reader must be able to check the boundary claim")
    p.check(("CLEAN" in out.upper() and
             ("not reached" in out.lower() or "no uncontaminated" in out.lower())),
            "with only 53 of the needed 65 steps, it refuses to quote a clean number",
            "saying 'there is no uncontaminated comparison yet' is the honest "
            "answer; printing -16 sigma instead is not")

p.done()
