> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# BLIND EAR PROTOCOL — does `sounds_good_v0` agree with Iddo's ear?

לזכרו של לָאוֹר ז״ל. Written 2026-09-15. **Protocol only. Nothing has been played, cut or served.**

## Why

`sounds_good_v0.py` is a HYPOTHESIS. The only ear data on record is 11 taps (1 good, 10 bad) and one
3-clip blind ranking (2026-09-05). On the taps v0 points the wrong way (AUC 0.10): it ranks the one
"good" clip below 9 of the 10 "bad" ones. The existing judge was already benched on the same kind of
data (kappa 0.0). One small, well-built test settles whether v0 is worth anything.

## The question, fixed in advance

> When v0 scores render X above render Y, does Iddo, not knowing which is which, prefer X?

Render vs render only. Not render vs real Darwish: that asks "can he tell it is ours", a different
test (`darwish_ab2.py`, never taken). A training loop needs the order among our own renders.

## 1. Choosing the 20 pairs (a script does it before he listens)

- **Pool:** renders in `out/sounds_good_v0.json → our_renders`, excluding the `human*` controls.
  - Prefer clips he has **not** rated or heard blind before: 26 of 43 are unheard.
  - Treat `darwish_v2/3/4.mp3` and `machine1/2/3.mp3` as the same three renders, and never pair a render with itself.
- **18 unique pairs, spread by v0 score gap.** Big gaps are where v0 must be right if it means anything; small gaps test fine resolution.

  | v0 gap | pairs |
  |---|---|
  | 10 points or more | 8 |
  | 4 to 10 points | 6 |
  | under 4 points | 4 |

- **2 repeat pairs:** 2 of the big-gap pairs come back later with sides swapped. They test whether his own answers repeat. Total shown: 20.
- **Balance:** no clip in more than 3 pairs, and at least 5 pairs that mix categories (checkpoint / mode preview / Chai render).
- **Seed and freeze:**
  - One fixed RNG seed.
  - Write `blind_pairs_v0.json`: pairs, clip cut points, sides, order, and v0's predicted winner for each pair.
  - Post its SHA1 to RAMCHAT **before** the session. Once posted, nobody may change weights, anchors or pairs.

## 2. The clips

- **Length 20 s.** At ~142 BPM that is about 12 bars: enough to hear the groove and a phrase. 40 clips is about 13 minutes.
- **Cut point:** both clips of a pair are cut by the same rule. Take the start of the 60 s window v0 actually scored (`start_s` of the median window), plus 10 s. For files shorter than 30 s, cut from the start.
- **Loudness-matched** to -9.0 LUFS integrated, ±0.5 LU (below the ~1 LU just-noticeable difference), so level is not a clue. This is the same rule as `darwish_ab2.py`.
- **50 ms fade** in and out, so no click gives a clip away.
- **Rendering runs on eran2 at nice 19** with ffmpeg, never on the PC. The audio stays on this machine and the fleet: no upload, no publishing, no chat attachments.

## 3. What he sees and answers

- **No new app** (ONE HARNESS LAW). Add a `/pairs` flow to the existing `taste_server.py` on 127.0.0.1:8868, agreed first with its owner (claude-cli-SONNET-psytaste) on RAMCHAT.
- **How the page works:**
  - Each pair shows two players labelled `א` and `ב`, then `צמד 7 מתוך 20`.
  - `<audio controls preload="none">`, no autoplay. He presses play himself and can replay.
  - Clips are served only as `/pairs/clip?slot=N`. Filenames, scores and the answer key never go over the wire.
- **One tap per pair:**
  - `א נשמע טוב יותר` / `ב נשמע טוב יותר`
  - `אותו דבר` (a tie, allowed; it is counted but not scored)
  - An optional free-text word or two.
- **Saving:** every tap is appended at once to `blind_pairs_v0_answers.jsonl`, with pair id, side chosen and timestamp. He can stop at any point and pick up later. Nothing is shown about v0 until all 20 are answered.
- **Question wording (Hebrew, exactly):** `איזה מהשניים נשמע לך טוב יותר — כמוזיקה, בעולם של דרוויש?`

## 4. Computing agreement (a script, not a person)

For each answered, non-tie, non-repeat pair: **agree** if his choice is v0's predicted winner.

- **A** = agreements / decided pairs (out of 18 unique).
- **One-sided binomial p** against chance (0.5), plus a Wilson 95% interval.
- **A_big** = agreement on the 8 big-gap pairs.
- **Self-consistency** = how many of the 2 repeat pairs he answered the same way both times.
- Also written out: the same agreement for `judge.py`'s score and for the raw capped |z| distance (`ours_vs_darwish.json`). This shows whether v0 beats what already exists.

Results are appended to `sounds_good_gate_log.jsonl` next to this file, in the same PASS/FAIL style as `judge/gate.py`.

## 5. Decision rules, set before any answer exists

p = one-sided binomial against 0.5, computed on the **decided** pairs (ties removed). The counts
below assume all 18 unique pairs were decided; with ties, the p column is the rule.

| outcome | rule | meaning |
|---|---|---|
| **INCONCLUSIVE, his ear** | he flips on both repeat pairs | His ear does not repeat at 20 s. The test cannot judge v0. Re-run with 30 s clips. |
| **INCONCLUSIVE, too close** | fewer than 14 decided pairs (too many ties) | The pairs were too similar. Re-pick with bigger gaps. |
| **RELIABLE (for pre-filtering)** | p ≤ 0.02 (14/18 gives p = 0.015) **and** at least 7 of the 8 big-gap pairs agree | v0 may *pre-sort* renders for his ear. It still never picks a checkpoint alone. |
| **PROMISING** | 0.02 < p ≤ 0.15 (13/18 gives p = 0.048, 12/18 gives p = 0.119) | Not yet. Run 20 **fresh** pairs. Combined ≥ 26/36 (p ≈ 0.006) upgrades it to RELIABLE. |
| **NOT RELIABLE** | p > 0.15 (11/18 or fewer: p ≥ 0.24) | v0 is **BENCHED**, like judge.py. Record it. |

For scale: 14/18 still has a Wilson 95% lower bound of about 55%. "Reliable" here means clearly better than a coin, not right on every pair. Say that whenever the word is used.

## 6. What is forbidden after the answers arrive

- Re-weighting v0 on these 20 pairs and calling the result validated. That fits noise. A v1 is tested only on **new** pairs, chosen and frozen the same way.
- Dropping pairs after seeing the answers.
- Reporting A without n, p and the interval.

## 7. Burden on Iddo

- One sitting of about 15 minutes, or two of about 8.
- 20 taps, no typing required, no scores to read.
- He can stop at any time, and his answers so far are kept.
