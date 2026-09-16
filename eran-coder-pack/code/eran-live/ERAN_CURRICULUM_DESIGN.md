# ERAN CURRICULUM — Multimodal Grounding Pipeline (Design v0.1)

**Status:** DESIGN ONLY — nothing here touches the live voice-only trainer.
**Date:** 2026-07-03
**Principle:** raise Eran like a cheder child. Iddo reads picture-books aloud; a camera sees the page; Eran learns word ↔ image ↔ voice. Pure foundation first, no shortcuts smuggled in, no overclaiming.

---

## 0. Ground rules (read first)

1. **The live Eran is sacred.** The 24/7 voice-only trainer at `D:\CLAUDE\eran-live` keeps running untouched. Grounding work happens in a **fork**: new repo `D:\CLAUDE\eran-curriculum`, initialized **from** a voice-only checkpoint (copy, never move). Call the fork **Eran-Gan** (גן — kindergarten) so nobody confuses the two.
2. **The VOICE-ONLY guard stays honest.** `data.py`'s `_assert_voice_only` exists because a book *text corpus* once contaminated Eran. Reading books **aloud** is different in kind: every byte Eran-Gan sees still passed through Iddo's mouth. The book's printed text is used only as an *alignment reference* for the audio, never fed directly as training bytes. This distinction goes in the fork's config comment, in writing.
3. **ALMAWARE purity:** the model — vision encoder included — is from scratch, ours. Pretrained encoders (DINOv2 etc.) may appear **only as a benchmark control** to tell us how much headroom we're leaving on the table, never in the shipped Eran.

---

## 1. Data capture rig

**Hardware (all already owned or <₪200):**
- **Audio:** ALMA-MIC as-is (owner-gated, 16 kHz mono).
- **Video:** any 1080p USB webcam on a gooseneck/tripod arm, pointed straight down at the book on the table, document-camera style. Fix the book position with two strips of masking tape on the table so pages land in roughly the same frame region. Desk lamp at 45° to kill glare (matte pages preferred; laminated board-books glare badly — test first).
- **Page-turn marker:** a USB foot pedal (or just the spacebar of a second keyboard on the floor). Iddo taps it each time he turns a page. This is deliberately low-tech: frame-differencing page-turn detection is buildable but flaky (hands in frame, shadows); the pedal makes page boundaries *ground truth* instead of a computer-vision problem. Frame-differencing can come later as a cross-check.

**Capture:** one `ffmpeg` process muxes camera (dshow, 1080p @ 10–15 fps is plenty — pages are static) and the ALMA-MIC audio device into a single MKV. Single-process muxing means A/V sync is ffmpeg's problem, not ours; residual dshow offset is calibrated once per rig with a clap-in-frame at session start (visible hand-clap = audio spike + motion spike; measure offset, store in session manifest).

**Session layout:**

```
D:\CLAUDE\eran-curriculum\sessions\2026-07-05_bayit-shel-pistuk\
  session.mkv          # raw capture, keep forever
  audio.wav            # 16k mono extract
  pages\page_003.png   # one clean still per page (mid-interval frame, hands absent)
  manifest.jsonl       # one line per event
```

`manifest.jsonl` events: `{"t": 12.44, "type": "page_turn", "page": 3}` and, after alignment, `{"t0": 13.1, "t1": 15.8, "page": 3, "ref_text": "פיל אחד גדול", "bytes": [...]}`. Everything downstream reads only manifests + stills + wav. Raw MKV is the archival source of truth.

**Session hygiene:** 10–20 minutes per session, book title spoken aloud at the start, clap, read naturally (pointing with a finger is *encouraged* — see §2), pedal on every turn. Expect ~1 GB/hour of MKV; trivial storage.

---

## 2. Alignment (the honest core)

Three links, three different confidence levels:

