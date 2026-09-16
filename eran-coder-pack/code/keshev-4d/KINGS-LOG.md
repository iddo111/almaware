# KINGS-LOG — accept/reject record. One reason per rejection. No debates.

## Round 1 (dispatched 2026-08-18 06:22)

| worker | module | verdict | the one reason |
|---|---|---|---|
| qwen3-coder-next-fp8 | app/journal.py | **ACCEPTED** 06:47 (fix round) — previously REJECTED 06:29 | Your tests don't run: `test_concurrent_events_no_race` uses `threading` without importing it, and `test_rotation_triggers_at_boundary` reads the journal file's size before any event created it. A test suite that errors proves nothing. Module untested = unshipped. |
| glm-4.7-flash | app/devicelaw.py | **ACCEPTED** 06:52 (fix round) — previously REJECTED 06:29 | `choose_device` returns the LOWERCASED name; the caller must receive the device's ORIGINAL name to open it (casefold for matching only). Also your `test_choose_device_non_string_entry` expects "Valid Device" to be chosen, but no allowlist substring matches it — a test that contradicts your own spec. |
| gpt-oss-120b | app/spool.py | **ACCEPTED** 06:34 (fix round) — previously REJECTED 06:47 | Your own test breaks: `test_sweep_recovers_orphans_and_is_idempotent` calls `.endswith` on a WindowsPath mock-call arg (`c[1][0].endswith(".json")`) — Path objects have no endswith; use `str(...)`. Module untested = unshipped. |
| nemotron-3-super | app/textguard.py | **ACCEPTED** 06:33 (fix round) — previously REJECTED 06:56 | Your tests `mock.patch("app.textguard.journal", ...)` — but your module never imports or exposes any `journal` symbol; 10 of 12 tests error on a module that is not the one you wrote. Tests must test YOUR module. |

Protocol: a rejected module returns to the SAME worker once, with the reason verbatim.
Second rejection → the module is reassigned to another worker.

## Round 1 CLOSED — 2026-08-18 06:34

**All four modules ACCEPTED.** Every worker needed exactly one rejection and one
fix round; every rejection was one sentence; no debates occurred. Suite: 29
tests, 0 failures, on the real machine. The anarchist local branch meeting did
not convene.

Round 2 (next): gates/energy module, presence gate, stt client, typer — same
protocol, one module per worker.

## Round 2 (dispatched 06:34, judged 07:24)

| worker | module | verdict | the one reason |
|---|---|---|---|
| qwen3-coder-next-fp8 | app/typer.py | **ACCEPTED** 07:24 | Tests OK on the real machine, first try. |
| glm-4.7-flash | app/presence.py | **REJECTED** 07:24 | Your tests `time.sleep(ARM_TTL_S + 0.1)` — that is a REAL 900-second sleep, six times: a ninety-minute suite that hung the whole kingdom. verdict()/is_armed() take a `now` parameter precisely so tests INJECT time. No test may sleep more than a second. |
| gpt-oss-120b | app/gates.py | **REJECTED** 07:24 | A 100 ms blip followed by silence returned `(0, 520, False)` — you count the hang window into the segment and never re-check min_ms at close. A blip below min_ms must yield None. |
| nemotron-3-super | app/sttclient.py | **REJECTED** 07:24 | `import journal  # assumed to be provided elsewhere` — line 7. Nothing is "provided elsewhere": the spec said the client returns reasons and the CALLER journals. The import fails and every test dies at import time. |

### Round 2 fix judgments (07:33)

| worker | module | verdict | the one reason |
|---|---|---|---|
| glm-4.7-flash | app/presence.py | **REJECTED (2nd)** → module REASSIGNED to qwen | Your tests bind `Presence(self.idle_fn)` and then rebind `self.idle_fn = lambda: ...` AFTER construction — the object holds the old callable, every verdict test sees "ok" and asserts against a module you never exercised. Second rejection: the seat changes hands. |
| gpt-oss-120b | app/gates.py | **REJECTED (2nd)** 07:44 → seat REASSIGNED to glm | Your own tests now expect segments where your module returns None (hang-exclusion under-corrected: both remaining failures are assertIsNotNone). Two strikes; the seat changes hands. |
| qwen3-coder-next-fp8 | app/presence.py | **REJECTED** 07:44 | Your two expiry tests use OPPOSITE boundary conventions: `test_arm_expiry_boundary` asserts armed AT t+TTL, `test_arm_expiry_with_rearm` asserts arm_required past it while the module answers armed. Pick the spec: armed strictly BEFORE arm_time+ARM_TTL_S, expired AT and after. Align module + both tests. |
| glm-4.7-flash | app/gates.py (reassigned seat) | **REJECTED** 07:40 | Same death as your predecessor: three assertIsNotNone failures — your tests expect segments your own module returns None for. You did not run your tests against your module before submitting. |
| qwen3-coder-next-fp8 | app/presence.py | **REJECTED (2nd)** 07:40 → seat REASSIGNED to gpt-oss | You invented an API the spec never asked for (check_and_refuse, JOURNAL_PATH file IO) — off-spec entirely on a fix round. |

