# 🪟 BROKEN WINDOWS LAW — חוק החלונות השבורים: if it's not working, fix it IMMEDIATELY. Test the REAL output, not a proxy.

# KESHEV-4D — the fleet workers' own mic app. Fable is king.

**Iddo's charter (2026-08-18 06:10–06:20, dictated live):** the four 4D workers build KESHEV
from scratch, their own app — but under command: *"You control them, you tell them how and who
and what to build. It's not a democracy."* And: *"make sure they don't behave like a common
Tuesday anarchist local branch meeting — everyone disagrees, nothing happens, no revolution."*

## The protocol (מלכות, לא מועצה)

1. The king assigns each worker ONE module per round, with the binding scars quoted in the order.
2. The worker returns code + tests. No worker sees another worker's module in the same round.
3. The king runs the tests on the real machine. **Accepted** or **rejected with one reason** —
   recorded in `KINGS-LOG.md`. A rejected module is reassigned (same worker once, then another).
4. No votes, no debates, no consensus rounds. Disagreement = write better code next round.
5. **No audio device is ever opened by this app until it beats KESHEV A on the acceptance
   baseline** (mic-rebuild\INSIGHTS-FOR-KESHEV2.md §7). KESHEV A holds the mic. ONE-MIC LAW.

## The law every module inherits

- Python 3.12 stdlib only unless the order says otherwise. No torch on the PC, ever.
- Every guard ships with (a) a reachability test — it CAN fire on realistic input — and
  (b) a wiring test — production actually calls it. "Present, correct, not in the path" = build failure.
- Every drop/refusal journals one line. Never lose speech, never lie about it.
- Sacred Audio: no audio OUTPUT call sites; Bluetooth is never a mic; `_NEVER_MIC` is a
  source-level tuple, immune to config.
- Binding scars: `D:\CLAUDE\mic-rebuild\INSIGHTS-FOR-KESHEV2.md` (all of it) +
  `D:\CLAUDE\keshev-2\DECISIONS.md` (the 9 rulings) + `ADDENDUM-20260818.md` here.

## Round 1 assignments (dispatched 2026-08-18 ~06:20)

| worker | module | the scar it must honor |
|---|---|---|
| qwen3-coder-next-fp8 | `app/journal.py` + `tests/test_journal.py` | closed event vocab; append-only JSONL; one-line-per-fact; unknown event name = error |
| glm-4.7-flash | `app/devicelaw.py` + `tests/test_devicelaw.py` | USB-only capture; `_NEVER_MIC` source tuple (WH-1000\|Hands-Free\|Headset\|Bluetooth); IDLE_NO_MIC structural |
| gpt-oss-120b | `app/spool.py` + `tests/test_spool.py` | write-ahead BEFORE enqueue; evict=drop record keep file; every drop journals; sweep must be O(new), not O(journal) — A paid 15 s stalls for re-reading the whole journal per sidecar |
| nemotron-3-super | `app/textguard.py` + `tests/test_textguard.py` | logprob floor must be REACHABLE (A's floor sat below the whole real distribution and never fired once); hallucination blocklist; language whitelist argmax, `language=None` unrepresentable |

*לזכרה של עלמה ז״ל.*
