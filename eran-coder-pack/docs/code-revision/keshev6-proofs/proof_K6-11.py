# -*- coding: utf-8 -*-
"""proof_K6-11 -- the fallback rejects request ids the primary accepts.

    python proof_K6-11.py <path-to-keshev/common/protocol.py> <path-to-keshev6_server.py>

RUN ON eran1. FAILS against protocol.py.bak-rev-20260906, PASSES against the
fixed protocol.py. Pure stdlib, nothing loaded, nothing bound.

Measured 2026-09-06: :8737 logged 210 x `code=400 err=missing or malformed
X-Request-Id` inside one hour (01h), in the same window as 209 `judge-*`
requests on :8739. :8739 accepted every one of them; :8737 -- the server the
live mic FALLS BACK TO -- refused all of them on the shape of the id alone.

Why that is the scar and not a nit: on 2026-09-05 a voice judge scored HTTP 400
as an empty transcript and reported a live, working model as 0/209. A 400 that
depends on which of the two interchangeable servers you happened to reach is
exactly the input that produces a fabricated zero.

keshev6's rule is the reference (its own docstring says it is looser ON PURPOSE,
"so a client change can never turn into a silent 400"). This proves the two
servers now answer the SAME question the same way.
"""
from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
from pathlib import Path

PROTO = Path(sys.argv[1]).resolve()
K6 = Path(sys.argv[2]).resolve()
FAILS: list[str] = []


def check(name: str, ok: bool, detail="") -> None:
    print("  %-64s %s%s" % (name, "PASS" if ok else "FAIL",
                            ("  <- " + str(detail)) if detail else ""))
    if not ok:
        FAILS.append(name)


def load(path: Path, name: str):
    """Copy to a .py name first: a backup called *.bak-rev-20260906 has no
    loader, and importlib would hand back spec=None with no useful message."""
    tmp = Path(tempfile.mkdtemp(prefix="k6proof11-")) / (name + ".py")
    shutil.copy2(path, tmp)
    lex = path.parent / "lexicon.py"        # keshev6_server imports it at module level
    if lex.exists():
        shutil.copy2(lex, tmp.parent / "lexicon.py")
    spec = importlib.util.spec_from_file_location(name, tmp)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


# (id, must_be_accepted, why)
CASES = [
    ("a1b2c3d4-1788700000000", True,
     "what keshev-next/decoder.py really mints for his live mic"),
    ("d59f9236-000666", True,
     "the mic-rebuild shape, seen on :8737 today"),
    ("judge-001", True,
     "the judge client :8739 accepted 209 of these; :8737 refused them"),
    ("pc-measure-3", True, "the 12:00 benchmark client"),
    ("pc-wavheader-test", True, "the 12:00 benchmark client"),
    ("A1B2C3D4-1788700000000", True, "an uppercase session id is not a fault"),
    ("", False, "empty is not an id"),
    ("ab", False, "too short to be an id"),
    ("x" * 129, False, "over the length cap"),
    ("ab\ncd-000001", False, "a newline must never reach a log line"),
    (None, False, "not a string at all"),
    (12345, False, "not a string at all"),
]


def main() -> int:
    proto = load(PROTO, "k6_proto_under_test")
    k6 = load(K6, "k6_server_under_test11")
    print("proof_K6-11\n  fallback :8737 %s\n  primary  :8739 %s" % (PROTO, K6))

    disagree = []
    for rid, want, why in CASES:
        a = bool(proto.valid_request_id(rid))
        b = bool(k6.valid_request_id(rid))
        if a != b:
            disagree.append("%r :8737=%s :8739=%s  (%s)" % (rid, a, b, why))
    check("the two servers agree on every id shape seen in the logs",
          not disagree, " | ".join(disagree[:3]))

    wrong = []
    for rid, want, why in CASES:
        if bool(proto.valid_request_id(rid)) != want:
            wrong.append("%r -> %s, wanted %s (%s)"
                         % (rid, proto.valid_request_id(rid), want, why))
    check(":8737 accepts what a real client sends and refuses what it must",
          not wrong, " | ".join(wrong[:3]))

    # the canonical minted shape must still be accepted -- widening acceptance
    # must not become widening what we MINT.
    canonical = proto.make_request_id("d59f9236", 666)
    check("the canonical minted id is still accepted",
          proto.valid_request_id(canonical), canonical)
    check("make_request_id still refuses a malformed session (minting is strict)",
          _raises(proto.make_request_id, "judge", 1))

    print("\nproof_K6-11: %s" % ("PASS" if not FAILS else
                                 "FAIL (%d) -> %s" % (len(FAILS), FAILS)))
    return 0 if not FAILS else 1


def _raises(fn, *a) -> bool:
    try:
        fn(*a)
        return False
    except Exception:
        return True


if __name__ == "__main__":
    raise SystemExit(main())
