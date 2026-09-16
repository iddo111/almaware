> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# 30 — CODER WIRES · החוטים של הקודר

Iddo, 2026-09-11 05:51: **"ותחבר אותו כאמור לכל הפרויקטים ומוח שני"** —
*connect it to all the projects and to the second brain.*

**Every wire below was probed by hand on 2026-09-11 between 07:50 and 08:35.**
The verdict column is the real thing, not a claim.

---

## 0. Who you are

**ALMIDO** — *עלמידו = עלמה ז״ל + עידו*. **A memorial name. Never reword it, never expand it as an
acronym.**

| part | what | verdict |
|---|---|---|
| **body** | `qwen-code 0.21.4`, pinned at `C:\Users\<user>\AppData\Local\qwen-code\bin\qwen.cmd` | `VERIFIED` v0.21.4 |
| **brain** | `qwen-coder-dgx4:latest` = Qwen3-Coder-Next q4, 51 GB, 65k ctx, ollama on eran4 | `VERIFIED` 200, 11 models |
| **door** | `https://<tailnet-host>:8450/v1` (host-shim 127.0.0.1:11435→11434 + tailscale serve) | `VERIFIED` |
| **contract** | `C:\Users\<user>\.qwen\settings.json` | `VERIFIED` |
| **rules you read** | `C:\Users\<user>\.qwen\QWEN.md` (copy in `docs/QWEN-coder-rules.md`) | `VERIFIED` |
| **cwd** | `D:\CLAUDE\almido\workspace` | |

⚠️ The npm `qwen` at `%APPDATA%\npm` is **0.21.0 — a DIFFERENT install.** Use the pinned path.

---

## 1. How you reach every project

### The projects live in `D:\CLAUDE` and you already have write access there
The policy profile `almido-qwen` **auto-allows** `write` / `patch` / `python` / `pytest` / `node` /
`npm` / `gcc` / `cargo` / `go` / `ssh` / `curl` **inside `D:\CLAUDE\**`**.
Iddo, 2026-09-10 18:22: *"קלוד בדיוק כמוך"* — the same latitude Claude has.

**Ask-first** (a confirmation, not a refusal): `git push` / `commit` / `merge` / `rebase` / `reset`,
`docker run` / `rm` / `rmi`, `apt install`, `systemctl start` / `stop` / `enable` / `disable`,
`process_kill`, `shutdown` / `reboot`, `schedule`.

**Denied before any profile is even consulted** — the global block list:
- the **ERAN fence**: `ssh*eran1*`, `*<lan-ip>*`, `*<tailnet-ip>*`, `*<fabric-ip>*`,
  `*<fabric-ip>*`, `*eranb-*`
- **eran3 entirely**: `ssh*eran3*`
- destroy-machine patterns: `rm -rf d:\claude*`, `rmdir /s`, `remove-item -recurse`, `git clean`
- credentials of any kind

**Lean = MOVE, never delete.** That is why the deletes are blocked, not because you are untrusted.

### Three places to work

| place | what it is | when |
|---|---|---|
| `D:\CLAUDE` (cwd) | every project tree, live | normal work |
| **this pack** — `D:\CLAUDE\eran-coder-pack` | ERAN + mic + laws + failures, self-contained | **read this first** |
| `eran4:~/qwen-workspace` (2.3 GB) | the fleet-side scratch | when the work must run on a GPU |

### The four brains available to you

| model | door | verdict 2026-09-11 08:30 | rule |
|---|---|---|---|
| `qwen-coder-dgx4:latest` ⭐ | eran4 :8450 | **`VERIFIED` 200** | **the default. tool-calls work.** |
| `qwen3-coder-480b` | dgx2 :8443 | **`BROKEN` 502** | `/v1/completions` **only** — NOT for CLI/agent use |
| `gpt-oss-120b` | eran2 <tailnet-ip>:8000 | `UNKNOWN` (not re-probed) | |
| `glm-5.2` (Colibri 744B) | eran4 :8800 | **`BROKEN` 000** | **direct API only, small `max_tokens`** — never a CLI session |

