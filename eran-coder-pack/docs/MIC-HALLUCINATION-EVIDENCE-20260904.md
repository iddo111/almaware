> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# MIC HALLUCINATION EVIDENCE FILE — 2026-09-04
## תיק ראיות: הזיות מיקרופון קשב, 04/09/2026

Read-only investigation. Nothing was restarted, changed, or touched — audio devices, KESHEV, and Claude
Code were only *read*. This is the evidence half of the committee Iddo ordered at 17:53 JDT
(`"תריץ וועדת חקירה על הזייות מיק"`); it does not implement a fix, it establishes what actually
happened so a fix can be scored against real data.

חקירה בקריאה-בלבד. שום דבר לא הופעל מחדש, שונה, או נגע בו — התקני שמע, קשב, ו-Claude Code רק
נקראו. זהו החצי הראייתי של הוועדה שעידו הזמין בשעה 17:53 (`"תריץ וועדת חקירה על הזייות מיק"`);
הוא לא מיישם תיקון — הוא קובע מה באמת קרה כדי שתיקון יימדד מול נתונים אמיתיים.

**Bottom line up front / התמצית:** KESHEV really does hallucinate — I found and confirmed five
distinct real instances today, plus four more that are genuinely ambiguous and should stay marked
uncertain. The mechanism is exactly the classic Whisper failure mode: short stock phrases and
repeated tokens generated from silence or near-silence. KESHEV already has a filter (`textguard.py`)
that catches about a fifth of all bad decodes — and it works for what it targets — but it has at
least three demonstrated gaps, all documented below with exact evidence.

**עידו — האמת בשורה אחת:** קשב באמת הוזה. מצאתי ואישרתי חמישה מקרים אמיתיים היום, ועוד ארבעה
שנשארים לא ודאיים בכנות. המנגנון הוא בדיוק כשל וויספר הקלאסי: ביטויים קבועים ואסימונים חוזרים
שנוצרים משקט. לקשב כבר יש מסנן (`textguard.py`) שתופס כחמישית מהפענוחים הרעים — והוא עובד על מה
שהוא מכוון אליו — אבל יש לו לפחות שלושה פערים מוכחים, כולם מתועדים למטה עם ראיות מדויקות.

---

## 1. Sources used

| source | what it is | value |
|---|---|---|
| `C:\Users\<user>\.claude\projects\D--CLAUDE\6a17fb2f-...jsonl` | Claude Code session transcript (today, 14:31–17:59 UTC) | **Authoritative delivery record** — every string KESHEV actually pushed into Claude, as a `queued_command` attachment (`origin.kind: "human"`), millisecond timestamps |
| `...b73fb7e6-...jsonl`, `...bb023997-...jsonl`, `...70250ad2-...jsonl` | Three more Claude Code sessions active today (07:20–15:05 UTC combined) | Same delivery record, earlier in the day |
| `D:\CLAUDE\keshev-next\trial.log` | KESHEV's own decoder log (8.2 MB, spans 2026-08-24 → today, 116k lines) | Acoustic detail: `peak_rms`, VAD gate score, decoder log-probability (`lp`), and every `textguard` block/allow decision |

**Critical finding about the two sources:** `trial.log` only timestamps the *start* of a mic-engine
session, not each segment. I reconstructed per-segment time by summing each segment's own logged
duration — and then caught it drifting: a decoded "היי!" segment I estimated at 17:46 actually
reached Claude (per the transcript) at **17:59:53**, a 13-minute gap over one session. Pauses and
buffering between segments simply aren't in the logged durations. **Every exact time quoted below
comes from the Claude Code transcript (`queued_command` timestamp, authoritative), not from the
`trial.log` estimate.** `trial.log` is used only for the acoustic corroboration (energy, confidence,
what was blocked) — never for "what time did this happen."

**Negative result that matters:** KESHEV does **not** lack history. `trial.log` is a rich rolling
decoder log; the Claude Code transcripts independently retain every delivered string with
millisecond precision. The problem is real-time filtering gaps, not missing logs.

---

## 2. Confirmed hallucinations (high confidence)

### H1 — `"רק אל יאללה!"` — 2026-09-04 **17:52:42** JDT
The headline case, and the one that triggered this investigation.

