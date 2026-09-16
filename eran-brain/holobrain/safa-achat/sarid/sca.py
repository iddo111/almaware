# -*- coding: utf-8 -*-
"""SOUND-CLASS ALIGNMENT - the instrument the July prototype was missing.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL
> output, not a proxy.

WHY THIS FILE EXISTS, in one number
-----------------------------------
Recon B measured Latin against its documented daughters and against unrelated
languages with plain normalised edit distance, and got:

    worst daughter  lat-fra  0.8928
    best unrelated  lat-hun  0.9356
    margin                   0.0428

The gate SARID must pass is 0.15. That margin fails it by three and a half
times, and a 0.043 margin is EXACTLY the shape of the throat's burst-blind
ruler (noise seven times signal) and the first nezer's frozen 0.431 gate. So
the first job of this build is not to wire an objective. It is to show that a
better instrument widens that margin - or to report and stop.

WHY EDIT DISTANCE IS THE WRONG INSTRUMENT
-----------------------------------------
Levenshtein charges the same cost for every mismatch. Latin `p` against Spanish
`b` costs 1; Latin `p` against Finnish `a` also costs 1. But *p : b* is one of
the most frequent regular correspondences in the entire Romance record
(intervocalic voicing), and *p : a* is not a correspondence at all. An
instrument that cannot tell those apart is measuring alphabet overlap, not
descent - which is why the shuffled control landed INSIDE the unrelated band
at 0.9615: the signal that survived was meaning-aligned, but the ruler was too
blunt to read it.

WHAT SCA DOES INSTEAD
---------------------
Sound-Class-Based Alignment (List 2012, building on Dolgopolsky 1986): map each
segment to a sound CLASS, then align with a similarity matrix over classes
rather than a 0/1 identity test. Sounds that historically correspond sit close
together and cost little to align; sounds that never correspond cost a lot.
Prosodic context (whether a segment is in the syllable onset, nucleus or coda)
weights the columns, because initials are the most stable position
cross-linguistically and a vowel matching a vowel says much less than a
consonant matching a consonant.

This implementation is ours, stdlib + no dependency, and it is deliberately
CROSS-CHECKED against LingPy's own SCA on the host that has it
(`ruler.py --cross-check`). LingPy is the reference; if our numbers and theirs
disagree, ours is wrong and the journal says so. That is the ALMA Standard:
one thing that works, proven against the thing everyone else uses.

THE CLASS SET
-------------
Dolgopolsky's ten consonant classes, extended the way SCA extends them: the
laryngeals split from the velars, the liquids split from the nasals, vowels get
classes of their own instead of being deleted. Deleting vowels entirely (the
July prototype's `consonant_skeleton`) is right for Semitic roots and wrong for
Romance, where the stressed-vowel diphthongisations are half the sound laws.
"""
from __future__ import annotations

import unicodedata

# ---------------------------------------------------------------- the classes
# Each entry: IPA symbols -> class letter. Order matters only for the digraphs,
# which are matched before single characters.
_CLASS_TABLE = (
    ("ts dz tʃ dʒ tɕ dʑ tس", "S"),        # affricates -> sibilant class
    ("p b ɸ β f v ʙ", "P"),                # labial obstruents
    ("t d θ ð", "T"),                      # dental/alveolar obstruents
    ("s z ʃ ʒ ɕ ʑ ʂ ʐ", "S"),              # sibilants
    ("k g ɡ q ɢ x ɣ χ ʁ", "K"),            # velar/uvular obstruents
    ("m ɱ", "M"),                          # labial nasal
    ("n ŋ ɲ ɳ ɴ", "N"),                    # other nasals
    ("r ɾ ɽ ʀ ɹ ɻ", "R"),                  # rhotics
    ("l ɫ ʎ ɭ ʟ", "L"),                    # laterals
    ("w ʋ ɥ", "W"),                        # labial glides
    ("j ɰ", "J"),                          # palatal glide
    ("h ɦ ʔ ħ ʕ ʜ ʢ", "H"),                # laryngeals / pharyngeals
    ("i ɪ y ʏ ɨ ʉ", "I"),                  # close vowels
    ("e ɛ ø œ ə ɘ ɜ æ", "E"),              # mid front vowels
    ("a ɐ ɑ ɒ", "A"),                      # open vowels
    ("o ɔ ɵ ʌ ɤ", "O"),                    # mid back vowels
    ("u ʊ ɯ", "U"),                        # close back vowels
)