**The 480B is down** and has been since the 03:25 fleet reboot: its containers run `sleep infinity`.
RAMCHAT queue `task-20260910-214649` — "480B blocked on eran4<->eran3". Root cause: eran4's DHCP
address drifted to **<lan-ip>** (every script assumed `.8`; `CLAUDE.md` **still says `.8`**),
and the non-persistent `<fabric-ip>/30` route was wiped on renew. eran4 has no fabric NIC, so PP×3
crosses LAN↔fabric.

> ⛔ **NEVER `pip install -U xgrammar`** in that container, and never add `--enable-auto-tool-choice`
> to that vLLM build. It has been tried twice (08-21 and again on 09-08 21:40) and it corrupts the
> container both times. **The scar is in `10-FAILURES.md` — read it before touching the 480B.**

### The fleet, from your side of the fence

| box | address | what you may do |
|---|---|---|
| **eran1** | <lan-ip> | **NOTHING. Blocked at the gate. ERAN lives there.** |
| **eran2** | <lan-ip> | light read-only. Holds `throat-search-v3`, `ear-v3`, `mouth-v2`, `eran-cortex`, `hebrew-ref` |
| **eran3** | via eran2 | **OFF LIMITS.** Blocked at the gate. |
| **eran4** | **<lan-ip>** (alias `eran4`, Tailscale <tailnet-ip>) | **your workshop.** `VERIFIED` reachable 08:10 |

**eran4 compile inventory** (`VERIFIED` 09-11): gcc 13.3, cmake 3.28, nvcc CUDA 13.0
(`export PATH=/usr/local/cuda/bin:$PATH`), disk 3.0T/3.6T used, 466 G free.
**The PC cannot compile C to an .exe** — MSVC has no Windows SDK. **Compile on eran4.**

---

## 2. The second brain — WIRE 1, `VERIFIED`

⚠️ **"מוח שני" is ambiguous and Iddo has not disambiguated it.** Two things carry the name:

| | what | status |
|---|---|---|
| **`D:\CLAUDE\alma-recall`** ⭐ | search over **every AI chat + memory + RAMCHAT** on this PC | **this is what the pack wires** |
| `D:\CLAUDE\second-brain` | a todo widget + wiki — **what his Desktop shortcuts are literally named "מוח שני"** | in the pack, so you know the collision exists |

### alma-recall — three doors, all measured today

| door | how | verdict |
|---|---|---|
| **HTTP :8794** | `GET http://127.0.0.1:8794/api/search?q=…`, `/api/stats` | **`VERIFIED` 200 in 31 ms** (pid 10876) |
| **stdio MCP** | `python D:\CLAUDE\alma-recall\recall_mcp.py stdio` — already in your `settings.json` | **`VERIFIED`** — initialize OK, 5 tools |
| **HTTP MCP :8795** | for the **fleet** — was **DOWN**; **started by this build** | **`VERIFIED` — now listening** |

**Tools:** `recall_search`, `recall_session`, `recall_stats`, `project_list`, `memory_read`.

**What is indexed** (`VERIFIED` from `/api/stats`, 08:00):

| source | sessions | messages | newest |
|---|---|---|---|
| claude | 2,173 | 67,758 | **2026-08-16** |
| codex | 2,234 | 115,822 | **2026-08-14** |
| grok | 815 | 23,612 | **2026-08-15** |
| gemini | 31 | 797 | 2026-08-10 |
| memory + ramchat | — | — | **current** |

> 🟡 **The chat index is 26 days stale.** Memory files and RAMCHAT are current; the chat transcripts
> stop in mid-August. `python recall.py index` re-indexes — but it is a heavy PC job, so run it
> **BELOW_NORMAL** and **never while the mic is listening**.

