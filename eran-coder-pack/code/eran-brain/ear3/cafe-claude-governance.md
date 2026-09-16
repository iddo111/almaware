# קפה-קלוד — Content Governance for Cortex Training / ממשל-תוכן לאימון הקורטקס

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — test the REAL output, not a proxy.

**עברית:** 96 פרקים (16.6 שעות) — אפס קבצי ביקורת ליד המדיה; פרק-01 חסום (שיחת טלפון פרטית) אבל זהות הקובץ לא רשומה בשום מקום; לפי כלל 5 שום פרק אינו "נקי" עד ביקורת.
**English:** 96 episodes (16.6 h) — ZERO review files sit next to the media; Episode-01 is blocked (private phone call) but its exact file identity is recorded nowhere; per MISTAKES rule 5, no episode is "clean" until reviewed.

---

## ⛔ THIS FILE IS ITSELF PRIVATE — NEVER PUBLISH

This document names private-content categories inside Iddo's personal recordings.
It must never leave this machine: no cloud push, no artifact, no zip, no shard,
no quote in a public page. **Training code MUST load the restricted list
programmatically from the JSON block at the bottom of this file (or a copy of
it), never hard-code paths, and must refuse to run if this file is missing.**

Audited: 2026-08-26 (read-only pass; nothing in `D:\קפה-קלוד` was modified).

## 1. Governance / review files found — and their rulings

Inside `D:\קפה-קלוד` and its parent `D:\`:

| file | ruling |
|---|---|
| `D:\קפה-קלוד\PROJECT_SUMMARY.md` | content summary only — **no publish/private ruling** (unclear) |
| `D:\קפה-קלוד\PLAN_Eran_From_Scratch_Model.md` | build plan — no ruling |
| `D:\קפה-קלוד\handouts\README.md` | folder readme — no ruling |
| `D:\קפה-קלוד\handouts\ALMAWARE_FULL_HANDOUT_Eran_20260702.md` | vision doc — no ruling |
| `D:\קפה-קלוד\handouts\ALMAWARE_Connection_Not_Weight_20260702.md` | concept doc — no ruling |
| `D:\קפה-קלוד\handouts\claude_design_question_20260702.md` | design note — no ruling |
| `D:\` (drive root) | no governance files |

**No CONTENT-REVIEW\*, VERDICT\*, or \*.review file exists anywhere in the
library.** The only rulings that exist live OUTSIDE it:

| external source | ruling |
|---|---|
| `D:\CLAUDE\MISTAKES.md` rule 5 | read every review file before deriving anything from media; **embeddings are a derivative** |
| `D:\CLAUDE\eran-federation-app\cloud-inference\make_shards.mjs` (header comment) | "The Cafe-Claude episode … STOPPED by its own CONTENT-REVIEW.md: private phone call inside — DO NOT PUBLISH. It stays private, and so do its embeddings." |
| RAMCHAT post 2026-08-24 21:35 (claude-cli-FABLE) | "Cafe-Claude Episode-01 is BLOCKED by its own CONTENT-REVIEW.md (private phone call inside) — do NOT publish it or derivatives." |
| memory `reference_cafe_claude_recordings.md` | dates 2026-06-25 and 2026-07-01 are held-out eval — never train on them |

**⚠ The CONTENT-REVIEW.md itself was NOT found anywhere searched: all of
`D:\CLAUDE` (depth 4), `D:\` (depth 2), the eran project dirs,
`E:\ALMA-Backups` (depth 4), git history, RAMCHAT logs. A full-drive
filename sweep was started but stopped before completing — "not found" is
confirmed only for the areas above.** It sat next to a staging copy of the
episode that was apparently deleted with the derivatives on 2026-08-24
(MISTAKES.md #5). Consequence: **which WAV is "Episode-01" is recorded
nowhere.** The restriction therefore cannot be pinned to one path and attaches
to the whole unreviewed library.

## 2. RESTRICTED list

1. **"Episode-01" — the private-phone-call episode: identity UNKNOWN.** Until
   Iddo (or a review pass he blesses) identifies it, every episode is a
   candidate to BE it.
2. **Held-out eval dates — never train (15 files, 1.12 h):**
   all root WAVs dated `202606 25******` (10 files) and `20260701******`
   (5 files), plus their `cleaned\*.mp3` and `transcripts\*` siblings.
   Exact list is in the JSON block below.

## 3. UNREVIEWED ≠ clean — the honest count

- Episodes with a per-episode content review on disk: **0 of 96.**
- **All 96 episodes are UNREVIEWED.** Per rule 5 they need review before ANY
  derivation (training, embeddings, shards, transcripts pushed anywhere).
- 40+ episodes (everything after 2026-07-03, plus all of August) had no
  transcript at audit time — they cannot even be keyword-screened yet.
- **The library is LIVE:** new WAVs landed on 08-18, 08-21 and TODAY
  (2026-08-26, latest 16:01), and a transcription run (session 6085f961,
  keshev-stt-pc :8737, "56 files todo of 96") was writing into
  `transcripts\` during this audit. Any freeze/manifest goes stale in hours.

## 4. Red flags the (missing) reviews would need to cover

Shallow keyword scan of the 58 non-empty transcripts (June–July episodes
only; categories, no content). Flags mean "a human must look", not "guilty":

- **Possible phone-call openings/closings:** transcripts of `20260702000225`,
  `20260702201939`, `20260626171819` (+ `_ALL_combined.txt`).
- **Medical / health-adjacent terms:** `20260702201939`, `20260702205719`,
  `20260628092804`.
- **Financial terms (money, debts, bank):** ~20 transcripts, incl. the
  06-25 block, `20260626165009`, `20260626175647`, `20260702*`,
  `dgx_compare\whisper_dgx\20260711172117`.
- **Other people's first names spoken:** nearly every transcript (1–8 distinct
  names each); `er_an_model.txt` and `_ALL_combined.txt` aggregate them.
- **Phone numbers / long digit runs:** none detected.
- `transcripts\_ALL_combined.txt` concatenates everything — it inherits every
  flag above and must be treated as the most sensitive single file.

## 5. Usable-for-cortex-training policy

```
total episodes (root WAVs)                    96      16.57 h
  − held-out eval dates (06-25, 07-01)       −15      −1.12 h
  = CANDIDATE set (pending review)            81      15.45 h
  − restricted (Episode-01 + review fails)     ?           ?
  = USABLE set                            **0 until reviewed**