_SEG2CLASS: dict = {}
for _syms, _cls in _CLASS_TABLE:
    for _s in _syms.split():
        _SEG2CLASS.setdefault(_s, _cls)

VOWEL_CLASSES = frozenset("IEAOU")
CONSONANT_CLASSES = frozenset("PTSKMNRLWJH")
CLASSES = "PTSKMNRLWJHIEAOU"

# Diacritics and length/stress marks that never change the class.
_STRIP = set("ːˑ.ˈˌ‿͡ʰʲʷˠˤ̃̈̊̄̆̌̂ⁿ˞ʱ̥̬")


def normalise(seg: str) -> str:
    """One CLDF segment -> its bare IPA core."""
    s = unicodedata.normalize("NFD", seg.strip().lower())
    out = [ch for ch in s
           if ch not in _STRIP and not unicodedata.combining(ch)]
    return unicodedata.normalize("NFC", "".join(out))


def sound_class(seg: str) -> str:
    """The SCA class of one segment. '?' when the symbol is unknown.

    Unknown is a CLASS, not a silent skip. The July prototype skipped unknown
    symbols, which quietly shortened a word and made two words look more alike
    than they are. A '?' that matches nothing is honest; a deletion is not.
    """
    s = normalise(seg)
    if not s:
        return "?"
    if s in _SEG2CLASS:
        return _SEG2CLASS[s]
    for n in (3, 2):                       # digraph/trigraph affricates
        if s[:n] in _SEG2CLASS:
            return _SEG2CLASS[s[:n]]
    if s[0] in _SEG2CLASS:
        return _SEG2CLASS[s[0]]
    return "?"


def classes(segments) -> str:
    """A segmented word -> its sound-class string."""
    return "".join(sound_class(s) for s in segments)


# ------------------------------------------------------------ the score matrix
# Similarity between two classes. The numbers encode what the comparative
# record says about which sounds correspond, at three strengths:
#   identity           +
#   same manner family + (a labial for a labial, a vowel for a vowel)
#   everything else    -
# A vowel aligned to a consonant is the heaviest penalty in the matrix: that
# alignment is almost never a correspondence and letting it be cheap is how a
# blunt ruler turns noise into evidence.

_IDENT = 10.0
_NEAR = 5.0                # obstruents that regularly interchange
_VOWEL_VOWEL = 3.0         # vowels correspond loosely; they say less
_FAR = -3.0                # same broad type, no known correspondence
_CROSS = -8.0              # consonant against vowel
_UNKNOWN = -1.0            # '?' - neutral-ish, never rewarding

# Obstruent neighbourhoods: pairs that the record shows interchanging often.
_NEAR_PAIRS = {
    frozenset("PT"), frozenset("TK"), frozenset("PK"),      # stop shifts
    frozenset("TS"), frozenset("SK"),                       # assibilation
    frozenset("KH"), frozenset("PH"), frozenset("TH"),      # lenition to zero
    frozenset("SH"),
    frozenset("MN"),                                        # nasal place
    frozenset("RL"),                                        # liquid interchange
    frozenset("WJ"),                                        # glide interchange
    frozenset("WP"), frozenset("JI"), frozenset("WU"),      # glide/vowel
}


def score(a: str, b: str) -> float:
    """Similarity of two sound classes."""
    if a == "?" or b == "?":
        return _UNKNOWN
    if a == b:
        return _IDENT
    av, bv = a in VOWEL_CLASSES, b in VOWEL_CLASSES
    if av != bv:
        return _NEAR if frozenset(a + b) in _NEAR_PAIRS else _CROSS
    if av and bv:
        return _VOWEL_VOWEL
    return _NEAR if frozenset(a + b) in _NEAR_PAIRS else _FAR


