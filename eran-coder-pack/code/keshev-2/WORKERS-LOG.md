# KESHEV 2 — WORKERS LOG (the 4D crew's contributions, kept vs rejected)

> 🪟 **BROKEN WINDOWS LAW:** if it's not working, fix it IMMEDIATELY.

Router: http://<lan-ip>:8010 (eran1). Crew: qwen3-coder-next-fp8,
glm-4.7-flash, nemotron-3-super, gpt-oss-120b. Protocol: workers advise and
draft; the lead reviews, hardens, tests, and RULES (DECISIONS.md). Raw
outputs are preserved under `harness/council/`, `harness/drafts/`,
`harness/adversarial/`.

## Council round (2 questions, 4 workers each, ~2 min wall)

| worker | Q1 armed-default | Q2 rival-interlock | outcome |
|---|---|---|---|
| qwen3-coder-next-fp8 | armed-by-default, 60/180/900 | (a)+(c), structural verdict | Q1 position REJECTED (60/180 would mute hands-free dictation at minute 3 — physics of the workload); its argument against pid-scan ACCEPTED into D-002 |
| glm-4.7-flash | armed-by-default, inverted thresholds | (a)+(c) plus pid-scan fallback | Q1 numbers rejected as direction-inverted; Q2 pid-scan fallback REJECTED (PID reuse/cmdline fragility) |
| nemotron-3-super | EMPTY (reasoning consumed budget) | EMPTY | no vote either question |
| gpt-oss-120b | presence-default, 120/600/900 | (a)+(c), 90s freshness | Q1 position ACCEPTED (ruling D-003); 90s freshness tightened to 180s by ruling (false-alive is cheap, false-dead is the double-mic scar) |

## Draft round

| draft | worker | verdict |
|---|---|---|
| tools/lint.py (6 gates + self-test) | qwen3-coder-next-fp8 | **KEPT, heavily reworked.** Kept: G1 AST shape, G2/G4/G5/G6 regex families, gate/self-test structure. Rejected: `get_production_files` monkeypatch self-test (replaced with explicit file-list parameters); `endswith("k2/configstore.py")` path-separator bug that would have flagged configstore itself on Windows; harness/ in the production surface. |
| device-law adversarial cases | glm-4.7-flash | **KEPT ~80%.** Its "Audio Relay" (spaced) case EXPOSED A REAL GAP — the tuple had only "audiorelay"; marker added. Two classifications were hallucinated and corrected in tests: "Microphone (Realtek High Definition Audio)" claimed FORBIDDEN via reasoning that fabricated substring matches (it is UNKNOWN), same for a Hebrew-named mic. |

## Adversarial round (find the guard that cannot fire)

| module | reviewer | outcome |
|---|---|---|
| k2/interlock.py | gpt-oss-120b | see harness/adversarial/ + triage below |
| k2/typer.py | glm-4.7-flash | see harness/adversarial/ + triage below |
| k2/presence.py | nemotron-3-super | see harness/adversarial/ + triage below |
| k2/sttclient.py | qwen3-coder-next-fp8 | see harness/adversarial/ + triage below |

**Triage — interlock / gpt-oss-120b (retry at 4000 tokens): 1/3 partially
valid.** F3 half-accepted: NULL+ACCESS_DENIED on K2's own mutex (a K2
under a different ELEVATION holds the name) crashed with OSError instead
of exiting 11 as a duplicate — fixed, with injected-create tests proving
both the new branch and the still-loud unknown-error branch fire. Its
proposed fix ("treat any nonzero GetLastError as duplicate") was rejected
as over-broad. F1 rejected: the mutex is kernel-authoritative for
liveness (OS-released on death); requiring A's journal to stay readable
forever would forbid capture for all time once A is archived. CAVEAT
RECORDED for the capture milestone: the future device-open must demand a
FRESH ticket (granted_at), closing the millisecond A-startup race. F2
rejected: threat-model mismatch — the ticket token guards against
accident in our own process; a "determined attacker" can forge the
VERDICT itself, and no Python privacy trick changes that.

**Triage — sttclient / qwen3-coder-next-fp8: 1/3 valid, and the 1 was
worth the whole round.** F2 (mixed-script loanword-majority trips the
retry trigger on a CORRECT decode) is REAL — accepted as ruling D-009:
retry now wins only on higher avg_logprob, both scores journalled, plus a
regression test ("סוכה event"). F1 (no client-side VAD) rejected for THIS
module — silence gating belongs to the future segmenter, noted in
next-night scope; inner VAD stays forbidden (species #3). F3 (late reply
accepted after deadline) rejected — misreads the one-socket-per-request
transport; a post-deadline reply has no socket to arrive on.

**Triage — presence / nemotron-3-super: EMPTY (third empty of the
night, at max_tokens=1600). Declared out for tonight; its reasoning
consumes the budget before content on every long prompt through this
router. Follow-up for the 4D fleet owners: nemotron needs either a
reasoning-suppressed route or a much larger completion budget.**

**Triage — typer / glm-4.7-flash: 0/3 valid.** All three findings claim
code is UNREACHABLE (TERMINAL_EXES check, FOCUS_BLOCK emission, the Enter
recheck emission) — and all three paths are executed by passing tests
(`test_paste_failure_in_terminal_parks_never_unicode`,
`test_own_window_hard_block`, `test_enter_rechecks_gates_at_enter_time`).
Two findings misread line order (emissions come BEFORE the returns). The
irony is noted: the reviewer hunting guards-that-cannot-fire produced
findings-that-cannot-fire; the reachability TESTS are the real defense.

## Score tonight (final)

* Real catches by workers: 3 — glm's spaced "Audio Relay" (tuple gap),
  qwen's mixed-script retry edge (ruling D-009 + code change + test),
  gpt-oss's ACCESS_DENIED elevation duplicate (code change + 2 tests).
* Positions adopted into rulings: gpt-oss on armed-default (D-003), the
  unanimous (a)+(c) interlock design (D-002).
* Findings rejected with reasons on record: 7 (3 glm typer unreachability
  claims disproven by executing tests, qwen's client-VAD + late-reply,
  gpt-oss's journal-required + token-privacy).
* Hallucinations caught by lead review: 3 (2 glm device classifications,
  1 qwen lint self-test design that could not survive Windows paths).
* nemotron-3-super: 0 usable outputs in 3 attempts (empty content at
  max_tokens=1600 twice and 1600 again on adversarial) — needs a
  reasoning-suppressed route or a much larger budget on this router;
  flagged to the 4D fleet owners.
* Draft keep-rate: qwen lint draft kept-reworked; glm device cases kept
  ~80%. Every kept line passed lead review + tests before landing.
