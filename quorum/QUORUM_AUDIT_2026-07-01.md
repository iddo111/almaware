# QUORUM — Audit & Roadmap (Agent 6, 2026-07-01)

> **לזכרה של עלמה ז״ל.** ALMAWARE standards. Q3 top-priority domain.

---

## 1. What QUORUM is

**קוורום — a council of AI minds.** One front door where you pose a question and
**many distinct models answer / deliberate / argue**, with the *process* made
visible. Two ancestries fused into one app:

1. **Iddo's flagship spec (2026-06-26):** *"I want to see Grok and Claude arguing a
   Talmudic debate — **שקלא וטריא** (give-and-take)."* The value is the **dialectic
   itself** being watchable: positions (דעות) → קושיא/תירוץ/ראיה/דחייה
   (challenge/defense/proof/refutation) → a closing **מסקנה** that names where the
   **מחלוקת** stands and which position is strongest. Truth refined by adversarial
   give-and-take among different minds.
2. **The engineering reality:** a **canonical multi-AI hub** that consolidated four
   older surfaces (SuperMind Spar, AI Council, Clodistan Bus, TrioChat) into one
   stdlib-only server with six modes.

**Design DNA:** 100% ours (orchestration + UI + transport — **no Flask, no
frameworks, pure `http.server`**); the trained models are "the rock." Hebrew-first
RTL web UI. Injection-defended (cross-model output fenced as
`<untrusted-model-output>` = DATA, never instructions).

---

## 2. Where it lives (current files)

