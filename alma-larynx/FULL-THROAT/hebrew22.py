# -*- coding: utf-8 -*-
"""hebrew22.py - what a mouth must physically HAVE to say all 22 Hebrew letters.

Iddo, 2026-08-30 03:51: "אני רוצה פה מלא כל 22 אותיות
אחהע גיכק דטלנת בומף זסשרץ"

That is the Sefer Yetzirah division into five places of articulation:
  אחהע  gutturals  - the throat
  גיכק  palatals   - the palate
  דטלנת linguals   - the tongue
  זסשרץ dentals    - the teeth
  בומף  labials    - the lips
4 + 4 + 5 + 5 + 4 = 22.

This file is the GAP ANALYSIS: for each letter, the organ that physically makes
it, and whether ERAN's current planned throat has that organ. It is deliberately
brutal - the answer is mostly no.

THE FINDING THAT MATTERS: ח and ע are PHARYNGEAL. Japanese, German and English
have no pharyngeals, so no talking robot in the published record was ever built
with a pharyngeal constrictor. For those two letters there is nothing to copy.
"""

# organ keys
FOLD_ADD = "fold adduct/abduct"   # slam the glottis shut, or hold it open for breath
PHARYNX = "PHARYNGEAL squeeze"    # constrict the throat above the larynx
T_BACK = "tongue back"            # body rises to velum/uvula
T_TIP = "tongue tip"              # tip to the alveolar ridge
LATERAL = "lateral channel"       # air around the SIDES of the tongue
GROOVE = "tongue groove + TEETH"  # the narrow jet that makes a sibilant hiss
LIPS = "lips"                     # close and release
TEETH_LIP = "lower lip to TEETH"  # labiodental
VELUM = "velum / NASAL branch"    # open the nose
TIMING = "closure-release TIMING"  # plosives and affricates

# what the currently planned throat actually has:
#   5 radial pinch stations on a soft tube, one tension servo, no tongue,
#   no teeth, no nasal branch, no pharyngeal station, no fold ad/abduction.
HAVE = {
    LIPS: "partial",   # the outermost pinch station can squeeze the tube shut
    T_BACK: "no", T_TIP: "no", LATERAL: "no", GROOVE: "no",
    TEETH_LIP: "no", VELUM: "no", PHARYNX: "no", FOLD_ADD: "no",
    TIMING: "partial",  # servos can be timed, but with no closure organ to time
}

GROUPS = [
    ("אחהע", "GUTTURAL", "the throat", [
        ("א", "alef",   "[ʔ] glottal stop",            [FOLD_ADD, TIMING]),
        ("ה", "he",     "[h] glottal fricative",       [FOLD_ADD]),
        ("ח", "het",    "[ħ] PHARYNGEAL fricative",    [PHARYNX]),
        ("ע", "ayin",   "[ʕ] PHARYNGEAL voiced",       [PHARYNX, FOLD_ADD]),
    ]),
    ("גיכק", "PALATAL", "the palate", [
        ("ג", "gimel",  "[g] velar plosive",           [T_BACK, TIMING]),
        ("י", "yod",    "[j] palatal approximant",     [T_BACK]),
        ("כ", "kaf",    "[k] / [χ] velar plos./fric.", [T_BACK, TIMING]),
        ("ק", "qof",    "[k] / [q] uvular plosive",    [T_BACK, TIMING]),
    ]),
    ("דטלנת", "LINGUAL", "the tongue", [
        ("ד", "dalet",  "[d] alveolar plosive",        [T_TIP, TIMING]),
        ("ט", "tet",    "[t] alveolar plosive",        [T_TIP, TIMING]),
        ("ל", "lamed",  "[l] lateral approximant",     [T_TIP, LATERAL]),
        ("נ", "nun",    "[n] alveolar NASAL",          [T_TIP, VELUM]),
        ("ת", "tav",    "[t] alveolar plosive",        [T_TIP, TIMING]),
    ]),
    ("זסשרץ", "DENTAL", "the teeth", [
        ("ז", "zayin",  "[z] voiced sibilant",         [GROOVE]),
        ("ס", "samekh", "[s] voiceless sibilant",      [GROOVE]),
        ("ש", "shin",   "[ʃ] postalveolar sibilant",   [GROOVE, T_TIP]),
        ("ר", "resh",   "[ʁ] uvular trill/approx.",    [T_BACK]),
        ("ץ", "tsadi",  "[ts] AFFRICATE",              [GROOVE, T_TIP, TIMING]),
    ]),
    ("בומף", "LABIAL", "the lips", [
        ("ב", "bet",    "[b] / [v]",                   [LIPS, TIMING, TEETH_LIP]),
        ("ו", "vav",    "[v] labiodental",             [TEETH_LIP]),
        ("מ", "mem",    "[m] bilabial NASAL",          [LIPS, VELUM]),
        ("פ", "pe",     "[p] / [f]",                   [LIPS, TIMING, TEETH_LIP]),
    ]),
]


