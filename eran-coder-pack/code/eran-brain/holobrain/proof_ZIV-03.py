"""PROOF ZIV-03 -- the checkpoint carries its run, and close_loop LOADS it

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

    python proof_ZIV-03.py            # the LIVE files  -> must PASS (exit 0)
    python proof_ZIV-03.py --old      # the .bak-rev-20260906 backups -> must FAIL (exit 1)

The proof runs the CODE, not the live process: this chain has no service, no port and no
scheduler, so there is nothing running to disturb. Where the real corpus cannot be used
(eye.pt is a grayscale encoder against a colour corpus -- that IS ZIV-01) the run happens
inside proof_fixture.py's tiny matching world.
"""
import io
import os
import sys
import tempfile
import contextlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import proof_fixture as PF                                           # noqa: E402


def cap(fn, *a, **k):
    """Run fn, returning (result, exception, stdout)."""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            return fn(*a, **k), None, buf.getvalue()
    except BaseException as e:                                       # noqa: BLE001
        return None, e, buf.getvalue()


def main():
    print("== proof ZIV-03 against %s ==" % PF.which())

    tmp = os.path.join(tempfile.gettempdir(), "ziv03")
    p = PF.build(tmp, hand=False)
    z = PF.load(PF.src("zivug.py"), "z03z")
    rc, e, _ = cap(PF.run_main, z, PF.argv(p, "--no-hand"))
    if e is not None:
        return PF.bad("zivug did not finish: %r" % e)
    import torch
    pt = os.path.join(p["out"], "zivug.pt")
    ck = torch.load(pt, map_location="cpu")
    meta = ck.get("meta") or {}
    for k in ("steps", "seed", "holdout_take", "holdout_fonts", "best_step", "corpus"):
        if k not in meta:
            return PF.bad("the checkpoint says nothing about %r -- two files cannot "
                          "check they are describing the same model (keys: %s)"
                          % (k, sorted(ck.keys())))
    c = PF.load(PF.src("close_loop.py"), "z03c")
    if not hasattr(c, "load_zivug_heads"):
        return PF.bad("close_loop.py has no loader: state/zivug.pt is write-only and "
                      "close_loop retrains its own heads at a different step count")
    want = {"holdout_take": 5, "holdout_fonts": 1, "seed": 1933,
            "corpus": {"ear": PF.load_fp(p["ear"], "V"),
                       "letters": PF.load_fp(p["letters"], "X"),
                       "eye": PF.load_fp(p["eye"])}}
    heads, why = c.load_zivug_heads(pt, torch.device("cpu"), want)
    if heads is None:
        return PF.bad("the matching checkpoint was refused: %s" % why)
    bad_want = dict(want, seed=7)
    heads2, why2 = c.load_zivug_heads(pt, torch.device("cpu"), bad_want)
    if heads2 is not None:
        return PF.bad("a checkpoint from a DIFFERENT run was accepted silently")
    print(why)
    print("and refused when it does not match: %s" % why2)
    return PF.ok("zivug.pt carries steps/seed/holdout/corpus and close_loop loads it, "
                 "refusing a checkpoint from another run")

if __name__ == "__main__":
    raise SystemExit(main())
