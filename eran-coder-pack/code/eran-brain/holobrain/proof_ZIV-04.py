"""PROOF ZIV-04 -- the floor is measured on ALL takes, and --loto reports mean +- sd

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

    python proof_ZIV-04.py            # the LIVE files  -> must PASS (exit 0)
    python proof_ZIV-04.py --old      # the .bak-rev-20260906 backups -> must FAIL (exit 1)

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
    print("== proof ZIV-04 against %s ==" % PF.which())

    tmp = os.path.join(tempfile.gettempdir(), "ziv04")
    p = PF.build(tmp, hand=False)
    z = PF.load(PF.src("zivug.py"), "z04")
    rc, e, out = cap(PF.run_main, z, PF.argv(p, "--no-hand"))
    if e is not None:
        return PF.bad("zivug did not finish: %r" % e)
    if "ALL 6 takes" not in out:
        return PF.bad("only one held-out take was ever measured -- take 5 was hard-coded "
                      "and the six floors span 22.7 points")
    import json
    j = json.load(open(os.path.join(p["out"], "zivug.json")))
    fl = j.get("ear_floor_all_takes")
    if not fl or len(fl) != 6:
        return PF.bad("the six floors are not recorded: %r" % fl)
    exp = [0.9242, 0.8788, 0.6970, 0.7879, 0.7121, 0.8485]
    if max(abs(a - b) for a, b in zip(sorted(fl), sorted(exp))) > 2e-3:
        return PF.bad("the floors do not reproduce ruler-measured.json: %s" % fl)
    rc, e, out2 = cap(PF.run_main, z, PF.argv(p, "--no-hand", "--loto"))
    if e is not None:
        return PF.bad("--loto did not finish: %r" % e)
    lj = os.path.join(p["out"], "zivug-loto.json")
    if not os.path.exists(lj):
        return PF.bad("--loto wrote no aggregate")
    L = json.load(open(lj))
    if len(L["shape_to_sound"]) != 6 or "sd" not in L:
        return PF.bad("the aggregate is not six-fold with an sd: %r" % L)
    print([round(100 * x, 1) for x in fl], "-> sd %.4f" % L["sd"]["ear_floor"])
    return PF.ok("all six floors measured and reproducing ruler-measured.json, and "
                 "--loto reports every claim as mean +- sd over the six splits")

if __name__ == "__main__":
    raise SystemExit(main())