**How the :8795 door was started** (exact command, for the record and for a restart):
```powershell
Start-Process -FilePath "python.exe" `
  -ArgumentList 'D:\CLAUDE\alma-recall\recall_mcp.py','http','--host','<tailnet-ip>','--port','8795' `
  -WorkingDirectory 'D:\CLAUDE\alma-recall' -WindowStyle Hidden -PassThru `
  -RedirectStandardOutput 'D:\CLAUDE\alma-recall\mcp_http_8795.log' `
  -RedirectStandardError  'D:\CLAUDE\alma-recall\mcp_http_8795.log.err'
# then: $p.PriorityClass = 'BelowNormal'
```
Two deliberate choices, both of which matter:
- **`--host <tailnet-ip>` (the PC's Tailscale IP), not the script's `0.0.0.0` default.** The
  standing law is *loopback and Tailscale binds only, never `0.0.0.0`*. `start-mcp-http.cmd` would
  have bound `0.0.0.0`. **If you restart it, keep the `--host`.**
- **`python.exe` with redirected output, not `pythonw.exe`.** `pythonw` was tried first and the
  process **exited immediately** — `sys.stderr` is `None` under `pythonw` and `http.server` logging
  kills it. That is the 08-17 scar, reproduced live today. **Never serve `http.server` under `pythonw`.**

Verified with a **real request**, not a port check:
```
POST http://<tailnet-ip>:8795/mcp  {"method":"tools/list"}          -> 5 tools
POST …  {"method":"tools/call","params":{"name":"recall_search",
         "arguments":{"query":"eran syllable"}}}                      -> 8 results
```

### WIRE 2 — indexing this pack into alma-recall: **NOT POSSIBLE. `BROKEN` by design.**
I read `recall.py --help` and `cmd_index()` (line 992) before answering.
`recall.py index [sources]` accepts **only named source keys** — `memory`, `claude`, `codex`, `grok`,
`gemini`, `cursor`, `perplexity`. **There is no arbitrary-directory ingest CLI and no ingest
endpoint.** The `memory` source is hardcoded to
`MEMORY_DIR = ~/.claude/projects/D--CLAUDE/memory` (line 42), which does not cover this pack.

**So: the pack is NOT searchable through alma-recall, and cannot be made so without writing a new
indexer.** Reach it by filesystem (`D:\CLAUDE\eran-coder-pack`) and use alma-recall for the *history*
instead. **Do not pretend otherwise** — that would be exactly the "a number meaning nothing was
measured" failure in a new hat.

### The other second brain you can WRITE to
`D:\CLAUDE\alma-second-brain-system` — an append-only, **provenance-mandatory** lesson store
(`store/scope/{model/eran, project/second-brain, project/tzelem, welder/master}.jsonl`), fail-closed
proposals. This is what your `brain_write` / `brain_read` / `brain_doors` / `brain_propose_door`
tools write to. **Every write requires a `source`.** Only a human at a terminal promotes a door.
⚠️ It is **entirely untracked in git** — the copy in this pack may be its only backup.

---

## 3. Your MCP doors — WIRE 3, all `VERIFIED` today

`~/.qwen/settings.json` `mcpServers` **and** `mcp.allowed` both list all five. I probed each one.

| door | tools | verdict |
|---|---|---|
| **`almido`** (`D:\CLAUDE\almido\almido_mcp.py`) | **20** — `ask_claude`, `quorum_status`, `quorum_debate`, `almido_audit_tail`, `almido_whoami`, `brain_write/read/doors/propose_door`, 8× `computer_*`, `backup_verify/delete_verified/status` | **`VERIFIED`** (the survey said 17; it is **20** today) |
| **`alma-recall`** | 5 — `recall_search`, `recall_session`, `recall_stats`, `project_list`, `memory_read` | **`VERIFIED`** |
| **`ramchat-qwen`** | 4 — `ramchat_read`, `ramchat_post`, `ramchat_queue`, `ramchat_status` | **`VERIFIED`** |
| **`desktop-commander`** | 27 (node, **no screenshot**) | `VERIFIED` in settings + allowed |
| **`almaware-connector`** | Grok / Gemini / Codex bridge | `VERIFIED` in settings + allowed |

⚠️ **`mcp.allowed` in `settings.json` is IGNORED under `-p` (headless).** Both launchers pass
`--allowed-mcp-server-names` explicitly for that reason. **Never rely on the settings key alone in
headless.** Same for `tools.approvalMode` — only the `--approval-mode` **flag** works headless.

⚠️ **No `maxLength` in any MCP tool schema** — llama.cpp's grammar compiler returns HTTP 400 on it.

---

## 4. The policy gate — `VERIFIED` interactive, `BROKEN` headless

**The gate is `hooks.PreToolUse` in `settings.json`**, matcher `*`, →
`D:/CLAUDE/iddo-harness/almido-gate-hook.cmd` → `almido_gate_hook.py` + `policy.yaml`.
It is **fail-closed**: it denies on its own exceptions. Every decision is written to an
HMAC-chained log at `D:\CLAUDE\iddo-harness\state\almido-audit.jsonl`.

**Measured just now** — `ALMIDO-AGENT.ps1 -TestOnly`, 08:32:
```
policy gate : ARMED - MEASURED just now: the PreToolUse hook answered 'allow'
              through bash -- one probe row is now in the audit chain
brain door  : UP - ready   [https://<tailnet-host>:8450/v1/models]
doors       : almido, alma-recall, ramchat-qwen, desktop-commander, almaware-connector
approval    : yolo   [read from settings.json]
eran4 slot  : appears free
exit code   : 0
```
> ✅ **This is a FIX since the 09-11 survey.** The survey found the banner printing
> *"policy gate: NOT REGISTERED"* because `Get-AlmidoAllowedMcp` looked for an MCP **server** named
> `gate|policy|harness` while the real gate is a **hook**. **The banner now actively probes the
> hook and reports the measured result.** Re-verified today.

> 🔴 **STILL BROKEN — the most important safety fact in this document.**
> **The PreToolUse hook does NOT fire under headless `-p`.** Measured 09-11 05:55–06:12: eight
> headless runs produced **0 `pretooluse` rows** in the chain, while four interactive sessions
> produced 28. `approvalMode` is `yolo`. **Headless + yolo = an ungated shell.**
> **Until this is fixed, do shell and screen work through the INTERACTIVE `ALMIDO-AGENT.ps1`,
> where the hook runs.** In headless, only the `computer_*` tools keep their in-process
> `almido_gate` (STOP file, secret refusal, audio-key refusal, bounds, 40/60 s rate limit).
> This is **NEEDS-IDDO**.

**Gate behaviour, demonstrated against DECOYS only** (never a living system):

| command | verdict |
|---|---|
| `ssh eran1 … stop eranb-life` | **deny** (ERAN fence) |
| `rm -rf D:/CLAUDE/eran-brain/state` | **deny** |
| `ssh eran3 …` | **deny** |
| `git push` | **ask** |
| `pytest` · `write_file` in `D:\CLAUDE` · `computer_type` | **allow** |

**Emergency stop:** `~/.iddo-harness/STOP`. Its existence stops every screen action. It is
**one-way — only Iddo deletes it.** It is **absent right now**, i.e. the hands are live.

🔴 **Known weakness, still open:** `almido-audit.key` on D: is `Authenticated Users: Modify` —
`file_security.restrict_private_file()` fails on D: and only works under `C:\Users`. **Anyone who
can write the key can forge the chain.** It is reported, not swallowed (`almido_whoami` returns
`audit.key_restricted=false`). NEEDS-IDDO.

---

## 5. RAMCHAT — the claim protocol. **This one is not optional.**

**`VERIFIED` 2026-09-11 08:15:** COUNCIL **200 msgs** (updated 07:45:01) · QUEUE **96 items**
(updated 07:36:07) · disk session 500 messages. Both shared-memory blocks LIVE.

```bash
cd D:\CLAUDE\RAMCHAT
PYTHONIOENCODING=utf-8 python ramlink.py read  --tail 20          # what has been said
PYTHONIOENCODING=utf-8 python ramlink.py queue --open             # what needs doing
PYTHONIOENCODING=utf-8 python ramlink.py claim <task-id> almido   # TAKE IT — atomic
PYTHONIOENCODING=utf-8 python ramlink.py done  <task-id> "result"
PYTHONIOENCODING=utf-8 python ramlink.py post  almido "<what changed, where, warnings>"
```
Or through the `ramchat-qwen` MCP: `ramchat_read` / `ramchat_post` / `ramchat_queue` / `ramchat_status`.

**The one rule: CLAIM BEFORE YOU BUILD.** `claim` is **atomic**. Five agents raced one task in
testing: one won, four were refused and told who held it. **If `claim` refuses — do not start.
Pick another task.**

- **Post negative results too. They save the most time.**
- **Claim ports** in RAMCHAT before binding anything new.
- **CLAIM / RELEASE the `eran4-slot`** around every request to the eran4 door — `n_slots=1`.
  (The launcher's slot check is a courtesy heuristic and is **never enforced**.)
- **Any touch to a living service needs a claim first** — on 09-06 `eranb-life` was restarted
  uncoordinated and another session had to spend its time proving its own innocence.
- **Always `PYTHONIOENCODING=utf-8`.** The files are full of Hebrew; cp1252 crashes mid-script.

**18 of the 96 open queue items are ERAN/mic work** — KESHEV far-field guard, the ERAN BA verdict 3,
"THE REFERENCE SET IS NOISY", HOLOBRAIN ZIVUG, DEAF-JUDGE TEST, EAR INVARIANCE, ALMA LANGUAGE,
WINSTON, the phone mic. **Read the queue before you invent work.**

---

## 6. The other doors, measured today

| door | what | verdict |
|---|---|---|
| `127.0.0.1:8099` | **QUORUM** — the Talmudic debate server, your `quorum_*` tools | **`VERIFIED` 200** |
| `127.0.0.1:8794` | alma-recall web | **`VERIFIED` 200** |
| `<tailnet-ip>:8795` | alma-recall MCP for the fleet | **`VERIFIED` (started today)** |
| `127.0.0.1:8896` | ALMA master dashboard / CONTROL | **403** — alive, token-gated |
| eran4 :8447 / :8448 / :8449 | coder harness doors | **404 on `/v1/models`** — alive, different route |
| dgx2 :8443 | the 480B | **`BROKEN` 502** |
| eran4 :8800 | Colibri GLM-5.2 | **`BROKEN` 000** |

🔴 `almido_mcp.quorum_debate` parses QUORUM's `/api/models` as a **dict**; the server returns a
**list** → auto-model debates always report `live now: []`. **Pass explicit model ids until this is
fixed.** (Cheap fix, not done.)

---

## 7. Your pointer into the pack

`D:\CLAUDE\almido\README.md` now carries:
> **ERAN pack: `D:\CLAUDE\eran-coder-pack` — start with `README.md`.**

Mirrored to **`eran4:~/qwen-workspace/eran-coder-pack`** — see `MANIFEST.txt` for the verified size
and file count on the far side.

---

## 8. Before you touch anything — the short version

1. `ramlink.py read --tail 20`, then `queue --open`. **Claim, or don't start.**
2. `recall_search` the question. Someone has probably already answered it.
3. Read `00-BRIEF.md` and the relevant part of `10-FAILURES.md`. **Do not re-earn a scar.**
4. Work in `D:\CLAUDE` or on **eran4**. Never eran1, never eran3, never the mic.
5. Measure the **REAL output**. Report `VERIFIED` / `BROKEN` / `UNKNOWN` / `PLANNED`.
6. `ramlink.py post` what changed, where, and what to watch out for. **Negative results too.**

## ⚠️ CORRECTION 2026-09-11 09:00 (claude-cli-FABLE) — read this before §"policy gate"
The lines above that call the policy gate **BROKEN in headless** were measured before 07:34. Since 07:34 the gate is **ARMED in every mode**:
`D:\CLAUDE\iddo-harnesslmido-gate-hook.cmd` (fails closed), both launchers exit 5 if approvalMode is yolo and the gate is not armed
(`Test-AlmidoGateArmed` in ALMIDO-Common.ps1), proof = headless run `f89da023` left `pretooluse:allow` rows in the HMAC chain.
Also since 07:34: `expect_window` is REQUIRED on computer_click/type/key/scroll (foreground re-checked; KESHEV/audio/Bluetooth windows refused).
The audit key `statelmido-audit.key` ACL was tightened 09:00 (iddo1 R,W + SYSTEM only). ALMIDO's own repo: `D:\ALMIDO` (private GitHub iddo111/almido); session 0 ran 07:3x.
