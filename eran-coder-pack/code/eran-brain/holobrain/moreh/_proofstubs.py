"""_proofstubs — the two eran2-only modules (school-v2/ruler.py and gesture.py) as stand-ins, so
moreh/ruler.py can be imported and driven on the PC without a mouth and without rendering anything.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

These stubs replace only the MOUTH and the VERIFIER. Everything under test — the argument handling, the
error accounting, the ceiling arithmetic, the fold-local lambda — is the real moreh/ruler.py code.
"""
import sys
import types

# letter, hebrew, place, manner, nasal, voiced, family, twin-of  (verbatim from school-v2/ruler.py)
FACTS = {
    "a":   ("alef", "א", "glottal", "vowel", 0, 1, "glottal", None),
    "aya": ("ayin", "ע", "glottal", "stop", 0, 0, "glottal", None),
    "ba":  ("bet", "ב", "lips", "stop", 0, 1, "lips", None),
    "va":  ("vet", "ב", "lips", "fricative", 0, 1, "lips", None),
    "ga":  ("gimel", "ג", "back", "stop", 0, 1, "back", None),
    "da":  ("dalet", "ד", "tip", "stop", 0, 1, "tip", None),
    "ha":  ("he", "ה", "glottal", "fricative", 0, 0, "glottal", None),
    "wa":  ("vav", "ו", "lips", "approximant", 0, 1, "lips", None),
    "za":  ("zayin", "ז", "tip", "fricative", 0, 1, "tip", None),
    "cha": ("chet", "ח", "back", "fricative", 0, 0, "glottal", None),
    "ta":  ("tet", "ט", "tip", "stop", 0, 0, "tip", None),
    "ya":  ("yod", "י", "palate", "approximant", 0, 1, "glottal", None),
    "ka":  ("kaf", "כ", "back", "stop", 0, 0, "back", None),
    "kha": ("khaf", "כ", "back", "fricative", 0, 0, "back", "cha"),
    "la":  ("lamed", "ל", "tip", "approximant", 0, 1, "tip", None),
    "ma":  ("mem", "מ", "lips", "nasal", 1, 1, "lips", None),
    "na":  ("nun", "נ", "tip", "nasal", 1, 1, "tip", None),
    "sa":  ("samekh", "ס", "tip", "fricative", 0, 0, "tip", None),
    "pa":  ("pe", "פ", "lips", "stop", 0, 0, "lips", None),
    "fa":  ("fe", "פ", "lips", "fricative", 0, 0, "lips", None),
    "tza": ("tsadi", "צ", "tip", "affricate", 0, 0, "tip", None),
    "qa":  ("qof", "ק", "back", "stop", 0, 0, "back", "ka"),
    "ra":  ("resh", "ר", "tip", "tap", 0, 1, "tip", None),
    "sha": ("shin", "ש", "palate", "fricative", 0, 0, "tip", None),
}


def install(verdict=False, fails=("stub verifier: nothing was rendered",)):
    """put the stand-ins in sys.modules under the names moreh/ruler.py imports them by"""
    v2 = types.ModuleType("ruler")
    v2.FACTS = FACTS
    v2.SYLS = list(FACTS)
    v2.judge = lambda syl, spec, seed=0: (verdict, list(fails), "", None)
    sys.modules["ruler"] = v2

    g = types.ModuleType("gesture")
    g.mouth2 = object()                      # "a mouth is present" -- nothing is ever rendered
    g.clean = lambda spec, report=False: ((dict(spec), []) if report else dict(spec))
    g.readable = lambda spec: {"stub": True}
    g.to_gesture = lambda spec: {"stub": True}
    g.render = lambda spec, seed=0, ports=False: None
    sys.modules["gesture"] = g
    return v2, g
