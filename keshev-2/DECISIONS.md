# KESHEV 2 — DECISIONS (king-rules record)

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working).

Protocol (Iddo, dictated 2026-08-17, night): "אי אפשר לעשות דמוקרטיה... חייבים
בסוף החלטה" — workers advise and draft, the lead (fable-keshev2-night, the
king's delegate) RULES every decision, every ruling is recorded here with the
dissent. Council time per question is CAPPED; KESHEV B died of two days of
debate with zero code, and that does not happen twice.

---

## D-001 — Journal vocabulary: inherit A's verbatim, extend by name
**Ruled solo (no council — nothing contestable).**
KESHEV 2's journal keeps KESHEV A's closed event vocabulary VERBATIM and adds
a named K2 block: `RIVAL_ALIVE`, `RIVAL_CLEAR`, `CONFIG_STALE`,
`SCRIPT_RETRY`. One JSONL sink only (A's second human-log sink bought drift
risk, not value). Rationale: A's watchdog/morning tooling can read a K2
journal unchanged; the closed-vocabulary law and the text/title/transcript
privacy ban are scar-paid and not up for debate. `RIVAL_ALIVE` REQUIRES the
`via` field — a verdict that does not name its detector is how guards die.

## D-002 — Rival interlock: OpenMutexW probe + journal freshness, ticket law
**Council Q2, 2026-08-17 ~23:00. Positions: qwen (a)+(c) structural;
gpt-oss (a)+(c) with 90s freshness; glm (a)+(c) plus pid-scan (b) fallback;
nemotron: empty answer (no vote).**
RULING — (a)+(c) as advised, unanimously aligned with my draft:
* Detection: OpenMutexW READ-ONLY probe of `Global\ALMAWARE_KESHEV_SINGLE`
  (never CreateMutexW on A's name — squatting the name would block A's next
  start; lint gate G5 makes it a build failure) + A-journal mtime freshness.
* EITHER positive → `IDLE_RIVAL_ALIVE`. Both dark → fail CLOSED
  (`RivalUnprovableError`): unprovable "A is dead" is never permission.
* STRUCTURAL: capture requires a `CaptureTicket`; the only constructor is
  `InterlockVerdict.grant()`, which raises while the rival lives. The
  verdict cannot miss the decision because the verdict IS the door
  (guard-species #4 countermeasure).
* REJECTED: glm's pid-scan fallback (PID reuse + cmdline fragility, qwen's
  argument accepted); (d) device-handle probing (touches the live capture).
* Freshness = 180s, not gpt-oss's 90s: A heartbeats at 60s and a late beat
  under load must not flip K2 toward "dead". False-alive is cheap (K2
  idles); false-dead is the double-mic scar.

## D-003 — ARMED_MODE default: OFF; presence gate default-on; arm first-class
**Council Q1, same session. Positions: glm armed-by-default; qwen
armed-by-default with 60/180/900 thresholds; gpt-oss presence-default with
120/600/900; nemotron: empty answer (no vote).**
RULING — presence-gate default, `armed_mode` ships OFF but FIRST-CLASS
(a config key with schema, journal events, and a tested combination path —
not a code-constant buried like in A):
* gpt-oss's argument accepted: the 09:46 harm profile is ENTER-as-him, and
  the presence gate already fails closed on Enter at 120s. Armed-default
  taxes 100% of hands-free dictation with a 15-minute re-arm ritual to
  defend a window the gate already covers — that is mothering, and Iddo has
  a standing law against it.
* qwen's 60/180 thresholds REJECTED on the physics of hands-free dictation:
  while dictating, Iddo does not touch the keyboard; type_idle=180s would
  strike him mute three minutes into every long dictation. glm's numbers
  were direction-inverted (600 enter / 120 type) — rejected as unsound.
