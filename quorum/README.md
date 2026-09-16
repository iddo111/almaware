# לזכרה של עלמה ז״ל

# 🗳️ QUORUM — שקלא וטריא (Talmudic AI debate)

**A council of AI minds arguing a question in the Talmudic form.** Pose a שאלה →
distinct models (private Alma Harness routes, callable CLIs, local ollama) state עמדות, then argue back
and forth — **קושיא → תירוץ → ראיה → דחייה** — and one strong model writes the
closing **מסקנה** naming where they agree, where the מחלוקת stands, and the
strongest position. The value is watching the *dialectic itself*.

100% ours — stdlib `http.server` only, no Flask/frameworks. Hebrew-first RTL.
This is the fresh ALMAWARE-tree scaffold (the earlier working copy lived untracked
in `D:\grok\quorum`; see [QUORUM_AUDIT_2026-07-01.md](QUORUM_AUDIT_2026-07-01.md)).

## Born inert (ALMAWARE safe default)
`config.ENABLED = False`. The server boots and shows status/UI, but **`/debate`
will not reach any model** until you turn it on:
```powershell
# inert — UI + model detection only:
.\run-quorum.ps1
# live debate (reaches your installed CLIs):
.\run-quorum.ps1 -Enable          # or set config.ENABLED=True, or env QUORUM_ENABLED=1

# Explicit private Alma routes (no tailnet hostname is embedded in the package):
.\run-quorum.ps1 -Enable -HarnessUrl 'https://your-node.your-tailnet.ts.net:8446'
```
Then open **http://127.0.0.1:8099**. Loopback-only by default; for phone access over
Tailscale set `QUORUM_HOST=0.0.0.0` (still gated by `_authorized()` + optional
`QUORUM_TOKEN`).

### Optional `codex-interactive` provider

The interactive Codex bridge is a separate, opt-in provider. Quorum does not
search for it, create its state, spawn Codex, or open another listener. The
stdio MCP bridge must first create the SQLite database and join the exact
`codex-interactive` participant. Only then may the Quorum process be launched
with all three explicit values:

```powershell
$env:QUORUM_CODEX_INTERACTIVE_ENABLED = '1'
$env:QUORUM_CODEX_INTERACTIVE_ROOT = 'D:\path\to\validated-bridge-project'
$env:QUORUM_CODEX_INTERACTIVE_DB = 'D:\path\to\runtime\quorum_bridge.sqlite3'
```

The root and database paths must be absolute, `bridge_state.py` must be directly
under that root, and the database must already exist. Discovery omits the
provider when any check fails or the participant is inactive. A debate turn is
accepted only when the provider ID, debate ID, turn ID, request nonce, non-empty
response, and SHA-256 digest all match. Configuration or roster presence alone
does not prove live Quorum participation.

## Files
| file | role |
|---|---|
| `config.py` | master `ENABLED=False` gate, ports, model prefs, limits |
| `ai_clients.py` | the ONE lego — `ask`/`astream`/`detect_models` over exact Alma routes, CLIs, and ollama; `Reply` contract |
| `shakla.py` | **flagship** — the שקלא-וטריא engine (positions → קושיא/תירוץ → מסקנה) |
| `server.py` | stdlib HTTP + SSE + bright RTL page; loopback gate |
| `render.py` | transcript → bright RTL HTML (PDF = TODO) |
| `run-quorum.ps1` | launcher (`-Enable` for live) |

## Design contracts
- **failure-is-a-value** — `ai_clients.ask()` never raises (returns `Reply(ok=False,…)`);
  `shakla.run_shakla()` never raises (yields `error` then `done`).
- **injection defense** — every model's words shown to another model are fenced as
  `<untrusted-model-output>` = DATA, never instructions.
- **the models are the rock** — we orchestrate explicitly configured private
  Harness routes and the user's own installed CLIs; no embedded API keys or SDKs.
- **presence is not health** — a CLI entry means its executable is installed.
  A provider joins a debate only after a real non-empty first turn. Alma routes
  additionally require exact ready model IDs and exact response route identity.
- **local DGX 4D fleet** — `qwen3-coder-next-fp8` (eran1), `glm-4.7-flash`
  (eran2), `nemotron-3-super` (eran3) and `gpt-oss-120b` (eran4) are
  first-class HTTP providers, all fronted by the ONE alma-router (v3, systemd
  on eran1 :8010, OpenAI-compatible); the model name selects the box. The
  router URL comes from `state\settings.json` (`fleet_router_url`) or env
  `QUORUM_FLEET_ROUTER_URL` — never embedded in code. The router must list AND
  echo the exact model asked for; gpt-oss Harmony analysis-channel scaffolding
  is stripped so only the answer enters the transcript. See `4D-COUNCIL.md`
  for the one-command council HOW-TO.

## Roadmap (next)
1. **Real token streaming** — `astream` currently returns the whole answer as one
   chunk; wire per-token streaming from the CLIs (`Popen` line reads).
2. **PDF export** on Desktop (bright RTL) via `render.py`.
3. **More modes** folded in later (parallel chat / courtroom) — keep שקלא-וטריא primary.
4. **Always-on** supervisor + idempotent scheduled task, once the debate is proven reliable.
5. **git** — commit this tree (the audit's #2 gap: the old copy was unversioned).
