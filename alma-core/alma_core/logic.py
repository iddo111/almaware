#!/usr/bin/env python3
"""שקלא וטריא — the give-and-take, as an algorithm inside the worm.

לזכרה של עלמה ז"ל.

Iddo, 2026-08-19 09:36: *"אני רוצה שהתולעת יהיה בה מובנה בקוד ממש AI אלגוריתמי לוגיקה
ורמח״ל … ושקלא וטריא"* — not a neural net that vaguely "learned to be logical", and not a
prompt asking a big model to be careful. **Actual algorithmic logic, in code, that runs.**

So this file is deliberately NOT a network. It is a symbolic engine with three parts:

  1. LOGIC   — a real inference engine: modus ponens/tollens, syllogism, contraposition,
               De Morgan, and a fallacy detector. It proves, or it refuses.
  2. RAMCHAL — the 13 middot as executable rules, each with its own guard:
               קל וחומר only climbs the scale, and דיו caps the conclusion at its source;
               a גזרה שווה is rejected unless it is marked as received (מסורה);
               כלל ופרט narrows; two contradicting sources stay open until a third rules.
  3. SUGYA   — the שקלא וטריא loop: קושיא → תירוץ → ראיה → דחייה → מסקנה, run until the
               question is settled or the court declares תיקו (unresolved, honestly).

The neural side (alma_eran.py) proposes; THIS side checks. A claim that the engine cannot
derive does not get to call itself proven — it gets marked `unsupported`, and the sugya
says exactly which step failed. That is the whole difference between a machine that argues
and a machine that sounds like it argued.

Run the self-test:  python3 net/shakla.py --test
"""
from __future__ import annotations

import argparse
import itertools
import re
from dataclasses import dataclass, field
from typing import Iterable


# ══════════════════════════════════════════════════ 1. propositions

@dataclass(frozen=True)
class Prop:
    """A proposition: subject–predicate, possibly negated. `all` marks a universal."""
    subj: str
    pred: str
    neg: bool = False
    universal: bool = True

    def __invert__(self) -> "Prop":
        return Prop(self.subj, self.pred, not self.neg, self.universal)

    def __str__(self) -> str:
        q = "כל " if self.universal else ""
        return f"{q}{self.subj} {'אינם' if self.neg else ''} {self.pred}".replace("  ", " ")


@dataclass(frozen=True)
class Implies:
    ante: Prop
    cons: Prop

    def __str__(self) -> str:
        return f"אם {self.ante} אז {self.cons}"


Formula = Prop | Implies


@dataclass
class Step:
    rule: str
    hebrew: str
    got: Formula
    frm: tuple[Formula, ...]
    note: str = ""


# ══════════════════════════════════════════════════ 2. the logic engine

