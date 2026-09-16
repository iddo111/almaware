# Hebrew STT — what shipped, what it fixed, and how to undo it

2026-08-07. Deployed to `alma-stt` on **eran4**. gpt-oss, colibri and alma-mic on eran4
were checked before and after and are unaffected.

---

## 1. What shipped, and why it is not the fine-tuned model

Three checkpoints were measured **through eran4's own serving code** (`server.py` +
`decode_policy.py`, fp16, restricted he/en language choice). This matters: the previous
round measured in a *training* harness, which has no suppression gate and no two-class
language restriction, so its numbers do not describe what a user experiences.

| candidate | what it is |
|---|---|
| `OLD` | `openai/whisper-large-v3-turbo` — what eran4 served until today |
| **`S20`** | **0.80 × openai-turbo + 0.20 × ivrit-ai, fp16 — SHIPPED** |
| `ft70` | the fine-tuned model (soup α=0.70 + training) — **not shipped** |

**Corpus WER / median-per-utterance WER, as served** (suppression counted as a deletion,
because a deletion is what the user sees):

| eval set | n | OLD | **S20 (shipped)** | ft70 |
|---|---|---|---|---|
| his held-out Hebrew — tierA | 203 | 45.33 / 57.69 | **30.74 / 42.86** | 23.30 / 21.74 |
| his held-out Hebrew — retain | 196 | 46.89 / 75.00 | **32.22 / 57.14** | 21.20 / 25.00 |
| general Hebrew — FLEURS, **human labels** | 300 | 32.02 / 23.43 | **29.31 / 18.75** | 22.59 / 12.50 |
| general English — FLEURS, **human labels** | 200 | 5.38 / 4.26 | **5.19 / 3.94** | 7.08 / 5.00 |
| his English — iddo_en | 314 | 56.90 / 12.92 | **30.60 / 25.00** | 68.38 / 22.22 |

**ft70 was rejected.** It is by far the best Hebrew model — his Hebrew median error falls
57.69 → 21.74 — but it pays for it in English, and he is **52.8% English**:

- general English, human labels: 5.38 → **7.08** (+32% relative). This is *not* a routing
  problem — its language-ID on FLEURS English is already 100%, so the English decoder
  itself is worse.
- his English: language-ID falls 99.7% → **80.9%**, i.e. one English utterance in five is
  decoded as Hebrew. Measured example: `What's up, man` → **`זה בסוף, מה?`**
- Across his held-out clips ft70 improves 283/379 Hebrew utterances but improves only
  **2 of 57** English ones and makes 23 worse.

That is the same defect he complained about, moved from Hebrew into English. It fails the
"no bad regression on his English" bar, so it stays off the wire.

**S20 clears the bar cleanly:** it is better than production on **both** human-labelled
sets — the only unbiased measurements available — and on his Hebrew.

---

## 2. The honest caveat about the "his English" row

S20's huge apparent win on his English (56.90 → 30.60 corpus) is **mostly production
avoiding catastrophic loops, not better typing**. Production degenerates into repetition
on his speech; two clips alone score 4390% and 3571% WER:

```
REF : Return again, return again, return to the love you sing
OLD : return again return again return again return again return again … (×20)
S20 : again return again turn to the love
```

By the robust statistic the picture reverses: **median** English WER on that set goes
12.92 → 25.00, i.e. the *typical* English utterance got worse. Two things to hold at once:

- the reference text for `iddo_en` was written by production's own model family, so it is
  biased *toward* production and against anything that diverges from it;
- on `fleurs_en`, where the labels were written by **humans**, S20 is genuinely better
  than production (5.19 vs 5.38 corpus, 3.94 vs 4.26 median).

Ship decision rests on the human-labelled row. The machine-labelled row is the thing to
watch in daily use.

---

## 3. The defect that dominates everything, and it is not the model

On eran4's serving path production **emits nothing at all for 32% of his Hebrew clips**
(39% on `retain`). He speaks; nothing is typed. Cause is `decode_policy.py`:

- `MIN_ALLOWED_LANGUAGE_MASS = 0.75` — abstains when the model is not confident the audio
  is he-or-en. Production is genuinely unsure about his voice (language-ID 72–65% on his
  Hebrew), so it abstains constantly.
