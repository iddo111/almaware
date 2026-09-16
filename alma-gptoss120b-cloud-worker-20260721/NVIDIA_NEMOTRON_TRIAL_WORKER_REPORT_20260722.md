# NVIDIA Nemotron trial worker integration report

Timestamp: 2026-07-22 19:57 IDT

## Scope and canonical-path decision

- Reused the existing Alma cloud-worker bundle at `D:\CLAUDE\alma-gptoss120b-cloud-worker-20260721`.
- Did not create another Alma, Harness, Federation product, or service directory.
- Did not modify `D:\CLAUDE\dgx4-dual-model-harness`: its README explicitly keeps cloud credentials/routes outside the canonical local two-DGX Harness.
- Did not modify `D:\CLAUDE\alma-federation` or Eran1/Eran2 training.
- Did not deploy, publish, upload a secret, enable billing, or change a cloud account.

## Implemented

- Added an opt-in `nvidia` provider adapter for exact model `nvidia/nemotron-3-ultra-550b-a55b`.
- Kept the pre-existing Groq GPT-OSS route as the default.
- Added six independent gates before an NVIDIA network request:
  1. `PROVIDER=nvidia`
  2. exact NVIDIA model ID
  3. `NVIDIA_TRIAL_ENABLED=true`
  4. `NVIDIA_BILLING_MODE=trial-only`
  5. `NVIDIA_API_KEY` present
  6. per-request `allow_trial_credit: true`
- Added `trial-credit-limited`, `trial-only`, `autoSpend: false`, and acknowledgement truth fields/status headers.
- Added explicit `accountCreditBalanceVerified: false` and `providerBillingGuarantee: false`; the Worker does not pretend to know external account billing state.
- Added NVIDIA-specific conservative defaults: 3 requests/day, 2 requests/minute, 256 maximum completion tokens.
- No retry, paid-provider escalation, local fallback, DGX fallback, or provider substitution is implemented.
- Added a reusable live verifier which refuses to run without `--allow-trial-credit` and never prints the API key.

## Evidence

### Static/unit verification

Command:

```powershell
npm test
npm run check
```

Result:

- `7/7` tests passed.
- Syntax checks passed for Worker, providers, and browser app.
- Tests prove trial opt-in status, refusal before provider fetch without acknowledgement, exact model routing, no-auto-spend headers, streaming output, and quota enforcement.

### Live end-to-end worker generation

Command:

```powershell
npm run verify:nvidia-trial -- --allow-trial-credit
```

Safe result:

```json
{
  "VERIFIED": true,
  "executionMode": "local-worker-module-with-live-provider",
  "provider": "nvidia",
  "model": "nvidia/nemotron-3-ultra-550b-a55b",
  "exactMarker": "ALMA_NVIDIA_WORKER_OK_20260722165737",
  "nonemptyGeneration": true,
  "generationVerified": true,
  "billingMode": "trial-only",
  "pricingClass": "trial-credit-limited",
  "autoSpend": false,
  "dayRequests": 1
}
```

This exercised `worker.fetch -> provider adapter -> https://integrate.api.nvidia.com/v1/chat/completions -> streamed SSE -> worker audit -> quota status` with exact provider/model headers and an exact-marker response.

## Status

- **VERIFIED**: existing Worker module routes to the exact NVIDIA Nemotron Ultra model and returns an exact nonempty marker.
- **ACTIVE**: local opt-in provider implementation and reusable verifier.
- **INACTIVE BY DESIGN**: Cloudflare/public deployment, secret upload, and browser exposure were not performed because publishing was explicitly out of scope.
- **UNKNOWN**: remaining NVIDIA trial-credit balance and exact per-account quota; no API exposing that balance was used.
- **BLOCKED FOR PRODUCTION**: NVIDIA API Trial Terms do not authorize production use without a separate subscription. This integration is research/trial only.

## Rollback

Runtime rollback requires no file deletion or cloud action:

- keep or restore `PROVIDER=groq`; or
- omit NVIDIA variables; or
- set `NVIDIA_TRIAL_ENABLED=false`.

Those states prevent NVIDIA provider calls. Because no deployment or secret upload occurred, there is no external state to roll back.

## Changed files

- `src/providers.js`
- `src/worker.js`
- `test/worker.test.mjs`
- `scripts/verify-nvidia-trial.mjs`
- `package.json`
- `README.md`
- `PROVIDER-INVENTORY.md`
- this report
