# -*- coding: utf-8 -*-
"""PROOF TZ-13 — the per-resolution memory column is that resolution\'s own cost

Run it against the code on disk:      python proof_TZ-13.py
Run it against the pre-fix backup:    python proof_TZ-13.py <dir-with-the-old-modules>
It must FAIL on the old code and PASS on the new. That is the whole point of it.
"""
import os
import sys
import warnings

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

def main():
    import gate2
    rows = gate2.bench(n_strokes=400,
                       which=[("1080p", 1920, 1080), ("480p", 480, 270)])
    big, small = rows[0], rows[1]
    assert "row_peak_rss_mb" in small, (
        "the table still reports peak_wset, the peak over the WHOLE process "
        "lifetime, which is monotone — so every row silently carries every earlier "
        "row's peak and the table only reads correctly smallest-first.")
    assert small["row_peak_rss_mb"] < big["row_peak_rss_mb"], (
        f"480p is reported as costing {small['row_peak_rss_mb']:.1f} MB against "
        f"1080p's {big['row_peak_rss_mb']:.1f} MB")
    print(f"PASS  {ROOT}")
    print(f"      run 1080p FIRST, then 480p:")
    for r in rows:
        print(f"      {r['name']:>6}  own cost {r['row_peak_rss_mb']:7.1f} MB   "
              f"(process peak {r['process_peak_rss_mb']:7.1f} MB)")


if __name__ == "__main__":
    try:
        main()
    except BaseException as e:                                    # noqa: BLE001
        print(f"FAIL  {ROOT}\n      {type(e).__name__}: {e}")
        sys.exit(1)
    sys.exit(0)