- **17:48:24** — last real dictation: "...אנחנו צריכים מודל שיכול להיות פסיכולוגית ילדים ריזונינג, מודל" (cut off mid-sentence)
- **[4 minutes 18 seconds of total silence — no dictation reaches Claude at all]**
- **17:52:42.449** — `"רק אל יאללה!"` arrives as a `queued_command`
- **17:52:59.009** — Iddo: `"לא אמרתי יאללה"` ("I didn't say yalla") + `"זה הזיית מיק"` ("this is a mic hallucination") — same batch, 17 seconds later

`trial.log` independently shows KESHEV's decoder twice producing a *bare, standalone* `"יאללה"` /
`"יאללה!"` output with nothing else in the segment. The later of the two carries a decoder
log-probability of **lp=-0.93** — far worse than the **-0.02 to -0.30** range typical of confident
real speech elsewhere in the same log — and is immediately preceded by a `textguard:repetitive`
drop (repeated "וואו") and a confidence-threshold drop (`lp=-1.54`). In other words: a burst of
garbage decodes, and this one just barely survived the confidence gate.

### H2 — `"אדוני היושב"` — 2026-09-04 **17:17:09** JDT
- **17:17:09.734** — `"אדוני היושב"` ("Mr. Chairman...") arrives as its own `queued_command`
- **17:17:33.082** — flushed to Claude combined with Iddo's own next words: `"אדוני היושב זה הזיה"` — i.e. Iddo's real words `"זה הזיה"` ("this is a hallucination") land immediately after the phantom fragment, in the same delivered message

This is a **truncated** (2-word) match of the single best-documented Whisper-Hebrew hallucination:
`"אדוני היושב-ראש, חברי הכנסת"` ("Mr. Chairman, members of the Knesset") — see H5 below. KESHEV's
own blocklist exists specifically to catch that phrase, but only matches it in full; a partial
decode slips straight through.

