let consoleToken = "";
let verifiedRoute = null;
let verificationExpiryTimer = null;
const VERIFICATION_TTL_MS = 5 * 60 * 1000;
const STATUS_POLL_MS = 60 * 1000;

const byId = (id) => document.getElementById(id);

function setState(element, text, kind) {
  element.textContent = text;
  element.className = `state ${kind}`;
}

function formatBytes(value) {
  if (!Number.isFinite(value)) return "--";
  return `${(value / 1024 ** 3).toFixed(2)} GiB`;
}

function addMessage(kind, label, text) {
  const article = document.createElement("article");
  article.className = `message ${kind}-message`;
  const heading = document.createElement("p");
  heading.className = "message-label";
  heading.textContent = label;
  const body = document.createElement("p");
  body.textContent = text;
  article.append(heading, body);
  byId("transcript").appendChild(article);
  article.scrollIntoView({ block: "end", behavior: "smooth" });
}

function verificationIsCurrent(model) {
  return Boolean(
    verifiedRoute &&
    verifiedRoute.model === model.model &&
    verifiedRoute.digest === model.digest &&
    Date.now() - verifiedRoute.verifiedAt < VERIFICATION_TTL_MS
  );
}

function clearVerifiedRoute() {
  verifiedRoute = null;
  if (verificationExpiryTimer !== null) {
    clearTimeout(verificationExpiryTimer);
    verificationExpiryTimer = null;
  }
}

function rememberVerifiedRoute(model, digest) {
  clearVerifiedRoute();
  verifiedRoute = { model, digest, verifiedAt: Date.now() };
  verificationExpiryTimer = setTimeout(() => {
    clearVerifiedRoute();
    void refreshStatus();
  }, VERIFICATION_TTL_MS);
}

function renderNode(node) {
  const wrapper = document.createElement("article");
  wrapper.className = "node";
  const loaded = Math.max(0, Math.min(Number(node.weight_files || 0), 15));
  const shards = Array.from({ length: 15 }, (_, index) =>
    `<span class="shard ${index < loaded ? "loaded" : ""}" title="Shard ${index + 1}"></span>`
  ).join("");
  const state = node.reachable ? `${loaded}/15 shards · ${formatBytes(node.weight_bytes)}` : `Unreachable · ${node.error || "unknown error"}`;
  wrapper.innerHTML = `
    <div class="node-head">
      <strong>${node.name} / ${node.hostname || "no identity"}</strong>
      <span class="node-meta">${state}</span>
    </div>
    <div class="shard-rail" aria-label="${loaded} of 15 checkpoint shards present">${shards}</div>`;
  return wrapper;
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (options.method === "POST") headers["X-Console-Token"] = consoleToken;
  const response = await fetch(path, { ...options, headers, cache: "no-store" });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

async function refreshStatus() {
  byId("refresh").disabled = true;
  setState(byId("model-state"), "Checking", "pending");
  try {
    const status = await api("/api/status");
    const model = status.model;
    byId("model-name").textContent = model.model || "gpt-oss:120b";
    byId("model-parameters").textContent = model.parameters || "--";
    byId("model-quantization").textContent = model.quantization || "--";
    const inferenceVerified = verificationIsCurrent(model);
    if (!inferenceVerified && verifiedRoute) clearVerifiedRoute();
    if (inferenceVerified && model.loaded) {
      setState(byId("model-state"), "Verified", "good");
    } else {
      setState(byId("model-state"), model.loaded ? "Route listed" : "Blocked", model.loaded ? "pending" : "bad");
    }
    setState(byId("cluster-state"), status.cluster_ready ? "Copies present" : "Incomplete", status.cluster_ready ? "good" : "bad");
    byId("nodes").replaceChildren(...status.nodes.map(renderNode));
    byId("training-gate").textContent = status.training_gate;
    byId("fullweights-gate").textContent = status.fullweights_training_gate;
    byId("seed-count").textContent = status.curriculum.seed_examples;
    byId("eval-count").textContent = status.curriculum.eval_cases;
    byId("interfaces").textContent = status.curriculum.interfaces.join(" / ");
    byId("training-lock").textContent = "Locked";
    byId("training-lock").className = "lock";
    byId("start-training").disabled = true;
    byId("last-refresh").textContent = `Live refresh ${status.timestamp}`;
    byId("chat-status").textContent = model.loaded
      ? (inferenceVerified ? "Exact model was verified by a fresh visible GUI nonce." : "Route listed; submit a fresh GUI prompt to verify output.")
      : (model.error || "Inference blocked.");
  } catch (error) {
    clearVerifiedRoute();
    setState(byId("model-state"), "Blocked", "bad");
    byId("chat-status").textContent = error.message;
  } finally {
    byId("refresh").disabled = false;
  }
}

byId("chat-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const prompt = byId("prompt").value.trim();
  if (!prompt) return;
  clearVerifiedRoute();
  setState(byId("model-state"), "Checking", "pending");
  const nonceBytes = crypto.getRandomValues(new Uint8Array(8));
  const nonce = `GPTOSS-GUI-${Array.from(nonceBytes, (value) => value.toString(16).padStart(2, "0")).join("").toUpperCase()}`;
  const verificationPrompt = `${prompt}\n\nVerification nonce (return exactly): ${nonce}`;
  addMessage("user", "You", verificationPrompt);
  byId("prompt").value = "";
  byId("send").disabled = true;
  byId("chat-status").textContent = "GPT-OSS 120B is generating...";
  try {
    const result = await api("/api/chat", {
      method: "POST",
      body: JSON.stringify({ prompt: verificationPrompt, nonce, max_tokens: 256 }),
    });
    if (!result.verified || result.done !== true || result.model !== "gpt-oss:120b" || result.nonce !== nonce || !result.route_digest || !result.content.includes(nonce)) {
      throw new Error("Visible exact-model nonce verification failed.");
    }
    rememberVerifiedRoute(result.model, result.route_digest);
    addMessage("assistant", result.model, result.content);
    setState(byId("model-state"), "Verified", "good");
    byId("chat-status").textContent = `${result.model} visibly returned ${nonce}.`;
  } catch (error) {
    clearVerifiedRoute();
    setState(byId("model-state"), "Blocked", "bad");
    addMessage("error", "Blocked", error.message);
    byId("chat-status").textContent = error.message;
  } finally {
    byId("send").disabled = false;
  }
});

