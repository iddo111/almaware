# שפה אחת / Safa Achat — Specification v0.1

**Goal.** A comparative-linguistics AI over all languages — living, dead, and
reconstructed — that searches for shared roots and cognates across the world's
lexicon ("reverse Babel"), in the direction of Zephaniah 3:9 — "כי אז אהפוך אל
עמים שפה ברורה". The verse is the *inspiration*; the method is
computational historical linguistics, done by the book.

---

## 1. Architecture (layers)

```
input text (any script)
   │
   ▼
[L0] Universal byte/script layer      Unicode NFC → UTF-8 bytes.
                                      No per-language tokenizer. Byte n-grams
                                      give an orthographic baseline and are
                                      the input representation for a future
                                      byte-level neural encoder.
   │
   ▼
[L1] Phonetic layer                   Broad IPA transcription per word.
                                      Normalization strips length/stress
                                      marks and combining diacritics.
   │
   ▼
[L2] Sound-class layer                Dolgopolsky-style consonant classes
                                      (P T S K M N R W J H). Sounds that
                                      historically correspond share a class,
                                      making comparison robust to shallow
                                      phonetic drift.
   │
   ▼
[L3] Correspondence layer             Documented sound laws applied as
                                      normalization (Grimm's law for
                                      Germanic; Proto-Semitic reflex tables
                                      for Arabic/Aramaic vs Hebrew). Every
                                      rule application is reported.
   │
   ▼
[L4] Comparative-method layer         For a language pair, align consonants
                                      of same-concept words and count
                                      RECURRING correspondences across
                                      distinct concepts. Recurrence — not
                                      similarity — is the evidence standard.
```

Implementation map: `safa/bytetok.py` (L0), `safa/phonology.py` (L1–L2),
`safa/rules.py` (L3), `safa/distance.py` + `safa/cognates.py` (scoring),
`safa/comparative.py` (L4).

## 2. Cognate-candidate scoring

Comparison happens **only within a semantic slot** (same Swadesh concept) —
semantic control is a precondition of the comparative method, and it kills
the largest source of false positives (meaning-blind string trawling).

For a word pair, after L1–L3 processing:

| component   | weight | what it measures |
|-------------|--------|------------------|
| `dolgo_sim` | 0.50   | normalized Levenshtein similarity of consonant-class skeletons (Semitic-root-friendly) |
| `ipa_sim`   | 0.35   | normalized Levenshtein similarity of full normalized IPA (vowels count) |
| `initial`   | 0.15   | first consonant class matches (word-initials are historically the most stable position) |

`byte_sim` (UTF-8 byte-bigram Jaccard) is computed and reported but **not**
mixed into the score: it is script-bound by construction and would reward
same-script pairs for the wrong reason.

### Verdicts (the honesty layer)

| condition | verdict |
|-----------|---------|
| score ≥ 0.60, same family     | `likely cognate (within family)` |
| score ≥ 0.60, different family| `lookalike — needs systematic correspondence evidence` |
| 0.40 ≤ score < 0.60           | `possible — weak signal` |
| otherwise                     | `no signal` |

**Invariant (unit-tested):** a cross-family pair can *never* receive the
"likely cognate" verdict from surface similarity alone. Upgrading a
cross-family lookalike requires L4 evidence — many recurring correspondences
— and in v0.1 the system never performs that upgrade automatically.

## 3. The comparative method module (L4)

The comparative method (developed by the 19th-century Neogrammarians; modern
treatments: Lyle Campbell, *Historical Linguistics: An Introduction*; Hock,
*Principles of Historical Linguistics*; Rankin, "The Comparative Method" in
*The Handbook of Historical Linguistics*) rests on the regularity of sound
change: if two languages descend from a common ancestor, sound
correspondences between their cognates are *systematic*, not sporadic.

`recurring_correspondences(entries, lang_a, lang_b, min_count)` aligns the
raw consonant strings (no L3 rules — we want to *observe* correspondences,
not assume them) of every same-concept pair via Needleman–Wunsch and counts
each aligned consonant pair over **distinct concepts**. Pairs attested in ≥
`min_count` concepts are reported.

On the bundled 21-concept list this already recovers real, citable
correspondences:

- Hebrew ʃ : Arabic s (in *shem/ism, shalom/salām, sheva/sabʿa, …*) —
  the well-known š~s relation between Hebrew and Arabic.
- Hebrew v : Arabic b (*kelev/kalb, av/ab, sheva/sabʿa*) — Hebrew
  begadkefat spirantization of *b*.
