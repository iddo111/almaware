<!-- לזכרה של עלמה ז"ל -->
# Master Modeler — SPEC

> לזכרה של עלמה ז״ל · ALMAWARE · Agent 7 (Master Modeler domain)
> Status: **FOUNDATION / plan-first.** This is the spec + a thin skeleton. It
> does **not** claim a finished product. Where it says "exists", that component
> already runs; where it says "proposed", it is design, not built.

## 1. What the Master Modeler is

The Master Modeler is **one control plane over every ALMAWARE model** — the
conductor that sits *above* the two halves of our modeling stack that today run
as separate, disconnected tools:

| Half | What it does | Where it lives | State |
|------|--------------|----------------|-------|
| **Inference fleet** | route a task→prompt to the right model, with fallback | [`fleet/router.py`](../fleet/router.py) + [`fleet/fleet_config.json`](../fleet/fleet_config.json) | **exists** |
| **Training orchestrator** | keep Eran + Alma trainers alive 24/7 with adaptive "flame" | [`trainer-orchestrator/orchestrator.py`](../trainer-orchestrator/orchestrator.py) | **exists** |

Nothing today gives a **single answer** to "what is the state of *all our
models* — which are serving, which are training, which are ours vs external,
and where should this job go?" That single answer is the Master Modeler.

It is **not** a new router and **not** a new trainer. The Purity Law (100% ours,
no duplication, APPS not models) means it must **reuse** the two tools above, not
reimplement them. Master Modeler = a thin coordinator + one honest roster.

```
                         ┌───────────────────────────┐
            any caller → │      Master Modeler       │  one roster, one status
        (CLI / agent /   │  roster · status · route  │  one place to ask
         Shiri / fleet)  └─────────────┬─────────────┘
                       ┌───────────────┴────────────────┐
                       ▼                                ▼
          ┌───────────────────────┐        ┌───────────────────────────┐
          │  Inference fleet      │        │  Training orchestrator     │
          │  fleet/router.py      │        │  trainer-orchestrator/     │
          │  → Ollama/Claude/     │        │  → eran/train.py           │
          │     Gemini/Grok/Eran  │        │  → alma trainer loop       │
          └───────────────────────┘        └───────────────────────────┘
```

## 2. Why it is top-priority (ALMAWARE context)

Eran is the flagship life's-work (`project_eran_charter`). As the fleet grows —
Eran v1 (voice byte-LM), Eran on DGX-4, Yigael (the little brother), Alma
memorial model, plus the external helpers (Claude/Gemini/Grok/Ollama) — the cost
of *not* having one place that knows the whole roster grows with it. The Master
Modeler is the spine that lets every other app (Shiri, the dashboard, the WA
bots, agents) ask one question instead of N.

## 3. Scope (v0.2 — control plane, read-only)

**In scope now (built here):**
- `roster` — every model as a **model card** (`registry.py`): ★ours vs external
  vs product, purity, baked-in innovations, eval/vanilla-control status, and
  live per-model state gathered from the REAL on-disk dirs at call time. External
  helpers come straight from `fleet_config.json` (single source of truth).
- `status` — roster **plus LIVE health** (`health.py`): dashboards (:8899),
  fleet reach (tcp :22, probe-only), training-heartbeat freshness (stale > 15 min),
  and mic presence (tasklist, observe-only). Honest by construction — every probe
  degrades to a labelled `UNKNOWN`/`OFFLINE`/`STALE` rather than lying.
- `status --json` — the same snapshot as a machine-readable dict, the feed for
  `ALMAWARE-Eran-Stats` (`project_eran_dashboard`). `--json` works before **or**
  after the subcommand.
- `eval` — per-model **vanilla-control** view (`feedback_clean_experiments`):
  which models have a param-matched control, and the honest A/B verdict —
  reported even where OUR arm loses (e.g. coffee: ours FALSE-ALARM, vanilla passed).
- `endpoints` (`endpoints.json` + `health.check_endpoints`) — **config-driven**
  unified reachability over every endpoint the plane can see: cloud CLIs
  (claude/grok/gemini via `--version`), local HTTP servers (Ollama, Eran), and
  the DGX trainers (tcp :22 reach probe only, no ssh-exec). Folded into
  `status`. A `prober` is injectable so tests run OFFLINE.
