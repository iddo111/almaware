#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""refresh_live.py (eran1) -- keep the LIVE section of listen_server.py TRUE.

The page at :8807 says "LIVE ... refreshed as the search runs". On 2026-08-30 it
was serving twelve wavs dated 08-25 03:21 -- five days stale, no writer alive,
and the arms in their names (eran3-ba-4, eran4-ba-8) belong to a campaign that
no longer runs. A page that claims live and is not live is a broken window; the
stale twelve were moved to ~/eran-search-live-archive-20260825/, not deleted.

This pulls the CURRENT best of each throat-search worker from eran2 and writes
the sidecar label listen_server reads. Every number on the page is copied from
that worker's own best.json -- nothing is computed here, so the page cannot
drift from the search.

eran2 is reached by EXPLICIT IP on purpose: eran1's ~/.ssh/config still carries
the stale <lan-ip> for eran2 (the live address is .59, and eran2's own
config carries a stale .26 for eran1). Reported, not silently patched.
"""
import json
import os
import subprocess
import sys

ERAN2 = "eran2@<lan-ip>"
LIVE = os.path.expanduser("~/eran-search-live")
TMP = "/tmp/_live_pull"

# (remote dir, output stem, human prefix)
SOURCES = [
    ("throat-search-v4/run/v4-ba-cv-10", "LIVE-v4-seed10", "v4 seed10"),
    ("throat-search-v4/run/v4-ba-cv-13", "LIVE-v4-seed13", "v4 seed13"),
    ("throat-search-v4/run/v4-ba-cv-14", "LIVE-v4-seed14", "v4 seed14"),
    ("throat-search-v4/run/v4-ba-cv-11", "LIVE-v4-seed11", "v4 seed11"),
    ("throat-search-v4/run/v4-ba-cv-12", "LIVE-v4-seed12", "v4 seed12"),
    ("throat-search-v4/run/v4-control-ba-cv-10", "LIVE-v4-zz-control",
     "v4 CONTROL (no learning)"),
    ("throat-search-v3/run/ba-cv-0", "LIVE-v3-zz-old-cv0",
     "v3 cv-0 (the OLD one Iddo critiqued)"),
]


def label(prefix, b):
    near = {d["unit"]: d["wdist"] for d in b.get("nearest", [])}
    ba = near.get("ba")
    ma = near.get("ma")
    # Name the rival you actually measured. The first version printed
    # "ba-ma" while computing min over EVERY rival unit -- for ba-cv-0 that
    # is not ma, and the page showed +0.29 where the ma margin is +0.41.
    rival_u = min((u for u in near if u != "ba"), key=lambda u: near[u], default=None)
    gs = b.get("gate_stats", {})
    bits = [f"ERAN ba · {prefix}"]
    if ba is not None:
        bits.append(f"wdist {ba:.2f}")
        if ma is not None:
            bits.append(f"vs ma {ma - ba:+.2f}")
        if rival_u and rival_u != "ma":
            bits.append(f"nearest rival {rival_u} {near[rival_u] - ba:+.2f}")
    if "dip" in gs:
        bits.append(f"closure {gs['dip']:.3f}")
    if "core_s" in gs:
        bits.append(f"vowel {gs['core_s']:.3f}s")
    if not b.get("gate_pass", True):
        bits.append("GATES FAIL")
    return " · ".join(bits)


def main():
    os.makedirs(LIVE, exist_ok=True)
    os.makedirs(TMP, exist_ok=True)
    n = 0
    for rdir, stem, prefix in SOURCES:
        wav, js = f"{TMP}/{stem}.wav", f"{TMP}/{stem}.json"
        r = subprocess.run(
            ["scp", "-q", "-o", "ConnectTimeout=10", "-o", "BatchMode=yes",
             f"{ERAN2}:~/{rdir}/best.wav", f"{ERAN2}:~/{rdir}/best.json", TMP],
            capture_output=True)
        if r.returncode != 0:
            print(f"skip {stem}: {r.stderr.decode()[:120]}", file=sys.stderr)
            continue
        os.replace(f"{TMP}/best.wav", wav)
        os.replace(f"{TMP}/best.json", js)
        with open(js, encoding="utf-8") as f:
            b = json.load(f)
        with open(os.path.join(LIVE, f"{stem}.json"), "w", encoding="utf-8") as f:
            json.dump({"unit": label(prefix, b),
                       "source": f"eran2:~/{rdir}/best.json"}, f,
                      ensure_ascii=False, indent=1)
        os.replace(wav, os.path.join(LIVE, f"{stem}.wav"))
        n += 1
    print(f"refreshed {n}/{len(SOURCES)}")


if __name__ == "__main__":
    main()
