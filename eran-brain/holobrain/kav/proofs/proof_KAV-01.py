"""KAV-01 proof — the regression gate watches the denominator the project believes

Run: python proofs/proof_KAV-01.py old   -> must FAIL (exit 1)
     python proofs/proof_KAV-01.py new   -> must PASS (exit 0)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness


def check(organ):

    import ast, io
    src = io.open(os.path.join(organ, "tests", "test_joiner.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    wide_on, narrow_pins = [], []
    for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef)]:
        body = ast.dump(fn)
        skipped = any("skipif" in ast.dump(d) or "skip" == getattr(d, "attr", "")
                      for d in fn.decorator_list)
        if "measure_join_wide" in body:
            print(f"    wide test {fn.name}: skipped={skipped}")
            if not skipped:
                wide_on.append(fn.name)
        if "measure_join_narrow" in body:
            # "pinned" means: it asserts an accuracy EQUAL to a recorded number, i.e.
            # round(r["accuracy"][name], 4) == want. Reporting the table is fine.
            pins = any(getattr(c.func, "id", "") == "round" and "accuracy" in ast.dump(c)
                       for c in ast.walk(fn) if isinstance(c, ast.Call))
            print(f"    narrow test {fn.name}: pins exact accuracy={pins}")
            if pins:
                narrow_pins.append(fn.name)
    assert wide_on, ("no always-on test measures the WIDE 19-solid denominator — the "
                     "gate still pins the 3-shape number the project calls broken and "
                     "skips the one it says to believe")
    assert not narrow_pins, (f"the narrow 49-question gate is still pinned exactly by "
                             f"{narrow_pins}: any real improvement to joiner.fit moves "
                             f"FOLD_GROVE's narrow accuracy and FAILS the suite")
    print(f"    always-on wide tests: {wide_on}")


_harness.run(check)
