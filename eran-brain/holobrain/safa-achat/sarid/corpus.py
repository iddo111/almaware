# -*- coding: utf-8 -*-
"""THE CORPUS - the host object. Every array, every IPA string, lives HERE.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL
> output, not a proxy.

This is the WINSTON pattern, kept exactly: **a spark is a scalar**. Segments,
alignments, correspondence tables and matrices are the body; the weave's knots
only ever exchange single numbers about them. The spells in `voices.py` are
closures over ONE Corpus instance, so the anatomy in `weave.py` can stay pure
loom semantics with no tensors smuggled down a cord.

WHAT IT READS
-------------
CLDF (Cross-Linguistic Data Formats) word lists: `cldf/forms.csv` plus
`cldf/languages.csv`. That is the format Lexibank, NorthEuraLex and ASJP all
publish in, which is why the ingest is written once and pointed at whichever
dataset Gate 0 approved.

The one field that matters most is `Segments` - space-separated IPA, already
segmented by the dataset's own transcription pipeline. We do not re-segment. A
home-made segmenter is a silent source of divergence, and this workspace has
been bitten by a second decoder before (winston/atelier.py says so in its own
docstring).

Family membership comes from the dataset's `Family` column where it has one.
It is used for exactly one thing and it is the important one: **holding out
whole language families**, never random words. That is the 2026-08-21
session-leak scar in its linguistic form - random-word holdout leaks a
language's own phonology into its own test set and every number goes up for
free.
"""
from __future__ import annotations

import csv
import os
import random
import sys
from collections import defaultdict
from dataclasses import dataclass, field

csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))


@dataclass
class Form:
    """One word, in one language, for one concept."""
    lang: str
    concept: str
    form: str
    segments: tuple            # already-segmented IPA, the dataset's own
    family: str = ""
    cognateset: str = ""       # expert judgement, "" when the dataset has none

    @property
    def ipa(self) -> str:
        return "".join(self.segments)


@dataclass
class Corpus:
    """A word list, indexed the three ways the comparative method asks for it."""
    name: str = ""
    path: str = ""
    forms: list = field(default_factory=list)
    _by_lang: dict = field(default_factory=dict)
    _by_concept: dict = field(default_factory=dict)
    lang_family: dict = field(default_factory=dict)
    n_cognacy: int = 0                 # how many forms carry an expert judgement

    # ------------------------------------------------------------------ ingest

    @classmethod
    def from_cldf(cls, root: str, name: str = "",
                  langs: set | None = None) -> "Corpus":
        """Read a CLDF word list. `langs` restricts the ingest, for speed."""
        cldf = os.path.join(root, "cldf")
        if not os.path.isdir(cldf):
            cldf = root
        fam, gloss = {}, {}
        lpath = os.path.join(cldf, "languages.csv")
        if os.path.exists(lpath):
            with open(lpath, encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    fam[r["ID"]] = (r.get("Family") or "").strip()
        ppath = os.path.join(cldf, "parameters.csv")
        if os.path.exists(ppath):
            with open(ppath, encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    gloss[r["ID"]] = (r.get("Concepticon_Gloss")
                                      or r.get("Name") or r["ID"]).strip()

        c = cls(name=name or os.path.basename(root.rstrip("/\\")), path=root)
        c.lang_family = fam
        cog_by_form = {}
        cogpath = os.path.join(cldf, "cognates.csv")
        if os.path.exists(cogpath):
            with open(cogpath, encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    cog_by_form[r.get("Form_ID", "")] = (
                        r.get("Cognateset_ID") or "").strip()

        with open(os.path.join(cldf, "forms.csv"), encoding="utf-8") as f:
            for r in csv.DictReader(f):
                lg = r["Language_ID"]
                if langs is not None and lg not in langs:
                    continue
                segs = tuple((r.get("Segments") or "").split())
                if not segs:
                    continue
                cog = cog_by_form.get(r.get("ID", ""), "") or (
                    r.get("Cognacy") or "").strip()
                pid = r["Parameter_ID"]
                c.forms.append(Form(
                    lang=lg, concept=gloss.get(pid, pid), form=r.get("Form", ""),
                    segments=segs, family=fam.get(lg, ""), cognateset=cog))
        c.reindex()
        return c

    def reindex(self) -> None:
        self._by_lang = defaultdict(list)
        self._by_concept = defaultdict(list)
        self.n_cognacy = 0
        for fo in self.forms:
            self._by_lang[fo.lang].append(fo)
            self._by_concept[fo.concept].append(fo)
            if fo.cognateset:
                self.n_cognacy += 1

    # -------------------------------------------------------------- the views

    @property
    def langs(self) -> tuple:
        return tuple(sorted(self._by_lang))

    @property
    def families(self) -> tuple:
        return tuple(sorted({f for f in self.lang_family.values() if f}))

    def by_lang(self, lang: str) -> list:
        return self._by_lang.get(lang, [])

    def by_concept(self, concept: str) -> list:
        return self._by_concept.get(concept, [])

    def family_of(self, lang: str) -> str:
        return self.lang_family.get(lang, "")

    def langs_in_family(self, family: str) -> tuple:
        return tuple(sorted(lg for lg in self.langs
                            if self.family_of(lg) == family))

    def concept_map(self, lang: str) -> dict:
        """concept -> segments, one form per concept (the first attested)."""
        out = {}
        for fo in self.by_lang(lang):
            out.setdefault(fo.concept, fo.segments)
        return out

    def shared(self, a: str, b: str) -> list:
        """Every concept both languages attest, as (concept, seg_a, seg_b).

        Semantic control is a PRECONDITION of the comparative method: two words
        are only ever compared inside the same concept slot. Comparing across
        slots is how chance resemblance gets counted as evidence.
        """
        ma, mb = self.concept_map(a), self.concept_map(b)
        keys = sorted(set(ma) & set(mb))
        return [(k, ma[k], mb[k]) for k in keys]

    def shuffled_against(self, a: str, b: str, seed: int = 0) -> list:
        """THE NULL MODEL, and the reason SARID is not Ruhlen.

        The same two languages, the same inventories, the same phonotactics,
        the same number of pairs - with the meaning link destroyed. Any score a
        method reports here is what it would have reported on noise. Every
        claim in this organ is quoted against this number, never on its own.
        """
        pairs = self.shared(a, b)
        rb = [p[2] for p in pairs]
        rnd = random.Random(seed)
        rnd.shuffle(rb)
        return [(pairs[i][0], pairs[i][1], rb[i]) for i in range(len(pairs))]

    # -------------------------------------------------------------- holdout

    def split_by_family(self, held_out: str):
        """Leave-one-FAMILY-out. Never leave-one-word-out.

        Returns (fit_langs, test_langs). The 08-21 session-leak scar: a random
        split lets a language's own phonology sit on both sides of the wall and
        every number goes up for free. A family wall is the only honest one,
        and `weave.py` additionally makes it a TOPOLOGY - no cord runs from a
        held-out family to any fitting knot, so a leak is a graph error rather
        than a statistics mistake.
        """
        fit, test = [], []
        for lg in self.langs:
            (test if self.family_of(lg) == held_out else fit).append(lg)
        return tuple(fit), tuple(test)

    def summary(self) -> dict:
        return {"name": self.name, "forms": len(self.forms),
                "doculects": len(self.langs), "families": len(self.families),
                "concepts": len(self._by_concept),
                "expert_cognacy_forms": self.n_cognacy}