### H3 — `"אדוני"` alone — 2026-09-04 **06:52:47** JDT
Same failure, a different day-part: a bare `"אדוני"` landed sandwiched between two `"ששש."` fillers,
in the middle of Iddo actively typing/saying, in real time: `"המיק יוצר הזייות ללא סוף"` ("the mic
produces endless hallucinations") → `"סדר מייד או תוריד אותו"` ("fix it now or take it down"). The
mic hallucinated again *while Iddo was complaining about it hallucinating.*

### H4 — `"‫-T-T-T-T-T-T"` repetition tail — 2026-09-04 **06:49:48** JDT
The cleanest self-demonstrating case in the whole dataset. Iddo dictates a real, coherent sentence
that gets cut off and decays into repeated garbage:

> `"ואם היו לך אזניים היי‫-T-T-T-T-T-T"` — *"and if you had ears you'd..."* → `-T-T-T-T-T-T`

His very next dictated sentence, seconds later: `"היית שומע שאני לא מדבר"` — **"you would hear that
I am not speaking."** Iddo is narrating, in real time, that he was silent — while the decoder was
still emitting confident-looking text. This is a different failure shape than H1–H3: a *real*
utterance that decays into a repetition loop mid-transcription, rather than a stock phrase invented
from pure silence. KESHEV's repetitive-content filter did not catch it, because the segment as a
whole still contained real content at the front.

### H5 — `"אדוני היושב-ראש, חברי/חבריי הכנסת"` (full phrase) — **11 occurrences today, 0 delivered**
The full Knesset-opening sentence — Israeli Hebrew ASR's best-known hallucination, almost certainly
leaking from Knesset-broadcast training data — appeared **11 times** in today's `trial.log`. Every
single occurrence:
1. was immediately preceded by multiple consecutive `SKIP steady-noise` / `decode=empty` segments
   (15–40+ seconds of genuine room silence, textbook Whisper trigger), and
2. was caught and discarded by KESHEV's own `textguard` blocklist before it ever reached Claude or
   Iddo.

This is included as **proof the existing defense works** for the exact string it targets. The
residual risk is only in truncated matches (H2, H3) and in stock phrases the blocklist doesn't
cover yet.

---

## 3. Likely / uncertain — marked honestly, not resolved

Per the brief: *do not assume.* These four stay UNCERTAIN because the evidence does not clear them
either way.

| text | when | why uncertain |
|---|---|---|
| **`"קצת קצת קצת"`** | 17:38:59 JDT | The exact phrase Iddo flagged as ambiguous. Came from an unusually short (2.24s vs the normal 5.06s), VAD-truncated segment during a locally low-energy stretch (peak_rms 4893, well below the ~11,000–18,000 range of confident speech nearby). A real 3× repeat for emphasis is also completely normal Hebrew speech. The `repetitive` filter does **not** fire on a repeated *real* word (only on garbled tokens/single letters) — a demonstrated gap either way. |
| **`"3"`** (lone digit) | 17:54:06 JDT | Arrived 1ms before an unrelated real command it doesn't grammatically belong to. Stray-digit insertion is a documented Whisper pattern, but could be incidental. Low stakes either way. |
| **`"אממ" / "אממ..."`** | 4 occurrences, 14:31–17:41 (mixed sessions) | Ordinary Hebrew filler *and* a documented Whisper hallucination pattern during hesitation-like low-energy audio. Each `trial.log` instance: moderate-to-low energy, moderate confidence (lp -0.48 to -0.74) — not as extreme as H1–H4. Iddo never singled out a specific instance. |
| **`"אה" / "אה..." / "איי!"`** | several, scattered | Ordinary interjections; mixed acoustic evidence; not explicitly disowned. |

---

## 4. Confirmed REAL — despite looking exactly like the suspects above

Included deliberately, as a control: **brevity and apparent disconnection are not reliable
hallucination signals on their own.**

- **The Kabbalah/gematria burst** (06:36–06:48 JDT, session `bb023997`): `"ומי"`, `"איך"`, `"כמה"`,
  `"למה"`, `"כיצד"`, `"מתי"`, `"והאומנם"`, `"הכצעקתה"`, `"אתבש"`, `"אלבם"`, `"קבלת התורה"`,
  `"משה רבינו"`, `"זה רבי נחמן"` — in isolation this reads like noise. Read in full, it's one
  coherent real discussion about Rebbe Nachman of Breslov's story of reciting the Torah backward
  and the `מחני נא` / `אני נחמן` acrostic. VAD just chopped one long train of thought into many
  short delivery batches, several sharing identical timestamps.
- **`"שומע?"` / `"אתה שומע?"`** (4+ times all day) — every instance carries high decoder confidence
  (lp ≈ -0.02 to -0.04). Iddo's habitual mic check-in. Real.
- **`"דיברנו"`** — single instance, lp=-0.07, high energy, fits grammatically with a real sentence
  moments earlier ("מה שדיברנו"). Real.
- **`"היי!" / "עמודים!" / "יואו! כן!" / "אלמידו"`** (17:59–18:01 JDT) — matches the independently
  documented, real ALMIDO agent project. Iddo reacting live to something on screen. Real.

---

## 5. Frequency table

**Recurring short strings across all 353 `queued_command` deliveries today** (most of the 316
real fragments are unique long sentences; only fillers repeat):

| text | count |
|---|---|
| `שששש.` | 3 |
| `ששש.` | 2 |
| `--` | 2 |
| `נכון?` | 2 |
| `שומע?` | 2 |
| `אממ...` | 2 |
| `אדוני` / `אדוני היושב` (Knesset fragment, H2+H3 combined) | 2 |
| `יאללה` / `יאללה!` (trial.log decoder output, combined) | 2 |

**Recurring patterns caught by `textguard` and never delivered** (from `trial.log`, today only):

| pattern | count |
|---|---|
| `אדוני היושב-ראש, חברי/חבריי הכנסת` (Knesset full phrase) | 11 |
| extended letter `אה` (`אהההההההההה...`) | 18 |
| extended letter `ש` (`ששששששששששש...`) | 13 |
| extended laugh `ח` (`חחחחחחחח` etc, all variants) | 6 |
| garbled-token repeats (`GXR`, `TGXR`, `LARROXR`) | 3 |
| extended `אווו` ("wow") | 3 |
| dash-only / no-content (`-\n-\n-...`) | 3 |
| `לא לא לא לא לא לא` / `מסכים מסכים מסכים` (repeated real-word phrases) | 2 |

**Recurrence is the strongest evidence in this file.** The Knesset phrase alone (11×, always
blocked) proves this is a systematic leak, not a one-off fluke — and its two truncated escapes
(H2, H3) prove the systematic leak has a systematic gap.

---

## 6. Timing analysis

**Do phantoms cluster on silence?** Yes, cleanly. Every one of H1–H4 arrived either right after a
multi-second-to-multi-minute gap in real dictation (4m18s before H1; 15–40s of logged room silence
before each of the 11 H5 instances), or as a corrupted tail glued onto real speech that had just
ended (H2, H4). **None of the confirmed hallucinations occurred inside a dense, continuous run of
confident dictation.** This matches Whisper's textbook failure mode exactly.

**Do identical timestamps predict hallucination?** The brief asked me to check this specifically —
**the answer is no.** Several messages today share the exact same millisecond timestamp because
KESHEV batches multiple short fragments together when it flushes to Claude (e.g. the Kabbalah burst,
the ALMIDO burst, and `"עמודים!"`/`"יואו! כן!"` both at 15:00:03.226Z). That batching pattern shows
up equally in confirmed-**real** bursts and is **absent** from the two clearest hallucinations (H1
and H4 each arrived as a single, isolated delivery — not part of a same-timestamp batch). Identical
timestamps mean "delivered in the same flush," nothing more. I checked this honestly rather than
assume it, per instructions, and the correlation the brief hypothesized did not hold up.

---

## 7. System / mechanism findings (not hallucination content, but load-bearing)

- **S1 — 3-hour engine crash-loop, 16:46–19:49 JDT.** The `gui` mic-engine variant in `trial.log`
  restarted roughly every 20 seconds continuously for **3 hours 3 minutes**, logging zero audio
  segments each time, before Iddo switched to `gui6` at 16:53 JDT (which then ran normally and
  produced most of today's evidence). No phantom text came out of this window because no audio was
  ever captured — but it's 3 hours of the mic being dead, flagged here under Broken Windows law.
- **S2 — the delivery format carries no confidence signal.** KESHEV pushes text into Claude Code as
  `{type: "queued_command", origin: {kind: "human"}, prompt: <text>}`. There is no field for decoder
  confidence or "this barely passed the filter." H1's `lp=-0.93` and a normal decode's `lp=-0.05`
  look *identical* on arrival. This is the structural reason a hallucination is invisible until a
  human catches it after the fact.
- **S3 — the existing filter (`app/textguard.py`) works, with three demonstrated gaps.** It stopped
  77 of 384 decode-ok segments today (20%) before they could reach Claude — 53 for repetitive
  content, 9 for the Knesset blocklist, 9 for one-letter-word runs, 3 for dash-only "no content," 1
  for a "thanks" blocklist entry. Confirmed gaps: **(a)** a truncated/partial match of a blocklisted
  phrase is not caught (H2, H3); **(b)** a repeated *real* dictionary word is not caught by the
  repetitive filter (U1, `קצת קצת קצת`); **(c)** a real sentence that decays into repetition
  mid-utterance is not caught at all, because the segment as a whole still contains real content
  (H4).

---

## 8. Honest limitations

- No raw audio (`.wav`) was available or examined for any segment — this was a read-only,
  log-and-transcript investigation. All acoustic classification rests on logged proxy metrics
  (`peak_rms`, VAD gate score, decoder `lp`, surrounding silence), never on direct listening.
- `trial.log` truncates its logged decoded text to roughly 30 raw characters for many longer
  utterances (a byte-length cap in the logger), so exact wording of long real sentences is
  sometimes cut off mid-word in that log. This does not affect the short filler/hallucination
  phrases central to this investigation, which are short enough to survive intact.
- **Clarification on `"אממ הזיית מיק"`:** the brief listed this alongside the disowned `"רק אל
  יאללה!"`. Traced in context (a standalone `"אממ..."` at 14:47:27.808, then `"אממ הזיית מיק"` at
  14:47:40.682), this reads almost certainly as **Iddo's own genuine real-time commentary** — "um,
  [that] was a mic hallucination," reacting to an earlier glitch — not itself an example of
  fabricated/inserted text in the H1–H4 sense. Flagged honestly rather than folded silently into
  the confirmed-hallucination list.

---

## 9. Files

- Evidence file (this document): `D:\CLAUDE\_status-reports-archive\MIC-HALLUCINATION-EVIDENCE-20260904.md`
- Machine-readable catalogue: `D:\CLAUDE\_status-reports-archive\mic_hallucinations_20260904.json`
- Source logs (unmodified): `D:\CLAUDE\keshev-next\trial.log`,
  `C:\Users\<user>\.claude\projects\D--CLAUDE\{6a17fb2f-c846-444e-a168-b2a58e4d43e3, b73fb7e6-ee1e-4dcf-85d9-876f47b28f32, bb023997-c47a-4077-96d7-c4edbf8528ea, 70250ad2-3189-40a6-9ffe-9fee609d52ba}.jsonl`

This is the evidence half only. No fix was implemented, no textguard rule was changed, no service
was restarted. Ready for the committee's decision half to score any proposed fix (blocklist
expansion, a repeated-real-word check, a confidence field on `queued_command`, a LoRA on Whisper)
against these 5 confirmed + 4 uncertain cases rather than against guesses.
