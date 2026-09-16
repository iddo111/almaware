"""_proofkit — load "the live file" or "the .bak-rev-20260906 backup" as a module, by path.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Shared by the proof_MOREH-*.py scripts of the 2026-09-06 code revision. A backup is copied to a
temporary *.py inside the SAME directory first, so the module's own os.path.dirname(__file__) still
finds the lessons and its siblings — and so importlib will load it at all (it refuses a name that does
not end in .py). The copy is removed at exit.
"""
import atexit
import importlib.util
import os
import shutil
import sys

BAK = ".bak-rev-20260906"


def load(directory, basename, name, old=False):
    directory = os.path.abspath(directory)
    if directory not in sys.path:
        sys.path.insert(0, directory)
    path = os.path.join(directory, basename)
    if old:
        src = path + BAK
        if not os.path.exists(src):
            raise FileNotFoundError("no backup at %s" % src)
        path = os.path.join(directory, "_probe_%s_%d.py" % (name, os.getpid()))
        shutil.copyfile(src, path)
        atexit.register(lambda p=path: os.path.exists(p) and os.remove(p))
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    m.__proof_source__ = os.path.basename(path if not old else basename + BAK)
    return m