byId("preflight").addEventListener("click", async () => {
  byId("preflight").disabled = true;
  byId("training-log").textContent = "Running the native runner's safe no-load preflight...";
  try {
    const result = await api("/api/train/preflight", { method: "POST", body: "{}" });
    byId("training-log").textContent = JSON.stringify(result, null, 2);
    await refreshStatus();
  } catch (error) {
    byId("training-log").textContent = `BLOCKED: ${error.message}`;
  } finally {
    byId("preflight").disabled = false;
  }
});

byId("tool-eval").addEventListener("click", async () => {
  byId("tool-eval").disabled = true;
  byId("training-log").textContent = "Running exact-model tool-call conformance...";
  try {
    const result = await api("/api/tool-eval", { method: "POST", body: "{}" });
    byId("training-log").textContent = JSON.stringify(result, null, 2);
  } catch (error) {
    byId("training-log").textContent = `BLOCKED: ${error.message}`;
  } finally {
    byId("tool-eval").disabled = false;
  }
});

byId("start-training").addEventListener("click", async () => {
  byId("start-training").disabled = true;
  try {
    const result = await api("/api/train/start", {
      method: "POST",
      body: JSON.stringify({ method: "native" }),
    });
    byId("training-log").textContent = JSON.stringify(result, null, 2);
  } catch (error) {
    byId("training-log").textContent = `BLOCKED: ${error.message}`;
  } finally {
    await refreshStatus();
  }
});

byId("refresh").addEventListener("click", refreshStatus);

async function initialize() {
  const config = await api("/api/config");
  consoleToken = config.token;
  byId("chat-model-badge").textContent = config.model;
  await refreshStatus();
}

initialize().catch((error) => {
  byId("chat-status").textContent = `Console initialization failed: ${error.message}`;
});

setInterval(() => { void refreshStatus(); }, STATUS_POLL_MS);