def status(organs):
    """A letter is reachable only if EVERY organ it needs is present."""
    vals = [HAVE[o] for o in organs]
    if all(v == "yes" for v in vals):
        return "YES"
    if any(v == "no" for v in vals):
        return "NO"
    return "MAYBE"


def main():
    print("=" * 78)
    print("ERAN'S MOUTH vs THE 22 LETTERS - can he say them?")
    print("=" * 78)
    tally = {"YES": 0, "MAYBE": 0, "NO": 0}
    need = {}
    for letters, name, place, rows in GROUPS:
        print("\n%s  %s (%s)" % (letters, name, place))
        print("-" * 78)
        for ch, translit, ipa, organs in rows:
            st = status(organs)
            tally[st] += 1
            for o in organs:
                if HAVE[o] != "yes":
                    need.setdefault(o, []).append(ch)
            print("  %s  %-7s %-28s %-5s  needs: %s"
                  % (ch, translit, ipa, st, ", ".join(organs)))
    print("\n" + "=" * 78)
    print("SCORE:  YES %d   MAYBE %d   NO %d   (of 22)"
          % (tally["YES"], tally["MAYBE"], tally["NO"]))
    print("=" * 78)
    print("\nORGANS THAT MUST BE BUILT, ranked by how many letters they unlock:")
    for organ, chars in sorted(need.items(), key=lambda kv: -len(kv[1])):
        print("  %-24s unlocks %2d letters:  %s"
              % (organ, len(chars), " ".join(chars)))
    print("\nNOTE: ח and ע need a PHARYNGEAL constrictor. Japanese, German and")
    print("English have no pharyngeals - so no talking robot in the published")
    print("record has ever been built with one. For those two letters there is")
    print("nothing to copy. That part ERAN would be the first to build.")


if __name__ == "__main__":
    main()


def build_order():
    """Greedy: at each step add the ONE organ that turns the most letters
    from NO to YES. This is the actual build order - it accounts for the fact
    that TIMING alone unlocks nothing, because a plosive needs an organ to
    close before there is anything to time."""
    all_letters = [(ch, organs) for _, _, _, rows in GROUPS for ch, _, _, organs in rows]
    have = set()
    done = set()
    steps = []
    pool = sorted({o for _, organs in all_letters for o in organs})
    while len(done) < len(all_letters):
        best, best_new = None, []
        for cand in pool:
            if cand in have:
                continue
            trial = have | {cand}
            new = [ch for ch, organs in all_letters
                   if ch not in done and set(organs) <= trial]
            if len(new) > len(best_new):
                best, best_new = cand, new
        if best is None:
            break
        have.add(best)
        done.update(best_new)
        steps.append((best, best_new, len(done)))
    print("\n" + "=" * 78)
    print("BUILD ORDER - add these organs in this sequence")
    print("=" * 78)
    for i, (organ, new, total) in enumerate(steps, 1):
        print("  %d. + %-24s -> unlocks %-2d new:  %-18s   TOTAL %2d/22"
              % (i, organ, len(new), " ".join(new), total))
    return steps


if __name__ == "__main__":
    build_order()
