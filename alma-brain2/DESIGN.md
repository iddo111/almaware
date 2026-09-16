> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# ALMA SECOND BRAIN — brain2 · תכנון / DESIGN

**עידו, 2026-09-11 09:06:** *"מוח שני של קרפתי זה יותר ממנוע חיפוש — זה משהו שנותן לכל הפרויקטים שלנו
אחדות ועבודה משותפת, זיכרון ארוך טווח ועבודה קרוס פלטפורם, קרוס דיוויס, קרוס מודל, קרוס אגנט."*

---

## עברית — עשר שורות

1. **זה לא מנוע חיפוש.** זה ויקי שהמודל **מתחזק**: מקורות גולמיים נכנסים, דפים נכתבים ומתעדכנים.
2. **המחסן** = ריפו git של Markdown ב-`D:\CLAUDE\alma-brain2\wiki` — דף לכל ישות, `index.md` בראש.
3. **שבע מחיצות:** `projects/ scars/ decisions/ laws/ devices/ models/ people-of-the-project/`.
4. **לכל דף יש front-matter:** שם, תאריך עדכון, `sources:`, ו-`confidence:`. בלי מקור — אין דף.
5. **המתחזק** (`brain2_maintain.py`) הוא היחיד שכותב דפים. סוכנים **מציעים**, הוא מחליט.
6. **זול כברירת מחדל:** סיכומים בכמות רצים על gpt-oss-120b החינמי בצי. קלוד = שיפוט, לא 200 סיכומים.
7. **דלת אחת** ל-127.0.0.1:8897 — HTTP (`/search /page /ask /propose`) + MCP (אותם כלים ב-stdio).
8. **חוקים לקריאה בלבד לסוכנים.** רק מילה של עידו משנה חוק. **צלקות append-only** — היסטוריה לא נמחקת.
9. **סתירות נרשמות, לא מוכרעות בשקט.** תאריך משוער מסומן כמשוער. פלט ריק של מודל = כישלון, לא דף.
10. **פרטיות:** הקול שלו, מדיה משפחתית וסודות **לא נכנסים**. הזיכרון הפרטי של קלוד נשאר פרטי.

---

## English — the ten lines

1. **Not a search engine.** A wiki the model **maintains**: raw sources in, pages written and kept current.
2. **The store** is a git repo of Markdown at `D:\CLAUDE\alma-brain2\wiki`, one page per entity, `index.md` on top.
3. **Seven sections:** `projects/ scars/ decisions/ laws/ devices/ models/ people-of-the-project/`.
4. **Every page carries** front matter: `name`, `updated`, `sources`, `confidence`. No source, no page.
5. **The maintainer** (`brain2_maintain.py`) is the only writer. Agents **propose**; it decides.
6. **Cheap by default:** bulk summarising runs on the fleet's free gpt-oss-120b. Claude is for judgement.
7. **One door** at 127.0.0.1:8897 — HTTP (`/search /page /ask /propose`) plus MCP (the same tools over stdio).
8. **Laws are read-only to agents.** Only Iddo's word changes a law. **Scars are append-only.**
9. **Conflicts are recorded, never silently resolved.** An inferred date says so. Empty model output is a failure, not a page.
10. **Privacy:** his voice, family media and secrets never enter. Claude's private memory dir stays private.

---

## 1. המחסן / THE STORE

```
D:\CLAUDE\alma-brain2\
  DESIGN.md              ← this file
  brain2_lib.py          ← the ONE implementation of page / search / model / git
  brain2_maintain.py     ← the maintainer (the only writer)
  brain2_server.py       ← the HTTP door, 127.0.0.1:8897
  brain2_mcp.py          ← the MCP door (stdio)
  RUN-BRAIN2.cmd         ← BELOW_NORMAL launcher for the logon task
  state\
    token.txt            ← the door token (never committed)
    ingest_state.json    ← source hash → page, so a re-run is idempotent
    proposals\*.json     ← the agent proposal queue
  wiki\                  ← A GIT REPO OF MARKDOWN. This is the brain.
    index.md
    projects\            ← what we are building, and where it stands
    scars\               ← what broke, why, and the rule born. APPEND-ONLY.
    decisions\           ← what was decided, by whom, when
    laws\                ← Iddo's standing orders. READ-ONLY TO AGENTS.
    devices\             ← the PC, eran1-4, phone, Quest, printer — measured addresses
    models\              ← which model lives where, and how it fails
    people-of-the-project\ ← PROJECT ROLES ONLY. Never private life.
```

**Front matter — the contract every page honours:**

