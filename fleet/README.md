<!-- לזכרה של עלמה ז"ל -->
# ALMAWARE Multi-AI Fleet (Google Cloud)

> לזכרה של עלמה ז"ל

Maximize **free AI compute** by sending each task to the right model:
cheap/fast jobs run on **Ollama (free, no API cost)**, complex jobs on
**Claude / Gemini**, real-time on **Grok**. Routing is data-driven — one JSON
file decides everything.

```
                 ┌──────────────┐
   task + prompt │   router.py  │  reads fleet_config.json
   ────────────► │  classify →  │  picks model → calls provider → falls back
                 └──────┬───────┘
     ┌──────────┬───────┼──────────┬───────────────┬─────────────┐
     ▼          ▼       ▼          ▼               ▼             ▼
  Ollama    Anthropic Gemini      xAI           xAI           ER:N (eran)
 gemma2:2b  haiku/    flash/pro   grok        grok-web      eran-local /
 (free,GCP) sonnet    (free tier, (reasoning) (LIVE WEB     eran-dgx4
  CloudRun) (Hebrew)   long ctx)              search)       (OUR own byte-LM,
                                                             local :7800 /
                                                             DGX via SSH tunnel)
```

**ER:N (eran provider)** is ALMAWARE's *own* from-scratch byte-LM
(`eran/chat_server.py`). Hebrew / creative / ALMAWARE-specific routes go to it
first. It's a **prototype** (4-layer, trained only on Iddo's voice), so each
Eran route declares `fallback_to: [eran-dgx4, sonnet]` — if Eran is offline or
returns nothing, the request escalates to a real capable model automatically.

- `eran-local` → `http://localhost:7800` (start: `python D:/CLAUDE/eran/chat_server.py`)
- `eran-dgx4`  → `http://localhost:7801` via SSH tunnel: `ssh -N -L 7801:localhost:7800 eran4`

**grok-web** is plain `grok` + xAI **Live Search** (`search_parameters`) for
real-time web/current-events tasks; `grok` (no web) stays for pure reasoning.

## Files

| File | What it does |
|------|--------------|
| `router.py` | Smart router. Classifies a task, picks the best model, calls it, falls back on failure. |
| `fleet_config.json` | Model registry + task→model routing table. **Edit this to change behavior.** |
| `setup_secrets.sh` | Stores `ANTHROPIC_API_KEY`, `XAI_API_KEY`, `GEMINI_API_KEY` in GCP Secret Manager. |
| `deploy_ollama_cloudrun.sh` | Deploys Ollama (gemma2:2b) to Cloud Run free tier. |

## How routing works

1. You give a **task type** (`--task code`) or let the router **auto-classify**
   (`--auto`) from the prompt text (keywords + Hebrew detection + length).
2. The router looks up `task_routing[task]` in `fleet_config.json` → a model key.
3. It dispatches to that model's provider. If the call fails, it walks
   `defaults.fallback_chain` (gemma2:2b → haiku → gemini-flash) so a request
   never dies just because one provider is down or a key is missing.

### Task assignment logic (the policy)

| Task | Model | Why |
|------|-------|-----|
| simple replies, WhatsApp, fast | `gemma2:2b` (Ollama) | free, instant, no API cost |
| code generation | `sonnet` (or `gemini-pro`) | strongest code |
| document / long context | `gemini-pro` | huge context window, free tier |
| real-time / news / web search | `grok-web` | xAI Live Search (real web) |
| reasoning (no web) | `grok` | reasoning without a search round-trip |
| Hebrew / creative / ALMAWARE / "ask Eran" | `eran-local` → falls back to `sonnet` | our own model first; real model as safety net |
| high volume / batch | `gemma2:2b` / `haiku` | cheapest per call |

All of this lives in `fleet_config.json` — change the table, not the code.
To send Hebrew NLP straight to the best model instead of our prototype, point
`hebrew` / `hebrew_nlp` back at `sonnet`.

## Testing

- `python -m pytest test_router.py -q` — **hermetic** unit tests (no network;
  every provider branch, routing, and the fallback walk are mocked). 43 tests.
- `python test_fleet.py` — **live** health check: real call to every endpoint,
  prints status + latency. SKIPs gracefully when a key/host is absent; never
  prints a secret (error strings are redacted).

## Quick start

```bash
# 1. Auth + project
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# 2. Store API keys in Secret Manager
export ANTHROPIC_API_KEY=sk-ant-...
export XAI_API_KEY=xai-...
export GEMINI_API_KEY=AIza...
./setup_secrets.sh

# 3. Deploy the free Ollama backend to Cloud Run
./deploy_ollama_cloudrun.sh           # prints a service URL
export OLLAMA_URL=https://ollama-fleet-xxxx.run.app

# 4. Use the router
python router.py --list                       # show the fleet
python router.py --task code "reverse a list in Python"
python router.py --auto "what's the latest on AI chips?"   # → grok
echo "סכם את הטקסט הזה..." | python router.py --task document
```

Run anywhere the env vars are present. On GCP, `setup_secrets.sh` + the
`--update-secrets` deploy flag surface the keys as env vars automatically; the
router just reads `os.environ`.

### CLI flags

| Flag | Meaning |
|------|---------|
| `--task TYPE` | force a task type (keys in `fleet_config.json`) |
| `--auto` | auto-classify the task from the prompt |
| `--list` | print the fleet + routing table |
| `--dry-run` | show which model *would* be picked, don't call it |
| `--json` | full JSON result (task, model, provider, free, output) |

## Adding a new model

1. Add an entry under `models` in `fleet_config.json`:
   ```json
   "deepseek": {
     "provider": "ollama",
     "model_id": "deepseek-r1:7b",
     "endpoint_env": "OLLAMA_URL",
     "endpoint_default": "http://localhost:11434",
     "cost_tier": "free",
     "free": true,
     "best_for": ["reasoning"],
     "notes": "..."
   }
   ```
2. Point one or more task types at it in `task_routing`
   (e.g. `"reasoning": "deepseek"`).
3. If it's a **new provider** (not ollama/anthropic/gemini/xai), add a
   `call_<provider>()` function in `router.py` and one branch in `dispatch()`.
   Existing providers need **zero code changes**.

## Free-tier strategy

- **Ollama on Cloud Run** — `min-instances=0` scales to zero (no idle cost);
  gemma2:2b fits in 4Gi RAM. This is the workhorse for high-volume/simple jobs.
- **Gemini** — Google AI Studio free quota (flash + pro). Best free option for
  long-context document work.
- **Claude / Grok** — paid, reserved for what genuinely needs them (complex
  code, best Hebrew, real-time). The router only reaches for them by policy.

## Notes / requirements

- `gcloud` CLI must be installed and authenticated (it was **not** on PATH on
  this machine — install the Google Cloud SDK first).
- `router.py` is dependency-free (standard library `urllib` only) — no `pip
  install` needed. Python 3.8+.
- Cloud Run requires billing enabled on the project even to use the free tier.
- Secrets are never written into any file here; they come from your shell env
  → Secret Manager → runtime env vars.
