#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
loop_seed.py -- builds the SEED SITTING for loop.py (the morning rounds).

Round /ah/: the k8 fit (eran2:~/throat-one-sample/out/best.wav), k16, k24, and
the NO-LEARNING control rendered from the neutral adult /a/ (mouth2.vowel_knots
("a"), f0 105, via train_one.render on eran2 -- the same renderer the fits used).

Round /ma/: the syl3 fit (out/best-ma.wav + out/result-ma.json), the v1-boxed
fit (its old [c_pos, velum, ...] genome converted to the current
[c_pos, c_area, ...] layout -- c_area was hard-zero then, velum is fixed 0.75
now), the v2-onetemplate fit (genome APPROXIMATED from its log -- the run had
no FINAL line; marked as such in the KEY), and the no-learning control = the
search's own starting point P0.

    python loop_seed.py ah      # appends the /ah/ seed round
    python loop_seed.py ma      # appends the /ma/ seed round
    python loop_seed.py reset   # wipes state/KEY (pool files are kept)
"""
import io
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import loopgen  # noqa: E402

LOOP = os.path.join(ROOT, "loop")
STATE = os.path.join(LOOP, "state.json")
KEY = os.path.join(LOOP, "KEY.json")
POOL = os.path.join(LOOP, "pool")
HOST = "eran2"
R = "throat-one-sample/out"

CONTROL_AH = [-0.9229073710206798, -0.8713493779120841, -1.2464713328963373,
              -0.32892991496979634, 1.5752519153010287, 2.0, 2.0, 1.6108444963466666]
# train_syl2 P0 for ma: pos (0.90+1.00)/2, area (0+0.30)/2, 0.60, 0.10, 0.05, 0.30
CONTROL_MA = [0.95, 0.15, 0.60, 0.10, 0.05, 0.30]


def load_state():
    if os.path.isfile(STATE):
        with io.open(STATE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"rounds": [], "gen": {}, "next_round": 1, "built": time.strftime("%Y-%m-%d %H:%M:%S")}


def save_state(st):
    with io.open(STATE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)


def pull(remote, local):
    os.makedirs(os.path.dirname(local), exist_ok=True)
    subprocess.run(["scp", "-o", "BatchMode=yes", "-q", "%s:%s" % (HOST, remote), local], check=True)
    return local


def rjson(remote):
    out = subprocess.run(["ssh", "-o", "BatchMode=yes", HOST, "cat %s" % remote],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def seed_ah(st):
    rn = st["next_round"]
    tag = "r%02d-ah" % rn
    d = os.path.join(POOL, tag)
    clips = []
    for k, wav, js in (("k8", "best.wav", "result.json"), ("k16", "best-k16.wav", "result-k16.json"),
                       ("k24", "best-k24.wav", "result-k24.json")):
        name = "ERAN-ah-r%02d-%s.wav" % (rn, k)
        p = pull("%s/%s" % (R, wav), os.path.join(d, name))
        g = rjson("%s/%s" % (R, js))
        clips.append({"name": name, "path": p, "genome": g["knots"], "kind": "fit-" + k,
                      "ok": True, "note": "loss %.4f F %s" % (g["loss"], [round(x) for x in g["F"]])})
    man = loopgen.remote_render("ah", tag, items=[{"name": "ERAN-ah-r%02d-control.wav" % rn,
                                                    "genome": CONTROL_AH, "kind": "control-no-learning"}])
    c = man["items"][0]
    assert c["ok"], c
    clips.append({"name": c["name"], "path": c["path"], "genome": c["genome"],
                  "kind": "control-no-learning", "ok": True,
                  "note": "neutral adult /a/ = mouth2.vowel_knots('a'), f0 105, no search"})
    st["rounds"].append({"round": rn, "unit": "ah", "sigma": None, "generation": 0,
                         "made": time.strftime("%Y-%m-%d %H:%M:%S"), "timing": man["timing"],
                         "clips": clips, "chosen": None, "seed": True})
    st["gen"].setdefault("ah", 0)
    st["next_round"] = rn + 1
    return rn


def seed_ma(st):
    rn = st["next_round"]
    tag = "r%02d-ma" % rn
    d = os.path.join(POOL, tag)
    clips = []
    # 1. syl3 fit (per-unit gesture, c_area searched)
    g3 = rjson("%s/result-ma.json" % R)
    name = "ERAN-ma-r%02d-syl3.wav" % rn
    clips.append({"name": name, "path": pull("%s/best-ma.wav" % R, os.path.join(d, name)),
                  "genome": g3["params"], "kind": "fit-syl3", "ok": True,
                  "note": "loss %.4f params %s" % (g3["loss"], [round(x, 3) for x in g3["params"]])})
    # 2. v1-boxed fit: old layout [c_pos, velum, ten, d_c, d_t, d_v] -> [c_pos, c_area=0, ten, d_c, d_t, d_v]
    g1 = rjson("%s/v1-boxed/result-ma.json" % R)
    p1 = g1["params"]
    name = "ERAN-ma-r%02d-v1boxed.wav" % rn
    clips.append({"name": name, "path": pull("%s/v1-boxed/best-ma.wav" % R, os.path.join(d, name)),
                  "genome": [p1[0], 0.0, p1[2], p1[3], p1[4], p1[5]], "kind": "fit-v1boxed", "ok": True,
                  "note": "genome CONVERTED from the old velum-searched layout (velum %.2f dropped; now fixed 0.75)" % p1[1]})
    # 3. v2-onetemplate fit: no FINAL in syl2-ma.log; genome approximated from its last printed line
    name = "ERAN-ma-r%02d-v2onetemplate.wav" % rn
    clips.append({"name": name, "path": pull("%s/v2-onetemplate/best-ma.wav" % R, os.path.join(d, name)),
                  "genome": [0.90, 0.0, p1[2], 0.29, 0.14, 0.90], "kind": "fit-v2onetemplate-genome-approx", "ok": True,
                  "note": "genome APPROXIMATED from syl2-ma.log it 180 (c_pos 0.90 dur 0.29/0.14/1.17->0.90 cap); tenseness borrowed from v1"})
    # 4. control = P0, no learning
    man = loopgen.remote_render("ma", tag, items=[{"name": "ERAN-ma-r%02d-control.wav" % rn,
                                                    "genome": CONTROL_MA, "kind": "control-no-learning"}])
    c = man["items"][0]
    assert c["ok"], c
    clips.append({"name": c["name"], "path": c["path"], "genome": c["genome"],
                  "kind": "control-no-learning", "ok": True,
                  "note": "train_syl2 P0 for /ma/ on the frozen /ah/ vowel, no search"})
    st["rounds"].append({"round": rn, "unit": "ma", "sigma": None, "generation": 0,
                         "made": time.strftime("%Y-%m-%d %H:%M:%S"), "timing": man["timing"],
                         "clips": clips, "chosen": None, "seed": True})
    st["gen"].setdefault("ma", 0)
    st["next_round"] = rn + 1
    return rn


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "ah"
    if what == "reset":
        for f in (STATE, KEY):
            if os.path.isfile(f):
                os.remove(f)
        print("state + KEY removed")
        sys.exit(0)
    st = load_state()
    rn = {"ah": seed_ah, "ma": seed_ma}[what](st)
    save_state(st)
    r = st["rounds"][-1]
    print("seeded round %d (%s):" % (rn, what))
    for c in r["clips"]:
        print("  %-38s %-28s %6d B  %s" % (c["name"], c["kind"], os.path.getsize(c["path"]), c.get("note", "")))
