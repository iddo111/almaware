"""PROOF ZIV-05 -- MURPHY rules BEFORE the save, and a FOOLING ruling costs the run

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

    python proof_ZIV-05.py            # the LIVE files  -> must PASS (exit 0)
    python proof_ZIV-05.py --old      # the .bak-rev-20260906 backups -> must FAIL (exit 1)

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
    print("== proof ZIV-05 against %s ==" % PF.which())

    tmp = os.path.join(tempfile.gettempdir(), "ziv05")
    p = PF.build(tmp, hand=False)
    for f in ("zivug.pt", "zivug.json"):
        try:
            os.remove(os.path.join(p["out"], f))
        except OSError:
            pass
    z = PF.load(PF.src("zivug.py"), "z05")
    z.watch = lambda *a, **k: {"fooling": True, "score": 9.9, "spoke": ["fake_witness"],
                               "evidence": {}, "undeclared": []}
    rc, e, out = cap(PF.run_main, z, PF.argv(p, "--no-hand"))
    if e is not None:
        return PF.bad("zivug did not finish: %r" % e)
    clean = os.path.join(p["out"], "zivug.pt")
    suspect = os.path.join(p["out"], "SUSPECT", "zivug.pt")
    if rc == 0:
        return PF.bad("MURPHY ruled FOOLING and the run still exited 0 -- his verdict "
                      "costs nothing, and watch()'s return value is discarded")
    if os.path.exists(clean) or not os.path.exists(suspect):
        return PF.bad("a suspect checkpoint was written where a clean one goes "
                      "(clean=%s suspect=%s)" % (os.path.exists(clean),
                                                 os.path.exists(suspect)))
    import json
    j = json.load(open(os.path.join(p["out"], "zivug.json")))
    if not (j.get("murphy") or {}).get("zivug", {}).get("fooling"):
        return PF.bad("the ruling is not recorded in zivug.json: %r" % j.get("murphy"))
    print("exit %s, checkpoint quarantined, verdict recorded" % rc)
    return PF.ok("watch() is called before torch.save, its dict is captured, the "
                 "checkpoint is quarantined and the run exits non-zero")

if __name__ == "__main__":
    raise SystemExit(main())
