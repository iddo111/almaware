#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""brain.py -- the one door into the three-level second brain. / הדלת האחת.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

לזכרה של עלמה ז"ל.

THREE LEVELS (Iddo, 2026-09-05 16:32)
  project   a brain per PROJECT   -- collective, published to the council, read by QUORUM
  model     a brain per MODEL     -- private: ERAN, MIKO, WINSTON, DARWISH, the coder
  welder    a brain for the WELDER -- the master modeler, the thing that connects models

One shape for all three: an append-only JSONL of
  ts, author, scope, id, kind, text, refs[], outcome, provenance, seq, sha

APPEND-ONLY IS THE POINT. A lesson can be superseded, never quietly deleted. The
2026-09-03 corpus fraud survived a month because the record could be, and was,
overwritten in place. `brain.py verify` recomputes every sha and seq, so a
rewritten line is detectable rather than merely deplored.

PROVENANCE IS MANDATORY. The Master Modeler's own 2026-09-05 report found
`food/train` sitting in the tree with no record of where it came from -- "which
is why the TTS fraud survived a month". write() refuses an entry without it.

FAIL-CLOSED BY CONSTRUCTION. `propose` records a wanted door and returns
"pending". There is no installer in this codebase -- see proposals.install(),
which exists only to raise. A door is wired by a human, by hand, or not at all.
Iddo's 11th commission, this morning: ~100 written laws against 2 executable
gates; the advisory gate "was never once exercised in six months". This is the
mechanical kind.

  python brain.py write model eran --author eran --kind learned --source "sitting-4" "…"
  python brain.py read  project tzelem --query depth -n 10
  python brain.py doors
  python brain.py propose --proposer eran --name kav-mesh --why "…" --spec-json '{}'
  python brain.py pending
  python brain.py decide p-abc123 approved --by iddo --note "…"
  python brain.py verify model eran
  python brain.py prior-art r-d8df4af504 --project tzelem
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import bridge  # noqa: E402
import doors as doors_mod  # noqa: E402
import proposals  # noqa: E402
import store  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _out(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=1))


def main(argv: list | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="brain.py", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("write", help="record a lesson (provenance is mandatory)")
    w.add_argument("scope", choices=list(store.SCOPES))
    w.add_argument("id")
    w.add_argument("text")
    w.add_argument("--author", required=True)
    w.add_argument("--kind", required=True, choices=list(store.KINDS))
    w.add_argument("--source", required=True, help="provenance: where this came from")
    w.add_argument("--ref", action="append", default=[])
    w.add_argument("--outcome", default="")
    w.add_argument("--no-publish", action="store_true", help="do not tell the council")

    r = sub.add_parser("read", help="retrieve before acting")
    r.add_argument("scope", choices=list(store.SCOPES))
    r.add_argument("id")
    r.add_argument("--query", default="")
    r.add_argument("-n", type=int, default=20)
    r.add_argument("--kind", action="append", default=None, choices=list(store.KINDS))

    sub.add_parser("list", help="which brains exist on disk")

    s = sub.add_parser("stats", help="counts for one brain")
    s.add_argument("scope", choices=list(store.SCOPES))
    s.add_argument("id")

    v = sub.add_parser("verify", help="recompute every sha and seq -- the tamper check")
    v.add_argument("scope", choices=list(store.SCOPES))
    v.add_argument("id")

    d = sub.add_parser("doors", help="what tools do I have RIGHT NOW (probed, not declared)")
    d.add_argument("--no-stdio", action="store_true")
    d.add_argument("--no-ports", action="store_true")
    d.add_argument("--no-skills", action="store_true")

    p = sub.add_parser("propose", help="propose a new door -- ALWAYS pending, never installed")
    p.add_argument("--proposer", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--why", required=True)
    p.add_argument("--spec-json", default="{}")

    pend = sub.add_parser("pending", help="proposals awaiting a human")
    pend.add_argument("--status", default="pending",
                      choices=["pending", "approved", "rejected", "all"])

    dec = sub.add_parser("decide", help="a HUMAN approves or rejects a proposal")
    dec.add_argument("pid")
    dec.add_argument("decision", choices=["approved", "rejected"])
    dec.add_argument("--by", required=True)
    dec.add_argument("--note", default="")

    pa = sub.add_parser("prior-art", help="put a project's prior art into a QUORUM room")
    pa.add_argument("room_id")
    pa.add_argument("--project", default="")
    pa.add_argument("-n", type=int, default=8)
    pa.add_argument("--query", default="")

    a = ap.parse_args(argv)

    if a.cmd == "write":
        prov = {"source": a.source}
        if a.no_publish:
            _out(store.write(a.scope, a.id, a.author, a.kind, a.text,
                             refs=a.ref, outcome=a.outcome, provenance=prov))
        else:
            _out(bridge.write_and_publish(a.scope, a.id, a.author, a.kind, a.text,
                                          refs=a.ref, outcome=a.outcome, provenance=prov))
    elif a.cmd == "read":
        _out(store.read(a.scope, a.id, query=a.query, n=a.n, kinds=a.kind))
    elif a.cmd == "list":
        _out(store.list_brains())
    elif a.cmd == "stats":
        _out(store.stats(a.scope, a.id))
    elif a.cmd == "verify":
        res = store.verify(a.scope, a.id)
        _out(res)
        return 0 if res.get("ok") else 1
    elif a.cmd == "doors":
        _out(doors_mod.doors(stdio=not a.no_stdio, include_ports=not a.no_ports,
                             include_skills=not a.no_skills))
    elif a.cmd == "propose":
        try:
            spec = json.loads(a.spec_json)
        except ValueError as exc:
            print("--spec-json is not JSON: %s" % exc, file=sys.stderr)
            return 2
        _out(proposals.propose(a.proposer, a.name, a.why, spec))
    elif a.cmd == "pending":
        _out(proposals.list_proposals(None if a.status == "all" else a.status))
    elif a.cmd == "decide":
        _out(proposals.decide(a.pid, a.decision, a.by, note=a.note))
    elif a.cmd == "prior-art":
        res = bridge.prior_art(a.room_id, a.project, n=a.n, query=a.query)
        _out(res)
        return 0 if res.get("ok") else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
