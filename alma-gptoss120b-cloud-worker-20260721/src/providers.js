const DEFAULT_BASE = "https://api.groq.com/openai/v1";
const NVIDIA_DEFAULT_BASE = "https://integrate.api.nvidia.com/v1";
const REQUIRED_MODEL = "openai/gpt-oss-120b";
const NVIDIA_NEMOTRON_MODEL = "nvidia/nemotron-3-ultra-550b-a55b";

function integer(value, fallback, min, max) {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  return Number.isFinite(parsed) ? Math.min(max, Math.max(min, parsed)) : fallback;
}

export function publicProviderCatalog(env = {}) {
  const selected = env.PROVIDER || "groq";
  return [
    {
      id: "groq",
      label: "GroqCloud Free",
      active: selected === "groq",
      model: env.MODEL_ID || REQUIRED_MODEL,
      credentialConfigured: Boolean(env.GROQ_API_KEY),
      cloudInference: true
    },
    {
      id: "nvidia",
      label: "NVIDIA Nemotron API Trial",
      active: selected === "nvidia",
      enabled: env.NVIDIA_TRIAL_ENABLED === "true",
      model: NVIDIA_NEMOTRON_MODEL,
      credentialConfigured: Boolean(env.NVIDIA_API_KEY),
      cloudInference: true,
      pricingClass: "trial-credit-limited",
      billingMode: "trial-only",
      autoSpend: false,
      accountCreditBalanceVerified: false,
      providerBillingGuarantee: false,
      requestAcknowledgementRequired: true,
      note: "Opt-in NVIDIA API Catalog trial route. It never retries into a paid provider or silently falls back."
    },
    {
      id: "gemini",
      label: "Google Gemini",
      active: false,
      credentialConfigured: false,
      cloudInference: true,
      note: "Adapter inspected but intentionally disabled: no Worker-compatible API secret was found and it does not serve the required GPT-OSS 120B model."
    },
    {
      id: "perplexity",
      label: "Perplexity",
      active: false,
      credentialConfigured: false,
      cloudInference: true,
      note: "No existing adapter or credential was found; no paid call is attempted."
    }
  ];
}

function nvidiaAdapter(env) {
  if (env.NVIDIA_TRIAL_ENABLED !== "true") {
    throw new Error("NVIDIA trial route is disabled; set NVIDIA_TRIAL_ENABLED=true explicitly");
  }
  if ((env.NVIDIA_BILLING_MODE || "trial-only") !== "trial-only") {
    throw new Error("NVIDIA worker supports trial-only billing mode; paid or automatic billing is forbidden");
  }
  if (!env.NVIDIA_API_KEY) throw new Error("NVIDIA_API_KEY is not configured in the Worker");
  if (env.MODEL_ID && env.MODEL_ID !== NVIDIA_NEMOTRON_MODEL) {
    throw new Error(`NVIDIA trial contract requires ${NVIDIA_NEMOTRON_MODEL}`);
  }

  return {
    id: "nvidia",
    label: "NVIDIA Nemotron API Trial",
    model: NVIDIA_NEMOTRON_MODEL,
    pricingClass: "trial-credit-limited",
    billingMode: "trial-only",
    autoSpend: false,
    accountCreditBalanceVerified: false,
    providerBillingGuarantee: false,
    requiresTrialCreditAcknowledgement: true,
    endpoint: `${(env.NVIDIA_BASE_URL || NVIDIA_DEFAULT_BASE).replace(/\/$/, "")}/chat/completions`,
    buildRequest(messages, options = {}) {
      return new Request(this.endpoint, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${env.NVIDIA_API_KEY}`,
          "Content-Type": "application/json",
          "Accept": "text/event-stream"
        },
        body: JSON.stringify({
          model: NVIDIA_NEMOTRON_MODEL,
          messages,
          stream: true,
          temperature: Math.min(1, Math.max(0, Number(options.temperature ?? 0))),
          max_tokens: integer(
            options.maxCompletionTokens,
            integer(env.NVIDIA_MAX_COMPLETION_TOKENS, 256, 32, 1024),
            32,
            integer(env.NVIDIA_MAX_COMPLETION_TOKENS, 256, 32, 1024)
          ),
          chat_template_kwargs: {
            enable_thinking: false,
            force_nonempty_content: true
          }
        })
      });
    }
  };
}

function groqAdapter(env) {
  if (!env.GROQ_API_KEY) throw new Error("GROQ_API_KEY is not configured in the Worker");
  if ((env.MODEL_ID || REQUIRED_MODEL) !== REQUIRED_MODEL) {
    throw new Error(`Cloud contract requires ${REQUIRED_MODEL}`);
  }

  return {
    id: "groq",
    label: "GroqCloud Free",
    model: REQUIRED_MODEL,
    endpoint: `${(env.GROQ_BASE_URL || DEFAULT_BASE).replace(/\/$/, "")}/chat/completions`,
    buildRequest(messages, options = {}) {
      return new Request(this.endpoint, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${env.GROQ_API_KEY}`,
          "Content-Type": "application/json",
          "Accept": "text/event-stream"
        },
        body: JSON.stringify({
          model: REQUIRED_MODEL,
          messages,
          stream: true,
          reasoning_effort: "low",
          include_reasoning: false,
          temperature: Math.min(1.2, Math.max(0, Number(options.temperature ?? 0.35))),
          max_completion_tokens: integer(
            options.maxCompletionTokens,
            integer(env.MAX_COMPLETION_TOKENS, 768, 64, 2048),
            64,
            integer(env.MAX_COMPLETION_TOKENS, 768, 64, 2048)
          )
        })
      });
    }
  };
}

export function resolveProvider(env = {}) {
  const selected = env.PROVIDER || "groq";
  if (selected === "groq") return groqAdapter(env);
  if (selected === "nvidia") return nvidiaAdapter(env);
  throw new Error(`Provider ${selected} is disabled`);
}

export const REQUIRED_GPT_OSS_MODEL = REQUIRED_MODEL;
export const REQUIRED_NVIDIA_NEMOTRON_MODEL = NVIDIA_NEMOTRON_MODEL;
