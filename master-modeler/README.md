<!-- לזכרה של עלמה ז"ל -->
# Master Modeler

> לזכרה של עלמה ז״ל · ALMAWARE

**One control plane over every ALMAWARE model.** It doesn't route or train —
it *reuses* the tools that already do (`fleet/router.py`, `registry.py`,
`health.py`, `trainer-orchestrator/`) and answers, in one place: *what is the
state of all our models, and where should this job go?*

See [`SPEC.md`](SPEC.md) for the full design. This is **v0.2** — a **read-only**
control plane. It observes and routes; it never kills or starts anything.

## Quick start

```bash
cd D:\CLAUDE\master-modeler

python master_modeler.py roster          # every model card, ours (★) vs external
python master_modeler.py status          # model cards + LIVE health + endpoints (honest)
python master_modeler.py status --json   # same, machine-readable (dashboard feed)
python master_modeler.py eval            # per-model vanilla-control comparison
python master_modeler.py route-plan training       # RECOMMEND a worker (Fable/cheap/DGX)
python master_modeler.py route-plan --list         # every task-tag -> worker
python master_modeler.py route --task hebrew "תרגם: hello"   # delegate to router (real call)
python master_modeler.py route --dry-run "what's the news?"  # show pick, no call
python master_modeler.py control stop eran   # GATED STUB — prints, never acts

python demo.py                           # OFFLINE demo + self-test (13 checks, no network)
```

## Unified endpoint registry (`endpoints.json`)

`status` now includes a **config-driven** reachability view over every endpoint
the control plane can see, from one file — `endpoints.json`:

- **cloud CLIs** — `claude` / `grok` / `gemini` (checked read-only via `--version`)
- **local HTTP** — Ollama (`:11434`), Eran chat server (`:7800`) via GET
- **DGX trainers** — `eran1..eran4` via a **TCP :22 reach probe only** (never ssh-exec)

Add an endpoint by appending to `endpoints.json` — no code change. Every check
is read-only and degrades to a labelled `OFFLINE` / `UNKNOWN` rather than lying.
`health.check_endpoints(prober=...)` accepts an injected prober so tests run
fully offline (see `demo.py`).

## Routing helper (`route-plan` / `routing.py`)

`route-plan <tag>` **recommends** a worker for a task tag — pure policy, it never
calls a model or launches a job. It encodes Iddo's rule:

| tag | recommended worker | why |
|-----|--------------------|-----|
| `hard-design` / `reasoning` | **Fable** (fallback sonnet, grok) | Fable for the hard stuff |
| `cheap-bulk` / `bulk` / `fast` | **Ollama local** (fallback Haiku) | cheap models for bulk |
| `training` | **DGX fleet** eran1..eran4 | DGX for training, never the PC |
| `hebrew` / `creative` | **Eran** (ours, fallback sonnet) | ours-first (Purity Law) |

Free text works too (`route-plan "do a cheap bulk job"` -> `cheap-bulk`); an
unknown tag falls back to a safe cheap default, never a silent wrong pick.
`training` is recommend-only — the plane never auto-launches a training run.

`--json` works before or after the subcommand. Stdlib only (Python 3.8+), no
`pip install`. It imports `registry.py` (model cards) + `health.py` (live pings),
reads the **existing** `fleet/fleet_config.json` and `fleet/eran_live_status.json`,
and imports `fleet/router.py` for actual routing — single source of truth,
nothing copied.

## Read-only safety

The whole tool OBSERVES and routes only. The single OS call anywhere in it is a
`tasklist` process *read* (mic presence) — there is no kill, start, write, or
ssh-exec. Eran's training (`D:\CLAUDE\eran-live`) and the mic are **never**
auto-touched (`registry.SAFETY.never_touch`). The `control` verb is a gated stub:
it prints what it *would* do, refuses via `registry.assert_read_only`, and won't
even plan an action against a sacred target.

## What's real vs proposed

- ✅ `roster`, `status` (+`--json`), `eval`, `route`, `route-plan` all work today (verified live).
- ✅ `status` is **live** — config-driven endpoints (cloud CLIs / local / DGX reach)
  + dashboard/reach pings + heartbeat freshness + mic.
- ✅ `route-plan` recommends a worker per task tag (Fable/cheap/DGX); `demo.py`
  runs the whole thing **offline** against a mock prober (13/13 checks pass).
- 🟡 `control` is a **stub** only; real gated lifecycle control is next (SPEC §5.2).
- ⬜ Eval-**gated** promotion (route only after beating a param-matched control)
  is still proposed. See SPEC.md §5.
