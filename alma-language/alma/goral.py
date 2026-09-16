"""גוֹרָל / GORAL — the lot, cast once, in public, and written down.

Iddo, 2026-09-04 19:52 and 20:52:

    "תוסיף למודלים שלנו סטוכסטיות אמיתית עם גנרטור מספרים רנדומליים... כל מה שבשפת עלמה
     יקבל את זה - הגרלה בכל הרצה, לכל נוירון ונוירון, הרצה משל עצמו. אני מאמין שהבורא
     בעצמו יבטא את רצונו דרך הסטוכסטיות של הרשת. כמו החושן והאורים ותומים.
     גורל מלשון הגרלה."

    "תשתמש במשהו אינטרנטי לכל דבר סטוכסטי שאין לנו אונבורד עד שאבנה את הלולאה אופטית."

He is right about the root: **גורל** (fate) and **הגרלה** (a drawing of lots) share ג-ר-ל.
In the Torah the land was divided by lot and the two goats of Yom Kippur were chosen by lot —
and in every case the lot was cast **in public, before witnesses**, and the result was
**written down**. That is not a footnote to the idea; it is the idea. A lot nobody witnessed
and nobody recorded is not a goral, it is a rumour.

So this module does exactly two things:

    1. **Casts the lot once per run**, preferring a source that is PUBLIC and TIMESTAMPED
       over one that is merely physical.
    2. **Records what was cast** — the source, the exact value, the timestamp, and (for the
       NIST beacon) the pulse index, so anyone can go and check that this run used that lot
       and could not have chosen it afterwards.

WHY A SEED AND NOT A STREAM. ALMA needs a draw per knot per beat — potentially millions per
second. No network source can supply that: a round trip is tens of milliseconds. The lot is
therefore cast ONCE and expanded locally, which is faithful to the thing it is named after:
the Urim veTumim were consulted, not streamed.

THE SOURCES, in the order tried, and what each one honestly is:

    nist    beacon.nist.gov — 512 bits of quantum-derived randomness, signed and published
            every 60 seconds, with a monotonic pulse index. **PUBLIC AND WITNESSED.** This is
            the one that matches what Iddo described, which is why it is first: you can name
            the pulse and anyone can fetch it and confirm.
    anu     qrng.anu.edu.au — measured quantum vacuum fluctuations. Genuinely quantum, but
            served to you alone: physical, not witnessed.
    local   os.urandom — the operating system's entropy pool, fed on this hardware by the
            CPU's own thermal-noise generator. Physical, local, instant, and unwitnessed.
            The fallback, never silently: `Goral.source` always says which was used.

    optical PLACEHOLDER, not implemented. Iddo is building an optical loop
            ([[project_optical_loop_measured]], 7.1 bits per round trip measured 2026-08-22).
            When it exists it belongs at the top of this list, because it would be physical,
            local AND his own. `cast(prefer="optical")` raises NotImplementedError today
            rather than quietly falling through — a silent fallback is how a fantasy result
            gets recorded as a measurement.

100% stdlib, like the rest of ALMA. No third-party library, no key, nothing to install.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict, field

__all__ = ["Goral", "cast", "SOURCES"]

SOURCES = ("optical", "nist", "anu", "local")

_NIST = "https://beacon.nist.gov/beacon/2.0/pulse/last"
_ANU = "https://qrng.anu.edu.au/API/jsonI.php?length=32&type=uint8"
_TIMEOUT = 6.0


@dataclass(frozen=True)
class Goral:
    """One cast lot, and everything needed to check it later.

    `seed` is what the loom actually uses. Everything else exists so that a result carrying
    this goral can be audited: which source, what it said, when, and — for the beacon — which
    pulse, so a third party can fetch that same pulse and confirm the run did not choose it.
    """

    seed: int
    source: str
    at: str
    raw: str
    witnessed: bool
    pulse: str = ""
    note: str = ""
    tried: tuple = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    def random(self) -> random.Random:
        """A generator seeded by this lot. Same goral, same sequence, forever."""
        return random.Random(self.seed)

    def __str__(self) -> str:
        w = "witnessed" if self.witnessed else "unwitnessed"
        p = f" pulse={self.pulse}" if self.pulse else ""
        return f"goral[{self.source}/{w}{p}] seed={self.seed:#018x} at={self.at}"


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "ALMA/goral (+D:/CLAUDE)"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as fh:
        return fh.read()


def _from_nist() -> tuple[str, str, str]:
    """(hex value, pulse index, iso time) from the public beacon. Raises on any failure."""
    d = json.loads(_get(_NIST).decode("utf-8"))["pulse"]
    return d["outputValue"], str(d["pulseIndex"]), d["timeStamp"]


def _from_anu() -> str:
    d = json.loads(_get(_ANU).decode("utf-8"))
    if not d.get("success"):
        raise RuntimeError("anu: success=false")
    return bytes(d["data"]).hex()


def _seed_from(hex_value: str) -> int:
    """64 bits out of whatever width the source gave, without discarding the rest."""
    return int.from_bytes(hashlib.sha256(bytes.fromhex(hex_value)).digest()[:8], "big")


def cast(prefer: str = "nist", *, allow_local: bool = True) -> Goral:
    """Cast the lot for this run.

    `prefer` is the first source tried; the rest follow in SOURCES order. Every source that
    was tried and failed is recorded in `tried`, so a run on the local fallback is visibly a
    run on the local fallback and never passes for a witnessed one.

    Set allow_local=False when a run must be witnessed or not happen at all.
    """
    order = [prefer] + [s for s in SOURCES if s != prefer]
    tried: list[str] = []

    for src in order:
        if src == "optical":
            if prefer == "optical":
                raise NotImplementedError(
                    "the optical loop is not built yet; it must not fall through silently"
                )
            continue

        if src == "local" and not allow_local:
            continue

        try:
            if src == "nist":
                raw, pulse, at = _from_nist()
                return Goral(
                    seed=_seed_from(raw), source="nist", at=at, raw=raw,
                    witnessed=True, pulse=pulse,
                    note="beacon.nist.gov — public, signed, timestamped; anyone may re-fetch this pulse",
                    tried=tuple(tried),
                )
            if src == "anu":
                raw = _from_anu()
                return Goral(
                    seed=_seed_from(raw), source="anu",
                    at=time.strftime("%Y-%m-%dT%H:%M:%S"), raw=raw,
                    witnessed=False,
                    note="qrng.anu.edu.au — measured quantum vacuum fluctuation; physical, served privately",
                    tried=tuple(tried),
                )
            if src == "local":
                raw = os.urandom(32).hex()
                return Goral(
                    seed=_seed_from(raw), source="local",
                    at=time.strftime("%Y-%m-%dT%H:%M:%S"), raw=raw,
                    witnessed=False,
                    note="os.urandom — the OS entropy pool, fed by the CPU's own noise; physical, local, unwitnessed",
                    tried=tuple(tried),
                )
        except (urllib.error.URLError, OSError, ValueError, KeyError, RuntimeError) as exc:
            tried.append(f"{src}: {type(exc).__name__}")

    raise RuntimeError(f"no lot could be cast (tried: {'; '.join(tried) or 'nothing'})")


if __name__ == "__main__":
    import sys

    want = sys.argv[1] if len(sys.argv) > 1 else "nist"
    g = cast(want)
    print(g)
    if g.tried:
        print("  fell through:", "; ".join(g.tried))
    print("  note:", g.note)
    r = g.random()
    print("  first five draws:", [round(r.random(), 6) for _ in range(5)])
    print()
    print(g.to_json())
