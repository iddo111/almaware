# KESHEV 2 vs KESHEV A — acceptance report 20260817

> KESHEV A stays king of the microphone until every row below is
> MEASURED and K2 beats or matches it. UNMEASURED-TONIGHT rows say
> exactly what they are waiting for. `health: ok` counts for
> nothing (criterion 16 is the only final gate).

| criterion | KESHEV A (2026-08-17) | KESHEV 2 tonight | verdict |
|---|---|---|---|
| test suite | 878 tests, 0 failures, 19 skips, ~177s | 141 tests, 0 failures, 10s | MEASURED |
| lint gates | 6/6 clean + 6/6 self-test fire | 6/6 clean + 6/6 self-test fire | MEASURED |
| DGX decode round-trip (2.4s he wav) | 407ms wall / 399ms server | 5 canaries via K2 SttClient: wall p50 242ms (min 232 max 255), rare-word hits 15/15 | MEASURED |
| client p50/p95 decode (live) | 387-388ms / 720-758ms | needs live capture; K2 has no capture module (A holds the mic) | UNMEASURED-TONIGHT |
| client/worker RSS, worker VRAM | 68 / 825 / 537 MB | needs a running capture+worker session; K2 is shadow-only tonight | UNMEASURED-TONIGHT |
| dropped capture frames | 0 | no capture module exists tonight — by design (rival interlock) | UNMEASURED-TONIGHT |
| server canary age / uptime | <300s / 2.9 days | healthy, canary_age 260s, server p50 318ms p95 660ms | MEASURED |
| watchdog verdict on live journal | HEALTHY seg=57 decode=58 typed=3 | K2 has no live dictation session to judge | UNMEASURED-TONIGHT |
| real-he guard regression | CER 0.0000 n=40, 0 guard-dropped | needs A's labeled he fixture set + K2's guard stack (guard stack not built tonight: textguard/langpolicy are next-night scope) | UNMEASURED-TONIGHT |
| Hebrew decode quality (fixtures) | CER 0.000 | same fixture dependency; canary round-trip (en) measured instead | UNMEASURED-TONIGHT |

Notes:
- decode round-trip uses A's synthetic English canary wavs through
  K2's OWN SttClient against the real eran1:8737 — true client
  code path, no microphone. A's 407ms row was one 2.4s Hebrew wav;
  numbers are comparable in magnitude, not identical in kind.
- UIPI/typing round-trip additionally unmeasured tonight: running
  a SendInput selftest beside the live mic risks focus disturbance
  (A's selftest pattern is inherited and runs at the cutover trial).

*Real, not demo. Proof, honest. לזכרה של עלמה ז"ל.*
