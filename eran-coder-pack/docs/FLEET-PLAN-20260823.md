> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# Fleet plan — four machines, four tracks

**Iddo's allocation, 2026-08-23 10:09:** *"יש לנו ערן אחד האמיתי · שתיים — דרוויש ותולעת · ויש מקום פנוי לאמן."*

**What this replaces.** CLAUDE.md still describes eran1/2/3 as a live Qwen3-Coder-480B cluster.
Measured 2026-08-23 10:06: **no `llama-server`, no vLLM, no `rpc-server` on any node; eran1:8080
UNREACHABLE; eran2 and eran3 at 0 % GPU for days.** That fleet is gone. This plan is the truth.

---

## 🧬 eran1 · <lan-ip> — ERAN. Nothing else lands here.

| | |
|---|---|
| running | `eran_life.py --live`, up **1 d 16 h**, beat **37,613,000**, 63 prototypes, unit `ga` |
| deliverable | the 22 syllables Iddo recorded in the booth this morning enter ERAN's exam |
| acceptance | **leave-one-session-out**, `t06` as its own fold. No segment-level split — that is the scar that cost 14 points ([[project_eran_session_leak_scar]]) |
| rule | the worm and everything else **move off**. ERAN gets the whole GPU. |

The booth data is real and audited: 66 files, 22 syllables × 3 takes, 16 kHz mono, 26.9 s,
levels healthy. One file (`tsa_t06_2`) peaks at −0.4 dBFS — droppable, it is 1 of 66.

**Talker-id rule (new, and it matters):** when Iddo records again he must stay **t06**.
`booth.py` hands out a fresh id per run, so a second session would make his own voice two
different exam folds — the session-leak scar, reintroduced. Needs a `--talker` flag before the
next recording.

---

## 🎵🐛 eran2 · <lan-ip> — Darwish v1 + the Beit-Din worm

**Darwish v1** — full plan in `darwish-midi/DARWISH-V1-PLAN.md`. Corpus is settled:

| | |
|---|---|
| corpus | **95 clean tracks** from the official @DARWISH channel only (68 matched locally + 27 fetched today), duration-verified 1:1 |
| dropped | 239 files / 6.7 GB — three different people named Darwish, whole festivals of other artists, a talk show |
| next | rung (b) tokenizer: drums **with velocity**, own bass lane, **a real lead lane**, note length, section marks |
| then | size the model to the token count that produces (v0 was 1.36 M params on 5.36 M tokens = 3.9 tok/param, ~5× oversized) |
| acceptance | `voice/sonic_scan.py` gates vs a real track — variety ≥ 0.06, highs ≥ 5 %, width ≥ 0.20, lead lane non-empty in ≥ 30 % of bars |

**The Beit-Din worm** — `almido/beitdin_net.py`. First result, 2026-08-23 09:59 on eran1:

| arch | params | heldout |
|---|---|---|
| **beit-din** (3 seats, median + dissent channel) | 4,922,880 | **1.3894** |
| vanilla | 4,922,112 | 1.4750 |

Size-matched to 768 params (0.016 %). **−0.086 nats, 5.8 % better.** n = 1 — seeds 18–21 and
the `--no-dissent` ablation are running. The ablation is the real question: **is the win the
median, or the dissent channel?**

---

## 🌌 eran3 — the free slot. Cosmos + whatever trains next.

587 GB free, 115 GB RAM, GPU 0 %, idle for days. Reachable only via ProxyJump through eran2.

| | |
|---|---|
| install | `nvidia/Cosmos3-Edge-Policy-DROID` — 3.86 B, a **world ACTION model**, not a video toy |
| licence | NVIDIA Open Model License — commercial OK, derivative is yours, **outputs are yours**, no ban on training a competitor. Dies only if you circumvent a safety guardrail or sue NVIDIA. |
| then | serve it OpenAI-style and register it in the Alma Harness router (`dgx4-dual-model-harness/alma_harness.py`, `MODELS` + `ALIASES`) |
| blocker | **the Alma Harness is DOWN** — nothing listening on 8095, no `alma_harness.py` process. It must come up before anything plugs into it. |

---

## 🎙️ eran4 · <lan-ip> — voice, and it is already earning its keep

The one thing on this fleet that works exactly as designed, and nobody had reported it:

```
2026-08-23 03:30  KESHEV nightly LoRA — 2,200 new utterances of Iddo's voice
2026-08-23 03:35  training lora_r16 on voice_corpus + the 2,200
2026-08-23 03:53  candidate did NOT beat the deployed model — nothing swapped
                  "this is the gate doing its job, not a failure"
```

28 min CPU, trains nightly, **promotes only if it wins.** Leave it alone.
Also finishing: `nvidia/Cosmos3-Nano` (15.75 B omni — text/image/video/audio/**action**), 20 GB in.

---

## The 70B LoRA — it was never a project

Searched memory and all 209,106 indexed messages. The origin is **2026-08-13 13:07**, and it is
a caveat in my own answer, not a plan:

> *"אל תאמן 70B+ משקולות מלא — **שם רק LoRA**. הצי memory-rich אבל bandwidth-modest."*
> *"השורה התחתונה: Qwen2.5-14B לפיין-טיון, **ערן מאפס ללב**."*

"LoRA for 70B" meant *if* you touch a 70B, then only LoRA. No code, no config, no run, no queue
item ever existed. Recording it here so it stops being remembered as a thing that stalled.

---

## Order of work

1. **Free eran1** — move the worm to eran2. ERAN gets its GPU back.
2. **Fold t06 into ERAN's exam**, leave-one-session-out. Add `--talker` to `booth.py` first.
3. **Darwish rung-(b) tokenizer** on the 95 clean tracks, on eran2.
4. **Cosmos Edge-Policy onto eran3**; bring the Alma Harness up; register it.
5. Leave eran4 alone except the Cosmos-Nano download.
