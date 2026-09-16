# שפה אחת / Safa Achat

**Comparative-linguistics AI over all languages — living, dead, and
reconstructed.** The long-range dream is "reverse Babel": trace the world's
words back along documented sound changes, find the shared roots that are
really there — toward the horizon of Zephaniah 3:9, *"כי אז אהפוך אל עמים
שפה ברורה"* — a clear language between peoples.

The dream is big; the method is strict. This repo is v0.1: a small, honest,
fully offline prototype of the pipeline.

## What it does (today)

Given Swadesh-style wordlists (bundled: 21 concepts × Hebrew, Arabic,
Aramaic, English, German, Latin — three scripts, two families, one dead
language), it:

1. Normalizes everything through a **universal byte/script layer**
   (Unicode NFC → UTF-8 bytes; no per-language tokenizer).
2. Reduces broad IPA to **Dolgopolsky-style sound classes**.
3. Applies **documented sound laws** (Grimm's law; Proto-Semitic reflexes)
   and shows before/after scores — e.g. Latin *pater* ~ English *father*
   jumps from 0.79 to 0.93 once f→p / ð→t are accounted for.
4. Scores every same-concept cross-language pair and issues a **verdict
   with built-in epistemic honesty**: cross-family lookalikes (*earth ~
   eretz*, *six ~ shesh*) are never labeled cognates — they are labeled
   "lookalike — needs systematic correspondence evidence".
5. Runs a real **comparative-method check**: recurring sound
   correspondences per language pair. Hebrew~Arabic yields 7 recurring
   correspondences (ʃ:s, v:b, ʔ:ʔ, …); Hebrew~English yields **0**. That
   asymmetry — not any single word pair — is what family relationship
   looks like.

## Run it

```
cd safa-achat
python demo.py                          # the whole pipeline on bundled data
python -m unittest discover -s tests -v # 15 tests, incl. the honesty invariant
```

Pure Python 3.10+ stdlib. No pip installs, no network, no GPU.

## Honest limits (read before dreaming)

- **This does not reconstruct a proto-language**, and no automatic tool
  reliably can. Reconstruction requires expert-verified cognate sets.
- **Beyond ~8–10k years the signal drowns** in chance resemblance and
  borrowing (Campbell & Poser 2008; Ringe 1992). "Proto-World" is not a
  finding this project can produce, and it will never claim one.
- **Similarity is not cognacy.** *Lev/qalb* ("heart") are near-synonyms and
  NOT cognates; *sheva/seven* look alike across families and prove nothing
  by themselves. The code encodes this: the "likely cognate" verdict is
  structurally unreachable for cross-family pairs (unit-tested).
- Loanwords, nursery words (*ima/umm/mama*), and onomatopoeia mimic
  cognates; scale-up (SPEC §6) adds explicit modeling for them.

What CAN honestly be built: a machine that applies the comparative method
at a scale no human team can — thousands of languages, every documented
sound law, statistical significance testing — and hands linguists ranked,
evidence-annotated candidates. Clarity, one correspondence at a time.

## Layout

```
SPEC.md            method, scope (provable vs speculative), roadmap
demo.py            end-to-end demo on bundled data
data/swadesh.tsv   21 concepts x 6 languages, broad IPA
safa/              bytetok | phonology | rules | distance | cognates | comparative
tests/test_safa.py unit tests incl. the honesty invariant
```

ALMAWARE · v0.1 · 100% our own code, stdlib only.