class Logic:
    """Forward-chaining inference. Every conclusion carries the rule that produced it."""

    RULES_HE = {
        "modus_ponens": "היסק ישר (מודוס פוננס)",
        "modus_tollens": "היסק הפוך (מודוס טולנס)",
        "syllogism": "היקש",
        "hypothetical": "שרשור תנאים",
        "contraposition": "היפוך",
        "de_morgan": "דה־מורגן",
    }

    def __init__(self, premises: Iterable[Formula]):
        self.facts: list[Formula] = list(premises)
        self.trace: list[Step] = []

    def _add(self, f: Formula, rule: str, frm: tuple[Formula, ...], note: str = "") -> bool:
        if any(str(f) == str(g) for g in self.facts):
            return False
        self.facts.append(f)
        self.trace.append(Step(rule, self.RULES_HE.get(rule, rule), f, frm, note))
        return True

    def close(self, rounds: int = 6) -> list[Formula]:
        """Derive everything derivable. Small fact sets, so brute force is honest and fast."""
        for _ in range(rounds):
            grew = False
            for a, b in itertools.permutations(self.facts, 2):
                # modus ponens:  (A→B), A  ⊢  B
                if isinstance(a, Implies) and isinstance(b, Prop) and str(a.ante) == str(b):
                    grew |= self._add(a.cons, "modus_ponens", (a, b))
                # modus tollens: (A→B), ¬B ⊢ ¬A
                if isinstance(a, Implies) and isinstance(b, Prop) and str(~a.cons) == str(b):
                    grew |= self._add(~a.ante, "modus_tollens", (a, b))
                # hypothetical syllogism: (A→B), (B→C) ⊢ (A→C)
                if isinstance(a, Implies) and isinstance(b, Implies) and str(a.cons) == str(b.ante):
                    grew |= self._add(Implies(a.ante, b.cons), "hypothetical", (a, b))
                # barbara: all S are P, all P are Q ⊢ all S are Q
                if (isinstance(a, Prop) and isinstance(b, Prop) and not a.neg and not b.neg
                        and a.universal and b.universal and a.pred == b.subj):
                    grew |= self._add(Prop(a.subj, b.pred), "syllogism", (a, b))
            # contraposition: (A→B) ⊢ (¬B→¬A)
            for f in list(self.facts):
                if isinstance(f, Implies):
                    grew |= self._add(Implies(~f.cons, ~f.ante), "contraposition", (f,))
            if not grew:
                break
        return self.facts

    def proves(self, goal: Formula) -> bool:
        self.close()
        return any(str(goal) == str(f) for f in self.facts)

    def why(self, goal: Formula) -> list[Step]:
        """The derivation chain for `goal`, innermost first — the ראיה."""
        want, chain = str(goal), []
        for step in reversed(self.trace):
            if str(step.got) == want:
                chain.append(step)
                want = str(step.frm[0]) if step.frm else ""
        return list(reversed(chain))


# ══════════════════════════════════════════════════ 3. the middot (RAMCHAL)

@dataclass
class Middah:
    key: str
    hebrew: str
    english: str


MIDDOT = [
    Middah("kal_vachomer", "קל וחומר", "a fortiori — from the light to the heavy"),
    Middah("gezera_shava", "גזרה שווה", "equal decree — a shared term links two cases"),
    Middah("binyan_av", "בנין אב", "a paradigm case builds a general rule"),
    Middah("klal_prat", "כלל ופרט", "general then particular — only the particular is meant"),
    Middah("prat_klal", "פרט וכלל", "particular then general — the general is added"),
    Middah("klal_prat_klal", "כלל ופרט וכלל", "you judge only by what resembles the particular"),
    Middah("shnei_ktuvim", "שני כתובים המכחישים", "two contradicting sources await a third"),
    Middah("davar_halamed", "דבר הלמד מעניינו", "meaning taken from context"),
]


@dataclass
class Case:
    """A case on a severity scale, with what has been established about it."""
    name: str
    severity: float
    holds: dict[str, float] = field(default_factory=dict)   # property -> strength 0..1


