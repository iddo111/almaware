# -*- coding: utf-8 -*-
"""PROOF TZ-4 — every measurement can name the painter that made it

Run it against the code on disk:      python proof_TZ-4.py
Run it against the pre-fix backup:    python proof_TZ-4.py <dir-with-the-old-modules>
It must FAIL on the old code and PASS on the new. That is the whole point of it.
"""
import os
import sys
import warnings

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import canvas


def main():
    assert hasattr(canvas, "source_hashes"), (
        "canvas.py cannot name itself. freeze.py pins the RULER and nothing pinned "
        "the PAINTER, so canvas.py moved +511/-240 lines underneath every stored "
        "gate number without a single alarm.")
    h = canvas.source_hashes()
    assert set(h) >= {"render", "ownership", "footprint", "constants"}, h
    assert all(isinstance(v, str) and len(v) == 16 for v in h.values()), h

    import night_sheet
    assert hasattr(night_sheet, "_painter_check"), (
        "night_sheet.py will still print a number made by a painter that no longer "
        "exists")
    try:
        night_sheet._painter_check({"when": "2026-09-05T19:39:12",
                                    "painter": {"render": "0000000000000000"}})
    except SystemExit as e:
        print(f"PASS  {ROOT}")
        print(f"      painter = {h}")
        print(f"      night_sheet refuses a stale record: {str(e).splitlines()[0]}")
        return
    raise AssertionError("night_sheet printed a record whose painter is not this one")


if __name__ == "__main__":
    try:
        main()
    except BaseException as e:                                    # noqa: BLE001
        print(f"FAIL  {ROOT}\n      {type(e).__name__}: {e}")
        sys.exit(1)
    sys.exit(0)
