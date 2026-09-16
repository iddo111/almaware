> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# judge2 — corpus licence + attribution record

Every corpus the discriminator may eat, and what travels with it. Verified 2026-09-01.

| corpus | where | n | licence | attribution that must travel |
|---|---|---|---|---|
| FLEURS he_il | eran4 `~/heb-corpus` (1.1 G, 3,242 wav, 16 kHz mono, 9.47 h, 1,502 speaker ids) | 3,242 | **CC-BY-4.0** | **FLEURS (Conneau et al. 2022), Google — CC BY 4.0** |
| booth t06 | PC `eran-brain/booth/staged/t06` | 657 | Iddo's own voice | private |
| booth t07 | PC `eran-brain/booth/staged/t07` (+4 in `trash/`) | 128 (+4) | Iddo's own voice | private |
| booth t08-raw | PC `eran-brain/booth/t08-raw` | 117 | Iddo's mic capture, **UNVERIFIED** | private — see QUARANTINE below |
| food/train | PC `eran-brain/food/train` | 396 (22 units × 6 takes × 3) | Iddo's own voice | private |
| ERAN queue | PC `eran-brain/judging/queue` | 1,937 wav + 1,937 json | machine output | none |

**CC-BY obligation, verbatim from the corpus's own SOURCE.json:** "CC-BY permits derivatives
WITH ATTRIBUTION. Any syllable cut from this carries the line above; it does not stop
travelling because the clip got shorter."

Any model, dataset card, artifact or paper that trains on FLEURS-derived syllables must
carry the attribution line. A syllable is a derivative.

## QUARANTINE — t08-raw
Not cleared for the human class. Measured, not guessed:
- take-vs-floor SNR **7.1 dB** (food/train 24.4, booth t06 17.8, booth t07 16.5) — floor
  −30.1 dBFS, ~20 dB louder background than every curated set on disk.
- not syllable takes: 23 files exactly 5.06 s and 23 exactly 1.09 s (fixed-length chunking),
  median 1.86 s, 43 files over 3 s.
- pitch unverifiable: pyin and yin both return a degenerate repeated 282.1 Hz; only 9 of 112
  land under 180 Hz, where Iddo's measured voice lives (ear3 calib t06 f0 median 112.7 Hz;
  food/train 88 Hz; booth t07 102 Hz).
- provenance: identical filenames exist in `D:\CLAUDE\keshev-next\segments` (18,436 wav),
  captured 08:20:34–08:33:56 on 2026-09-01 — inside the window of the KESHEV repeat-loop
  malfunction reported at 08:36 the same morning.

**Honest keep-rate for the human class: 0 of 117** until a human ear or an STT pass confirms
the content. 112 of 117 contain some periodic energy; that is not the same claim.
