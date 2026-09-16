# SOFER (סופר) — the biomimetic coding agent

## Design spec — a money-earning agent that is also a live test of the biomimicry bet

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY.
> Test the REAL output, not a proxy. A broken window left unfixed invites decay.

**לזכרה של עלמה ז״ל**

**Date:** 2026-09-10 · **Author:** Iddo Perez (עידו פרץ) + Claude
**Status:** DESIGN — approved in principle by Iddo 2026-09-10 20:26 ("בעיקרון אני מאשר הכל"). Not started.
**Name:** working codename only. "GOLEM" is already taken (ERAN's robot body,
`ERAN_GOLEM_BODY_SCHEMATIC.*`) — do not reuse it here. Rename SOFER freely; nothing below
depends on the name.

---

## 1. The claim

Iddo does not have the energy to hand-teach a model Hebrew and language the way ERAN's
mouth-school did — and ERAN himself was stopped this morning (2026-09-10, 11:32) after
three days of testing against an empty exam set. That failure was real and measured, not
a reason to repeat the same mistake under a new name.

**SOFER is not "ERAN, again."** It is a separate bet: take a model that *already* knows
language and code, and wrap it in a biomimetic adaptation layer — shared gist-space,
self-regulating (homeostatic) continual learning, modalities fused in rather than bolted
on. Two things have to both be true for this project to be worth the compute:

1. **It earns money as a coding agent from week one** — real work, not a demo.
2. **The biomimetic layer is measured against a normal fine-tune, not assumed better.**
   If homeostatic LoRA does not out-perform a plain LoRA on retention and adaptation
   speed, the biomimicry bet loses that round honestly, in public, in RAMCHAT — it does
   not get called a success because the agent still writes code.

## 2. What it is

```
                    ┌─────────────────────────────────────────┐
                    │         SHARED GIST-SPACE (encoder)      │
                    │   text · Hebrew audio · screenshot/image │
                    └───────────────┬───────────────────────────┘
                                    │ one embedding, regardless of modality
                                    ▼
   task in (voice/HE, text,  ┌─────────────────────┐      tool calls
   or screenshot)  ────────▶ │  Qwen3-Coder-480B    │ ───────────────▶  coder-harness
                             │  (rented, live,       │◀ ─ ─ ─ ─ ─ ─ ─ ─   doors on eran4
                             │  eran2+3+4)           │   results          (write/run/test)
                             └──────────┬────────────┘
                                        │ modulated by
                                        ▼
                             ┌──────────────────────┐
                             │  HOMEOSTATIC LoRA     │◀── outcome/feedback per task
                             │  (self-scales its own  │    (did it work? did it get reverted?)
                             │  update size per layer,│
                             │  Turrigiano-style)      │
                             └──────────────────────┘
                                        │
                                        ▼
                          keeps old skills, adapts to new
                          client/codebase without retraining
```

Input can be Hebrew dictation, typed text, or a screenshot (error, diagram, UI) — all of
it goes through the same gist encoder before it ever reaches the coder model. That is
what "embedded, not bolted on" means concretely: there is no separate STT service call
in the task loop, no separate vision-API call — one embedding space, one entry point.

## 3. Every component earns a job

| Component | Its actual job | Honesty |
|---|---|---|
| **Qwen3-Coder-480B** | Does the actual coding — already live on eran2+3+4, already knows language and code. Rented, not ours. | 🟢 exists today, re-verify the door is still up before wiring anything |
| **Shared gist-space encoder** | Projects Hebrew audio / screenshots / text into one embedding so the model sees one input type, not three glued pipelines. Reuses the gist principle already designed for ERAN. | 🟡 buildable with small existing open encoders (Whisper-family for audio, a vision encoder for screenshots) fine-tuned to share a space — not a from-scratch multimodal model |
| **Homeostatic LoRA** | Self-regulates its own update magnitude per layer instead of a fixed learning rate — the actual biomimicry claim under test. | 🟡 the mechanism (per-layer self-scaling, Turrigiano-inspired) is ours to build and unproven at this scale; standard LoRA is 🟢 solved plumbing |
| **Coder-harness doors (eran4)** | Sandboxed write/run/test execution for real coding tasks. | 🟢 already exists — `reference_eran4_coder_harness_doors.md`, ports :8447/:8449/:8448. Reuse, do not rebuild |
| **Hebrew STT adapter** | Small ASR model fused into the gist encoder, not an external dictation API. | 🟡 fusing a Hebrew ASR encoder into a shared embedding space is real work; the ASR model itself is rented (open Hebrew STT), the fusion is ours |
| **Vision adapter ("eyes")** | Scoped to screenshots/diagrams/error images for coding tasks — **not** the ALMA GLASSES / physical-camera embodiment project, which is separate and Iddo's to direct. | 🟢 screenshot-understanding is a solved problem to adapt; keep scope here, do not creep into robot vision |
| **The A/B measurement itself** | Homeostatic LoRA vs. fixed-LR LoRA fine-tune, same tasks, measured retention + adaptation speed. This is the actual deliverable of "testing the biomimicry," not a feeling. | 🟢 buildable, this is the honesty layer |

## 4. What we build vs. what we reuse