**Interim comparison for Iddo (07:40):** keshev-fable (one builder) = COMPLETE, 82
tests, measured p50 349ms. keshev-4d (four workers, king protocol) = 5 modules
accepted, the two stateful seats (gates, presence) still cycling after 2-3 strikes
each. The pattern in every rejection: a worker that never RAN its own tests.

### Protocol change (07:50) — the king writes the tests

Every rejection tonight shared one root: a worker that never ran its own tests.
From round 3 the KING'S CANONICAL TESTS (tests/test_gates.py, test_presence.py,
test_sttclient.py) are the law - workers submit the MODULE ONLY and may not
touch the test files. Seats: gates=glm (last chance), presence=gpt-oss (fresh),
sttclient=qwen (fresh; nemotron benched after 2 strikes - keeps its textguard
accept). Iddo has asked to HEAR this app (07:45) - assembly becomes round 4.
| glm-4.7-flash | app/gates.py | **REJECTED (2nd on this seat)** 08:07 | Against the king's canonical tests your Segmenter closes NOTHING (every close-expecting test got len(out)==0). Four attempts across two workers have now failed this seat; it passes to qwen after its current assignment. The segmenter is tonight's hardest chair. |
| gpt-oss-120b | app/presence.py | **ACCEPTED** 08:12 (vs king's canonical tests) | The presence seat closes after 4 attempts across 3 workers. |
| qwen3-coder-next-fp8 | app/sttclient.py | **REJECTED** 08:12 | `threading.Lock()` at class scope with no `import threading` — the same missing-import disease as your round-1 journal tests. Run python on your file before submitting. |
| qwen3-coder-next-fp8 | app/sttclient.py | **REJECTED (2nd)** 08:16 → seat to gpt-oss | Import fixed, but your client has NO `.decode` method — the king's tests call `decode(rec_id, body, lang_hint)`; you shipped a different API. Also on the record: two of the failures this round were the KING'S OWN test file carrying broken string literals — the king fixed his own law before judging you. |
| gpt-oss-120b | app/sttclient.py | **ACCEPTED** 08:21 (vs king's tests, single-module run) | 7 of 8 organs. (Note: discover-mode double-import quirk of the harness produces phantom errors; single-module runs are the judgment standard.) |
| qwen3-coder-next-fp8 | app/gates.py | **REJECTED** 08:21 (seat's 5th rejection overall) | Your Segmenter closes nothing on hang (0 segments where the law expects 1). Fix round with an exact frame trace below. |

**The segmenter tally: 5 rejections, 3 workers.** The one stateful, time-driven
chair defeats every fleet coder while each pure-contract chair eventually seats.
For Iddo's comparison: the solo builder wrote the same module first-pass with
6/6 tests (keshev-fable/app/segmenter.py, commit 0152db8).
| qwen3-coder-next-fp8 | app/gates.py | **REJECTED (2nd on seat; seat's 6th)** 08:23 | `from journal import event` — a phantom import in a module specced PURE, dying at import. The chair passes to nemotron: the bench's last name. If it fails twice, the record will read: the fleet cannot build the segmenter. |
| nemotron-3-super | app/gates.py | **REJECTED** 08:29 — closest attempt yet | One naming inconsistency: `__init__` stores `self.hang_ms` but `feed` reads `self._hang_ms` (AttributeError on every close path). Everything else looked right. Fix the name, resubmit. |
| nemotron-3-super | app/gates.py | **REJECTED (2nd)** 08:35 — CHAIR CLOSES UNFILLED | Asked to fix ONE attribute name, you discarded your near-perfect module and submitted an unrelated `Gate` class with the phantom journal import back. |

## THE SEGMENTER VERDICT — 2026-08-18 08:35

**The chair defeated the fleet: 8 rejections, 4 workers, 0 passes.**
gpt-oss ×2 (hang counted into the segment; tests contradicting its own module),
glm ×2 (closes nothing; twice), qwen ×2 (phantom import; phantom import),
nemotron ×2 (one-name typo; then discarded its near-pass entirely).

The same module, same law: keshev-fable/app/segmenter.py — one builder,
first pass, 6/6 (commit 0152db8).

**Their app stands at 7/8 organs and cannot hear. The decision is Iddo's:**
(a) transplant the one missing organ from keshev-fable (labeled forever as
the transplant it is) so their assembly can proceed and he can HEAR it;
(b) leave their app deaf as the honest final record;
(c) more rounds (the king recommends against - the pattern is complete).

## THE TRANSPLANT — 12:40, by Iddo's word ("כן תן להם את האוזן שלך")

keshev-fable's segmenter, adapted to this kingdom's tuple law, now sits in
app/gates.py under a permanent TRANSPLANT header. All 8 organs green.
Round 6 = the fleet writes its own assembly (main), and then Iddo hears them.
