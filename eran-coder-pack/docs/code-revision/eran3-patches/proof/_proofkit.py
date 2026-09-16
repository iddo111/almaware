# -*- coding: utf-8 -*-
"""Shared helpers for the CODER-* proof scripts.

Every proof takes a TARGET path (a file or a directory) and must FAIL against the
original eran3 code and PASS against the patched code, so it is run twice:

    python proof_CODER-07.py ../orig/train.py    -> expected FAIL (exit 1)
    python proof_CODER-07.py ../new/train.py     -> expected PASS (exit 0)

train.py cannot be imported here (it needs torch, and this is a Windows PC where
no training may run at all), so its pure helpers are lifted out by AST and
executed on their own. watchdog.py is pure stdlib and is imported for real.
"""
import ast
import importlib.util
import pathlib
import sys
import uuid

PREAMBLE = "import os, sys, time, json, math, shutil\n"


def load_module(path, name=None):
    """Import a python FILE as a module under a unique name."""
    path = str(path)
    name = name or ("proofmod_%s" % uuid.uuid4().hex)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def extract(path, names, preamble=PREAMBLE):
    """Execute ONLY the named top-level defs/assignments from a python file.

    Returns (namespace, missing_names). Nothing else in the file runs, so a file
    whose imports are unavailable here (torch) can still be tested where it is
    pure python.
    """
    src = pathlib.Path(path).read_text(encoding="utf-8")
    tree = ast.parse(src)
    want = set(names)
    picked = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in want:
                picked.append(node)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in want:
                    picked.append(node)
                    break
    ns = {}
    exec(compile(preamble, "<preamble>", "exec"), ns)
    if picked:
        mod = ast.Module(body=picked, type_ignores=[])
        exec(compile(ast.fix_missing_locations(mod), str(path), "exec"), ns)
    missing = sorted(n for n in want if n not in ns)
    return ns, missing


class Proof(object):
    def __init__(self, ident, target):
        self.id = ident
        self.target = pathlib.Path(target)
        self.fails = []
        print("PROOF %s  target=%s" % (ident, self.target))

    def check(self, ok, label, detail=""):
        mark = "ok  " if ok else "FAIL"
        print("  [%s] %s%s" % (mark, label, ("  -- " + detail) if detail else ""))
        if not ok:
            self.fails.append(label)
        return ok

    def fail(self, label, detail=""):
        return self.check(False, label, detail)

    def done(self):
        if self.fails:
            print("PROOF %s: FAIL (%d check(s) failed: %s)"
                  % (self.id, len(self.fails), "; ".join(self.fails)))
            sys.exit(1)
        print("PROOF %s: PASS" % self.id)
        sys.exit(0)


def target_from_argv(default_rel):
    if len(sys.argv) > 1:
        return pathlib.Path(sys.argv[1])
    return pathlib.Path(__file__).resolve().parent.parent / default_rel
