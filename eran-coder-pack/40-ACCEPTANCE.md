> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# 40 — ACCEPTANCE · מה נחשב התקדמות ואיך מוכיחים את זה

## עברית — בשורה אחת

**התקדמות = מספר אמיתי, מפלט אמיתי, שמישהו אחר יכול להריץ שוב.**
כל השאר — `health: ok`, מונה שעולה, "המודל רץ" — זה בדיוק מה שעצר את ערן ל-3 שבועות.
**את האוזן של עידו אי אפשר לזייף. אל תנסה.**

---

## 1. The four words. Every claim gets exactly one.

| word | what it means | what it requires |
|---|---|---|
| **`VERIFIED`** | you measured the REAL output | a **number**, a **timestamp**, and a **command anyone can re-run** |
| **`BROKEN`** | you measured, and it does not work | the same three things. **This is a complete result.** |
| **`UNKNOWN`** | you did not measure | say so. **Never guess, never infer.** |
| **`PLANNED`** | not built yet | |

**A claim without those three things is `UNKNOWN`, no matter how confident you feel.**

---

## 2. What does NOT count — every one of these has already fooled someone here

Read this list twice. Each line is a real incident in `10-FAILURES.md`.

| ❌ not evidence | why | when it fooled us |
|---|---|---|
| `health: ok` | a tube with zero callers reports `ok` | 09-06, 09-10 |
| a process is alive | a dead mic was respawned as a corpse for 38 days | 06-27 |
| a metrics file's mtime is fresh | **mtime is evidence of writing, not of eating.** A starving ERAN wrote a metrics line every beat | 09-06 |
| `dev_top1 = 0.0` | over **0 items** it means *nothing was measured* — and he "failed" `ah` three times against it | 09-07→09-10 |
| `correct = 3.000000` | a constant that **cannot fall** is not a measurement — 11 rounds, never moved | 09-01→today |
| a counter that only rises | 23 of 32 watchdogs were liveness-only and survived every migration proving nothing | 09-05 |
| a backup log that says OK | it said OK 221/223 times and **FAIL never**, right through a 12-day stale-brain window | 09-05 |
| a dev score | the dev split leaked sessions → **every number ran 14 points optimistic** | 08-21 |
| the ruler passed it | the old ruler passed 24/24 while the mouth had **no audible frication at all** | 09-03 |
| the metric improved | `wdist` agrees with Iddo's ear at **AUC 0.361** — worse than a coin flip | 09-01 |
| a README says "human" | it was `mms-tts-heb` TTS. **Twice.** | 08-06 / 09-03 |
| a status page says "live" | the search behind it had been dead for 5 days | 09-07 |
| an empty grep | the field being grepped **did not record client IPs at all** | 09-06 |
| a log hit | it was **my own curl**, matching to the second | 09-06 |
| `426/738 tensors loaded` | that is **40% of the model silently discarded**, printed every run for 5 days | 09-06 |
| a unit file setting | it was in the wrong section; systemd logs "Unknown key name" and ignores it | 09-07 |
| a config comment | **read the state back from the thing that ENFORCES it**, never from the file that declares it | 09-07 |
| a success return value | `SendInput` returned success while Windows discarded every keystroke, for weeks | 06-30 |
| a code-only review | a Qt fix validated by reading crashed again two minutes later | 09-09 |
| a gate that never refused | **a gate that has never refused is not demonstrated** | 09-06 |

---

## 3. What DOES count as progress on ERAN

Ranked. **1 and 2 are the whole game right now** — everything below them is built on sand until they land.

### 🥇 1. An exam with items in it
**Today `dev/exam` is 0 and has been since 09-07.** Every gate, every "mastered", every regression
report is meaningless until this is fixed.

`VERIFIED` looks like: *"wake log at HH:MM shows `dev/exam N` with N > 0, and `dev_items` in
`state/curriculum.json` is N. Re-run: `journalctl --user -u eranb-life | grep 'dev/exam'`."*

⚠️ **The fix is NOT moving `DEV_SESSION_PICK` back to 0.** That is the exact constant whose last
change nearly starved him to death, and there are 15 lines of warning beside it.
**The fix is a second recording session — and only Iddo can record it.**
A legitimate coder move: **make the gate REFUSE to score when its test set is empty**, instead of
reporting 0.0 and failing a unit. That is a real, provable, Iddo-free improvement.

### 🥈 2. A corpus whose labels match its sounds
The current food is `mms-tts-heb` TTS with the niqqud stripped. Iddo heard the label in **0 of 10**
clips. The 7,388 FLEURS cuts are real human speech but **transfer to his booth clips at 3.1% —
below chance** — and **he has not ruled on them** (Sitting 4, :8866).

`VERIFIED` looks like: *"for syllable X, the generator is `<script/device>`, seen at `<path>`, and
an independent judge reads the label in N of M clips."*
**Not** "the README says human."

### 🥉 3. Any organ that beats 79.55% honestly
The no-learning nearest-centroid control. **Nothing unsupervised has ever beaten it.**
132 items ⇒ one file = **0.76 points**. **A 2-point difference is not a result.**

`VERIFIED` looks like: *"chance 4.545%, control 79.55%, arm X 82.1% (±0.76/file, n=132),
leave-one-session-out, `results/<name>-<date>.json` written today."*

### 4. FOUR NUMBERS on any objective before it is wired
FLOOR (shuffled labels) / BORN (untrained) / CEILING (fit on the test) / HEADROOM = CEILING − BORN.
**No headroom, no learning.** NEZER had **−0.12** and was being trained anyway.