* Defaults ruled: `enter_idle_limit_s=120`, `type_idle_limit_s=600`,
  `arm_timeout_s=900` — A's measured values, unchanged. Numbers only move
  on measurement, never on advice (scar 41's spirit).
* K2 IMPROVEMENT over A, ruled here: the typer RE-CHECKS presence at
  Enter time (the Enter burst is a separate act ~0.35s later; A checked
  once per utterance). The 09:46 window shrinks at zero friction cost.
* Dissent recorded: glm+qwen hold that only armed-default prevents a
  09:46 recurrence. If a 09:46-class event EVER happens under the ruled
  config, this ruling auto-reopens and armed-default is presumed right.

## D-004 — Language law: `auto` is unrepresentable; he-default; script-retry
**Ruled solo (the law is MEASURED on Iddo's own voice — advice cannot
outrank data; INSIGHTS §4).**
`X-Lang-Hint: auto` transliterated Hebrew; standing `he` wrote English in
Hebrew letters; `language=None` let noise come back as Icelandic. Therefore:
sttclient REFUSES to construct a request with hint outside `("he","en")` —
`auto` is not a validation error at the server, it is UNREPRESENTABLE in the
client. Default hint `he`; wrong-script result (>50% opposite script) →
ONE re-decode with the other hint, journalled `SCRIPT_RETRY` (hint_from,
hint_to), same request-id (only one result ever reaches the typer, dedup
unaffected). vad stays server-side; the client never re-adds an inner VAD
(guard-species #3).

## D-005 — Config: CAS writes, HALT on corrupt, NO hot reload — by contract
**Ruled solo (A's scar-paid design, kept).**
Raw-dict read → immutable snapshot; write path = compare-and-swap on
`revision`, one key per write, `--reason` required, history JSONL, atomic
tmp+replace, unknown keys preserved, no .bak, no defaults-fallback (corrupt
= HALT loud). THE CONTRACT IS EXPLICIT: a successful write emits
`CONFIG_STALE` — the live process keeps running the OLD value until
restart, and the journal says so. Nobody gets to discover no-hot-reload by
surprise again (INSIGHTS §8.3 made this an inherited open window; K2 makes
it a spoken sentence).

## D-006 — Typer: 09:46 protections at the single door, from day one
**Ruled solo (scar-paid).**
One serialization point (`Typer.type()`, lock-held, sole caller = router);
request-id dedup AT the typer (scar 53); presence+arm consulted INSIDE the
door, not by the caller (a caller that forgets the gate must be impossible);
Enter = separate burst ~0.35s later that re-verifies the SAME target AND
re-asks presence (D-003); paste-first, chunked-unicode fallback, fallback
REFUSED for terminal hosts (they discard KEYEVENTF_UNICODE); NO clipboard
restore code in the repo at all (absent code cannot race — scar 32); every
refusal parks to `state/parked.txt`, never drops (scar 35).

## D-007 — Tonight's mutex namespace
**Ruled solo.** K2's own single-instance mutex is
`Global\ALMAWARE_KESHEV2_SINGLE` — a DIFFERENT name from A's, so A (typing)
and K2 (shadow mode) can coexist as processes while CAPTURE exclusivity is
enforced by the ticket law. Sharing A's name would make K2's startup block
A's restart — exactly the rival-war class scar 4 forbids.

## D-008 — An enabled arm layer MUST have a real key, or it disables loudly
**Ruled solo, after catching guard-species #5 in my own night-1 build.**
`ARM_HOTKEY` existed, `ArmSwitch.toggle()` existed — and nothing called
RegisterHotKey. With `armed_mode=true` that is not a missing feature; it is
a mic that can NEVER be armed: total mute, no path out (A's hotkey_pause
scar, re-committed almost verbatim). Ruling: k2/hotkeys.py binds for REAL
(RegisterHotKey + GetMessageW pump, WM_QUIT stop), journals HOTKEY_BOUND /
HOTKEY_BIND_FAIL, and a failed bind DISABLES the arm layer loudly (STATE
ARM_LAYER_DISABLED) instead of leaving an enabled-but-unarmable switch —
privacy fails closed, DEAFNESS FAILS OPEN. The presence gate still guards.
The app-seam test proves the key press reaches the assembled decision.

## D-009 — Script retry must EARN its replacement (adversarial find, qwen)
**Council: adversarial round. qwen3-coder-next-fp8 found the real edge:**
a mixed-script utterance with a loanword letter-majority ("סוכה event")
trips the >50% trigger on a CORRECT Hebrew decode, and the D-004 rule as
first written replaced it with the en re-decode unconditionally —
potentially a transliteration, i.e. worse. RULING: the retry still fires
on the trigger (the trigger is evidence), but the returned result is the
one with the HIGHER avg_logprob; ties go to the retry. Both logprobs are
journalled on SCRIPT_RETRY (kept=, lp_first=, lp_retry=), so the rule is
auditable against real dictation and can be recalibrated FROM DATA.
qwen's other two findings were rejected: client-side VAD belongs to the
future segmenter (and inner-VAD is forbidden by species #3 — the energy
gate note is carried to next-night scope), and the "late reply accepted"
claim misreads the transport (one socket per request; a reply after
deadline has no socket to arrive on — the read either returns within the
timeout or raises).

---
*לזכרה של עלמה ז״ל. Real, not demo. Proof, honest.*