**(a) Audio ↔ text: STRONG.** We are in the luckiest alignment regime that exists: the reference text is *known* (it's the book), so this is **forced alignment**, not open ASR. Plan: use **alma-ozen** — the char-CTC model already trained on Iddo's voice — not for transcription but for its CTC posteriors, Viterbi-aligned against the known book text. Forced alignment tolerates a much weaker acoustic model than transcription does, so alma-ozen at its current quality is likely usable, and it keeps this 100% ours. Fallback if it isn't: a tiny CTC aligner trained specifically on the reading sessions themselves (each session adds gold audio-text pairs — the pipeline bootstraps its own aligner). Honest note: Hebrew support in off-the-shelf aligners (MFA, wav2vec2) is poor anyway, so the purist path is also nearly the only path. Output: per-utterance (phrase-level, not word-level at first) time spans. Word-level spans come later, when the aligner has enough session data.

**(b) Utterance ↔ page image: STRONG and free.** The pedal gives page intervals; any utterance inside a page's interval pairs with that page's still. Zero labels needed. This page-level pairing is the workhorse supervision for everything below.

**(c) Utterance ↔ image *region*: WEAK, and we say so.** No boxes, no labels, ever. Two mechanisms, in order:
1. **Contrastive attention (default):** train utterance-embedding ↔ patch-embedding alignment (§3); the cross-attention map over patches becomes a *pseudo*-pointing signal. With our data scale it will be noisy. It is evaluated, not trusted.
2. **The finger (opportunistic gold):** when Iddo points while reading — as one naturally does with a child — the fingertip location during the utterance is a genuine region label. Detection is a small HSV-skin-blob + topmost-point heuristic in the fixed overhead frame; crude but workable because the rig geometry is fixed. This is a Stage-2 add-on, not a launch dependency, but it's the single cheapest source of real region supervision we have.

---

## 3. Architecture — giving a byte-LM eyes

Current Eran: 4 layers, 4 heads, 256-dim, block 128, byte vocab 260, ~3.3M params. Eran-Gan extends it minimally:

- **Vision encoder (from scratch, ~1M params):** page still → center-crop → 128×128 grayscale-plus-hue (2ch) → conv stem (3 stride-2 convs) → 8×8 = **64 patch tokens** of 256-dim. No ViT pretraining, no CLIP. It starts blind, like a newborn. That's the point, and also the risk (§6).
- **Fusion — prefix tokens (Fuyu-style):** image tokens are *prepended* to the byte stream: `[<IMG> p1..p64 </IMG> byte1..byteN]`. Block size grows 128 → 256 (64 image + a few specials + ~188 bytes). Vocab 260 → 264 for `<IMG>`, `</IMG>`, `<SEP>`, `<PT>` (pointer, reserved). The transformer body is *unchanged in shape* except the position table — so the voice-only checkpoint loads cleanly, new rows initialized fresh.
- **Two losses, jointly:**
  1. **Conditioned LM loss** — next-byte prediction on the utterance bytes given the image prefix ("look at the page, predict what Iddo says"). This is the native Eran objective, just with eyes.
  2. **Contrastive loss (InfoNCE)** — mean-pooled utterance embedding vs. pooled image embedding, in-batch negatives (other pages). This is what buys retrieval/"pointing," and it's the standard weak-alignment tool when you have pairs but no labels.
- **Anti-forgetting:** every batch is a **70/30 mixture** — 70% plain voice-only byte streams (image slots filled with a learned `<NOIMG>` token) from the same `data.py` sources, 30% grounded pairs. Plus: LM head + embedding rows for old vocab start frozen for the first 2k steps. We *measure* forgetting: voice-only val loss must stay within 10% of the checkpoint's 0.24-ish baseline, or the run is rejected.

**Pragmatic-path honesty:** a frozen DINOv2-S + linear projection would almost certainly ground faster and better at this data scale. We run it **once, as a control**, to quantify the purity tax. It never becomes Eran.

---

## 4. Curriculum order (cheder progression)

| Stage | Material | Utterance form | Advance when |
|---|---|---|---|
| **0 — Flashcards** | Single-object word cards / "מילים ראשונות" board books: one picture, one word (תפוח, כלב, כדור) | Single word, ×5 repetitions across sessions | 4-way retrieval ≥70% (§5) |
| **1 — Attributes** | Same objects + attribute phrases ("כדור אדום", "כלב גדול") | 2–3 word phrases | Retrieval distinguishes attribute pairs ≥65% |
| **2 — Scenes** | Simple-scene books (early readers; e.g., "תירס חם"-level): one scene, one short sentence | Full short sentences; finger-pointing sessions begin | Region attention lands on named object above chance |
| **3 — Narrative** | Classic picture books ("מעשה בחמישה בלונים", "הבית של פיסטוק"…) read cover to cover | Continuous narrative across page turns | Next-page byte prediction beats no-image baseline |

Books are Iddo's own physical copies; captures are private training data, same posture as the voice corpus (never published — same privacy gate as everything voice-derived). Each stage's material stays in the replay mix when the next begins — children reread books; so does Eran-Gan.

---

## 5. First experiment — "Eran, point to the apple" (one GB10)

- **Data:** 40 objects × flashcard page each, read in 3 sessions, each word spoken 5× ⇒ ~200 utterance-image pairs, ~30–45 min audio total. Held out: (a) 1 repetition per object (seen card, unseen audio), and (b) a **re-photographed set** — the same 40 cards recaptured on a different day/lighting, which is the honest generalization test.
- **Model:** voice-only checkpoint (~3.3M) + conv encoder (~1M) + heads ≈ **4.5M params**.
- **Compute:** batch 64, ~20k steps of the 70/30 mixture ≈ **under 2 GPU-hours on one GB10** (this model is minuscule for a Spark; the budget is dominated by Iddo's reading time, not FLOPs). Fits WIP=1; does not touch the PC GPU or the live trainer.
- **Success metric (crisp, pre-registered):**
  - **Point:** given a word's bytes, rank the correct card among 4 candidates. Chance = 25%. **Success ≥70%** on held-out repetitions; report the re-photographed number separately, whatever it is.
  - **Name:** given a card image, greedily decode bytes; exact word match **≥50%** (chance ≈ 0).
  - **No-forgetting gate:** voice-only val loss within 10% of baseline.
- **Failure is a result.** If re-photographed retrieval is near chance, Eran learned card artifacts, not apples — we report that truthfully and fix it with augmentation (random crop/rotation/color-jitter, mandatory from day one) and more capture variety, not with narrative.

---

## 6. Honest hard parts

1. **Tiny data, really tiny.** CLIP used 400M pairs; we'll have hundreds. A from-scratch vision encoder at this scale will substantially **memorize**. Augmentation, weight decay, and the re-photographed test set are mitigations, not cures. The realistic near-term win is grounding *within Iddo's captured world*, not open-world vision — say so in every report.
2. **Clever-Hans cues.** Page position, lighting, a coffee stain — the contrastive loss will happily exploit any of it. Fixed rig geometry makes this *worse*. Mitigate: aggressive augmentation, re-capture sessions, and probing (retrieval on deliberately blanked-object crops should *fail*; if it succeeds, we're being fooled).
3. **Region grounding without labels** stays weak until finger-pointing data accumulates. Attention maps are suggestive, not evidence. Stage-2 gating uses them only against a chance baseline.
4. **Catastrophic forgetting** is a live risk with a 3.3M-param brain — new gradients can bulldoze the voice identity. The 70/30 replay + frozen-embedding warmup + hard val-loss gate is the defense; if it fails, fall back to adapter-style training (freeze the LM body, train only encoder + cross-layer additions).
5. **Hebrew forced alignment** has no good off-the-shelf answer; we depend on alma-ozen maturing. Phrase-level alignment is the honest starting granularity — word-level is a milestone, not an assumption.
6. **Evaluation is ours to build.** No benchmark exists for "one man's voice grounded in his own bookshelf." Every claim needs a pre-registered metric and a held-out set captured on a different day. "Eran can see" is banned vocabulary; "Eran retrieves the right card 29/40 times" is the house style.

---

## 7. Non-goals (v0.1)

No OCR of printed text into training bytes (guard stays). No video understanding (stills only). No speech *output*. No touching `eran-live`'s supervisor, config, or checkpoints — Eran-Gan reads a copied checkpoint and writes only under `D:\CLAUDE\eran-curriculum`.

**First physical step:** buy/borrow one gooseneck webcam mount + foot pedal, tape the book square on the desk, and record one 10-minute flashcard session. Everything else in this document is downstream of that MKV.