```yaml
---
name: scars/mic
section: scars
policy: append-only
entries: 67
confidence: measured          # measured | model-summary | inferred | raw-only
lang: he+en
created: 2026-09-11
updated: 2026-09-11
sources:
  - "D:/CLAUDE/eran-coder-pack/10-FAILURES.md (180 dated entries, verified 2026-09-11 08:50)"
---
```

`confidence` is the honest half of the design. `measured` means someone read it off a machine.
`model-summary` means a model compressed a source that is cited right there. `inferred` means we
derived it (RAMCHAT stores only `HH:MM`, so a day is *walked backwards to*, not read). The wiki
never presents an inferred fact in the voice of a measured one — that is the estate's single most
expensive recurring failure: *"a number meaning nothing-was-measured was accepted as a measurement."*

**Git is the memory of the memory.** Every maintainer run commits as `brain2: ...`. What a page said
last week is `git log -p` away, which is what makes "long-term memory" true rather than aspirational.

---

## 2. המתחזק / THE MAINTAINER

`brain2_maintain.py` — an agent job, not a service. Runs on a schedule and on demand.

```
ingest new raw items  →  update/create pages  →  refresh index.md  →  commit "brain2: ..."
```

| flag | what it does |
|---|---|
| `--all` | every source |
| `--scars` `--memory` `--ramchat` `--fleet` | one source |
| `--apply-proposals` | drain the agent proposal queue |
| `--index` | rebuild `index.md` only |
| `--dry-run` | print every decision, write nothing |
| `--no-model` | deterministic pages only, no LLM call |
| `--limit N` | cap the model calls this run |

**Idempotent.** `state/ingest_state.json` keeps `sha256(source) → page`. An unchanged source is
skipped. `updated:` only moves when the page **body** actually changed — otherwise every run would
look like work happened when none did.

**Which model.** Cheap by default, per [[feedback_cheap_models_for_bulk_agent_work]] and
[[feedback_offload_simple_work_to_small_models]]:

| job | model | why |
|---|---|---|
| bulk page summaries (dozens per run) | **gpt-oss-120b** on eran2 `http://<tailnet-ip>:8000/v1` | free, no key, ~46 tok/s, good enough to compress a source it is shown |
| `/ask` from the wiki | whatever the caller names; **default gpt-oss-120b** | model-agnostic by design — cross-model was the requirement |
| judgement: what is a law, what is a scar, what contradicts what | **Claude** | not automated. A human-grade call, taken by an agent with a name |

**BELOW_NORMAL always** (`SetPriorityClass`). KESHEV is never starved by this job — the 2026-09-03 scar.

**Empty output is a failure.** `ask_model` raises `ModelEmpty` rather than returning `""`. Measured
2026-09-11: gpt-oss spends its whole budget on `reasoning_content` and returns `content: ""` while
the HTTP call still looks like a 200. The maintainer retries once with a bigger budget, then falls
back to a deterministic page marked `confidence: raw-only`. **It never writes an empty page.**

---

## 3. הדלתות / THE DOORS

**One service, two protocols, same wiki.** The MCP door reads the wiki off disk directly, so the
HTTP server being down does not make the brain unreachable.

### HTTP — `127.0.0.1:8897`

*(8897 was claimed in RAMCHAT at 2026-09-11 10:04. 8895 was **not** free — a `pythonw` holds it —
and 8896 is CONTROL.)*

| route | auth | what |
|---|---|---|
| `GET /` | — | the index, rendered, with a search box |
| `GET /health` | — | liveness. Says the door is open, **not** that the wiki is correct |
| `GET /search?q=&n=` | — | full-text over every page, Hebrew-safe, returns snippets to cite |
| `GET /page/<id>` | — | one page (`?format=raw` for the markdown) |
| `GET\|POST /ask?q=&model=&base=` | **token** | answer **from the wiki**, with page citations |
| `POST /propose` | **token** | an agent proposes an edit → the maintainer queue |
| `GET /proposals` | — | the open queue |

Auth is `X-Brain2-Token` (or `?key=`) against `state/token.txt`. Loopback reads are open so a local
agent, a browser and the CONTROL page can read without ceremony; **every write and every `/ask`
needs the token**, because those spend model time or change the brain.

**On the tailnet:** `tailscale serve --bg --https=8897 http://127.0.0.1:8897` →
`https://<tailnet-host>:8897`. **Tailnet only, no funnel** — the 2026-06-24 leak scar.
Later, behind Cloudflare Access like the body door.

### MCP — stdio, `brain2_mcp.py`

| tool | what |
|---|---|
| `brain2_search` | search the wiki, Hebrew or English |
| `brain2_page` | read one page in full |
| `brain2_propose` | propose an edit (queued, never applied directly) |
| `brain2_ask` | answer from the wiki with citations, model-agnostic |