- English s : German z (*seven/sieben, six/sechs, sun/Sonne*) — German
  voicing of initial s.
- Hebrew ~ English: **zero** recurring correspondences at the same
  threshold. That negative result is the honest headline.

## 4. Data

`data/swadesh.tsv`: 21 Swadesh-style concepts x 6 languages = 126 rows.
Columns: `concept, lang, family, branch, status, orthography, ipa`.

- Semitic: Hebrew (living), Arabic (living), Aramaic (liturgical/dead in
  daily use) — three scripts, right-to-left, exercising the byte layer.
- Indo-European: English, German (Germanic, living), Latin (Italic, dead).
- Transcriptions are broad IPA, hand-checked at dictionary level.
- Deliberate stress-tests included:
  - *lev/qalb* ("heart"): same meaning, **different** Semitic roots — must
    score low (it does; Arabic *lubb* "core" is the true cognate of לב).
  - *eretz/earth*, *shesh/six*, *sheva/seven*: famous cross-family
    lookalikes (chance / possible ancient loanwords for the numerals) — must
    never be auto-claimed as cognates.
  - English "hound" (not "dog") is used for the dog concept, since *hound ~
    Hund ~ canis* is the actual inherited set; a data comment away from
    hiding this choice would have been dishonest, so it is stated here.

## 5. What is provable vs. speculative — scope discipline

**Solid (this prototype stands on it):**
- Regular sound correspondence within established families (Semitic;
  Indo-European) — mainstream, reproducible, and reproduced here.
- Grimm's law, High German shift, Proto-Semitic reflex tables (*ṯ → Heb š /
  Ar ṯ / Aram t; ḏ → Heb z / Ar ḏ*): documented sound laws (Rask 1818,
  Grimm 1822; Huehnergard, *Introduction to Ugaritic* / standard Semitic
  handbooks).
- Swadesh-style basic-vocabulary control lists as the comparison arena.

**Speculative (this project does NOT claim it):**
- Proto-World / Nostratic-style long-range relationships. Beyond roughly
  8,000–10,000 years, chance resemblance and borrowing swamp the signal
  (Campbell & Poser, *Language Classification: History and Method*, 2008;
  Ringe 1992 on the probability of chance lookalikes). Mass lexical
  comparison (Greenberg-style) is rejected by most historical linguists as
  a proof method. We may *rank* long-range hypotheses as search candidates;
  we will not present them as findings.
- Automatic proto-language reconstruction. v0.1 does not reconstruct
  anything. A future module may *propose* correspondence sets for human
  review; reconstruction claims require expert-verified cognate sets.
- Any theological identification of a specific "original language". The
  Zephaniah verse is treated as a moral horizon (clarity between peoples),
  not as a testable linguistic hypothesis.

**Known error sources the design must always disclose:** loanwords (Hebrew
and Arabic have borrowed from each other and from everyone), onomatopoeia
and nursery forms (*mama/ima/em/umm* partially reflect universal infant
phonetics — flagged in literature since Jakobson 1962), chance resemblance,
and areal convergence.

## 6. Roadmap (post-v0.1, in order)

1. **Data scale-up:** ingest open wordlists (Lexibank/CLDF, NorthEuraLex,
   IDS) — thousands of languages, real Swadesh-100/207 coverage; keep the
   TSV schema.
2. **Learned correspondences:** replace hand-coded L3 rules with
   correspondences *induced* from high-confidence same-family pairs
   (EM over alignment counts), reported with frequencies and examples.
3. **Statistical significance:** permutation test — shuffle concept labels,
   re-run, and report how often the observed correspondence counts arise by
   chance (Kessler, *The Significance of Word Lists*, 2001).
4. **Loanword modeling:** date-aware and semantics-aware loan flags
   (cultural vocabulary vs. basic vocabulary behave differently).
5. **Byte-level neural encoder:** train a small byte-transformer on L0
   representations, evaluated *against* the comparative-method module as
   ground truth — the network proposes, the method disposes.
6. **Reconstruction assistant (human-in-the-loop):** propose proto-segment
   candidates per correspondence set, always exported as "for expert
   review", never as claims.

## 7. Engineering constraints

- Pure Python 3.10+ stdlib. No network, no external models. Runs offline.
- Deterministic: same input, same output. All thresholds are named
  constants (`safa/cognates.py: LIKELY, POSSIBLE`).
- Every automated verdict string contains its own epistemic status; there
  is no code path that prints a cross-family "cognate" claim.
