# -*- coding: utf-8 -*-
"""PROOF TZ-14 — the page is stamped with the measurement\'s date, not a typed one

Run it against the code on disk:      python proof_TZ-14.py
Run it against the pre-fix backup:    python proof_TZ-14.py <dir-with-the-old-modules>
It must FAIL on the old code and PASS on the new. That is the whole point of it.
"""
import os
import sys
import warnings

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import io
import re


def main():
    import night_sheet
    assert not re.match(r"^\d{4}-\d{2}-\d{2}$", str(night_sheet.STAMP)), (
        f"STAMP is a hardcoded date ({night_sheet.STAMP!r}) used in the title of a "
        f"page whose own promise is that no number on it is typed by hand.")
    fake = {"when": "2030-01-02T03:04:05", "poses": 4}
    night_sheet._read = lambda name: (fake if name == "godot-gate1.json" else None)
    night_sheet.sec_godot = lambda g, n: ""
    night_sheet.sec_alma = lambda n: ""
    night_sheet.sec_still = lambda n: ""
    if hasattr(night_sheet, "_painter_check"):
        night_sheet._painter_check = lambda *a: ""
    out = night_sheet.build()        # build() writes the page and returns its PATH
    html = io.open(out, encoding="utf-8").read()
    assert night_sheet.STAMP == "2030-01-02", (
        f"the sheet still stamps itself {night_sheet.STAMP!r} while the measurement "
        f"it is printing says 2030-01-02")
    assert "<title>TZELEM night 2030-01-02</title>" in html, (
        "the page title is not the measurement's date")
    print(f"PASS  {ROOT}")
    print(f"      measurement when=2030-01-02T03:04:05  ->  STAMP="
          f"{night_sheet.STAMP!r}")


if __name__ == "__main__":
    try:
        main()
    except BaseException as e:                                    # noqa: BLE001
        print(f"FAIL  {ROOT}\n      {type(e).__name__}: {e}")
        sys.exit(1)
    sys.exit(0)
