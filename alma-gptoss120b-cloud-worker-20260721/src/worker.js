import { publicProviderCatalog, resolveProvider } from "./providers.js";

const JSON_HEADERS = {
  "Content-Type": "application/json; charset=utf-8",
  "Cache-Control": "no-store",
  "X-Content-Type-Options": "nosniff"
};

function json(data, status = 200, headers = {}) {
  return new Response(JSON.stringify(data), { status, headers: { ...JSON_HEADERS, ...headers } });
}

function clampInt(value, fallback, min, max) {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  return Number.isFinite(parsed) ? Math.min(max, Math.max(min, parsed)) : fallback;
}

function utf8Bytes(value) {
  return new TextEncoder().encode(String(value));
}

async function secureEqual(left, right) {
  const [a, b] = await Promise.all([
    crypto.subtle.digest("SHA-256", utf8Bytes(left)),
    crypto.subtle.digest("SHA-256", utf8Bytes(right))
  ]);
  const aa = new Uint8Array(a);
  const bb = new Uint8Array(b);
  let mismatch = aa.length ^ bb.length;
  for (let index = 0; index < aa.length; index += 1) mismatch |= aa[index] ^ bb[index];
  return mismatch === 0;
}

async function authorized(request, env) {
  if (!env.CHAT_ACCESS_TOKEN) return false;
  return secureEqual(request.headers.get("X-Alma-Access") || "", env.CHAT_ACCESS_TOKEN);
}

function normalizeMessages(payload, maxChars) {
  const raw = Array.isArray(payload.messages)
    ? payload.messages
    : [{ role: "user", content: String(payload.prompt || "") }];
  const messages = raw.slice(-16).map((entry) => ({
    role: ["system", "user", "assistant"].includes(entry?.role) ? entry.role : "user",
    content: String(entry?.content || "").trim()
  })).filter((entry) => entry.content);

  if (!messages.length || messages[messages.length - 1].role !== "user") {
    throw new Error("The last nonempty message must be from the user");
  }
  const totalChars = messages.reduce((sum, message) => sum + message.content.length, 0);
  if (totalChars > maxChars) throw new Error(`Conversation exceeds the ${maxChars}-character cloud quota guard`);
  return { messages, totalChars };
}

async function quotaStub(env) {
  const id = env.QUOTA.idFromName("alma-gpt-oss-120b-global");
  return env.QUOTA.get(id);
}