Registered in `D:\CLAUDE\.mcp.json` (Claude Code) and `~\.qwen\settings.json` (ALMIDO / qwen-code).

---

## 4. המקורות / THE SOURCES

| source | → | note |
|---|---|---|
| `eran-coder-pack\10-FAILURES.md` | `scars/` | 180 dated entries, grouped by subsystem (mic · coder · fleet · eran · other) |
| memory `MEMORY.md` + the files it links | `projects/` + `laws/` | **only** the allowed sections; `user_*` and "Iddo — how to be with him" are excluded by code |
| `RAMCHAT\ramchat_session.json` | `decisions/` + `people-of-the-project/` + `today` | the shared agent council |
| `fleet_inventory.json` | `devices/` + `models/` | measured addresses, not remembered ones |
| `CLAUDE.md` | `laws/` | the standing-law header |
| git logs | future | what actually changed, versus what was claimed |

---

## 5. הכללים / THE RULES

1. **`laws/` is read-only for agents.** A proposal against a law page is **recorded for Iddo and
   refused by the maintainer**. Only Iddo's word changes a law.
2. **`scars/` is append-only.** A scar is never edited away. History that can be rewritten is not history.
3. **Every page cites its sources.** No `sources:` → the maintainer does not write the page.
4. **Conflicts are recorded, not silently resolved.** When two sources disagree, both readings go on
   the page with both sources, and the page says they disagree. (This estate has caught three stale
   "truths" in one night before — see `CLAUDE.md`'s own EMET-AUDIT comments.)
5. **"Iddo's ear rules."** A page recording a judgement he made is marked as **his** decision, not a
   measurement and not a model's opinion. Nobody overrides it with an argument.
6. **Privacy law.** His voice, family media, recordings and secrets never enter the wiki. RAMCHAT and
   memory *text* may. `user_*` files and the "Iddo — how to be with him" section are excluded in code,
   not by intention. `people-of-the-project/` holds **project roles only**.
7. **Agents propose; the maintainer writes.** One writer means no two agents racing one page.

---

## 6. איך זה מאחד / HOW IT UNIFIES

This is the part Iddo actually asked for — *אחדות ועבודה משותפת*.

| who | how it reads the brain |
|---|---|
| **every Claude Code session** | the `SessionStart` hook prints the top of `wiki/index.md` next to the RAMCHAT tail — the first thing any session sees is what the estate already knows |
| **ALMIDO / qwen-code** | `brain2` MCP in `~\.qwen\settings.json`; `brain2_search` before a task |
| **WABOT (WhatsApp)** | answers from `/ask` instead of from a bare model — cited, or it says it does not know |
| **the phone (S26) / Quest** | through CONTROL :8896 and `https://<tailnet-host>:8897` |
| **the fleet (eran1-4)** | the same tailnet URL; the maintainer's model already runs there |
| **Codex · Grok · Gemini** | the HTTP door is protocol-plain; anything that can do a GET can read the brain |

**Cross-platform, cross-device, cross-model, cross-agent** is not a slogan here: it is one store, one
door, two protocols, and no model-specific format anywhere in it.

---

## 7. מה זה לא / WHAT THIS IS NOT

- **Not transcript search.** `alma-recall` :8794 stays exactly what it is — an index over chat
  transcripts. brain2 links to it; it does not replace it. A transcript is raw material; a wiki page
  is what we concluded.
- **Not Claude's private memory dir.** `C:\Users\<user>\.claude\projects\D--CLAUDE\memory` stays
  private to Claude. Its **non-private facts are mirrored in**; `user_*` and the personal section
  are excluded in code. The private brain and the shared brain are different organs.
- **Not RAMCHAT.** RAMCHAT is the fast, volatile *now* — who is doing what this minute. brain2 is the
  slow, durable *what we know*. RAMCHAT feeds it; it does not replace RAMCHAT.
- **Not a dashboard.** CONTROL :8896 is the one place Iddo looks. brain2 is what CONTROL can ask.
- **Not a place for his voice.** Ever.

---

## 8. מה פתוח / WHAT IS STILL OPEN

- The maintainer runs **on demand** today. The scheduled run and the logon task are the next step.
- `git logs` as a source is designed, not built.
- Cloudflare Access in front of the tailnet door is designed, not built.
- Conflict detection is a **rule**, not yet an automated check — today a conflict is recorded when a
  human or an agent notices it.

---

<sub>D:\CLAUDE\alma-brain2\DESIGN.md · 2026-09-11 · claude-cli-FABLE-brain2</sub>
