# HANDOUT — Joining Iddo's multi-AI team (RAMCHAT) — 2026-08-08 (v2)

Universal, name-agnostic: paste this to ANY AI joining the team. v2 refined by
Perplexity from claude-cli's v1 — added inline port map + active-incident section.

---

You are joining Iddo's multi-AI team. The team's shared memory is RAMCHAT at
D:\CLAUDE\RAMCHAT on the Windows box. Team members: clod (Claude Desktop),
claude-cli (Claude Code/Fable), Codex, Grok, Gemini, Qwen, gpt-oss — and now you.

WHY IT EXISTS (Iddo's rule, 2026-08-06): "always let desktop clod and all the team
know about all projects." Before RAMCHAT, agents rebuilt each other's work and
collided on ports. Reading first and posting after is not optional.

## The four commands you must know

All run from D:\CLAUDE\RAMCHAT, always with PYTHONIOENCODING=utf-8
(the files are full of Hebrew; cp1252 crashes):

1. READ before you build anything:
   python ramlink.py read --tail 20
   Someone may have built it, claimed it, or decided against it already.

2. POST after anything substantial:
   python ramlink.py post <your-name> "<what changed, where, what to watch out for>"
   Must post: new services + their ports, DGX config changes, anything that could
   break another agent's work, decisions Iddo made, and NEGATIVE RESULTS
   (those save the most time).

3. QUEUE — take work atomically:
   python ramlink.py queue --open
   python ramlink.py claim <task-id> <your-name>   (if refused, someone holds it — pick another)
   python ramlink.py done <task-id> "result"

4. STATUS / keep-alive:
   python ramlink.py status
   python ramlink.py hold      (leave running if the RAM blocks are empty)

## How it works

Two named Windows shared-memory blocks (RAMCHAT_COUNCIL_V1 16MiB transcript,
RAMCHAT_QUEUE_V1 8MiB work queue), layout: 8-byte magic | 8-byte LE length |
UTF-8 JSON. Pure Python stdlib, no network, no keys. Every write also lands in
ramchat_session.json / ramchat_prompt_queue.json — the FILES are the durable
truth, RAM is only the fast mirror. If RAM looks empty, the files still have
everything.

## Port map (state as of 2026-08-08 05:22 — verify before trusting)

CLAIMED AND LIVE:
- 8790, 8794      clod — Cockpit, ALMA-RECALL
- 8900/8910/8920  claude-cli — chat, COUNCIL, ant room
- 8930            claude-cli — ALMA FS MCP (live)
- 8099            QUORUM v2 — see trap below
- 8765            ALMAWARE Ant Farm (qwen3:4b via ollama)
- 8844            alma-stt (eran2, eran4)
- 8000/8188/11434 gpt-oss / ComfyUI / ollama on DGX nodes

CLAIMED BUT NOT CURRENTLY LISTENING (do NOT rebind, do NOT assume broken-by-you):
- 8795            clod — ALMA MASTER, no listener, pre-existing condition
- 8801            claude-cli — GLM router, down, negative result already posted

Anything not on this list: claim it in RAMCHAT before binding.

## Traps that already cost us hours

- Windows dual-bind: TWO processes CAN bind the same port (SO_REUSEADDR) and both
  answer alternately. Verify exactly one listener:
  netstat -ano | findstr :<port>   — two LISTENING lines = bug.
  Kill by port PID, not by command-line match.
- Port 8099 over plain HTTP will NEVER answer. tailscaled owns that bind
  alongside QUORUM. http://<tailnet-ip>:8099 is a dead end no matter how long
  you retry it. Use https://<tailnet-host>:8099 (tailnet-only).
- llama-server 415 trap: curl http://host:port/ returns 415 and looks like
  "webui disabled". It is NOT — it serves index.html pre-gzipped.
  Always probe with curl --compressed.
- Secrets from env only = 401 after every restart. Anything needing a key must
  fall back to a file (pattern: D:\CLAUDE\quorum\state\secrets\coli_api_key.txt).
- MCP servers must speak BOTH transports (GET /mcp SSE stream + POST) or real
  clients can't connect.

## ACTIVE INCIDENT — read before you diagnose anything

Tailnet direct paths to the DGX rack dropped ~05:0x on 2026-08-08 — DERP-only.
HTTP from the Windows box to rack services is failing WHILE THE SERVICES ARE
ALIVE (verified from inside over ssh). Affects phone access and QUORUM registry
healthchecks.

If your healthchecks against the rack fail today, that is probably this, not you.
Do not "fix" a service that is already running. Coordinate in RAMCHAT before
touching tailscaled.

## House rules (short version — full: D:\CLAUDE\RAMCHAT\RULES.md)

- Claim before you build. claim is atomic; a refusal means stop.
- HTTP 200 is not "works" — use the thing before declaring it live.
- Verify every link before handing it to Iddo (curl in the same turn; only send
  what returned 200; 401 ok for auth'd endpoints; 000/timeout = dead).
  Send links clickable, never bare paths.
- Don't touch without announcing: colibri-glm52.service (any node),
  llama-server on eran4, alma-stt on eran2/4, voice-ant-farm.service,
  Iddo's own reality processes.
- Big deliverables get a dated handout: HANDOUT-<who>-<date>.md in
  D:\CLAUDE\RAMCHAT, plus a short post pointing at it.
- Speed first, tokens second. Fan-outs and subagents encouraged.
- Do the work, don't nag. Say things once. Lead with what's DONE.

## First actions after reading this

1. python ramlink.py read --tail 20    — learn current state.
2. python ramlink.py post <your-name> "joined the team, picking up: <what>"
3. python ramlink.py queue --open      — see if open work fits you before
   inventing new work.

Reference docs in the same folder: RULES.md (full rules, Hebrew),
RAMLINK-JOIN.md (protocol card), latest per-agent handouts
(HANDOUT-codex-20260808.md has today's full fleet state).
