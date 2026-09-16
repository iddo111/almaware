# state-big

Retraining of the four ants on the big human corpus. **Nothing in `state/`,
`recordings/` or `corpus-big/` was modified** — the running fleet services keep
using `state/`. This tree is built entirely alongside.

The result is in [RESULTS.md](RESULTS.md).

## Layout

```
state-big/
  RESULTS.md                  the answer
  formants.json               per-ant, per-unit F1/F2 for every colony
  vowel-space.svg             F1/F2 chart, before vs after
  corpus-vowels.json          what is actually in each training pool
  syllable-knowledge-big.json syllable discrimination, all colonies + references
  paired-tests-big.json       exact McNemar tests on the five comparisons
  train.log                   full training log
  corpus/
    items.json                the corpus as a file list (no audio copied)
    {train,heldout}_x.npy     14-dim frames, 40.4 h + 7.5 h
    {train,heldout}_counts.npy  frames per file -- the frame->file index
  <colony>/ant-{a,b,c,d}/current.json    checkpoints, format_version 3
  queen/current.json          which ant the Queen selected per colony, and why
  scripts/
```

The Queen ranks on held-out syllable discrimination, **not** quantisation error —
a prior controlled experiment showed quantisation error does not rank ants on
this task. She records a selection; she never merges or averages codebooks.

## Colonies

| colony | hours | speakers | what it isolates |
|---|---|---|---|
| `all-256` | 40.6 | 16 ids | the headline run |
| `multi-13.8h-256` | 13.8 | 15 ids | matched hours, many voices |
| `iddo-13.8h-256` | 13.8 | 1 | matched hours, one voice |
| `orig-253s-256` | 0.07 | 1 | 256 units on the ORIGINAL corpus — separates capacity from data |
| `random-frames-256` | 40.6 | 16 ids | 256 random real frames, k-means never run — separates the learner from the data |

Four ants per colony, seeds 7007 / 7019 / 7039 / 7057, 256 units. No weights and
no codebook are shared between ants; verified programmatically after training.
Held-out set is identical for every colony (7.52 h, 3 853 files), so held-out
error is comparable across the table.

## Reproduce

```powershell
$env:PYTHONIOENCODING="utf-8"
cd D:\CLAUDE\voice-ant-farm
python state-big\scripts\build_lists.py        # file lists + split integrity gates
python state-big\scripts\extract.py            # 14-dim frames to .npy  (~3 min)
python state-big\scripts\train_big.py          # all five colonies
python state-big\scripts\analyse.py            # formants + vowel space + SVG
python state-big\scripts\corpus_vowels.py      # input-side vowel content
python state-big\scripts\knowledge_big.py      # syllable discrimination
python state-big\scripts\paired_big.py         # paired significance tests
python state-big\scripts\queen.py              # Queen selection (selects, never merges)
python state-big\scripts\tables.py             # markdown tables for RESULTS.md
```

`train_big.py` is resumable: an ant whose `current.json` already exists is
skipped, so a killed run can be restarted without redoing finished ants.

## What was excluded, and why

* `fire/` and any ant-generated audio — synthetic; never trained on.
* `corpus-big/human/_unverified_provenance/` — 16 segments whose origin could
  not be proved not to be TTS.
* `corpus-syllables/` — VITS renderings. That is the *test* set for the syllable
  probes; training on it would invalidate them.
* YouTube / Spotify — see RESULTS.md.

## Verification performed

* `fastfeat.features_batch` is bit-identical to `acoustic_units.features`
  (max abs diff 0.0 over 25 random corpus files).
* `train_big.fit_codebook_big` reproduces `acoustic_units.fit_codebook`: on the
  original corpus it lands within 0.1 % of the same quantisation error at k=64
  and k=256, and reproduces the held-out errors recorded in `state/`
  (0.9685 / 0.9615 / 0.9948 / 0.9980).
* The formant estimator reproduces all four BEFORE values exactly
  (660/1064, 392/1948, 348/1332, 660/1064) from `state/`.
* No identical PCM in two splits; no session spanning two splits; the original
  24 recordings' segments stay in the split their source was in.
* `acoustic_units.load_checkpoint` accepts every checkpoint written here.