async function quotaCall(env, path, body) {
  const stub = await quotaStub(env);
  return stub.fetch(`https://quota.internal${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body)
  });
}

async function quotaStatus(env) {
  if (!env.QUOTA) return { available: false, reason: "QUOTA binding is missing" };
  try {
    const response = await quotaCall(env, "/status");
    return await response.json();
  } catch (error) {
    return { available: false, reason: String(error) };
  }
}

async function statusResponse(env) {
  const providers = publicProviderCatalog(env);
  const selectedProvider = env.PROVIDER || "groq";
  const provider = providers.find((entry) => entry.id === selectedProvider) || null;
  const quota = await quotaStatus(env);
  const providerReady = Boolean(
    provider?.credentialConfigured &&
    (selectedProvider !== "nvidia" || (
      provider.enabled &&
      (env.NVIDIA_BILLING_MODE || "trial-only") === "trial-only"
    ))
  );
  return json({
    ok: Boolean(providerReady && env.CHAT_ACCESS_TOKEN && env.QUOTA),
    service: "Alma Cloud Model Worker",
    runtime: "cloudflare-worker",
    uiHostedInCloud: true,
    gatewayHostedInCloud: true,
    inferenceHostedInCloud: true,
    localFallback: false,
    dgxFallback: false,
    provider: selectedProvider,
    model: provider?.model || null,
    credentialConfigured: Boolean(provider?.credentialConfigured),
    accessGuardConfigured: Boolean(env.CHAT_ACCESS_TOKEN),
    billingMode: provider?.billingMode || null,
    pricingClass: provider?.pricingClass || null,
    autoSpend: provider?.autoSpend ?? null,
    accountCreditBalanceVerified: provider?.accountCreditBalanceVerified ?? null,
    providerBillingGuarantee: provider?.providerBillingGuarantee ?? null,
    trialCreditAcknowledgementRequired: Boolean(provider?.requestAcknowledgementRequired),
    generationVerified: Boolean(
      quota.lastGenerationVerified &&
      quota.lastProvider === selectedProvider &&
      quota.lastModel === provider?.model
    ),
    lastGenerationAt: quota.lastGenerationAt || null,
    quota,
    providers
  });
}

async function recordNonemptyGeneration(env, provider) {
  try {
    await quotaCall(env, "/success", { model: provider.model, provider: provider.id });
  } catch {
    // Generation already reached the client. Status bookkeeping must not break chat.
  }
}

async function auditSse(stream, env, provider) {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let nonempty = false;
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      if (!line.startsWith("data:") || line.includes("[DONE]")) continue;
      try {
        const event = JSON.parse(line.slice(5).trim());
        if (String(event?.choices?.[0]?.delta?.content || "").trim()) nonempty = true;
      } catch {
        // Ignore partial or non-JSON provider comments.
      }
    }
  }
  if (nonempty) await recordNonemptyGeneration(env, provider);
}

async function chatResponse(request, env, ctx) {
  if (!env.CHAT_ACCESS_TOKEN || !env.QUOTA) {
    return json({ error: "Cloud deployment is incomplete", code: "CLOUD_NOT_CONFIGURED" }, 503);
  }
  if (!(await authorized(request, env))) {
    return json({ error: "Enter the private Alma access token", code: "UNAUTHORIZED" }, 401);
  }

  let payload;
  try {
    payload = await request.json();
  } catch {
    return json({ error: "Request body must be JSON", code: "BAD_JSON" }, 400);
  }

  let provider;
  try {
    provider = resolveProvider(env);
  } catch (error) {
    return json({ error: error.message, code: "PROVIDER_DISABLED" }, 503);
  }
  if (provider.requiresTrialCreditAcknowledgement && payload.allow_trial_credit !== true) {
    return json({
      error: "This request may consume limited NVIDIA API trial credits. Set allow_trial_credit=true for this request.",
      code: "TRIAL_CREDIT_ACK_REQUIRED",
      billingMode: provider.billingMode,
      autoSpend: false
    }, 412);
  }

  let normalized;
  try {
    normalized = normalizeMessages(payload, clampInt(env.MAX_MESSAGE_CHARS, 12000, 1000, 32000));
  } catch (error) {
    return json({ error: error.message, code: "BAD_MESSAGES" }, 400);
  }

  const providerMaxCompletionTokens = provider.id === "nvidia"
    ? clampInt(env.NVIDIA_MAX_COMPLETION_TOKENS, 256, 32, 1024)
    : clampInt(env.MAX_COMPLETION_TOKENS, 768, 64, 2048);
  const maxCompletionTokens = clampInt(
    payload.max_completion_tokens,
    providerMaxCompletionTokens,
    provider.id === "nvidia" ? 32 : 64,
    providerMaxCompletionTokens
  );
  const estimatedTokens = Math.ceil(normalized.totalChars / 4) + maxCompletionTokens;
  const quotaResponse = await quotaCall(env, "/consume", {
    estimatedTokens,
    dailyLimit: provider.id === "nvidia"
      ? clampInt(env.NVIDIA_DAILY_REQUEST_LIMIT, 3, 1, 20)
      : clampInt(env.DAILY_REQUEST_LIMIT, 900, 1, 1000),
    minuteRequestLimit: provider.id === "nvidia"
      ? clampInt(env.NVIDIA_MINUTE_REQUEST_LIMIT, 2, 1, 5)
      : clampInt(env.MINUTE_REQUEST_LIMIT, 20, 1, 30),
    minuteTokenLimit: clampInt(env.MINUTE_TOKEN_LIMIT, 7000, 1000, 8000)
  });
  if (!quotaResponse.ok) {
    const detail = await quotaResponse.json();
    return json(detail, 429, { "Retry-After": String(detail.retryAfter || 60) });
  }

  let upstream;
  try {
    upstream = await fetch(provider.buildRequest(normalized.messages, {
      temperature: payload.temperature,
      maxCompletionTokens
    }));
  } catch (error) {
    return json({ error: `${provider.label} could not be reached`, detail: String(error), code: "UPSTREAM_NETWORK" }, 502);
  }

  if (!upstream.ok || !upstream.body) {
    const detail = (await upstream.text()).slice(0, 1200);
    return json({
      error: `${provider.label} rejected the generation request`,
      upstreamStatus: upstream.status,
      detail,
      code: "UPSTREAM_REJECTED"
    }, upstream.status === 429 ? 429 : 502);
  }

  const [clientStream, auditStream] = upstream.body.tee();
  ctx.waitUntil(auditSse(auditStream, env, provider));
  return new Response(clientStream, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Accel-Buffering": "no",
      "X-Alma-Runtime": "cloudflare-worker",
      "X-Alma-Provider": provider.id,
      "X-Alma-Model": provider.model,
      "X-Alma-Billing-Mode": provider.billingMode || "provider-default",
      "X-Alma-Auto-Spend": String(provider.autoSpend === true),
      "X-Alma-Provider-Billing-Verified": String(provider.providerBillingGuarantee === true),
      "X-Alma-Local-Fallback": "false",
      "X-Content-Type-Options": "nosniff"
    }
  });
}

export class QuotaGate {
  constructor(state) {
    this.state = state;
  }

  async read(now = Date.now()) {
    const stored = await this.state.storage.get("quota");
    const minuteBucket = Math.floor(now / 60000);
    const dayBucket = new Date(now).toISOString().slice(0, 10);
    const data = stored || {};
    if (data.minuteBucket !== minuteBucket) {
      data.minuteBucket = minuteBucket;
      data.minuteRequests = 0;
      data.minuteTokens = 0;
    }
    if (data.dayBucket !== dayBucket) {
      data.dayBucket = dayBucket;
      data.dayRequests = 0;
    }
    return data;
  }

  async fetch(request) {
    const url = new URL(request.url);
    const now = Date.now();
    const data = await this.read(now);

    if (url.pathname === "/status") {
      return json({
        available: true,
        day: data.dayBucket,
        dayRequests: data.dayRequests || 0,
        minuteRequests: data.minuteRequests || 0,
        minuteEstimatedTokens: data.minuteTokens || 0,
        lastGenerationVerified: Boolean(data.lastGenerationVerified),
        lastGenerationAt: data.lastGenerationAt || null,
        lastProvider: data.lastProvider || null,
        lastModel: data.lastModel || null
      });
    }

    if (url.pathname === "/success" && request.method === "POST") {
      const body = await request.json();
      data.lastGenerationVerified = true;
      data.lastGenerationAt = new Date(now).toISOString();
      data.lastModel = String(body.model || "");
      data.lastProvider = String(body.provider || "");
      await this.state.storage.put("quota", data);
      return json({ ok: true });
    }

    if (url.pathname !== "/consume" || request.method !== "POST") {
      return json({ error: "Not found" }, 404);
    }

    const body = await request.json();
    const estimatedTokens = clampInt(body.estimatedTokens, 1, 1, 8000);
    const dailyLimit = clampInt(body.dailyLimit, 900, 1, 1000);
    const minuteRequestLimit = clampInt(body.minuteRequestLimit, 20, 1, 30);
    const minuteTokenLimit = clampInt(body.minuteTokenLimit, 7000, 1000, 8000);

    if ((data.dayRequests || 0) >= dailyLimit) {
      return json({ error: "Daily cloud quota guard reached", code: "DAILY_QUOTA", retryAfter: 3600 }, 429);
    }
    if ((data.minuteRequests || 0) >= minuteRequestLimit) {
      return json({ error: "Minute request guard reached", code: "MINUTE_REQUEST_QUOTA", retryAfter: 60 }, 429);
    }
    if ((data.minuteTokens || 0) + estimatedTokens > minuteTokenLimit) {
      return json({ error: "Minute token guard reached", code: "MINUTE_TOKEN_QUOTA", retryAfter: 60 }, 429);
    }

    data.dayRequests = (data.dayRequests || 0) + 1;
    data.minuteRequests = (data.minuteRequests || 0) + 1;
    data.minuteTokens = (data.minuteTokens || 0) + estimatedTokens;
    await this.state.storage.put("quota", data);
    return json({ ok: true, dayRemaining: dailyLimit - data.dayRequests });
  }
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (request.method === "GET" && (url.pathname === "/api/status" || url.pathname === "/health")) {
      return statusResponse(env);
    }
    if (request.method === "POST" && url.pathname === "/api/chat") {
      return chatResponse(request, env, ctx);
    }
    if (url.pathname.startsWith("/api/")) return json({ error: "Not found" }, 404);
    return env.ASSETS.fetch(request);
  }
};
