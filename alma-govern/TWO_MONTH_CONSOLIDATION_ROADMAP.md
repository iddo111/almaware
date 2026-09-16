# ALMA two-month consolidation roadmap

Start: 2026-07-22  
Target audit: 2026-09-22  
Authority: [PUBLIC_BENEFIT_CHARTER.md](PUBLIC_BENEFIT_CHARTER.md)

This period consolidates existing work before expansion. It does not authorize
purchases, printing orders, legal filings, public deployment, physical drone
flight, medical claims, autonomous replication, or changes to third-party
accounts. Those actions require their own evidence and explicit approval.

## Status language

- `VERIFIED`: current evidence meets the stated bounded gate.
- `ACTIVE`: work has a named next deliverable and is underway.
- `BLOCKED`: an external dependency prevents the bounded deliverable.
- `UNKNOWN`: evidence is missing or stale.
- `PLANNED`: authorized scope, not yet started.

## Eight-week program

| Track | Weeks | Deliverable | Acceptance gate | State |
|---|---:|---|---|---|
| Governance | 1 | Charter plus fail-closed JSON proposal gate | Repository tests cover every hard boolean; candidate returns non-approval without evidence | `VERIFIED` — 36/36 tests; garden draft `REJECT` exit 3 |
| Product consolidation | 1–2 | One master index for Clod, Grok, ALMA, Eran, Perets, Yigael, Quorum, RAMCHAT, and hardware | Every entry has path, owner, status timestamp, evidence link, and duplicate/superseded marker | `ACTIVE` — existing `ALMAWARE_INDEX.md` selected as authority |
| Books and printing | 2–3 | Canonical manuscript map and print-readiness manifest | Hash, word/page count, format, rights check, proof status, and print decision for every book | `ACTIVE` — two adult Clod drafts and one bilingual kids manuscript located; nothing printed yet |
| Lab inventory | 2–3 | Chemistry, seed, electronics, maker, and equipment manifests | Physical count date, location, quantity, condition, hazard/storage flag, and unknowns | `PLANNED` — existing chemical PDFs are inputs, not fresh physical proof |
| Websites and knowledge | 3–4 | Route-level verification and repaired public entrypoints | Fresh GET, expected marker, assets, build/tests, deployment proof, and credential-free evidence | `ACTIVE` — Electric Cave version 3 verified 2026-07-20; custom domain blocked by DNS |
| Memristor learning | 4–5 | Sourced reading syllabus and acquisition shortlist | Primary/academic source, learning objective, owned/borrow/buy state, price checked at approval time | `PLANNED` — no purchase authorized |
| Robotics and drones | 5–7 | Non-weaponized bench prototypes and operating runbooks | Compile, identification, wiring/current gate, bench test, legal check, kill switch; flight is a separate gate | `ACTIVE` — garden sentinel compiles for Uno, Nano ESP32, and RP2040; no physical board verified |
| Business and charity | 6–8 | Draft mission, services, governance, budget, conflicts policy, and launch checklist | Independent review plus explicit approval for filing, banking, spending, fundraising, and publication | `ACTIVE` — organization protection packet drafted; no entity or public launch claimed |

## Current bounded hardware evidence

`arduino-neuron-builds/07-garden-memory-sentinel` is advisory-only. It starts
stopped, uses a transparent volatile stress state, controls only the built-in
LED, and makes no treatment claim. Source SHA-256:
`761A3220423C542CF53EDA3C7694B4D688D5DFE8938D33A805E820A52F2CFBDD`.

Compilation passed on 2026-07-22 for:

- Arduino Uno (`arduino:avr:uno`): 9,580 bytes flash; 280 bytes global SRAM.
- Arduino Nano ESP32 (`arduino:esp32:nano_nora`): 322,937 bytes flash;
  30,936 bytes global memory.
- Generic RP2040 (`rp2040:rp2040:generic`): 92,160 bytes flash; 8,956 bytes
  global memory. The first concurrent core invocation failed while writing
  compiler output; the isolated retry passed.

Compilation does not prove sensor voltage, soil calibration, wiring, field
benefit, medicinal safety, or community consent. No board was flashed.

## External-action gates

| Action | Required before execution |
|---|---|
| Buy books/components | Current price/source, duplicate check, budget and explicit purchase approval |
| Print books | Canonical manuscript, rights review, rendered proof, quantity/cost and explicit print approval |
| Publish a website/book | Final content review, privacy/rights check, working rollback and explicit publish approval |
| Form a business/charity | Jurisdiction, professional legal/accounting review, officers, budget and explicit filing approval |
| Fly a drone | Exact craft/operator/location, local aviation rules, insurance if applicable, safe test area and physical checklist |
| Scale agents/robots | Charter approval, quotas, audit logs, stop mechanism and separately recorded authorization |

## Unresolved aliases

- **Peter Pan** — reserved catalog placeholder. No matching first-party project,
  manuscript, character file, or media asset was found in `D:\CLAUDE` on
  2026-07-22. One remembered phrase or alternate title is needed to resolve it.
