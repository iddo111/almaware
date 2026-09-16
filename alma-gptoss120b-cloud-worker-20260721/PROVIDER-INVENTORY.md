# Provider inventory — read-only inspection, 2026-07-21

## GroqCloud

- Required model: `openai/gpt-oss-120b`.
- Existing local Alma adapter: yes, but it is loopback-bound and therefore not reused as a runtime.
- Worker credential: **BLOCKED** — `GROQ_API_KEY` was not configured in the inspected environment.
- Bundle status: implemented as the sole active provider adapter; no local fallback.

## Google Gemini

- Existing adapter code: `D:\CLAUDE\fleet\router.py` and `D:\CLAUDE\hermes-cloud\responder_cloud.py`.
- Existing Gemini CLI: present and authenticated for interactive CLI use.
- Worker-compatible API credential: not found. CLI OAuth files were not read or copied.
- Exact GPT-OSS 120B contract: not applicable.
- Bundle status: listed as inspected and disabled; no call is made.

## Perplexity

- Existing first-party adapter in the targeted active folders: not found.
- Credential environment name: not found.
- Exact GPT-OSS 120B contract: not established.
- Bundle status: listed as inspected and disabled; no call is made.

## NVIDIA API Catalog / Nemotron

- Exact model: `nvidia/nemotron-3-ultra-550b-a55b`.
- Existing credential: configured in the local environment; its value was not read, printed, copied, or written.
- Governing class: NVIDIA API trial, limited credits; not an unlimited-free or production route.
- Bundle status: implemented as an opt-in adapter, disabled by default.
- Spend guard: `trial-only`, `autoSpend: false`, no retries/fallback, conservative quotas, and per-request `allow_trial_credit: true` acknowledgement.
- Deployment status: not uploaded to Cloudflare and not published.

No credential value was printed, copied, stored, or committed during this inspection.