```

**The usable set is formally EMPTY today.** The 81-episode / 15.45 h figure is
the *candidate* ceiling, not a license. An episode enters the usable set only
when all three hold:

1. A per-episode `CONTENT-REVIEW-<stamp>.md` exists next to it with an explicit
   "publishable" or "train-ok (private-local)" ruling;
2. It is not dated 2026-06-25 or 2026-07-01;
3. It is not (or has been cleared of being) the Episode-01 phone-call episode.

Local-only training vs publishing are different bars: even "train-ok
(private-local)" clips must never have derivatives (embeddings, shards,
babbles, demo wavs) pushed to any public endpoint without a separate
"publishable" ruling — the 08-24 scar is exactly this.

## 6. Machine-readable restricted list (training code loads THIS)

```json
{
  "generated": "2026-08-26",
  "library_root": "D:\\קפה-קלוד",
  "policy": "deny-by-default: only episodes with an explicit review ruling may be used",
  "never_train_dates": ["2026-06-25", "2026-07-01"],
  "never_train_files": [
    "20260625165315.WAV", "20260625165526.WAV", "20260625170458.WAV",
    "20260625171050.WAV", "20260625171740.WAV", "20260625172207.WAV",
    "20260625172706.WAV", "20260625173229.WAV", "20260625173851.WAV",
    "20260625182956.WAV",
    "20260701130300.WAV", "20260701131248.WAV", "20260701131518.WAV",
    "20260701220133.WAV", "20260701235639.WAV"
  ],
  "blocked_episodes": [
    {
      "name": "Episode-01",
      "path": "UNKNOWN — CONTENT-REVIEW.md not found on disk; restriction attaches to the whole library until identified",
      "reason": "private phone call inside; DO NOT PUBLISH episode or any derivative (embeddings included)"
    }
  ],
  "unreviewed_is_restricted": true,
  "reviewed_ok": []
}
```

Training code contract: parse the JSON block above; refuse any file matching
`never_train_files` or `never_train_dates`; while `unreviewed_is_restricted`
is true, use ONLY files listed in `reviewed_ok` (currently none). Do not
invert this to a blocklist.
