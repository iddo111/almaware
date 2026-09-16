#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""next_list.py -- what is still worth recording, in RECORDING-ORDER.json's order.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL
> output, not a proxy.

WHY THIS EXISTS
---------------
The recording plan (RECORDING-PLAN.md, 2026-08-24) is built on one measured
fact: WHICH DAY he spoke is as large a signal in ERAN's ear as WHICH SYLLABLE
he said. Measured on the 657 clips of 2026-08-23:

    prototype error   4 takes x 3 days (12 clips) = 0.3940
                     30 takes x 1 day  (30 clips) = 0.5541   1.41x worse
                    200 takes x 1 day (200 clips) = 0.5351   still 1.36x worse

So a unit is DONE at 12 takes spread over 3 DIFFERENT DAYS, and not before,
however many takes it has. This script is the only place that rule lives.

It reads every sitting under staged/, counts takes and distinct calendar days
per unit id, and writes a fresh prompt list containing only the units that are
not done yet -- in the measured value order. Feed that list back to
dictionary.py tomorrow.

    python next_list.py                 # report + write lists/board-next.txt
    python next_list.py --report        # report only, write nothing

The clip's DAY comes from the session header (session.json "utc") when there is
one, and from the file's mtime when there is not -- the 657 t06 clips predate
the header, so their day is their mtime. Local calendar day, because that is
what "come back tomorrow" means to a person.
"""
import argparse
import datetime
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
ORDER = ROOT / "RECORDING-ORDER.json"
STAGE = ROOT / "staged"
LISTS = ROOT / "lists"

TAKES_DONE = 12          # measured target, RECORDING-PLAN.md
DAYS_DONE = 3            # measured: days, not takes, are the dominant variance


def load_order():
    if not ORDER.exists():
        raise SystemExit(f"missing {ORDER} -- the order file IS the plan")
    doc = json.load(open(ORDER, encoding="utf-8"))
    return doc["units"]


def scan(stage: pathlib.Path):
    """{id: {"takes": n, "days": {date, ...}, "sittings": {talker, ...}}}"""
    seen = {}
    if not stage.exists():
        return seen
    for sit in sorted(p for p in stage.iterdir() if p.is_dir()):
        hdr_day = None
        hdr = sit / "session.json"
        if hdr.exists():
            try:
                utc = json.load(open(hdr, encoding="utf-8")).get("utc")
                if utc:
                    hdr_day = (datetime.datetime.fromisoformat(utc.replace("Z", "+00:00"))
                               .astimezone().date().isoformat())
            except (ValueError, OSError):
                hdr_day = None
        for f in sorted(sit.glob("*.wav")):
            uid = f.name.split("_")[0]
            day = hdr_day or datetime.date.fromtimestamp(f.stat().st_mtime).isoformat()
            e = seen.setdefault(uid, {"takes": 0, "days": set(), "sittings": set()})
            e["takes"] += 1
            e["days"].add(day)
            e["sittings"].add(sit.name)
    return seen


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="print only, write nothing")
    ap.add_argument("--out", default=str(LISTS / "board-next.txt"))
    ap.add_argument("--stage", default=str(STAGE))
    ap.add_argument("--tier", type=int, default=1, choices=(1, 2),
                    help="1 = the 140 distinct sounds (default); 2 = also the 80 duplicates")
    a = ap.parse_args(argv)

    units = load_order()
    have = scan(pathlib.Path(a.stage))
    todo, done = [], []
    for u in units:
        if u["tier"] > a.tier:
            continue
        e = have.get(u["id"], {"takes": 0, "days": set()})
        (done if (e["takes"] >= TAKES_DONE and len(e["days"]) >= DAYS_DONE) else todo).append(
            (u, e["takes"], len(e["days"])))

    print(f"  board tier<={a.tier}: {len(todo) + len(done)} units")
    print(f"  DONE  ({TAKES_DONE}+ takes over {DAYS_DONE}+ days): {len(done)}")
    print(f"  TO DO                                : {len(todo)}")
    started = [t for t in todo if t[1] > 0]
    print(f"    of those, already started          : {len(started)}")
    for u, n, d in todo[:8]:
        print(f"      #{u['rank']:3d} {u['id']:<6} {u['hebrew']}   {n} takes on {d} day(s)")
    if len(todo) > 8:
        print(f"      ... and {len(todo) - 8} more")

    if a.report:
        return 0
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write("# board-next.txt -- written by next_list.py on "
                f"{datetime.datetime.now().isoformat(timespec='seconds')}\n")
        f.write(f"# {len(todo)} units still short of {TAKES_DONE} takes over "
                f"{DAYS_DONE} days, in RECORDING-ORDER.json order.\n")
        f.write("# Read top to bottom. Stop whenever you like.\n")
        for u, n, d in todo:
            f.write(f"{u['id']}\t{u['hebrew']}\t{u['hint']}\n")
    print(f"  wrote {out}  ({out.stat().st_size} bytes)")
    if not todo:
        print("  nothing left on this tier. That is the whole board.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