| Location | What | Notes |
|---|---|---|
| `D:\grok\quorum\app.py` | **Canonical server** (49 KB, ~900 lines) | The real thing. 6 modes. |
| `D:\grok\quorum\team.py` | Ad-hoc team: planner→specialists→synth | 20 KB |
| `D:\grok\quorum\debate.py` | "Debate rounds" mode | ⚠️ see Gap #1 |
| `D:\grok\quorum\courtroom.py` | Prosecutor/defense/judge + transcript | adversarial, legal frame |
| `D:\grok\quorum\bus_bridge.py` | Clodistan MQTT council bridge | |
| `D:\grok\quorum\router\` | Classify→route→execute→verify (claude_code + DeepSeek hands) | `/route` |
| `D:\grok\_shared\ai_clients.py` | **The lego** — one async ask/astream over 5 providers | 48 KB; shared contract |
| `D:\grok\quorum\start-quorum.ps1` | Real launcher | |
| `D:\CLAUDE\quorum-debates\` | Output PDFs/HTML/JSON/TXT | the 9-turn kidney debate lives here |
| `D:\CLAUDE\quorum-desktop\` | Tkinter desktop shell (Stage 0) | scaffold only, own git repo |
| `D:\CLAUDE\ensure-quorum.ps1` | **0 bytes — empty/dead** | real supervisor is in `D:\grok` |

**Modes today:** 💬 parallel chat · 🧪 ad-hoc team · ⚔️ debate-rounds · ⚖️ courtroom ·
🚌 MQTT bus · 🧭 router. Endpoints: `GET / /models /bus`, `POST /ask_stream(SSE)
/team(SSE) /debate(SSE) /courtroom(SSE) /ask_one /ask /bus/council /route`.
Port **8099**, loopback-only by default (+ Tailscale gate, optional `QUORUM_TOKEN`).

---

## 3. Current state (verified 2026-07-01)

- 🔴 **NOT running.** Nothing listening on `:8099`. No live `QUORUM` scheduled task
  found. The `D:\CLAUDE\ensure-quorum.ps1` supervisor is a **0-byte stub**.
- 🟡 **Untracked by git.** `git ls-files quorum` in `D:\grok` returns nothing — the
  canonical code is **not version-controlled**; only timestamped `.bak` files
  (`app.py.20260626_193719.bak`, `team.py.20260627_001426.bak`) protect it.
- 🟢 **P0 security already hardened** (2026-06-26): bind defaults to `127.0.0.1`
  (LAN/public hole closed); `codex` exec backend gated OFF behind
  `MULTIAI_ENABLE_CODEX=1`.
- 🟢 **Real artifact exists:** a genuine 9-turn שקלא-וטריא PDF on *כפיית תרומת כליה*
  (`D:\CLAUDE\quorum-debates\debate_kidney_20260626_201755.pdf`). Grok CLI debated
  as ר' גרוק and gave the sharpest argument.
- 🟡 **Reliability:** heavy local models (`deepseek-coder-v2`) time out across
  rounds; small locals occasionally leak garbled/Chinese tokens.

---

## 4. Gaps — what's missing (ranked)

### 🥇 Gap #1 — The flagship Talmudic form does not exist as a mode
This is the **#1 finding.** `debate.py` is **collaborative idea-sparring** ported
from SuperMind Spar: **R1 PROPOSE → R2 CRITIQUE → R3 SYNTH** ("the strongest 3–5
ideas that emerged"). That is brainstorming, **not** שקלא-וטריא. The Talmudic form
Iddo spec'd —
- **Round 0:** each model states its **position (דעה)**,
- **Rounds 1..N:** each **rebuts the others** — קושיא (challenge) → תירוץ (defense) →
  ראיה (proof) → דחייה (refutation), like אביי vs רבא,
- **Closing:** a **מסקנה** that *names the מחלוקת*, where they agree, and the
  strongest position —
…is **not** an implemented mode. `courtroom.py` is the closest adversarial engine but
it's a legal frame (prosecutor/defense/judge), not Talmudic dialectic. **The thing
Iddo most wants to watch is the one thing not yet built as a first-class mode.**

### 🥈 Gap #2 — Lives in `D:\grok`, not ALMAWARE, and unversioned
Canonical code sits under **Grok's workspace** (`D:\grok`), was "handed to Grok" for
always-on robustness, and is **untracked**. This collides with the **ALMAWARE Purity
Law** (ALMAWARE = 100% ours, in our tree) and with basic safety (no git history).
*Decision needed from Iddo:* does Quorum's home stay in `D:\grok` (Grok owns
always-on) or move to `D:\CLAUDE\quorum\` under version control?

### 🥉 Gap #3 — Not always-on / not reliable enough to "just watch"
No live scheduled task; supervisor stub is empty; heavy-model timeouts. For
"I open it and watch them argue" to be true it must be (a) running, (b) fast enough
that rounds complete, (c) self-healing.

### Gap #4 — Public face not wired
`iddoperez-quorum` Cloudflare Pages subdomain is the public face but debate
transcripts/outputs aren't published to it. Right now output is local PDFs only.

### Gap #5 — Desktop shell is Stage-0 only
`D:\CLAUDE\quorum-desktop\` is a 3 KB Tkinter window shell; not connected to the
engine.

---

## 5. TODO (prioritized, WIP=1)

**P0 — make the flagship real**
- [ ] **Build a true שקלא-וטריא mode** (`shakla.py`, sibling of `debate.py`):
  Round 0 positions → N rounds of targeted קושיא→תירוץ→ראיה→דחייה where each model
  is handed *one named opponent's* last claim to refute (not a generic critique) →
  closing מסקנה that explicitly outputs `agree[]`, `מחלוקת[]`, `strongest`. Reuse
  `ai_clients.astream` + the `_fence()` injection defense verbatim. Hebrew prompts.
- [ ] Add a ⚖️🗣️ **"דיון תלמודי"** radio + round-tagged RTL columns to the UI; keep
  the existing "debate" (idea-sparring) mode as a separate option — they're
  different tools, don't overwrite.
- [ ] Render the transcript to **PDF on Desktop** (per standing rule), bright RTL,
  reuse the proven `quorum-debates` renderer.

**P1 — own it & keep it alive**
- [ ] **Ownership decision** (ask Iddo): home = `D:\grok` (Grok always-on) vs move to
  `D:\CLAUDE\quorum\` + git. Then **commit the canonical code** either way — it is
  currently unversioned.
- [ ] Restore a working **always-on supervisor** + idempotent scheduled task; delete
  the 0-byte `D:\CLAUDE\ensure-quorum.ps1` stub or point it at the real launcher.
- [ ] **Reliability:** per-call retry + fast-model fallback; cap heavy models to one
  opening turn; lower `num_predict`; default **rounds=3** so מסקנה is populated.

**P2 — reach & polish**
- [ ] Wire selected debate transcripts to the **iddoperez-quorum** public page
  (HARD privacy gate: no PII / no private mic speech / no keys).
- [ ] Connect `quorum-desktop` shell to the engine, or retire it.
- [ ] Smoke-test harness for all 6 modes on loopback (`/models /ask_one /debate`
  SSE) so regressions are caught.

---

## 6. One-paragraph answer for the dispatcher

**Quorum is ALMAWARE's canonical multi-AI council** — a stdlib-only Hebrew/RTL web
app (port 8099, 100% ours orchestration) where many models answer side-by-side or
deliberate through six modes (parallel chat, ad-hoc team, debate-rounds, courtroom,
MQTT bus, router). **Current state:** real working code at `D:\grok\quorum\app.py`
with a genuine 9-turn Talmudic-debate PDF already produced — **but it is not running
right now, is untracked by git, and lives in Grok's workspace rather than ALMAWARE's
tree.** **The single most important gap:** the flagship form Iddo actually
asked for — watching AIs argue in true **שקלא-וטריא** (positions → קושיא/תירוץ/ראיה/
דחייה → מסקנה) — is **not yet a first-class mode**; today's "debate" mode is
collaborative idea-sparring, and "courtroom" is a legal frame. **Build next:** a real
`shakla.py` Talmudic-dialectic mode + UI + PDF, then version-control the code, settle
its home, and make it reliably always-on.
