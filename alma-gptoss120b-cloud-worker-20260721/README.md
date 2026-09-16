# Alma GPT-OSS 120B — cloud-only chat

This existing bundle implements the exact Chat 120 contract and now also contains
an opt-in NVIDIA Nemotron trial adapter. The Groq GPT-OSS route remains the default:

```text
public browser
  -> Cloudflare Worker static assets (the complete UI)
  -> Cloudflare Worker /api gateway
  -> GroqCloud Free
  -> openai/gpt-oss-120b
```

There is no PC or DGX inference, gateway, UI server, proxy, or fallback.

## What is included

- Responsive Hebrew/English chat UI with a right-side cloud signal rail.
- Streaming `POST /api/chat` proxy to the exact Groq model.
- Honest `GET /api/status` and `GET /health` truth fields.
- Required private `CHAT_ACCESS_TOKEN`; the Groq key never reaches the browser.
- Durable Object quota guard with per-minute token/request and daily request caps.
- A post-deployment acceptance script that rejects local URLs and requires a nonempty real generation.
- An explicitly selected NVIDIA API Catalog trial route for
  `nvidia/nemotron-3-ultra-550b-a55b`; it is disabled by default and has no paid fallback.

## Credentials and current blocker

Cloudflare Wrangler is already authenticated for the current account. A Worker-compatible Gemini key was not found; Gemini CLI OAuth is not a secret that can be copied into this Worker. No Perplexity adapter or credential was found. Neither provider serves the exact required GPT-OSS 120B route in this bundle, so neither is called.

The remaining required credential is a Groq free-tier API key. Create it in the Groq console. Do not paste it into source, `.env`, chat, or the browser UI.

An existing local `NVIDIA_API_KEY` can be used by the opt-in verifier without
copying or printing its value. It has not been uploaded to Cloudflare by this
change, and the NVIDIA adapter has not been published.

## Test locally without real provider calls

```powershell
Set-Location D:\CLAUDE\alma-gptoss120b-cloud-worker-20260721
npm test
npm run check
```

Tests mock GroqCloud and prove authorization, cloud truth fields, streaming, exact model routing, and quota rejection. They do not claim live inference.

## Opt-in NVIDIA Nemotron trial route

NVIDIA API Catalog access is governed by trial terms and may consume limited
trial credits. The adapter therefore requires every one of these gates:

- `PROVIDER=nvidia`;
- `MODEL_ID=nvidia/nemotron-3-ultra-550b-a55b`;
- `NVIDIA_TRIAL_ENABLED=true`;
- `NVIDIA_BILLING_MODE=trial-only`;
- a configured `NVIDIA_API_KEY` secret;
- `allow_trial_credit: true` in each chat request.

The worker reports `billingMode: trial-only`,
`pricingClass: trial-credit-limited`, and `autoSpend: false`. It never retries a
failed NVIDIA request through another provider, never enables billing, and
surfaces quota/rejection responses. Conservative defaults are one explicit
verification request per run, three NVIDIA requests per day, two per minute,
and 256 maximum completion tokens.

`autoSpend: false` describes Worker behavior, not the external NVIDIA account:
the Worker cannot inspect the remaining credit balance or guarantee the
provider account's billing configuration. Status therefore also reports
`accountCreditBalanceVerified: false` and `providerBillingGuarantee: false`.

Run the live exact-marker verifier only when intentionally allowing one trial
request:

```powershell
Set-Location D:\CLAUDE\alma-gptoss120b-cloud-worker-20260721
npm run verify:nvidia-trial -- --allow-trial-credit
```

This exercises the existing Worker module and the live NVIDIA endpoint without
deploying or publishing the Worker. Omitting `--allow-trial-credit` refuses the
call before network access.

## Intentional cloud deployment

The setup script has a safety stop because `wrangler secret put` and `wrangler deploy` change cloud state. After reviewing this folder:

```powershell
.\scripts\setup-cloud.ps1 -ConfirmCloudWrites
```

It interactively stores `GROQ_API_KEY` and `CHAT_ACCESS_TOKEN` as Cloudflare secrets and deploys the Worker. Save the private chat token in a password manager; users enter that token through the UI's **מפתח גישה** dialog. It is kept only in browser `sessionStorage`.

## Acceptance

Use the HTTPS Worker URL printed by `wrangler deploy`:

```powershell
.\scripts\acceptance.ps1 -BaseUrl 'https://alma-gpt-oss-120b.<your-workers-subdomain>.workers.dev'
```

Acceptance requires:

- public HTTPS, never localhost/private IP;
- runtime `cloudflare-worker`;
- exact model `openai/gpt-oss-120b`;
- local and DGX fallback both false;
- a real streamed response containing a unique nonce;
- `generationVerified: true` after the response.

Run the same URL from a phone on cellular data for the final physical independence check.

## Free-tier boundaries

The Worker guards below the official Groq free ceiling. Defaults are deliberately conservative and can be changed in `wrangler.jsonc`, never from the browser:

- 900 requests/day;
- 20 requests/minute;
- 7,000 estimated tokens/minute;
- 768 maximum output tokens per request;
- 12,000 input characters per conversation.

Free tiers are quota-limited and have no production SLA. A `429` is shown as a quota failure, not silently routed elsewhere.

NVIDIA's API Catalog route is also a limited trial rather than unlimited free
service. Keep it disabled unless a specific request acknowledges trial-credit
use. Rollback is configuration-only: leave `PROVIDER=groq`, remove/omit the
NVIDIA variables, or set `NVIDIA_TRIAL_ENABLED=false`.