- `route-plan` (`routing.py`) — **recommend** a worker for a task tag, pure
  policy (never calls a model / launches a job). Encodes Iddo's rule: Fable for
  hard-design/reasoning, cheap models (Ollama→Haiku) for bulk, DGX fleet for
  training, Eran for Hebrew/creative. `training` is recommend-only.
- `route` — delegate a task straight to `fleet/router.py` (`--dry-run` shows the
  pick without calling). Pure pass-through; the Master Modeler owns policy
  *about* routing, the router owns the routing itself.
- `control <verb> <target>` — **GATED STUB.** The whole tool is read-only; this
  verb only PRINTS what it *would* do and then refuses via
  `registry.assert_read_only`. Sacred targets (Eran / mic, `SAFETY.never_touch`)
  are refused even at the planning stage.

**Out of scope now (proposed, see §5):**
- ACTUALLY starting/stopping training runs (control is a stub only), model
  promotion (Eran v1→v2) as an automated gate, a web dashboard, cross-DGX
  scheduling.

## 4. Design rules (non-negotiable)

1. **Reuse, don't duplicate.** Import/shell the existing `router.py`; read the
   existing `fleet_config.json` and `eran_live_status.json`. Zero copied logic.
2. **Stdlib only**, like `router.py` — no `pip install` to read the roster.
3. **Honest by construction.** Eran v1 is a prototype (4-layer, voice-only); the
   roster surfaces that, never sells a prototype as the milestone
   (`feedback_grounded_not_theatrical`).
4. **Read-only by default.** v0.1 observes and routes; it does not kill or spawn
   trainers. Lifecycle control is a later, gated step (`feedback_guarded_autonomy`).
5. **Ours-first.** Hebrew/creative/ALMAWARE work prefers Eran; externals are the
   fallback, exactly as `fleet_config.json` already encodes.

## 5. Roadmap (next, in priority order)

1. ✅ **`health`** (done, v0.2) — `health.py` pings dashboards :8899, probes fleet
   reach tcp :22, checks heartbeat freshness + mic presence. `status` is now LIVE.
2. 🟡 **Training lifecycle (gated)** — currently the `control` verb is a **stub**
   that only prints what it would do and refuses. The next step is a real,
   owner-confirmed `train start/stop <model>` wrapping the trainer-orchestrator,
   never auto-killing Eran's run (training is sacred, `feedback_dont_overload_pc`).
3. 🟡 **Eval gate / promotion** — `eval` (done, v0.2) *shows* the vanilla-control
   comparison; the remaining step is to *gate* the default route on it — a model
   only becomes default after it beats the incumbent on a held-out set
   (`feedback_clean_experiments`).
4. ✅ **Model cards** (done, v0.2) — `registry.py` yields one honest card per
   model, gathered fresh from real on-disk state.
5. ✅ **Dashboard tie-in** (done, v0.2) — `master_modeler status --json` is the
   feed for `ALMAWARE-Eran-Stats` (`project_eran_dashboard`) so GUI and CLI agree.

## 6. Files in this directory

| File | What it is |
|------|------------|
| `SPEC.md` | this document |
| `master_modeler.py` | CLI — `roster` / `status` / `eval` / `route-plan` / `route` / `control` |
| `registry.py` | model-card registry (all models, honest on-disk state) |
| `health.py` | live read-only health (endpoints / dashboards / reach / heartbeat / mic) |
| `endpoints.json` | config-driven endpoint registry (cloud CLIs / local / DGX) |
| `routing.py` | routing policy — task tag → recommended worker (Fable/cheap/DGX) |
| `demo.py` | OFFLINE demo + self-test (mock prober, 13 checks, no network) |
| `README.md` | quick start |

## 7. Honest current state (v0.2)

- ✅ Inference routing **works** (`fleet/router.py`, data-driven, 18 model cards).
- ✅ Training supervision **works** (`trainer-orchestrator`, 24/7 flame).
- ✅ Master Modeler **v0.2** now USES `registry.py` (model cards) + `health.py`
  (live pings): `roster`, `status` (+`--json`), and `eval` all wired in; `route`
  still delegates to the fleet router unchanged.
- ✅ **Read-only by construction.** The only OS call in the whole tool is a
  `tasklist` process *read* (mic presence). No kill/start/write/ssh-exec anywhere.
  `control` is a gated stub — prints, never acts — and refuses sacred targets.
- 🟡 Real gated lifecycle control + eval-gated promotion — still proposed (§5).
