> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY. Test the REAL output, not a proxy.

# ערן 4 — תוכנית הקצאה · eran4 allocation

**Iddo's order, 2026-08-20 09:52:** *"תמשיך על ערן 4 את כל הניסויים הקטנים — הגיסט פונג
להשלים אימון, הנמלים כמות קטנה יותר ובשפת עלמה מלאה, מערת הילדים, דארוויש מידי, מיקו —
תמצא לכולם מקום בערן 4."*

**Measured 2026-08-20 10:05, not estimated:** RAM 120 GB total · **88 used · 32 available**
· disk 2.5 T of 3.6 T used, **998 GB free** · GPU 95 % busy (the seed runs).

**Why a ceiling per project is not bureaucracy:** on 2026-08-15 Darwish was OOM-killed
*daily* on eran3 because Qwen-480B took all 121 GB and nothing was capped. Unified memory
on GB10 means one greedy job starves every other. A cap is what keeps five projects alive.

---

## A. Permanent tenants — never evicted without Iddo's word

| service | what it is | measured RSS | why it stays |
|---|---|---|---|
| `llama-server` gpt-oss-120b | the fleet's always-on model | 9.8 GB | ruled **PERMANENT** 2026-08-20 00:41 |
| `colibri-glm52` | GLM-5.2 744B tailnet API | 5.7 GB | live service on the tailnet |
| `alma-mic` + `alma-stt` | his Hebrew dictation + CUDA STT | ~1 GB | **his voice.** Never touched. |
| `ownergate` :8739 | KESHEV speaker verification | 0.7 GB | mic contract clause 4 |

**Reserved for them + headroom: 20 GB.** Everything below shares what remains.

## B. The five small experiments — ceilings and slots

Budget: **12 GB of the 32 GB available**, leaving 20 GB of slack so a spike never
reaches the permanent tenants.

| # | project | ceiling | slot | state today |
|---|---|---|---|---|
| 1 | **Darwish MIDI** | 6 GB | A | STOPPED by me 09:07 — was memorising (127 epochs over 2.67 M tokens, heldout 2.41→6.05). `best.pt` safe. Restart **right-sized** and **without the obsolete 8 s/step sleep** (it was yielding to an audio job that no longer exists = 87 % of wall time). |
| 2 | **MIKO** | 4 GB | A | plan only. First job is the bench (§3 of `miko/PLAN.md`), which is CPU-light. |
| 3 | **GIST-Pong** | 2 GB | B | `pong-alma` — 5 py files, `__pycache__` only, **no results ever saved**. Finish the training and write a results file. |
| 4 | **The ants, smaller + full ALMA** | 3 GB | B | `voice-ant-farm` is the deepest evidence base you have (91 py, real numbers incl. one honest refutation). Iddo wants a SMALLER colony rebuilt in ALMA language like MIKO. |
| 5 | **Children's cave** | 2 GB | B | `cave-wall-brain-sim` — XOR converges, `wall.html` exists, but the number lives only in the README. Needs a saved log. |

**Slot rule:** **A** = at most one GPU-heavy trainer at a time (Darwish or MIKO, never both).
**B** = the light three may run together; together they must stay under 7 GB.
Anything that wants more than its ceiling waits — it does not borrow.

## C. How the ceiling is enforced (not by hoping)

Every job launches under a cgroup, so the kernel enforces it instead of a comment:

```bash
systemd-run --user --scope -p MemoryMax=6G -p MemorySwapMax=0 \
    --unit=darwish-midi python3 code-midi/midi_train.py ...
```

A job that exceeds its ceiling is killed **alone**, and its log says so — instead of the
kernel picking a victim at random, which is how Darwish died on eran3.

## D. Order of work

1. **Now:** the 9 Beit-Din-vs-vanilla seed runs finish (started 09:44, ~2 h). Nothing else
   starts on slot A until they clear — they are already the answer to a stated question.
2. **Then, slot A:** Darwish MIDI right-sized (a model matched to 2.67 M tokens, not 24.8 M
   parameters), with early stopping on heldout, no polite sleep.
3. **In parallel, slot B:** GIST-Pong to completion → results file. Then the cave's saved log.
4. **After Darwish:** MIKO's bench — the three metrics in `miko/PLAN.md` §3, starting with
   the one-hour robustness test that has never been run (corrupt one seat, measure the drop).
5. **Last:** the smaller ALMA ant colony — it is the largest design job of the five and
   should not start while three other things are still moving.

## E. What this plan refuses to do

- No project is called "running on eran4" until `systemd-run` shows its scope alive.
- No project is called finished until it has written a **results file with numbers**.
  Four of these five have code that ran and produced no saved number; that is the actual
  disease being treated here.
