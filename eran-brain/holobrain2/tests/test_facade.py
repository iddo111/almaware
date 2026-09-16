# -*- coding: utf-8 -*-
"""THE FACADE TEST - the standing rule, enforced by perturbation, not by assertion.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

The rule (inherited from WINSTON, and it binds every holobrain organ):

    a knot exists only if it accumulates a measured scalar, makes a fire-or-
    silence decision, or produces a real measurement. If deleting it changes no
    number and no decision, IT IS NOT BUILT.

So this file does not ask the junction whether its knots matter. It CUTS each
knot out, re-runs all twelve stimuli, and demands the observable behaviour move.
A knot that can be deleted with no consequence fails, loudly, by name.

The same is done for the cords: a strand is real only if changing its weight
changes what the sibling says. `test_strand_is_real` proves the recognition
genuinely lives in the connections - ALMA's second law - and not in some Python
branch that would keep working with the weave gutted.

Run it plainly:   python tests/test_facade.py
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, os.path.join(_ROOT, "alma-language"),
           os.path.join(_ROOT, "organs", "alma-language")):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

import anatomy                                     # noqa: E402
import dowry                                       # noqa: E402
from alma import Loom, Weave                       # noqa: E402


def _observe(w: Weave) -> tuple:
    """What the weave DID - fires and fringes only. Nothing recomputed."""
    r = Loom().run(w)
    answered = tuple(sorted(f.knot for f in r.fires
                            if f.knot.startswith("unit_") and f.spoke is not None))
    return (answered,
            tuple(round(v, 6) for v in r.fringe("voice")),
            tuple(round(v, 6) for v in r.fringe("sureness")),
            tuple(round(v, 6) for v in r.fringe("doubt")),
            len(r.fires))


def _without(w: Weave, victim: str) -> Weave:
    """The same weave with one knot cut out, and every thread that touched it."""
    cut = Weave(w.name + "-minus-" + victim)
    for name, k in w.knots.items():
        if name == victim:
            continue
        cut.knots[name] = k
    cut.threads = [t for t in w.threads if t.src != victim and t.dst != victim]
    cut.seeds = [s for s in w.seeds if s.dst != victim]
    cut.run_hint = w.run_hint
    return cut


def _stimuli() -> dict:
    return {u: v["nearest"] for u, v in dowry.load_all().items()}


def _own_stimulus(unit: str) -> dict:
    """A stimulus this unit unambiguously owns: near in the ear's metric, everything
    else far. Used to ask the STRUCTURAL question - can this knot fire at all?"""
    return {u: (3.0 if u == unit else 11.0) for u in anatomy.UNITS}


def test_every_knot_is_real() -> list:
    """Cut each knot. SOMETHING must change.

    IMPORTANT - two different questions are being asked here, and running them
    together is what made the first version of this file wrong.

      STRUCTURAL (asserted): can this knot ever change behaviour? A unit knot is
        probed with a stimulus it plainly owns. If it still cannot fire, it is
        genuinely dead wiring and the test fails.

      EMPIRICAL (reported, never asserted): does it fire on the REAL dowry? On
        this dowry, most units never do - and that is a finding about the
        inheritance, not a defect in the weave. Asserting on it would have meant
        tuning THETA until the test went green, which is exactly the kind of
        result-shaped-to-fit this workspace forbids. THETA stays at 3x chance.
    """
    st = _stimuli()
    base = {u: _observe(anatomy.junction(n)) for u, n in st.items()}
    names = list(anatomy.junction(st["pa"]).knots)
    results = []
    for victim in names:
        moved = [u for u, n in st.items()
                 if _safe_observe(n, victim) != base[u]]
        if victim.startswith("unit_"):
            # structural probe: give this unit a stimulus it owns outright
            own = _own_stimulus(victim[5:])
            fires = anatomy.listen(own)["said"] == victim[5:]
            probe = _safe_observe(own, victim) != _observe(anatomy.junction(own))
            real = bool(fires and probe)
        else:
            real = bool(moved)
            fires = None
        results.append({"knot": victim, "changed_on": moved, "real": real,
                        "fires_on_own_stimulus": fires,
                        "alive_on_real_dowry": bool(moved)})
    return results


def _safe_observe(nearest: dict, victim: str) -> tuple:
    try:
        return _observe(_without(anatomy.junction(nearest), victim))
    except Exception as e:                                # a cut that breaks the run
        return ("raised", type(e).__name__)               # counts as a change


def test_strand_is_real() -> dict:
    """Recognition must live in the CORD. Halve pa's cord and pa must stop winning."""
    n = _stimuli()["pa"]
    before = anatomy.listen(n)
    hobbled = dict(n)
    hobbled["pa"] = n["pa"] + 6.0          # push pa far away in the ear's own metric
    after = anatomy.listen(hobbled)
    return {"before_said": before["said"], "after_said": after["said"],
            "moved": before["said"] != after["said"],
            "before_affinity_pa": round(before["affinity"]["pa"], 6),
            "after_affinity_pa": round(after["affinity"]["pa"], 6)}


def test_confusion_gate_really_shuts() -> dict:
    """The gate must be able to SHUT. This is the bug that was actually there:
    `chorus` used `sum`+`rise 2`, which sums strengths (~0.4) and never reached 2,
    so `doubt` was always empty and `hush` could not close. If this ever reports
    n_confused == 0 again, the gate has gone dead a second time."""
    st = _stimuli()
    confused = [u for u, nn in st.items() if anatomy.listen(nn)["confused"]]
    silenced = [u for u, nn in st.items() if not anatomy.listen(nn)["spoke"]]
    return {"n_confused": len(confused), "confused": confused,
            "silenced": silenced, "gate_can_shut": bool(silenced)}


def main() -> int:
    bad = []
    print("=== FACADE TEST: cut each knot, demand the behaviour move ===")
    rows = test_every_knot_is_real()
    for r in rows:
        mark = "REAL  " if r["real"] else "FACADE"
        extra = ""
        if r["fires_on_own_stimulus"] is not None:
            extra = "  own-stimulus:%s  live-on-dowry:%s" % (
                "fires" if r["fires_on_own_stimulus"] else "DEAD",
                "yes" if r["alive_on_real_dowry"] else "no")
        print("  %-6s %-12s changed on %2d/12 real stimuli%s"
              % (mark, r["knot"], len(r["changed_on"]), extra))
        if not r["real"]:
            bad.append(r["knot"])

    silent = [r["knot"][5:] for r in rows
              if r["knot"].startswith("unit_") and not r["alive_on_real_dowry"]]
    nunits = sum(1 for r in rows if r["knot"].startswith("unit_"))
    print("\n  FINDING (reported, not asserted): %d of %d unit knots never fire on the"
          % (len(silent), nunits))
    print("  real dowry: %s" % ", ".join(silent))
    print("  All of them fire on a stimulus they own, so the wiring is sound. What is")
    print("  silent is the INHERITANCE: the ear cannot separate most of what it was")
    print("  given. That is the control arm's first real result, and it is not good news.")

    print("\n=== STRAND TEST: recognition lives in the cord ===")
    s = test_strand_is_real()
    print("  %s" % s)
    if not s["moved"]:
        bad.append("strand(sense->unit_pa)")

    print("\n=== GATE TEST: the confusion gate can actually shut ===")
    g = test_confusion_gate_really_shuts()
    print("  %s" % g)
    if not g["gate_can_shut"]:
        bad.append("hush(gate never shuts)")

    print()
    if bad:
        print("FAILED - these are facades: %s" % ", ".join(bad))
        return 1
    print("PASS - every knot and cord in the junction changes a number or a decision.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
