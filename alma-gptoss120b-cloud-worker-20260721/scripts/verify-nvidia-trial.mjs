import assert from "node:assert/strict";
import worker, { QuotaGate } from "../src/worker.js";

if (!process.argv.includes("--allow-trial-credit")) {
  throw new Error("Refusing live NVIDIA call without --allow-trial-credit");
}
if (!process.env.NVIDIA_API_KEY) {
  throw new Error("NVIDIA_API_KEY is not configured");
}

class MemoryStorage {
  constructor() { this.values = new Map(); }
  async get(key) { return this.values.get(key); }
  async put(key, value) { this.values.set(key, structuredClone(value)); }
}

function quotaBinding() {
  const gate = new QuotaGate({ storage: new MemoryStorage() });
  return {
    idFromName: (name) => name,
    get: () => ({
      fetch: (input, init) => gate.fetch(input instanceof Request ? input : new Request(input, init))
    })
  };
}

function extractSseContent(raw) {
  let content = "";
  for (const line of raw.split("\n")) {
    if (!line.startsWith("data:") || line.includes("[DONE]")) continue;
    try {
      const event = JSON.parse(line.slice(5).trim());
      content += String(event?.choices?.[0]?.delta?.content || "");
    } catch {
      // Ignore provider comments and incomplete non-content events.
    }
  }
  return content.trim();
}

const marker = `ALMA_NVIDIA_WORKER_OK_${new Date().toISOString().replace(/[^0-9]/g, "").slice(0, 14)}`;
const accessToken = crypto.randomUUID();
const env = {
  PROVIDER: "nvidia",
  MODEL_ID: "nvidia/nemotron-3-ultra-550b-a55b",
  NVIDIA_BASE_URL: "https://integrate.api.nvidia.com/v1",
  NVIDIA_API_KEY: process.env.NVIDIA_API_KEY,
  NVIDIA_TRIAL_ENABLED: "true",
  NVIDIA_BILLING_MODE: "trial-only",
  NVIDIA_MAX_COMPLETION_TOKENS: "128",
  NVIDIA_DAILY_REQUEST_LIMIT: "1",
  NVIDIA_MINUTE_REQUEST_LIMIT: "1",
  CHAT_ACCESS_TOKEN: accessToken,
  MAX_MESSAGE_CHARS: "2000",
  MINUTE_TOKEN_LIMIT: "2000",
  QUOTA: quotaBinding(),
  ASSETS: { fetch: () => new Response("asset") }
};

const before = await worker.fetch(
  new Request("https://alma.local/api/status"),
  env,
  { waitUntil() {} }
);
const beforeStatus = await before.json();
assert.equal(beforeStatus.ok, true);
assert.equal(beforeStatus.provider, "nvidia");
assert.equal(beforeStatus.model, "nvidia/nemotron-3-ultra-550b-a55b");
assert.equal(beforeStatus.billingMode, "trial-only");
assert.equal(beforeStatus.autoSpend, false);

const pending = [];
const response = await worker.fetch(new Request("https://alma.local/api/chat", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-Alma-Access": accessToken
  },
  body: JSON.stringify({
    messages: [{ role: "user", content: `Reply with exactly ${marker} and nothing else.` }],
    allow_trial_credit: true,
    temperature: 0,
    max_completion_tokens: 128
  })
}), env, { waitUntil(value) { pending.push(value); } });

assert.equal(response.status, 200, `worker returned HTTP ${response.status}`);
assert.equal(response.headers.get("X-Alma-Provider"), "nvidia");
assert.equal(response.headers.get("X-Alma-Model"), "nvidia/nemotron-3-ultra-550b-a55b");
assert.equal(response.headers.get("X-Alma-Billing-Mode"), "trial-only");
assert.equal(response.headers.get("X-Alma-Auto-Spend"), "false");
const raw = await response.text();
const content = extractSseContent(raw);
assert.equal(content, marker);
await Promise.all(pending);

const after = await worker.fetch(
  new Request("https://alma.local/api/status"),
  env,
  { waitUntil() {} }
);
const afterStatus = await after.json();
assert.equal(afterStatus.generationVerified, true);
assert.equal(afterStatus.quota.lastProvider, "nvidia");
assert.equal(afterStatus.quota.lastModel, "nvidia/nemotron-3-ultra-550b-a55b");

console.log(JSON.stringify({
  VERIFIED: true,
  executionMode: "local-worker-module-with-live-provider",
  provider: afterStatus.provider,
  model: afterStatus.model,
  exactMarker: marker,
  nonemptyGeneration: true,
  generationVerified: afterStatus.generationVerified,
  billingMode: afterStatus.billingMode,
  pricingClass: afterStatus.pricingClass,
  autoSpend: afterStatus.autoSpend,
  dayRequests: afterStatus.quota.dayRequests
}));