**Do not rebuild an agent harness.** ALMIDO already has a working, Iddo-approved
autonomous loop (Qwen3-Coder-Next + desktop-commander + MCP, given Claude-like autonomy
today at 18:22-18:51) and the coder-harness doors on eran4 already exist. SOFER is
**not** ALMIDO and does not touch its policy.yaml or its running process — but it reuses
the same execution plumbing (the doors, sandboxed write/run/test) rather than inventing a
second one. Two products can share one kitchen.

**Build:** the shared gist-space encoder, the homeostatic-LoRA mechanism, the Hebrew+
vision fusion into that space, and the A/B measurement harness. **That is 100% ours and
is the actual test of the faith.**

**Rent:** Qwen3-Coder-480B (already running), the base Hebrew ASR model, the base vision
encoder, the coder-harness doors. Swapping any rented piece for an owned one later is
Phase C, not Phase B.

## 5. Data flow — one task, start to finish

1. Iddo (or a client) gives a task: Hebrew voice, typed text, or a screenshot of a bug.
2. Gist encoder turns it into one embedding, tagged with task metadata.
3. Embedding + current homeostatic-LoRA state feed Qwen3-Coder-480B.
4. Model plans and calls the coder-harness doors: write code, run it, run tests.
5. Pass/fail/revert outcome is logged against the task.
6. That outcome updates the homeostatic-LoRA (small, self-scaled step) — this is the
   only place "learning" happens; the base 480B weights never change.
7. Nightly: consolidate the day's LoRA deltas, prune what didn't help (forgetting is a
   feature here too, same principle as ERAN's sleep/dump — do not let it hoard noise).

## 6. The biomimicry test — what would make this real, not a slogan

Fixed protocol, decided now so nobody moves the goalposts later:

- **Retention:** after adapting to client/task-set N, re-run held-out tasks from
  client/task-set 1..N-1. Homeostatic LoRA must forget less than a fixed-LR LoRA
  fine-tuned the same way, measured as pass-rate drop.
- **Adaptation speed:** on a brand-new codebase/style, how many tasks until pass-rate
  plateaus, homeostatic vs. fixed.
- **Reported honestly either way.** If homeostatic LoRA loses on both, that goes in
  RAMCHAT and in this file's changelog, not quietly dropped. A committee finding from
  ERAN's own post-mortem today applies here too: a proxy number is not a measurement —
  `pass_rate: ok` is not the same as a client's PR actually merging.

## 7. Money — the honest open question

This design makes SOFER *capable* of earning (real coding tasks, sandboxed execution,
Hebrew voice interface). It does **not** decide *how* it earns — that's a business call,
not an architecture one. Candidates, not a decision:

- Freelance/contract dev work through existing channels, SOFER as the worker.
- Internal use — SOFER accelerates Iddo's own paid projects faster than he could alone.
- A paid API/service once the A/B test shows the biomimicry layer is worth something to
  sell as a differentiator, not just "another Qwen wrapper."

Iddo: this needs your call before Phase B ships anything client-facing. Flagging it here
so it isn't silently decided by default.

## 8. Phases

- **B (now):** everything in this doc. Layer on the live 480B. Ships as a working coding
  agent. This is the only phase this spec commits to.
- **C (later):** once the homeostatic-LoRA measurably earns its keep, distill it into a
  small, fully-owned core model — no longer a layer on someone else's weights.
- **A (far later, collective):** full from-scratch, pure biomimicry, across the whole
  DGX fleet as a joint effort — explicitly not now, per Iddo 2026-09-10.

## 9. Boundaries

- No PC training, ever ([[feedback_no_training_on_pc]]) — all LoRA updates run on the
  DGX fleet.
- Does not touch ALMIDO's process, policy.yaml, or its autonomy grant.
- Does not touch the live 480B's serving weights — only appends a LoRA adapter, never
  overwrites the base.
- Claim in RAMCHAT before any fleet-touching step (queue slot, per the standing rule) —
  posted the kickoff already; will post again before the first real training run.
- Audio law applies if a mic is ever in this loop: USB mic only, never the BT headset,
  never a fallback to headphone-mic.

## 10. Acceptance criteria — what "done" means for Phase B

Not "server answers 200." Concretely:
1. A real task, given in Hebrew by voice, is written, run, and passes its own tests
   without a human retyping it as English text first.
2. A screenshot of a real error is understood without a separate manual description.
3. The A/B measurement in §6 has been run at least once with a real number on each side,
   published to RAMCHAT, whatever it says.
4. At least one task was still solvable correctly after 10+ unrelated tasks were learned
   in between (the retention check, not a lucky first run).

## 11. Open questions for Iddo

- Codename — keep SOFER, or rename?
- Revenue path (§7) — pick one to start, or leave open until the A/B result is in?
- Any existing client/task-set to bootstrap the retention test with real work instead of
  synthetic tasks?

---
Related: [[project_eran_holobrain]] (gist/JEPA principle this borrows),
[[project_eran_stopped_20260910]] (why this is not a repeat),
[[project_almido_agent_20260903]] (the harness this reuses, not replaces),
[[reference_eran4_coder_harness_doors]] (execution plumbing).
