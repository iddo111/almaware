#!/usr/bin/env python3
"""proof_ERAN-03.py -- an EMPTY dev split is blindness, not a verdict.

Defect: School.gate() consumed measure.dev_scores() without ever asking whether
the examiner had anything to look at. With the 2026-09-06 famine net
(DEV_SESSION_PICK 0 -> 1) the on-disk split marks NO file dev, so after the
next restart every gate returns dev_items=0, dev_top1=0.0 and sens=0.0 for
every unit -- indistinguishable from a child who got everything wrong. Left
alone that pushes `fails` to GATE_PATIENCE on each unit in turn, moves it to
revisit, marks all 13 mastered units "regressed", and rewrites curriculum.json
with those zeros every 200 beats. Nothing anywhere said "the dev set is empty".

School.gate and School._advance are lifted out of the file by source segment
and run against a stub examiner -- no numpy, no ears, no brain, no wav is read,
and the real state/ is never touched.

    python3 proof_ERAN-03.py            # body/school.py as it is now
    python3 proof_ERAN-03.py --bak      # body/school.py.bak-rev-20260906
"""
import ast
import importlib.util
import io
import os
import sys
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))


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


def real_genome():
    spec = importlib.util.spec_from_file_location(
        "g_real", os.path.join(HERE, "genome.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Measure(object):
    """The examiner, stubbed. It returns exactly what a blind exam returns."""
    def __init__(self, scores):
        self.scores = scores
        self.calls = 0

    def dev_scores(self, brain, ears, units=None):
        self.calls += 1
        return self.scores


class SchoolStub(object):
    def __init__(self, **kw):
        self.saved = 0
        self._no_dev_logged = None
        self.__dict__.update(kw)

    def now(self):
        return 1757160000.0

    def save(self):
        self.saved += 1


def build(path, scores, state):
    g = {"os": os, "json": None, "random": None, "sys": sys, "time": None,
         "genome": real_genome(), "measure": Measure(scores)}
    for dotted in ("School._advance", "School.gate"):
        seg = _seg(path, dotted)
        if seg is None:
            return None, None, dotted
        exec(compile(seg, dotted, "exec"), g)
    s = SchoolStub(**state)
    s._advance = g["_advance"].__get__(s)
    return g["gate"], s, None


def main():
    bak = "--bak" in sys.argv
    path = os.path.join(HERE, "school.py") + (".bak-rev-20260906" if bak else "")
    print("proof ERAN-03 -- a blind gate must skip, not condemn")
    print("  school    : %s" % path)
    if not os.path.exists(path):
        print("FAIL: missing %s" % path)
        return 1

    mastered = ["ma", "pa", "na", "ka", "sa", "ha", "va", "sha", "kha",
                "tha", "tsa", "ya", "aa"]
    results = []

    # --- case (a): the examiner saw NOTHING -------------------------------
    blind = {"per_unit": {}, "dev_top1": 0.0, "dev_items": 0,
             "fit_items": 139, "labeled_protos": 47}
    gate, s, missing = build(path, blind, {
        "unit": "la", "mastered": list(mastered), "pending_retention": {},
        "revisit": [], "fails": {"la": 5}, "last_gate": {}})
    if missing:
        print("  FAIL: %s not found in the file" % missing)
        return 1
    out = gate(s, object(), object())
    ok_fails = s.fails.get("la") == 5              # untouched
    ok_ladder = (s.unit == "la" and s.revisit == []
                 and sorted(s.mastered) == sorted(mastered))
    ok_saved = s.saved == 0                        # curriculum.json not rewritten
    ok_named = bool(out.get("no_dev")) and out.get("dev_items") == 0
    print("  (a) blind exam   fails la=%-4s ladder-intact=%-5s saved=%-2s "
          "no_dev=%-5s regressed=%s"
          % (s.fails.get("la"), ok_ladder, s.saved, out.get("no_dev"),
             len(out.get("regressed", []))))
    results.append(ok_fails and ok_ladder and ok_saved and ok_named)

    # --- case (b): a SIGHTED exam still works exactly as before -----------
    per_unit = {u: {"sens": 1.0, "spec": 1.0, "n_pos": 8} for u in mastered}
    per_unit["la"] = {"sens": 1.0, "spec": 1.0, "n_pos": 8}
    sighted = {"per_unit": per_unit, "dev_top1": 0.83, "dev_items": 112,
               "fit_items": 545, "labeled_protos": 47}
    gate, s2, _ = build(path, sighted, {
        "unit": "la", "mastered": list(mastered), "pending_retention": {},
        "revisit": [], "fails": {}, "last_gate": {}})
    out2 = gate(s2, object(), object())
    ok_pass = any("technical_pass" in e for e in out2.get("events", []))
    ok_items = out2.get("dev_items") == 112 and out2.get("no_dev") is False
    ok_saved2 = s2.saved == 1
    print("  (b) sighted exam technical_pass=%-5s dev_items=%-5s saved=%-2s "
          "unit->%s"
          % (ok_pass, out2.get("dev_items"), s2.saved, s2.unit))
    results.append(ok_pass and ok_items and ok_saved2)

    ok = all(results)
    print("RESULT: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
