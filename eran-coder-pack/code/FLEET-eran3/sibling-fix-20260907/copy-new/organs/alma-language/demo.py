"""ALMA Language v0.1 — demo. Runs three real weaves and checks answers.

    python demo.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from alma import Loom, from_json, parse_voice, to_voice  # noqa: E402

HERE = Path(__file__).parent
EX = HERE / "examples"


def banner(title: str) -> None:
    print()
    print("=" * 62)
    print(title)
    print("=" * 62)


def fmt(v: float) -> str:
    return f"{v:g}"


def main() -> None:
    loom = Loom()
    print("ALMA Language v0.1 -- a weave of knots. You address knots,")
    print("never registers. Three weaves follow; each checks itself.")

    # ------------------------------------------------ 1. heat (voice DSL)
    banner("1. heat -- C->F. Arithmetic lives in the connections.")
    heat = parse_voice((EX / "heat.voice").read_text(encoding="utf-8"))
    print("Spoken transcript (this text IS the program):")
    print("  " + "\n  ".join(to_voice(heat).splitlines()))
    r = loom.run(heat)
    print("Fringe 'show':", [(b, fmt(v)) for b, v in r.fringes["show"]])
    got = r.fringe("show")
    want = [212.0, 32.0, 98.6]
    assert len(got) == len(want) and all(
        abs(g - w) < 1e-9 for g, w in zip(got, want)), got
    print("OK  100C->212F, 0C->32F, 37C->98.6F "
          "(the strand multiplied, the bias added -- no code did)")

    # ------------------------------------------- 2. fib (JSON, VR format)
    banner("2. fib -- one knot, one thread, two strands = Fibonacci.")
    fib = from_json((EX / "fib.json").read_text(encoding="utf-8"))
    print("Loaded from examples/fib.json (the format a VR editor emits).")
    print("The self-thread has strands (w1,d1) and (w1,d2): every value")
    print("echoes back once after 1 beat and once after 2. That's all.")
    r = loom.run(fib)
    vals = [int(v) for v in r.fringe("show")]
    print("Fringe 'show':", vals)
    assert vals == [1, 1, 2, 3, 5, 8, 13, 21, 34], vals
    print("OK  Fibonacci, born from two strand delays. In VR: one knot")
    print("    holding two loops of rope, one loop visibly longer.")

    # -------------------------------------- 3. council (rise integration)
    banner("3. council -- speaks only when evidence crosses the line.")
    council = parse_voice((EX / "council.voice").read_text(encoding="utf-8"))
    print("Trigger 'rise 2': faint sparks wait in the tray across beats;")
    print("the knot fires only when their sum reaches 2.")
    r = loom.run(council)
    print("Fires:", [(f.beat, f.knot, fmt(f.spoke)) for f in r.fires])
    print("Fringe 'verdict':", [(b, fmt(v)) for b, v in r.fringes["verdict"]])
    got = r.fringe("verdict")
    assert len(got) == 1 and abs(got[0] - 2.3) < 1e-9, got
    print("OK  0.9+0.8+0.6 gathered over 3 beats -> spoke 2.3 once;")
    print("    the lone 0.5 at beat 6 never crossed the line: silence.")

    print()
    print("All three weaves ran and self-checked. The loom is real.")


if __name__ == "__main__":
    main()
