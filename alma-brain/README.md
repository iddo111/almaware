> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working).

# ALMA-BRAIN — the shared second brain
# ALMA-BRAIN — המוח השני המשותף

**One endpoint that Claude, Qwen and gpt-oss all query for "what do we know about X" and "what happened before".**
**נקודת קצה אחת שקלוד, קוון ו-gpt-oss שואלים: "מה אנחנו יודעים על X" ו"מה קרה קודם".**

Built 2026-08-16. Runs on the PC at **`http://<lan-ip>:8797`**, token-gated.
It is a thin layer **on top of ALMA-RECALL** — it does not re-index anything and does not replace it.

---

## For a model on a DGX box — use it in one line

```bash
~/brain-ask "what is KESHEV B"                       # the brief: facts + team + history
~/brain-ask -m gpt-oss:120b "what broke the mic"     # brief fed to your local model
~/brain-ask -n 6 "darwish training"                  # more hits per tier
```

The token is already installed at `~/.alma-brain-token` on eran1, eran2, eran3, eran4.
Raw HTTP, if you prefer: `GET /ask?q=...&token=...&n=4` (plain text) or `/ask.json` (JSON).

**Answer only from the brief.** It carries file paths — cite them. If the brief does not
contain the answer, say so. Never invent; that is the ALMA Standard.

---

## What a "second brain" actually is — and what is marketing

Tiago Forte's *Building a Second Brain* is **CODE** (Capture, Organise, Distil, Express)
over **PARA** (Projects, Areas, Resources, Archives). The honest core of it: your head is for
having ideas, not storing them, and *distilling* beats *hoarding*. The honest criticism: PARA
is one filing scheme among many, and most of the productivity-influencer layer around it is
marketing. What survives contact with reality is (a) capture everything cheaply,
(b) **distil** — a curated note beats a raw log, (c) make retrieval trivial.

For LLM agents the field settled on a three-tier split that maps onto the same idea:

| tier | what it is | here |
|---|---|---|
| **semantic** | distilled, durable facts | `~/.claude/projects/D--CLAUDE/memory/*.md` (325 files) |
| **team / decisions** | what the agents agreed | RAMCHAT council + work queue |
| **episodic** | what actually happened, verbatim | 5,250+ session transcripts (Claude, Codex, Grok, Gemini, Cursor) |

Real techniques: retrieval-augmented context, keeping episodic and semantic **separate**
(so curated facts are not drowned by raw logs), recency weighting, and consolidation
(episodic → semantic). Genuinely unsolved / oversold: automatic memory consolidation is
still unreliable — repeatedly LLM-rewritten memories **drift and corrupt**, which is exactly
why **ALMA-BRAIN never rewrites anything**. It retrieves. Distillation stays human-and-Claude
authored in the memory files. That is a deliberate choice, not a missing feature.

---

## What was actually broken before, and what changed

ALMA-RECALL (`:8794`) was already indexing 5,579 sessions and works. Four real defects
stopped it from being a shared brain:

1. **RAMCHAT was not indexed at all.** The team's own decision log — 495 council messages
   and 67 queue tasks — was invisible to every search. Now indexed as source `ramchat`.
2. **Stopword AND.** `fts_query()` ANDed *every* word, so the question
   *"what did Iddo decide about the MIDI model"* required `what AND did AND about AND the`
   and collapsed to 6 hits. Now: stopwords dropped (English **and** Hebrew), terms OR'd,
   then re-scored on coverage.
3. **No ranking beyond bm25.** A June Codex log outranked the August mic work. Now:
   `IDF × recency-decay(45-day half-life) × source-prior × title-match × substance`.
   IDF matters enormously here — in *this* corpus "Iddo" and "model" are near-stopwords
   because every document is about Iddo deciding something; "MIDI" is the real query.
4. **Bound to 127.0.0.1.** No DGX box could ever reach it. ALMA-BRAIN binds `0.0.0.0`
   **behind a shared token** so eran1–4 can query it.

And the presentation change that matters most: results are **split by tier**, so four
curated memory files always get their own section instead of losing to transcript volume.

---

## Files

| path | what |
|---|---|
| `D:\CLAUDE\alma-brain\brain.py` | the service (stdlib only; read-only over `recall.db`) |
| `D:\CLAUDE\alma-brain\brain-ask` | the one-line client, deployed to all 4 DGX |
| `D:\CLAUDE\alma-brain\token.txt` | the shared token |
| `D:\CLAUDE\alma-brain\start-brain.cmd` | launcher; a Startup-folder shortcut autostarts it |
| `D:\CLAUDE\alma-recall\recall.py` | **patched**: added the `ramchat` source (backup: `recall.py.bak-20260816-brain`) |

Freshness: a background thread re-indexes **RAMCHAT and the memory files every 5 minutes**
(both are tiny and incremental). The 5,000+ transcripts stay on ALMA-RECALL's own schedule —
ALMA-BRAIN never re-walks those.

---

## Honest limits

- **RAMCHAT messages carry only `HH:MM`, no date.** The council file stores no day, so
  per-message time is NULL and the whole transcript inherits the file's mtime. Ordering
  inside RAMCHAT is by position, not by timestamp.
- **It retrieves; it does not synthesise.** The brief is evidence, not an answer. The asking
  model writes the answer. That is deliberate — see the memory-drift point above.
- **Token in a plaintext file** on the PC and on each DGX (`~/.alma-brain-token`, mode 600).
  It gates the LAN, it is not a secrets system.
- **`current_council.json` / `current_queue.json` are deliberately NOT indexed** — stale
  Aug-12 RAM snapshots that duplicate `ramchat_session.json`.
- **Session transcripts are only as fresh as ALMA-RECALL's last full index.**
- No Gemini chat transcripts exist locally (Antigravity stores none) — only its workspace files.