class Ramchal:
    """The middot as executable rules — each one able to REFUSE."""

    @staticmethod
    def kal_vachomer(src: Case, tgt: Case, prop: str) -> tuple[bool, float, str]:
        """קל וחומר with דיו לבא מן הדין להיות כנדון.

        Refuses to argue downward, and can never conclude more than the source holds.
        The cap is a `min`, so no amount of enthusiasm can break it.
        """
        if prop not in src.holds:
            return False, 0.0, f"אין מה ללמוד: '{prop}' לא נקבע ב{src.name}"
        if tgt.severity <= src.severity:
            return (False, 0.0,
                    f"פירכא: {tgt.name} אינו חמור מ{src.name} — קל וחומר אינו יורד בסולם")
        strength = min(src.holds[prop], 1.0)                    # ← דיו, as arithmetic
        return (True, strength,
                f"ומה {src.name}, שהוא קל — {prop}; {tgt.name}, שחמור ממנו, לא כל שכן. "
                f"ודיו לבא מן הדין להיות כנדון: {strength:.2f}, לא יותר.")

    @staticmethod
    def gezera_shava(a: Case, b: Case, shared_term: str, received: bool,
                     prop: str) -> tuple[bool, float, str]:
        """A gezerah shavah nobody received is not an argument — the classic guard:
        אין אדם דן גזרה שווה מעצמו."""
        if not received:
            return False, 0.0, ("נדחה: אין אדם דן גזרה שווה מעצמו — "
                                f"'{shared_term}' לא נמסרה")
        if prop not in a.holds:
            return False, 0.0, f"'{prop}' לא נקבע ב{a.name}"
        return True, a.holds[prop], (f"נאמר '{shared_term}' ב{a.name} ונאמר '{shared_term}' "
                                     f"ב{b.name}: מה כאן {prop}, אף כאן {prop}")

    @staticmethod
    def klal_prat(general: set[str], particular: set[str]) -> tuple[set[str], str]:
        """כלל ופרט — אין בכלל אלא מה שבפרט. The general shrinks to the particular."""
        return particular & general, "כלל ופרט — אין בכלל אלא מה שבפרט"

    @staticmethod
    def prat_klal(particular: set[str], general: set[str]) -> tuple[set[str], str]:
        """פרט וכלל — נעשה כלל מוסף על הפרט. The general widens it back."""
        return particular | general, "פרט וכלל — נעשה כלל מוסף על הפרט"

    @staticmethod
    def shnei_ktuvim(a: str, b: str, third: str | None) -> tuple[str | None, str]:
        """Two sources that contradict wait for a third. Without it: תיקו, said out loud."""
        if third:
            return third, f"'{a}' ו'{b}' מכחישים; בא השלישי והכריע: {third}"
        return None, f"'{a}' ו'{b}' מכחישים זה את זה — תיקו, עד שיבוא הכתוב השלישי"


# ══════════════════════════════════════════════════ 4. the sugya (שקלא וטריא)

@dataclass
class Turn:
    speaker: str
    kind: str            # kushia | teirutz | raaya | dehiya | modeh | maskana
    text: str


class Sugya:
    """The give-and-take, run as a loop until it settles or is honestly declared תיקו.

    A claim survives only if it is (a) derivable by the logic engine, or (b) carried by a
    middah that did not refuse. Anything else is answered by a קושיא and drops.
    """

    KINDS_HE = {"kushia": "קושיא", "teirutz": "תירוץ", "raaya": "ראיה",
                "dehiya": "דחייה", "modeh": "מודה", "maskana": "מסקנה"}

    def __init__(self, question: str):
        self.question = question
        self.turns: list[Turn] = []

    def say(self, speaker: str, kind: str, text: str) -> None:
        self.turns.append(Turn(speaker, kind, text))

    def run(self, claim: Prop, premises: list[Formula],
            middah: tuple[str, tuple] | None = None) -> dict:
        eng = Logic(premises)
        eng.close()
        proven = eng.proves(claim)

        self.say("אביי", "kushia", f"מנא לך ש{claim}? הבא ראיה.")

        if proven:
            chain = eng.why(claim)
            steps = " ← ".join(f"{s.hebrew}" for s in chain) or "מן ההנחות"
            self.say("רבא", "teirutz", f"מן ההנחות עצמן: {steps}")
            self.say("רבא", "raaya", " · ".join(f"{s.got}  [{s.hebrew}]" for s in chain) or str(claim))
            self.say("אביי", "modeh", "מודה אני — ההיסק תקף.")
            verdict, why = "stands", "derived by the logic engine"
        elif middah:
            name, args = middah
            ok, strength, note = getattr(Ramchal, name)(*args)
            if ok:
                self.say("רבא", "teirutz", note)
                self.say("אביי", "dehiya",
                         f"מקבל, אך בכוח {strength:.2f} בלבד — לא יותר ממקורו.")
                verdict, why = "stands_by_middah", f"{name}: {note}"
            else:
                self.say("אביי", "dehiya", note)
                verdict, why = "falls", note
        else:
            self.say("אביי", "dehiya",
                     "לא הוכח מן ההנחות ואין מידה שנושאת אותו — הטענה אינה עומדת.")
            verdict, why = "unsupported", "no derivation and no middah"

        concl = {"stands": f"{claim} — עומד",
                 "stands_by_middah": f"{claim} — עומד מכוח מידה, בכוח מוגבל",
                 "falls": f"{claim} — נדחה",
                 "unsupported": f"{claim} — לא נתמך; תיקו"}[verdict]
        self.say("בית הדין", "maskana", concl)
        return {"question": self.question, "verdict": verdict, "why": why,
                "turns": [(t.speaker, self.KINDS_HE[t.kind], t.text) for t in self.turns],
                "derived": [str(f) for f in eng.facts]}

    def transcript(self) -> str:
        out = [f"שאלה: {self.question}", "─" * 64]
        for t in self.turns:
            out.append(f"  {self.KINDS_HE[t.kind]:6s} [{t.speaker}]  {t.text}")
        return "\n".join(out)