- `NO_SPEECH_THRESHOLD = 0.60`.

S20 cuts this to 18–30%; ft70 to **0%**. Stock-phrase hallucination ("תודה רבה") is
essentially absent on this path (≤0.5%) — on eran4 the hallucination shows up as
**deletion**, not as a wrong phrase. This is a *policy* number, tunable without any model
change, and it is still the single biggest everyday defect on the box.

The same class of bug exists separately in the Windows mic app
(`D:\CLAUDE\alma-mic\stt.py`): `log_prob_threshold = -1.0` deletes ~5% of real speech, in
a 13.5% total silent-deletion rate. **Unchanged — still worth doing and it is config-only.**

---

## 4. Ten held-out utterances, live through the deployed endpoint

Selected by fixed quantiles of production's error (0/8/20/35/55/75/92% for Hebrew,
5/45/85% for English) — **not** hand-picked. `NEW` was produced by POSTing the audio to
the live `http://<tailnet-ip>:8844/v1/transcribe`, i.e. the real deployed service.

| # | lang | dur | WER old → new | |
|---|---|---|---|---|
| 285 | he | 5.3s | **1043% → 52%** | loop fixed |
| 4958 | he | 3.7s | 100% → 100% | was silent, now types (wrongly) |
| 181 | he | 7.7s | 100% → 100% | **still broken** |
| 300 | he | 3.4s | 100% → 100% | **still silent** |
| 185 | he | 5.5s | 50% → **30%** | |
| 166 | he | 12.0s | 23% → **17%** | |
| 216 | he | 29.9s | 9% → 11% | slightly worse |
| 118 | en | 1.8s | 100% → 100% | **still silent** |
| 2 | en | 14.7s | 0% → 0% | unchanged, correct |
| 155 | en | 4.7s | 0% → 0% | unchanged, correct |

Corpus over these ten: **149.45% → 33.52%** (dominated by #285).

The two that matter most for honesty:

```
#181  REF : אה כמו, כמו סבא, כמו נעמי. תגיד לי, איפה נעלמתם, אח שלי? מה נסגר
      OLD : אההההההההההה… (runaway)
      NEW : אההההההההההה… (runaway — NOT fixed)

#300  REF : זאת אומרת, אין מה להגיד לי כל הכבוד, זה גם את קהל המצפות, אין מה להגיד לי
      OLD : <nothing typed>
      NEW : <nothing typed>   ← the suppression gate, not the model
```

And one that shows the win is real:

```
#166  REF : שאתה עכשיו מקליט תשמור אותו לא רק בשביל אימון משקלים שלי, בשביל ערן…
      OLD : כשאתה עכשיו מקליט… בשביל איראן נזהה את הקול שלי…
      NEW : שאתה עכשיו מקליט… בשביל איראן יזהה את הקול שלי…
```

Full per-utterance JSON:
`…\scratchpad\proof\live_results.json`

---

## 5. Regression check on eran4 — all pass

| | before | after |
|---|---|---|
| gpt-oss `:8000` chat completion | 0.44 / 0.31 / 0.29 s, HTTP 200 | **0.25 / 0.23 / 0.23 s, HTTP 200** |
| colibri `:8800` | HTTP 401 (listening, auth required) | **HTTP 401 — unchanged** |
| MemAvailable | 2571 MB | **3374 MB** |
| swap used | 15.8 / 16 GiB | 15.8 / 16 GiB — unchanged |
| services active | alma-stt, colibri, gptoss, alma-mic | **all four still active** |

The swap was already fully consumed before this work and remains so; nothing here made it
worse. Model swap is memory-neutral (fp16 in, fp16 out, 1542.9 MB) and the checkpoint was
pre-cast to fp16 **before** transfer specifically so the load peak on a box with ~3 GiB
free would not double.

Wire contract re-verified unchanged: `language=he`, `language=auto` and `language=en` all
return 200; wrong sample-rate still 400; >30 s still 413.

---

## 6. What is installed where, and how to roll back

**eran4** (serving the phone and the PWA):

| | |
|---|---|
| model | `/home/eran4/models/whisper-iddo-soup20` (fp16, 1542.9 MB, 0.234% zero bytes) |
| config | `~/.config/alma-stt.env` — now sets `ALMA_STT_MODEL` and a comma-separated allowlist |
| code | `~/services/alma-stt/server.py` — model id is now env-driven; allowlist is now a list |
| backups | `~/backups/alma-stt/*.bak-20260807_deploy` |

**Full rollback — restores the original model, code and allowlist:**

```bash
ssh eran4 'cp ~/backups/alma-stt/alma-stt.env.bak-20260807_deploy ~/.config/alma-stt.env && \
           cp ~/backups/alma-stt/server.py.bak-20260807_deploy   ~/services/alma-stt/server.py && \
           systemctl --user restart alma-stt.service && sleep 25 && \
           systemctl --user is-active alma-stt.service'
```

**Model-only rollback, keeping the phone fix** — comment out one line:

```bash
ssh eran4 "sed -i 's|^ALMA_STT_MODEL=|#ALMA_STT_MODEL=|' ~/.config/alma-stt.env && \
           systemctl --user restart alma-stt.service"
```

Verify either with `curl -s http://<tailnet-ip>:8844/health` **from the PC**
(<tailnet-ip>) — from eran4 itself the allowlist correctly returns 403.

**The phone blocker is fixed.** `ALMA_STT_ALLOWED_CLIENT` was the single string
`<tailnet-ip>`, compared with `==`, so the A70 got 403 on every request. It is now
`<tailnet-ip>,<tailnet-ip>` and `_allowed()` does a set membership test. Startup log
confirms: `allowed=['<tailnet-ip>', '<tailnet-ip>']`.

**Windows mic app — NOT changed.** It does not use eran4 at all; it runs faster-whisper
locally (`config.json: "model": "deepdml/faster-whisper-large-v3-turbo-ct2"`). The shipped
model is staged for it in CTranslate2 form at
`D:\CLAUDE\whisper-iddo\models\soup20-ct2`. To adopt it, set `"lora_dir"` in
`D:\CLAUDE\alma-mic\config.json` to that path and restart the `ALMA-MIC-Elevated`
scheduled task; revert by setting `"lora_dir"` back to `""`. This was **not** done here
because it was not measured through the mic app's own decode path (different VAD,
different thresholds), and swapping it unverified is how you get a regression.
`ft70-ct2-NOT-SHIPPED-hebrew-only` is also on disk — it is the rejected model; do not
point the mic app at it.

