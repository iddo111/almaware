#!/usr/bin/env python3
"""proof_ERAN-05.py -- an empty menu must NAME itself, and a famine must refuse the wake.

Defect: `menu = serve_menu(); item = choose(menu); if item:` -- when the school
served nothing, the beat fell straight through. No exception (an empty list is
not an error), no log line, no 'ate_nothing' key: the metrics line simply had
no "surprise" in it and the beats kept flowing at 215/s. That is exactly how
2026-09-06 nearly ended, and the fix that day moved a constant without adding
the second net: naming the famine.

Two halves, both lifted out of eran_life.py by source segment and run against
stubs -- no numpy, no ears, no brain, no wav, no state/ write, nothing
restarted:
  (a) Life.one_beat with an empty menu     -> must mark extra['ate_nothing']
  (b) Life._assert_food on a food dir whose every file is exam-only
                                           -> must RAISE at the door

    python3 proof_ERAN-05.py           # eran_life.py as it is now
    python3 proof_ERAN-05.py --bak     # eran_life.py.bak-rev-20260906
"""
import ast
import datetime
import io
import json
import os
import shutil
import sys
import tempfile
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
BIG = 10 ** 9


def _seg(path, dotted):
    src = io.open(path, encoding="utf-8").read()
    tree = ast.parse(src)

    def find(body, want):
        for n in body:
            if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == want:
                return n
        return None

    node, body = None, tree.body
    for part in dotted.split("."):
        node = find(body, part)
        if node is None:
            return None
        body = getattr(node, "body", [])
    return textwrap.dedent(ast.get_source_segment(src, node) or "")


def load(path, dotted, glb):
    seg = _seg(path, dotted)
    if seg is None:
        return None
    g = dict(glb)
    exec(compile(seg, dotted, "exec"), g)
    return g[dotted.split(".")[-1]]


class Obj(object):
    def __init__(self, **kw):
        self.__dict__.update(kw)


class Chem(object):
    def decay(self):
        pass

    def observe(self, s):
        pass

    def progress(self):
        return 0.0

    def snapshot(self):
        return {}


class Drives(object):
    def __init__(self, pick):
        self.pick = pick

    def choose(self, menu, brain, ears):
        return self.pick

    def tick(self):
        pass

    def eat_cost(self):
        pass

    def feed_progress(self, *a):
        pass

    def sleep_pressure(self, beat):
        return False


class School(object):
    def __init__(self, menu, unit="la", wavs=()):
        self.menu, self.unit, self._wavs = menu, unit, list(wavs)

    def serve_menu(self, chem=None):
        return list(self.menu)

    def _unit_wavs(self, unit):
        return list(self._wavs)


class Life(object):
    def __init__(self, menu, pick, school=None):
        self.beat = 0
        self.ablate = []
        self.chem = Chem()
        self.drives = Drives(pick)
        self.school = school or School(menu)
        self.brain = Obj()
        self.ears = Obj()
        self.cortex = Obj(layers=[])
        self.eaten_since_sleep = 0
        self.famine_beats = 0
        self.best_dev = -1.0
        self.logs = []
        self.extra = None

    def _log(self, m):
        self.logs.append(m)

    def _metrics_line(self, extra=None):
        self.extra = dict(extra or {})

    def checkpoint(self):
        pass


def main():
    bak = "--bak" in sys.argv
    path = os.path.join(HERE, "eran_life.py") + (".bak-rev-20260906" if bak else "")
    print("proof ERAN-05 -- name the famine, refuse the empty wake")
    print("  eran_life : %s" % path)
    if not os.path.exists(path):
        print("FAIL: missing %s" % path)
        return 1
    results = []
    tmp = tempfile.mkdtemp(prefix="proof-eran05-")
    try:
        gstub = Obj(GATE_EVERY=BIG, SLEEP_EVERY=BIG, BABBLE_EVERY=BIG,
                    SAVE_EVERY=BIG, SNAP_EVERY=BIG, STATE_DIR=tmp,
                    FOOD_TRAIN=os.path.join(tmp, "food"),
                    DEV_SESSION_PICK=1, DEV_SESSION_MOD=6, DEV_FRAC_MOD=5)

        # ---- (a) an empty menu must be NAMED in the metrics line ----------
        one_beat = load(path, "Life.one_beat",
                        {"os": os, "json": json, "datetime": datetime,
                         "genome": gstub, "parent": Obj(check_inbox=lambda *a, **k: None),
                         "sleep_mod": Obj(), "MIN_DEV_ITEMS_FOR_BEST": 20})
        if one_beat is None:
            print("  FAIL: Life.one_beat not found")
            return 1
        life = Life([], None)
        one_beat(life)
        named = "ate_nothing" in (life.extra or {})
        no_surprise = "surprise" not in (life.extra or {})
        said = any("ATE NOTHING" in m for m in life.logs)
        print("  (a) empty menu   metrics keys=%s  ate_nothing=%-5s logged=%-5s"
              % (sorted((life.extra or {}).keys()), named, said))
        results.append(named and no_surprise and said)

        # ---- (b) a wake with nothing edible must REFUSE -------------------
        food = os.path.join(tmp, "food")
        os.makedirs(food)
        for i in range(20):                        # session t01 -> ALL dev
            io.open(os.path.join(food, "ba_t01_%d.wav" % i), "w").close()
        meas = os.path.join(HERE, "proof", "measure.py")
        mg = {"os": os, "genome": gstub, "hashlib": __import__("hashlib")}
        session_of = load(meas, "session_of", mg)
        mg["session_of"] = session_of
        is_dev = load(meas, "is_dev", mg)
        food_exc = load(path, "FoodEmptyError", {})
        gl = {"os": os, "genome": gstub,
              "school_mod": Obj(measure=Obj(is_dev=is_dev))}
        if food_exc is not None:
            gl["FoodEmptyError"] = food_exc
        assert_food = load(path, "Life._assert_food", gl)
        if assert_food is None or food_exc is None:
            print("  (b) Life._assert_food=%s FoodEmptyError=%s -- nothing "
                  "refuses an empty wake"
                  % (assert_food is not None, food_exc is not None))
            results.append(False)
        else:
            life2 = Life([], None, school=School([], wavs=[]))
            raised = None
            try:
                assert_food(life2)
            except Exception as e:                 # noqa: BLE001 - we name it
                raised = e
            ok = raised is not None and type(raised).__name__ == "FoodEmptyError"
            print("  (b) all-dev food raised=%s" % (type(raised).__name__
                                                    if raised else "NOTHING"))
            if life2.logs:
                print("      %s" % life2.logs[-1][:150])
            # and a mixed diet must NOT refuse
            for i in range(20):
                io.open(os.path.join(food, "ba_t06_%d.wav" % i), "w").close()
            life3 = Life([], None, school=School([], wavs=[]))
            try:
                assert_food(life3)
                ok2 = True
            except Exception as e:                 # noqa: BLE001
                ok2 = False
                print("      unexpected refusal on a mixed diet: %s" % e)
            print("      mixed diet accepted=%s | %s"
                  % (ok2, life3.logs[-1][:150] if life3.logs else ""))
            results.append(ok and ok2)

        ok = all(results) and len(results) == 2
        print("RESULT: %s" % ("PASS" if ok else "FAIL"))
        return 0 if ok else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