GAP = -4.0                 # opening cost of an indel
GAP_EXTEND = -1.5          # affine: a long deletion is one event, not many
INITIAL_BONUS = 1.6        # the first segment is the most stable position


def align(seg_a, seg_b):
    """Global alignment over sound classes, affine gaps, initial weighting.

    Returns (score, columns) where each column is (class_a, class_b) and '-'
    marks a gap. The columns ARE the correspondence evidence: `comparative.py`
    counts them across distinct concepts to find recurring sound laws.
    """
    ca, cb = classes(seg_a), classes(seg_b)
    n, m = len(ca), len(cb)
    if n == 0 or m == 0:
        return 0.0, []
    neg = float("-inf")
    # M = match state, X = gap in b, Y = gap in a
    M = [[neg] * (m + 1) for _ in range(n + 1)]
    X = [[neg] * (m + 1) for _ in range(n + 1)]
    Y = [[neg] * (m + 1) for _ in range(n + 1)]
    M[0][0] = 0.0
    for i in range(1, n + 1):
        X[i][0] = GAP + GAP_EXTEND * (i - 1)
    for j in range(1, m + 1):
        Y[0][j] = GAP + GAP_EXTEND * (j - 1)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            w = 1.0 + (INITIAL_BONUS if (i == 1 and j == 1) else 0.0)
            s = score(ca[i - 1], cb[j - 1]) * w
            best_prev = max(M[i - 1][j - 1], X[i - 1][j - 1], Y[i - 1][j - 1])
            M[i][j] = best_prev + s
            X[i][j] = max(M[i - 1][j] + GAP, X[i - 1][j] + GAP_EXTEND)
            Y[i][j] = max(M[i][j - 1] + GAP, Y[i][j - 1] + GAP_EXTEND)
    end = max(M[n][m], X[n][m], Y[n][m])
    # backtrace
    cols = []
    i, j = n, m
    state = "M" if M[n][m] == end else ("X" if X[n][m] == end else "Y")
    while i > 0 or j > 0:
        if i == 0:
            cols.append(("-", cb[j - 1])); j -= 1; continue
        if j == 0:
            cols.append((ca[i - 1], "-")); i -= 1; continue
        if state == "M":
            cols.append((ca[i - 1], cb[j - 1]))
            w = 1.0 + (INITIAL_BONUS if (i == 1 and j == 1) else 0.0)
            prev = M[i][j] - score(ca[i - 1], cb[j - 1]) * w
            i, j = i - 1, j - 1
            state = ("M" if abs(prev - M[i][j]) < 1e-9 else
                     ("X" if abs(prev - X[i][j]) < 1e-9 else "Y"))
        elif state == "X":
            cols.append((ca[i - 1], "-"))
            prev = X[i][j]
            i -= 1
            state = "M" if abs(prev - (M[i][j] + GAP)) < 1e-9 else "X"
        else:
            cols.append(("-", cb[j - 1]))
            prev = Y[i][j]
            j -= 1
            state = "M" if abs(prev - (M[i][j] + GAP)) < 1e-9 else "Y"
    cols.reverse()
    return end, cols


def similarity(seg_a, seg_b) -> float:
    """Alignment score normalised to [0,1]. 1 = as alike as a word is to itself.

    The normaliser is the mean of the two self-alignment scores, which is the
    standard way SCA-based distances are turned into a similarity (List 2012):
    it keeps a long word and a short word on the same scale.
    """
    s, _ = align(seg_a, seg_b)
    sa, _ = align(seg_a, seg_a)
    sb, _ = align(seg_b, seg_b)
    denom = (sa + sb) / 2.0
    if denom <= 0:
        return 0.0
    return max(0.0, min(1.0, s / denom))


def distance(seg_a, seg_b) -> float:
    return 1.0 - similarity(seg_a, seg_b)
