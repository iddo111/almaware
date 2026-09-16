# -*- coding: utf-8 -*-
"""Acceptance test for the four-box panel. Run ON the box: python3 test_panel.py [port]"""
import json, sys, urllib.request

PORT = sys.argv[1] if len(sys.argv) > 1 else "8961"
Q = "מה הכלל של עידו לגבי המיקרופון והאוזניות, ולמה?"


def ask(mode):
    body = json.dumps({"q": Q, "k": 6, "mode": mode}).encode("utf-8")
    r = urllib.request.Request("http://127.0.0.1:%s/ask" % PORT, data=body,
                               headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=600))


for mode in ("fast", "best"):
    d = ask(mode)
    print("=" * 70)
    print("MODE: %s   %.1fs" % (mode, d["seconds"]))
    print("-" * 70)
    print(d["answer"])
    if d.get("panel"):
        print("-" * 70)
        for s in d["panel"]["steps"]:
            print("  %-7s %-24s %-10s %ss  %s" %
                  (s.get("role"), s.get("model"), s.get("verdict") or "",
                   s.get("seconds"), s.get("error") or ""))
        print("  flagged by BOTH auditors:", d["panel"]["flagged"])
    print()