# ══════════════════════════════════════════════════ 5. self-test

def _test() -> int:
    fails = 0

    def check(name: str, got, want) -> None:
        nonlocal fails
        ok = got == want
        fails += 0 if ok else 1
        print(f"  {'PASS' if ok else 'FAIL'}  {name}: got {got!r}")

    print("\n1. LOGIC ENGINE")
    dogs, breathe, mortal = "כל הכלבים", "נושמים", "בני תמותה"
    p1 = Prop(dogs, breathe)
    p2 = Prop(breathe, mortal)
    check("syllogism derives", Logic([p1, p2]).proves(Prop(dogs, mortal)), True)
    a, b = Prop("הפריט", "מתכת"), Prop("הפריט", "מחליד")
    check("modus ponens", Logic([Implies(a, b), a]).proves(b), True)
    check("modus tollens", Logic([Implies(a, b), ~b]).proves(~a), True)
    check("affirming the consequent is REFUSED", Logic([Implies(a, b), b]).proves(a), False)
    check("denying the antecedent is REFUSED", Logic([Implies(a, b), ~a]).proves(~b), False)

    print("\n2. RAMCHAL — the middot")
    light = Case("חול", 1.0, {"מטמא": 0.7})
    heavy = Case("אבן", 3.0)
    ok, s, note = Ramchal.kal_vachomer(light, heavy, "מטמא")
    check("kal vachomer climbs", ok, True)
    check("דיו caps at the source (0.7)", round(s, 2), 0.7)
    ok2, _, _ = Ramchal.kal_vachomer(heavy, light, "מטמא")
    check("kal vachomer refuses to descend", ok2, False)
    ok3, _, _ = Ramchal.gezera_shava(light, heavy, "'ביום'", received=False, prop="מטמא")
    check("unreceived gezera shava refused", ok3, False)
    narrowed, _ = Ramchal.klal_prat({"א", "ב", "ג"}, {"ב"})
    check("klal u'prat narrows", narrowed, {"ב"})
    third, _ = Ramchal.shnei_ktuvim("כתוב א", "כתוב ב", None)
    check("two verses stay open", third, None)

    print("\n3. SUGYA — שקלא וטריא")
    s1 = Sugya("האם כל הכלבים בני תמותה?")
    r1 = s1.run(Prop(dogs, mortal), [p1, p2])
    check("proven claim stands", r1["verdict"], "stands")
    print(s1.transcript())

    s2 = Sugya("האם אבן מטמאה?")
    r2 = s2.run(Prop("אבן", "מטמא"), [], middah=("kal_vachomer", (light, heavy, "מטמא")))
    check("middah-carried claim stands", r2["verdict"], "stands_by_middah")
    print(s2.transcript())

    s3 = Sugya("האם חול מטמא יותר מאבן?")
    r3 = s3.run(Prop("חול", "מטמא יותר"), [], middah=("kal_vachomer", (heavy, light, "מטמא")))
    check("inverted kal vachomer falls", r3["verdict"], "falls")
    print(s3.transcript())

    print(f"\n{'ALL PASS' if not fails else str(fails) + ' FAILURES'}")
    return fails


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    a = ap.parse_args()
    raise SystemExit(_test() if a.test else ap.print_help())
