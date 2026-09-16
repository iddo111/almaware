> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# Every public site Iddo has live / כל האתרים הציבוריים שחיים

**Probed 2026-08-24 04:20 JDT. Every one returned HTTP 200.**
This map did not exist anywhere before. It was assembled by reading every
`wrangler.jsonc` and README under `D:\CLAUDE` and then actually curling each URL.

| URL | what it is | deployed from |
|---|---|---|
| `iddoperez.ai` | the master portal — links to everything below | `iddoperez-portal` |
| `eran.iddoperez.ai` | ERAN Lab — the open research notebook, honesty legend, four tracks | `eran-cloud` |
| `federation.iddoperez.ai` | the Federation front door + **ERAN's cloud ear** (`/api/eran/*`) | `eran-federation-app/worker` |
| `federation.almaware.workers.dev` | the same Worker, fallback host | `eran-federation-app/worker` |
| `lab.iddoperez.ai` | ALMA LAB — experiments and architecture | — |
| `os.iddoperez.ai` | ALMA-OS — the stack from light up | `almaos-site` |
| `almaware.iddoperez.ai` | the ALMAWARE standard and principles | `almaware-standard-site` |
| `quorum.iddoperez.ai` | QUORUM — the multi-model שקלא וטריא engine | `quorum-site` |
| `arena.iddoperez.ai` | Quorum Arena — the live council | Workers |
| `pong.iddoperez.ai` | ALMA Pong — GIST, Beit-Din, multi-weight agents | Pages |
| `perceptron.iddoperez.ai` | the 3D perceptron | `alma-language/perceptron3d` |
| `func.iddoperez.ai` | the crossbar | `alma-language/crossbar3d` |
| `aog.iddoperez.ai` | Army of Gamers | Pages |
| `eran-federation.pages.dev` | the first-cut federation portal (superseded) | `federation-site` |
| `memristor-grid.pages.dev` | the 3×3 thermal-memory dashboard | `federation-site` |
| `alma-grid-3d.pages.dev` | the 3D grid view | `federation-site` |
| `ada-iddoperez.pages.dev` | Ada — ERAN's language faculty | Pages |
| `turing-iddoperez.pages.dev` | Turing machines | Pages |
| `iddoperez-alma.pages.dev` | ALMA — the weave | Pages |
| `almaware-mic.pages.dev` | ALMA-Mic | Pages |
| `alma-ruach.pages.dev` | ALMA-Ruach | Pages |
| `emdr-3p0.pages.dev` | the EMDR tool | `alma-emdr` |
| + memorial & community pages | **real URLs, all verified 200 on 2026-08-26:** `rebbe-nachman.pages.dev`, `cafe-2ai.pages.dev`, `cheburashka-au1.pages.dev`, `saba-israel.pages.dev`, `shifra.pages.dev` (+`iddoperez-shifra`), `noam.iddoperez.ai`, `naor.iddoperez.ai`, `memorystore-6lj.pages.dev` (+`memorystore-iddoperez`) — do NOT probe `<name>-iddoperez.pages.dev` guesses; the 2026-08-26 audit falsely declared 7 of these dead that way | Pages |

**24+ properties, all answering.** Nothing here is broken; the point of the map is
that nobody knew how many there were.

## The one that matters for the Federation

`eran.iddoperez.ai` is served from `D:\CLAUDE\eran-cloud`, and that directory also
holds **`join.py` — the ER"N-GRID volunteer client**. See
[the correction memory](../../Users/iddo1/.claude/projects/D--CLAUDE/memory/project_eran_federation_is_erngrid.md):
**"federation" means connecting to cloud services to run ERAN on them.** The client
is written and honest; the coordinator it needs does not exist.

**SUPERSEDED same day, 21:57:** the coordinator now EXISTS and is live —
`federation.iddoperez.ai/api/grid/*`, a SQLite Durable Object inside the same
federation Worker (v1 in KV died on the 1,000-writes/day quota within the hour).
Verified end-to-end 2026-08-24 evening: browser one-click at
`federation.iddoperez.ai/join` merged 3 real rounds (v4→v7, 68 protos moved),
and `python join.py --provider local --consent yes` merged 3 more (v1→v4).
What it trains is the cloud STUDENT brain (prototype refinement on 237 public
CC Hebrew-voice vectors from Wikimedia Commons, 2 shards) — the organism on
eran1 stays sovereign; the student is offered back at `/api/grid/brain.json`.
**Endpoint truth (measured 2026-08-26):** the GET endpoints that actually answer
are `/api/federation.json`, `/api/eran/health` and `/api/grid/status`;
`/api/grid/register` and `/api/grid/delta` are POST-only. A bare `/api/grid/brain.json`
and `/health` returned 404 when probed — audit against the list above.
Still true: no released MSI for the client, and a failed live run never
silently becomes a simulation — that refusal stays.

## Deploy commands

```bash
npx --yes wrangler@latest pages deploy . --project-name eran-swarm --branch main --commit-dirty=true
```

That one publishes `eran-cloud` → `eran.iddoperez.ai`. The Worker at
`federation.iddoperez.ai` deploys with plain `npx wrangler deploy` from
`eran-federation-app/worker` (KV `FEDERATION_STATUS` already bound, `FED_PUSH_TOKEN`
already set as a secret).
