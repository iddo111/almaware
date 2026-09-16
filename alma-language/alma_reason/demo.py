# -*- coding: utf-8 -*-
"""הדגמה — a שקלא וטריא you can watch, beat by beat.

    python -m alma_reason.demo

Nothing here is trained. These weights are random. The point of this file is
not accuracy — it is that the FORM runs: two seats, a חזקה each, six rounds of
קושיא and תירוץ, a gate that shuts when a standing runs out, and one מסקנה
line at the end. Whether it is RIGHT is `train.py`'s question, and RESULTS.md
answers it with numbers.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from .encoding import (encode_machloket, encode_syllogism,          # noqa: E402
                       machloket_feature_names,
                       syllogism_feature_names)
from .machloket import corpus as machloket_corpus                   # noqa: E402
from .syllogism import Syllogism                                    # noqa: E402
from .weave import trace                                            # noqa: E402

BAR = "─" * 74


def main() -> int:
    print(BAR)
    print("שקלא וטריא בשפת עלמה — הצורה היא המבנה, לא ההנחיה")
    print("The Talmudic give-and-take as an ALMA weave: knots, threads, sparks, beats.")
    print(BAR)
    print()

    names = syllogism_feature_names("raw")

    print("א. סילוגיזם תקף — BARBARA (כל M הוא P; כל S הוא M; לכן כל S הוא P)")
    print("   מתרץ: המסקנה מתחייבת.   מקשן: יש פירכא.")
    print()
    print(trace(encode_syllogism(Syllogism(1, "AAA"), "raw"), names, seed=1))
    print()
    print(BAR)
    print()

    print("ב. אותו מצב-רוח בדיוק, אבל בתמונה השנייה — AAA-2, ואמצע בלתי-מחולק.")
    print("   הפירכא כאן אמיתית: \"כל P הוא M; כל S הוא M\" אינו מחייב דבר.")
    print()
    print(trace(encode_syllogism(Syllogism(2, "AAA"), "raw"), names, seed=1))
    print()
    print(BAR)
    print()

    mnames = machloket_feature_names(machloket_corpus())
    m = next(x for x in machloket_corpus() if x.id == "shabbat-hanukkah")
    arg = encode_machloket(m, swap=False)
    print("ג. מחלוקת אמיתית — נר חנוכה, שבת כא ע\"ב")
    print(f"   מושב א׳ ({m.seat_a}): {m.claim_a}")
    print(f"   מושב ב׳ ({m.seat_b}): {m.claim_b}")
    print(f"   הפסק הנמסר: הלכה כ{m.seat_a if m.psak == 'A' else m.seat_b} "
          f"— {m.psak_rule}")
    print()
    print(trace(arg, mnames, seed=1))
    print()
    print(BAR)
    print("⚠ המשקלים כאן אקראיים ולא אומנו. מי שמנצח כאן אינו ראיה לכלום —")
    print("  הראיה היא שהצורה רצה: חזקה, סבבים, קושיא, תירוץ, דחייה, מסקנה.")
    print("⚠ These weights are random and untrained. Who wins here proves nothing;")
    print("  what it shows is that the FORM runs end to end. Numbers: RESULTS.md.")
    print(BAR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
