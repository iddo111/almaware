"""A tiny, MATCHING world, so the proofs can actually run the chain.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

2026-09-06, code revision. Every defect in this directory had to be proved on the CODE,
because the code itself cannot run: `eye/state/eye.pt` is a grayscale encoder and the
corpus went to colour on 08-31 (ZIV-01), so both entry points die before their first
step. A proof that only reads source text proves nothing about behaviour.

So this builds a WORLD the entry points can actually run in — a fresh encoder of the
right shape, a small colour corpus, a fresh hand — in a temp directory, and hands back
the argv that points at it. Nothing here touches the real corpus except to READ
`ear-human.npz`, which is 281 KB and is the one real thing in the fixture: 22 syllables x
6 takes x 3 clips, so the rectangularity asserts in both files are exercised for real.

Deliberately tiny — 22 letters x 4 typefaces x 2 images, and the callers use 2-3 training
steps. This is a smoke fixture on the PC, not training: nothing here is a model anyone
keeps, and no number it produces means anything.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "eye"))
sys.path.insert(0, os.path.join(HERE, "..", "hand"))

EAR = os.path.join(HERE, "ear-human.npz")
NAMES = ["alef", "bet", "gimel", "dalet", "he", "vav", "zayin", "het", "tet", "yod",
         "kaf", "lamed", "mem", "nun", "samekh", "ayin", "pe", "tsadi", "qof", "resh",
         "shin", "tav"]


def build(tmp, fonts=4, per_font=2, holdout_in_eye=None, hand=True, seed=7):
    """Write letters.npz / letters.json / eye.pt / hand.pt into `tmp`. Returns paths."""
    from eye import CH, PATCH, SIZE, Encoder                         # noqa: PLC0415

    d = np.load(EAR, allow_pickle=True)
    syllables = [str(s) for s in d["syllables"]]
    n_let = len(syllables)
    os.makedirs(tmp, exist_ok=True)

    rng = np.random.default_rng(seed)
    n = n_let * fonts * per_font
    X = np.zeros((n, SIZE, SIZE, CH), dtype=np.float32)
    y = np.zeros(n, dtype=np.int16)
    f = np.zeros(n, dtype=np.int16)
    c = np.zeros(n, dtype=np.int16)
    p = np.zeros(n, dtype=np.int16)
    i = 0
    for li in range(n_let):
        base = rng.random((SIZE, SIZE, 1)).astype(np.float32)        # one shape per letter
        for fi in range(fonts):
            for _ in range(per_font):
                ink = rng.random((1, 1, CH)).astype(np.float32) * 0.6 + 0.4
                X[i] = np.clip(base * ink + 0.02 * rng.random((SIZE, SIZE, CH)), 0, 1)
                y[i], f[i], c[i], p[i] = li, fi, fi % 3, 0
                i += 1
    np.savez_compressed(os.path.join(tmp, "letters.npz"), X=X, y=y, f=f, c=c, p=p)
    json.dump({"size": SIZE, "n": int(n), "per": fonts * per_font, "fonts": fonts,
               "channels": CH, "inks": ["a", "b", "c"], "papers": ["white"],
               "letters": [{"i": k, "name": NAMES[k], "char": NAMES[k][0],
                            "syllable": syllables[k]} for k in range(n_let)],
               "note": "PROOF FIXTURE -- not a corpus, not a result"},
              open(os.path.join(tmp, "letters.json"), "w", encoding="utf-8"))

    torch.manual_seed(seed)
    enc = Encoder()
    ck = {"encoder": enc.state_dict(), "gist_dim": 192, "size": SIZE, "patch": PATCH,
          "channels": CH, "note": "PROOF FIXTURE encoder -- random weights"}
    if holdout_in_eye is not None:
        ck["holdout"] = int(holdout_in_eye)
    torch.save(ck, os.path.join(tmp, "eye.pt"))

    hand_path = os.path.join(tmp, "hand.pt")
    if hand:
        from hand_eye import Winston                                 # noqa: PLC0415
        torch.save({"hand": Winston(n_let).state_dict()}, hand_path)
    elif os.path.exists(hand_path):
        # A temp directory is reused between proofs, and a hand.pt left behind by an
        # earlier build would quietly turn "no hand" back into "hand". The fixture has to
        # be the world it says it is.
        os.remove(hand_path)

    return {"ear": EAR, "eye": os.path.join(tmp, "eye.pt"),
            "letters": os.path.join(tmp, "letters.npz"),
            "meta": os.path.join(tmp, "letters.json"), "hand": hand_path,
            "out": os.path.join(tmp, "state")}


def argv(paths, *extra, holdout_fonts=1, steps=2, take=5):
    """The argv that points an entry point at the fixture. Tiny on purpose."""
    return (["--ear", paths["ear"], "--eye", paths["eye"], "--letters", paths["letters"],
             "--meta", paths["meta"], "--hand", paths["hand"], "--out", paths["out"],
             "--device", "cpu", "--steps", str(steps),
             "--holdout-fonts", str(holdout_fonts), "--holdout-take", str(take),
             "--i-know-this-is-the-PC"] + list(extra))


def load(path, name="mod"):
    """Import a .py OR a .bak-* file as a module, from its own directory.

    The backups sit beside the live files on purpose: `HERE` then resolves the same way
    for both, so old and new code see exactly the same world.
    """
    import importlib.util
    from importlib.machinery import SourceFileLoader
    spec = importlib.util.spec_from_file_location(
        name, path, loader=SourceFileLoader(name, path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


BAK = ".bak-rev-20260906"
DIRS = {"zivug.py": HERE, "close_loop.py": HERE, "show_sound_drawings.py": HERE,
        "eye.py": os.path.join(HERE, "..", "eye")}


def is_old():
    """`--old` runs the proof against the .bak-rev-20260906 backups. No flag = live."""
    return "--old" in sys.argv[1:]


def src(name):
    """The path to one source file, live or backed-up, chosen by the --old flag."""
    return os.path.join(DIRS[name], name + (BAK if is_old() else ""))


def which():
    return "OLD (%s)" % BAK if is_old() else "LIVE"


def run_main(mod, args):
    """mod.main(args), dropping flags this build's parser does not know.

    The backups predate --i-know-this-is-the-PC, --no-hand, --loto and --retrain-heads;
    argparse would exit 2 on them and that would look like a failure for the wrong
    reason. Dropping them is the honest comparison: the old code has no such behaviour.
    """
    new_flags = ("--i-know-this-is-the-PC", "--no-hand", "--loto", "--retrain-heads",
                 "--part-of-loto")
    try:
        return mod.main(list(args))
    except SystemExit as e:
        if e.code == 2:
            keep = [x for x in args if x not in new_flags]
            if keep != list(args):
                return mod.main(keep)
        raise


def load_fp(path, key=None):
    """guards.fingerprint, so a proof can build the `want` dict the loader compares."""
    import guards
    return guards.fingerprint(path, key)


def ok(msg):
    print("PASS: %s" % msg)
    return 0


def bad(msg):
    print("FAIL: %s" % msg)
    return 1
