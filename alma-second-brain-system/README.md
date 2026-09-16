> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# ALMAWARE Second Brain — three levels / מוח שני בשלוש רמות

**לזכרה של עלמה ז"ל.**

Iddo, 2026-09-05 16:32:

> "נגיד בקוורום יהיה לכל הפרויקט מוח שני כולל, ולכל מודל מוח שני, ולמודל שלנו שמחבר מודלים יהיה גם כן מוח שני"

| level | scope | who it belongs to | collective? |
|---|---|---|---|
| 1 | `project` | a PROJECT (tzelem, kav, eran-food) | **yes** — every write posts one digest line to RAMCHAT, and a QUORUM room reads it before it argues |
| 2 | `model` | a MODEL (eran, miko, winston, darwish, the coder) | **no — private on purpose.** A model's own tried/failed notes are working memory, not council noise |
| 3 | `welder` | the MASTER MODELER, the thing that connects models | **yes** — reachable as `master_modeler.py brain` |

## The two rules that are the whole point

**APPEND-ONLY.** A lesson can be superseded by a later line. It can never be quietly
deleted. `brain.py verify` recomputes every `sha` and `seq`, so a line rewritten in
place is *detectable* — not merely forbidden. The 2026-09-03 corpus fraud survived a
month because the record could be edited underneath.

**PROVENANCE IS MANDATORY.** `write()` refuses an entry with no `source`. The Master
Modeler's own report on 2026-09-05 found `food/train` sitting in the tree with no
provenance beside it — *"which is why the TTS fraud survived a month"*. An entry whose
origin is unrecorded is not a lesson, it is a rumour.

## Fail-closed, mechanically

Iddo's 11th commission of inquiry, the same morning: roughly **100 written laws against
2 executable gates**; the advisory gate *"was never once exercised in six months"*, the
mechanical one blocked its own author on day one.

So `brain_propose_door` is the mechanical kind:

* a proposal is a JSON file in `proposals/pending/`. It returns `"pending"`, always.
* **there is no installer in this codebase.** `proposals.install()` exists only to raise.
* `proposals.py` imports no `subprocess`, no `importlib`, no `socket`, no `urllib`,
  and `tests/test_proposals.py` **parses its AST** and fails if any of those ever
  appears — including in a future edit of that file.
* a second test watches `open()` at runtime and fails if the module touches anything
  outside its own queue.
* the MCP server exposes **no** promote/decide/install verb, so a model cannot approve
  its own door. Promotion is a human at a terminal running `brain.py decide`, and even
  approval only writes down the steps a person must perform by hand.

Building it this way caught its own author twice in one sitting (`re.compile` tripped
the first version of the AST scan; a sentence telling a human to edit `.mcp.json`
tripped the second). That is the gate working.

## Files

| file | what | written by |
|---|---|---|
| `store.py` | the append-only JSONL store, sha/seq tamper check | **qwen3-coder-next-eran4**, judged and corrected by claude-cli-BRAIN3 |
| `proposals.py` | the fail-closed proposal queue | **qwen3-coder-next-eran4**, judged and corrected by claude-cli-BRAIN3 |
| `doors.py` | what tools exist RIGHT NOW — probed, never declared | claude-cli-BRAIN3 |
| `bridge.py` | the wiring: level 1/3 → RAMCHAT, level 1 ← QUORUM | claude-cli-BRAIN3 |
| `brain.py` | the CLI facade | claude-cli-BRAIN3 |
| `tests/` | 53 tests. The judge writes the tests, never the builder | claude-cli-BRAIN3 |

The doors themselves live in **`D:\CLAUDE\almido\almido_mcp.py`** — extended, not forked,
so the local coder keeps one audited door with one gate:
`brain_write`, `brain_read`, `brain_doors`, `brain_propose_door`.

## Use it

```
python brain.py write model eran "הפה נסגר לפני /ba/" --author eran --kind learned --source sitting-4
python brain.py read  project tzelem --query depth -n 10
python brain.py doors                       # measured: spawns every MCP, fetches every service
python brain.py verify project tzelem       # the tamper check
python brain.py pending                     # proposals awaiting a human
python brain.py decide p-xxxxxxxxxx approved --by iddo --note "…"
python brain.py prior-art r-53d291a222      # put a project's past into a QUORUM room
python ..\master-modeler\master_modeler.py brain read     # level 3
```

A QUORUM room is matched to its project brain by its own **title** — `[brain:tzelem]`
in the title, or the slugged title otherwise. No hidden mapping file: the room says
what it is about.

## What `brain_doors` will not do

It will not read you a list. Every MCP server named in `.mcp.json`, `~/.qwen/settings.json`
and `~/.claude.json` is **spawned** and given a real `initialize` + `tools/list`
handshake, and only the tool names it actually answers with are reported. Every HTTP
service is really fetched. `netstat` is asked what is really listening, so a live
service nobody wrote down appears as `unclaimed`.

Two honesty rules were bought with measurements on 2026-09-05:
* **HTTP 401/403 is `up-gated`, not `down`.** Something is answering.
* **A slow answer is not a dead port.** QUORUM's `/api/health` probes every model before
  it replies; a 4 s timeout reported a demonstrably serving QUORUM as down. A TCP
  connect is asked as a second opinion, so `netstat` and this module cannot disagree.

## Untouched on purpose

`D:\ALMA-Second-Brain` is **Iddo's own Obsidian vault** — his brain, not a model's.
Nothing here reads or writes it. `alma-backup\second_brain.py` remains the *backup*
arm (it pulls each model's learned state to `E:\ALMA-Backups`); this is the read/write
arm, and the two do not overlap.