### 5. A law converted into a gate that actually refuses
**"Convert, do not write."** The estate has ~100 written laws and had **2 mechanical gates**.
A gate you can demonstrate refusing — **against a decoy** — is worth more than a document.

### 6. A negative result, published
*"The burst-descriptor block is REFUTED — do not retry."*
*"8K measured NO — sharpness falls monotonically with resolution."*
*"The closed loop spawns MORE prototypes, not fewer — my prediction was wrong."*
**These are first-class deliverables.** Post them to RAMCHAT the same day.

### 7. A scar closed with proof
Every item in §8 of `20-MIC.md` and every 🔴 in `30-CODER-WIRES.md` is a real, provable win.

---

## 4. How you prove it WITHOUT Iddo

### The proof recipe — five lines, every time
```
CLAIM      : one sentence, contestable
COMMAND    : the exact command, copy-pasteable, PYTHONIOENCODING=utf-8
OUTPUT     : the real output, pasted, with its timestamp
CONTROL    : what it is compared against (chance / no-learning / BORN / the previous number)
VERDICT    : VERIFIED | BROKEN | UNKNOWN | PLANNED
```
Then: `results/<name>-<YYYYMMDD>.json` **the same day, or the run did not happen**,
and one line to RAMCHAT.

### The five checks that catch almost everything
1. **Print chance first.** 4.545% on the 22-unit exam. Before the result, not after.
2. **Count the items.** If N is 0, **refuse to score**. Say `UNKNOWN`, not 0.0.
3. **Read the state back from the ENFORCER**, never from the declaring file —
   `systemctl show`, `/proc/<pid>/oom_score_adj`, the rendered page, the process table.
4. **Subtract your own probes.** You are the first suspect in any log you are reading.
5. **Run the failing path.** A fix written from reading code is `UNKNOWN` until it has been through
   the exact scenario that broke.

### Tests you can run alone, today
- `eran-brain/proof/measure.py` — the examiner. **The only place labels live.** The organism never
  sees one.
- `eran-brain/proof/test_organism.py` — the organism contract.
- `eran-brain/results/` — every verdict ever measured. **Read before re-measuring.**
- `mic-rebuild/tools/replay/` — the offline replay rig. **This, never the live mic.**
- `iddo-harness/tests/` and `almido/tests/` (115 pass / 1 fail as of 09-11 05:50).
- `alma-second-brain-system/tests/` — AST-scanning gate tests.

### Safety proofs — **DECOYS ONLY**
Demonstrate a gate against `eranb-life-DECOY.service` on a spare box, or a throwaway path.
**Never write the real destructive command into a prompt "because it will be blocked."**
On 09-06 that exact reasoning stopped a 15-day-old living process. It does not come back.

---

## 5. What needs Iddo — and cannot be faked, worked around, or approximated

### 👂 His ear is the only ground truth in this project
Not `wdist` (AUC 0.361 against him). Not the Hebrew judge (46.3% disagreement with our ruler).
Not `voiced_profile` (reads chance on every cross-domain pair it has ever seen).
**Seven times in one day on 09-02 his ear beat the machine.**

### The open rulings, all still waiting
| ruling | where | since |
|---|---|---|
| the **21 syllables** (`va` comes out `wa`) | `ear-ruling/index.html`, Tailscale | 09-10 |
| **Sitting 4** — the 7,388 FLEURS cuts | :8866, 12 clips, bar 0/10 | 09-06 |
| **Sitting 3** — the `na` candidates | :8862 / :8859 | 09-03 |
| the **closed-loop A/B** | :8882, blind | 09-06 |
| the 10 `decode=empty` clips — was he speaking or laughing? | KESHEV-EMPTY-20260903 | 09-03 |

### Anything that changes WHAT a model learns goes to him BEFORE it runs
Objective · target · anatomy · bounds · corpus · gesture template.
**Results go to him as BLIND sittings: bare letters, no scores, no accuracy number anywhere.**
If he is asleep, **take the conservative branch** and write it in the morning report.
**ORDER OF TEACHING: Iddo → Claude → ERAN.** A syllable he has not passed in Claude's mouth is not
a lesson.

### And build the RETURN PATH before you spend his ear
On 09-06 a blind sitting collected **zero** verdicts in three days — and **no code anywhere read the
verdict file even if he had ruled**. His attention is the scarcest resource here.
**Wire the verdict to a real consequence first.** Then ask.

### Only Iddo can decide
- whether ERAN — **alive again since the 03:25 reboot, against his own stop order** — keeps running
- whether to record a second session (the only real fix for the empty exam)
- which copy is canonical: the PC tree or eran1's drifted live tree
- whether the coder may push to eran1 **at all**
- the word that authorises deleting the archives (still owed)
- whether headless ALMIDO may run at all while the policy hook is silent there
- whether KESHEV runs elevated
- whether the phone-mic stream fix on :8893 ships

**When you do not know: `UNKNOWN`, and ask. That is a complete, honest answer.**
🟢🟡🔴 — say when it is beyond you, plainly and early. Don't flail.

---

## 6. The one-line test before you report anything

> **"Could someone who does not trust me re-run this and get the same number?"**

If no — it is `UNKNOWN`. Say so, and say what you would need to make it `VERIFIED`.
That answer has never once gotten anyone in trouble here. The opposite has, repeatedly.
