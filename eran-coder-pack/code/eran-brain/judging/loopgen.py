#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
loopgen.py -- THE ROUND GENERATOR for the judging loop (Iddo is the metric).

Given the winner of a round it makes the next round: the winner itself carried
over as the INCUMBENT plus three mutants around it, rendered on eran2 by the
very render() the search used (train_one.render for /ah/, train_syl2.render for
ma/na/la/ya -- via ~/throat-one-sample/loop_render.py), pulled to the PC over
scp, named by round. No metric anywhere in this file, on purpose: the only
number that steers the search is Iddo's click.

Sigma starts wide and shrinks as rounds pass (x0.8 per round, floor).
Measured 2026-09-02 21:23: one ssh render call ~1.3 s round trip, 0.2 s per
clip, scp ~1 s -- a round is ready in ~3-4 s, so generation is LIVE, not pooled.

    python loopgen.py smoke     # renders one throw-away round, prints timing
"""
import io
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
LOOP = os.path.join(ROOT, "loop")
POOL = os.path.join(LOOP, "pool")            # real files live here, never served by name
HOST = "eran2"
REMOTE_DIR = "throat-one-sample/loop"       # relative to ~ on eran2
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", HOST]

# sigma schedule per unit family. /ah/ is in log2-area units (train_one starts
# at 0.55); syllables are a fraction of the parameter span (train_syl2: 0.30).
SIGMA0 = {"ah": 0.55, "syl": 0.30}
SIGMA_FLOOR = {"ah": 0.05, "syl": 0.03}
SHRINK = 0.8
N_MUTANTS = 3
LABELS = ["A", "B", "C", "D"]


def fam(unit):
    return "ah" if unit == "ah" else "syl"


def sigma_for(unit, generation):
    """generation 0 = first generated round after the seed."""
    f = fam(unit)
    return max(SIGMA_FLOOR[f], SIGMA0[f] * (SHRINK ** generation))


def _run(cmd, stdin_text=None, timeout=120):
    p = subprocess.run(cmd, input=stdin_text, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError("%s -> rc %d\n%s" % (" ".join(cmd[:3]), p.returncode, p.stderr[-800:]))
    return p.stdout


def remote_render(unit, tag, items=None, mutate=None):
    """Render on eran2 into ~/throat-one-sample/loop/<tag>/ and pull to POOL/<tag>/.
    Returns the manifest (list of {name, genome, kind, ok, peak})."""
    job = {"unit": unit, "out_dir": "~/%s/%s" % (REMOTE_DIR, tag),
           "items": items or []}
    if mutate:
        job["mutate"] = mutate
    t0 = time.time()
    out = _run(SSH + ["cd ~/throat-one-sample && python3 loop_render.py"],
               stdin_text=json.dumps(job))
    line = [l for l in out.splitlines() if l.startswith("MANIFEST ")]
    if not line:
        raise RuntimeError("no MANIFEST from eran2:\n" + out[-800:])
    man = json.loads(line[-1][len("MANIFEST "):])
    t1 = time.time()
    dest = os.path.join(POOL, tag)
    os.makedirs(dest, exist_ok=True)
    _run(["scp", "-o", "BatchMode=yes", "-q", "-r",
          "%s:%s/%s/." % (HOST, REMOTE_DIR, tag), dest])
    t2 = time.time()
    man["timing"] = {"render_s": round(t1 - t0, 2), "pull_s": round(t2 - t1, 2)}
    for it in man["items"]:
        it["path"] = os.path.join(dest, it["name"])
        it["ok"] = bool(it["ok"]) and os.path.isfile(it["path"])
    return man


def make_round(unit, round_no, parent, generation, incumbent=None, seed=None):
    """parent = winner's genome (list). incumbent = {"path", "genome", "kind"} of the
    winner to carry over. Returns a round dict ready for loop.py's state."""
    tag = "r%02d-%s" % (round_no, unit)
    sigma = sigma_for(unit, generation)
    man = remote_render(unit, tag, mutate={
        "parent": parent, "sigma": sigma, "n": N_MUTANTS,
        "seed": seed if seed is not None else round_no * 7919,
        "prefix": "ERAN-%s-r%02d" % (unit, round_no)})
    clips = [it for it in man["items"] if it["ok"]]
    if incumbent:
        clips.append({"name": os.path.basename(incumbent["path"]), "path": incumbent["path"],
                      "genome": incumbent["genome"], "kind": "incumbent", "ok": True})
    return {"round": round_no, "unit": unit, "sigma": sigma, "generation": generation,
            "made": time.strftime("%Y-%m-%d %H:%M:%S"), "timing": man["timing"],
            "clips": clips, "chosen": None}


if __name__ == "__main__":
    if sys.argv[1:] and sys.argv[1] == "smoke":
        t = time.time()
        r = make_round("ah", 99, [-0.6013, -0.0092, -0.631, -1.4002, 1.6041, -1.8558, 1.8504, 1.933], 0)
        print(json.dumps({k: v for k, v in r.items() if k != "clips"}, indent=1))
        for c in r["clips"]:
            print(c["kind"], c["name"], c["ok"], os.path.getsize(c["path"]))
        print("TOTAL %.1f s" % (time.time() - t))