---

## 7. What is still bad

1. **~18–30% of his Hebrew still produces no text on eran4**, and ~13.5% in the mic app.
   Both are threshold constants, not model weights. This is now the largest defect and it
   is cheaper to fix than anything above.
2. **Runaway repetition is not fixed** (#181). Neither model solves it; it needs a
   repetition penalty or a compression-ratio check in the decode policy.
3. **ft70's Hebrew is much better than what shipped** (median 21.74 vs 42.86) and is
   sitting unused. The way to collect it without wrecking English is language-conditional
   routing — ft70 for `he`, S20/production for `en`. That needs two models resident;
   **eran4 cannot host it** (3.4 GiB available, swap already 100% consumed), so it would
   have to run on eran2 or eran3, which have ~25 and ~115 GiB free and already hold both
   checkpoints.
4. **No transcript in this corpus was written by a human.** Every `iddo_*` number measures
   agreement with a machine labeller and is biased toward production, which wrote the
   labels. Only the FLEURS rows are true accuracy. `training/make_verify_set.py` exports
   ~250 clips pre-filled for correction; an hour of Iddo's time makes every number here
   real. Until then, "his English got worse by median" cannot be distinguished from "his
   English diverged from the old model that wrote the reference".

---

## Files

- serving-path eval harness: `eran2:~/whisper-iddo/serve_eval.py`, `analyze_serving.py`,
  `robust.py`, `examples.py`
- per-utterance dumps, all 3 models × 5 sets: `eran2:~/whisper-iddo/serving_hyps/`
- deployable checkpoints: `eran2:~/whisper-iddo/deploy/{soup20-fp16,soup20-ct2,ft70-hf,ft70-ct2}`
- live proof: `…\scratchpad\proof\live_results.json`, `live_proof.py`
- previous round's training report: `D:\CLAUDE\whisper-iddo\results\RESULTS.md`
