import { randomUUID } from "node:crypto";
import { mkdir, open, readFile, rename, unlink, writeFile } from "node:fs/promises";
import path from "node:path";

const ACCESS_ENV = "ALMA_CHAT_ACCESS_TOKEN";
const HARD_ENLISTMENT_LIMITS = Object.freeze({
  maxEnlistedWorkers: 16,
  maxDepth: 3,
  maxChildrenPerWorker: 3,
  maxEnlistmentsPerRun: 4,
  maxTaskBudget: 16,
  maxLifetimeHours: 168
});

function asInt(value, fallback, min, max) {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  return Number.isFinite(parsed) ? Math.min(max, Math.max(min, parsed)) : fallback;
}

export function scrubSecrets(value) {
  if (typeof value !== "string") return value;
  return value
    .replace(/\b(?:gsk_|sk-)[A-Za-z0-9_-]{12,}\b/g, "[REDACTED_SECRET]")
    .replace(/\bBearer\s+[^\s"']+/gi, "Bearer [REDACTED_SECRET]")
    .replace(/\b(api[_-]?key|access[_-]?token)\s*[:=]\s*[^\s,"']+/gi, "$1=[REDACTED_SECRET]");
}

function paths(root) {
  const state = path.join(root, "state");
  return {
    root,
    state,
    tasks: path.join(state, "tasks.json"),
    workers: path.join(state, "workers.json"),
    results: path.join(state, "results"),
    quota: path.join(state, "quota.json"),
    lock: path.join(state, "controller.lock")
  };
}

async function readJson(file, fallback) {
  try {
    return JSON.parse(await readFile(file, "utf8"));
  } catch (error) {
    if (error.code === "ENOENT") return structuredClone(fallback);
    throw error;
  }
}

async function writeJsonAtomic(file, value) {
  await mkdir(path.dirname(file), { recursive: true });
  const temporary = `${file}.${process.pid}.tmp`;
  await writeFile(temporary, `${JSON.stringify(value, null, 2)}\n`, { encoding: "utf8", flag: "w" });
  await rename(temporary, file);
}

export async function loadConfig(root) {
  const config = await readJson(path.join(root, "armada.config.json"), null);
  if (!config) throw new Error("armada.config.json is missing");
  if (config.gateway?.expectedModel !== "openai/gpt-oss-120b") {
    throw new Error("Armada is pinned to openai/gpt-oss-120b");
  }
  for (const [name, hardMaximum] of Object.entries(HARD_ENLISTMENT_LIMITS)) {
    if (!Number.isInteger(config.enlistment?.[name]) || config.enlistment[name] < 1 || config.enlistment[name] > hardMaximum) {
      throw new Error(`Unsafe enlistment limit: ${name}`);
    }
  }
  return config;
}

export async function initialize(root) {
  const p = paths(root);
  await mkdir(p.results, { recursive: true });
  const tasks = await readJson(p.tasks, []);
  const workers = await readJson(p.workers, []);
  const quota = await readJson(p.quota, {});
  await writeJsonAtomic(p.tasks, tasks);
  await writeJsonAtomic(p.workers, workers);
  await writeJsonAtomic(p.quota, quota);
  return p;
}

function builtInWorkers(config) {
  return Object.entries(config.roles).map(([id, role]) => ({
    id,
    label: role.label,
    baseRole: id,
    parent: null,
    depth: 0,
    builtin: true,
    purpose: role.systemPrompt,
    createdAt: null,
    expiresAt: null,
    taskBudget: null,
    tasksUsed: 0
  }));
}

function workerIsActive(worker, now = new Date()) {
  if (worker.builtin) return true;
  return new Date(worker.expiresAt).getTime() > now.getTime()
    && worker.tasksUsed < worker.taskBudget;
}

async function workerCatalog(root, config) {
  const p = await initialize(root);
  const enlisted = await readJson(p.workers, []);
  return [...builtInWorkers(config), ...enlisted];
}

function findWorker(catalog, id) {
  return catalog.find((worker) => worker.id === id);
}

function workerSystemPrompt(config, worker) {
  const base = config.roles[worker.baseRole];
  if (!base) throw new Error(`Unknown base role: ${worker.baseRole}`);
  if (worker.builtin) return base.systemPrompt;
  return `${base.systemPrompt}\nSpecialization: ${worker.purpose}\nYou are an enlisted child worker. Stay within this specialization and do not claim to create accounts, credentials, deployments, or physical resources.`;
}

export async function listWorkers(root, config) {
  const now = new Date();
  return (await workerCatalog(root, config)).map((worker) => ({
    ...worker,
    active: workerIsActive(worker, now)
  }));
}

export async function enlistWorker(root, config, {
  parent,
  name,
  baseRole,
  purpose,
  taskBudget,
  lifetimeHours
}) {
  if (!config.enlistment?.enabled) throw new Error("Worker enlistment is disabled");
  const id = String(name || "").trim().toLowerCase();
  if (!/^[a-z][a-z0-9-]{2,31}$/.test(id)) {
    throw new Error("Worker name must be a 3-32 character lowercase slug");
  }
  const cleanedPurpose = scrubSecrets(String(purpose || "").trim());
  if (cleanedPurpose.length < 12 || cleanedPurpose.length > 400) {
    throw new Error("Worker purpose must be 12-400 characters");
  }
  if (!config.roles[baseRole]) throw new Error(`Unknown base role: ${baseRole}`);
  const p = await initialize(root);
  const enlisted = await readJson(p.workers, []);
  const catalog = [...builtInWorkers(config), ...enlisted];
  if (findWorker(catalog, id)) throw new Error(`Worker already exists: ${id}`);
  const parentWorker = findWorker(catalog, parent);
  if (!parentWorker || !workerIsActive(parentWorker)) throw new Error(`Parent worker is not active: ${parent}`);
  if (enlisted.length >= config.enlistment.maxEnlistedWorkers) throw new Error("ENLISTMENT_FLEET_LIMIT");
  const childCount = enlisted.filter((worker) => worker.parent === parent).length;
  if (childCount >= config.enlistment.maxChildrenPerWorker) throw new Error("ENLISTMENT_CHILD_LIMIT");
  const depth = parentWorker.depth + 1;
  if (depth > config.enlistment.maxDepth) throw new Error("ENLISTMENT_DEPTH_LIMIT");
  const budget = asInt(
    taskBudget,
    config.enlistment.defaultTaskBudget,
    1,
    config.enlistment.maxTaskBudget
  );
  const hours = asInt(
    lifetimeHours,
    config.enlistment.defaultLifetimeHours,
    1,
    config.enlistment.maxLifetimeHours
  );
  const createdAt = new Date();
  const worker = {
    id,
    label: id.replaceAll("-", " "),
    baseRole,
    parent,
    depth,
    builtin: false,
    purpose: cleanedPurpose,
    createdAt: createdAt.toISOString(),
    expiresAt: new Date(createdAt.getTime() + hours * 3600000).toISOString(),
    taskBudget: budget,
    tasksUsed: 0
  };
  enlisted.push(worker);
  await writeJsonAtomic(p.workers, enlisted);
  return worker;
}

export async function addTask(root, config, { role, prompt, priority = 50 }) {
  const worker = findWorker(await workerCatalog(root, config), role);
  if (!worker || !workerIsActive(worker)) throw new Error(`Unknown or inactive worker: ${role}`);
  const cleanedPrompt = scrubSecrets(String(prompt || "").trim());
  if (!cleanedPrompt) throw new Error("Task prompt is empty");
  if (cleanedPrompt.length > config.limits.maxInputCharacters) {
    throw new Error(`Task exceeds ${config.limits.maxInputCharacters} input characters`);
  }
  const p = await initialize(root);
  const tasks = await readJson(p.tasks, []);
  const now = new Date().toISOString();
  const task = {
    id: randomUUID(),
    role,
    prompt: cleanedPrompt,
    priority: asInt(priority, 50, 0, 100),
    status: "queued",
    createdAt: now,
    updatedAt: now,
    attempts: 0
  };
  tasks.push(task);
  await writeJsonAtomic(p.tasks, tasks);
  return task;
}

function currentBuckets(now = new Date()) {
  return {
    day: now.toISOString().slice(0, 10),
    minute: Math.floor(now.getTime() / 60000)
  };
}

async function consumeLocalQuota(root, config, estimatedTokens, now = new Date()) {
  const p = paths(root);
  const buckets = currentBuckets(now);
  const ledger = await readJson(p.quota, {});
  if (ledger.day !== buckets.day) {
    ledger.day = buckets.day;
    ledger.dayRequests = 0;
  }
  if (ledger.minute !== buckets.minute) {
    ledger.minute = buckets.minute;
    ledger.minuteRequests = 0;
    ledger.minuteEstimatedTokens = 0;
  }
  if ((ledger.dayRequests || 0) >= config.limits.dailyRequests) throw new Error("LOCAL_DAILY_QUOTA");
  if ((ledger.minuteRequests || 0) >= config.limits.minuteRequests) throw new Error("LOCAL_MINUTE_REQUEST_QUOTA");
  if ((ledger.minuteEstimatedTokens || 0) + estimatedTokens > config.limits.minuteEstimatedTokens) {
    throw new Error("LOCAL_MINUTE_TOKEN_QUOTA");
  }
  ledger.dayRequests = (ledger.dayRequests || 0) + 1;
  ledger.minuteRequests = (ledger.minuteRequests || 0) + 1;
  ledger.minuteEstimatedTokens = (ledger.minuteEstimatedTokens || 0) + estimatedTokens;
  ledger.updatedAt = now.toISOString();
  await writeJsonAtomic(p.quota, ledger);
  return ledger;
}

export function parseSse(text) {
  let output = "";
  for (const line of String(text).split(/\r?\n/)) {
    if (!line.startsWith("data:")) continue;
    const data = line.slice(5).trim();
    if (!data || data === "[DONE]") continue;
    try {
      const event = JSON.parse(data);
      output += String(event?.choices?.[0]?.delta?.content || "");
    } catch {
      // Provider comments and partial diagnostic events are not model output.
    }
  }
  return output.trim();
}

export async function getGatewayStatus(config, fetchImpl = fetch) {
  const response = await fetchImpl(`${config.gateway.baseUrl.replace(/\/$/, "")}/api/status`, {
    headers: { "Cache-Control": "no-cache" }
  });
  if (!response.ok) throw new Error(`Gateway status HTTP ${response.status}`);
  const status = await response.json();
  const identityOk = status.runtime === config.gateway.expectedRuntime
    && status.provider === config.gateway.expectedProvider
    && status.model === config.gateway.expectedModel
    && status.localFallback === false
    && status.dgxFallback === false;
  return { ...status, identityOk };
}

export async function callGateway(config, messages, options = {}, fetchImpl = fetch) {
  const accessToken = options.accessToken || process.env[ACCESS_ENV];
  if (!accessToken) throw new Error(`${ACCESS_ENV} is not set`);
  const response = await fetchImpl(`${config.gateway.baseUrl.replace(/\/$/, "")}/api/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Alma-Access": accessToken
    },
    body: JSON.stringify({
      messages,
      temperature: options.temperature ?? 0.2,
      max_completion_tokens: options.maxCompletionTokens
    })
  });
  if (!response.ok) {
    const detail = scrubSecrets((await response.text()).slice(0, 1200));
    throw new Error(`Gateway HTTP ${response.status}: ${detail}`);
  }
  const runtime = response.headers.get("X-Alma-Runtime");
  const model = response.headers.get("X-Alma-Model");
  const localFallback = response.headers.get("X-Alma-Local-Fallback");
  if (runtime !== config.gateway.expectedRuntime || model !== config.gateway.expectedModel || localFallback !== "false") {
    throw new Error(`Gateway identity mismatch: runtime=${runtime} model=${model} localFallback=${localFallback}`);
  }
  const output = parseSse(await response.text());
  if (!output) throw new Error("Gateway returned no model content");
  return { output: scrubSecrets(output), runtime, model, provider: response.headers.get("X-Alma-Provider") };
}

async function acquireLock(lockFile) {
  await mkdir(path.dirname(lockFile), { recursive: true });
  try {
    const handle = await open(lockFile, "wx");
    await handle.writeFile(JSON.stringify({ pid: process.pid, startedAt: new Date().toISOString() }));
    await handle.close();
  } catch (error) {
    if (error.code !== "EEXIST") throw error;
    throw new Error("ARMADA_LOCKED: another controller run owns the queue");
  }
  return async () => unlink(lockFile).catch(() => {});
}

function estimateTaskTokens(config, task, worker) {
  const maxCompletionTokens = Math.min(config.limits.defaultCompletionTokens, config.limits.maxCompletionTokens);
  return Math.ceil((workerSystemPrompt(config, worker).length + task.prompt.length) / 4) + maxCompletionTokens;
}

export function extractEnlistmentProposal(output) {
  const matches = [...String(output).matchAll(/^ENLIST_WORKER_JSON:\s*(\{.*\})\s*$/gmi)];
  if (!matches.length) return null;
  try {
    const value = JSON.parse(matches.at(-1)[1]);
    return {
      name: String(value.name || ""),
      baseRole: String(value.baseRole || ""),
      purpose: scrubSecrets(String(value.purpose || "")),
      firstTask: scrubSecrets(String(value.firstTask || "")),
      taskBudget: value.taskBudget,
      lifetimeHours: value.lifetimeHours
    };
  } catch {
    return null;
  }
}

async function runOne(config, task, worker, fetchImpl, accessToken, allowEnlistment) {
  const maxCompletionTokens = Math.min(config.limits.defaultCompletionTokens, config.limits.maxCompletionTokens);
  const startedAt = new Date().toISOString();
  try {
    const enlistmentInstruction = allowEnlistment
      ? "\nIf and only if a missing specialization is essential, end with one line: ENLIST_WORKER_JSON: {\"name\":\"lowercase-slug\",\"baseRole\":\"engineering|qa|research|ops\",\"purpose\":\"bounded purpose\",\"firstTask\":\"bounded delegated task\"}. The controller may reject it. Never request accounts, credentials, quota evasion, paid resources, or deployments."
      : "";
    const response = await callGateway(config, [
      { role: "system", content: workerSystemPrompt(config, worker) + enlistmentInstruction },
      { role: "user", content: task.prompt }
    ], { maxCompletionTokens, accessToken }, fetchImpl);
    return {
      taskId: task.id,
      role: task.role,
      status: "completed",
      startedAt,
      completedAt: new Date().toISOString(),
      model: response.model,
      runtime: response.runtime,
      output: response.output,
      enlistmentProposal: allowEnlistment ? extractEnlistmentProposal(response.output) : null
    };
  } catch (error) {
    return {
      taskId: task.id,
      role: task.role,
      status: "failed",
      startedAt,
      completedAt: new Date().toISOString(),
      error: scrubSecrets(String(error.message || error))
    };
  }
}

export async function runQueue(root, config, { fetchImpl = fetch, maxTasks, accessToken, allowEnlistment = false } = {}) {
  if (!(accessToken || process.env[ACCESS_ENV])) throw new Error(`${ACCESS_ENV} is not set`);
  const gateway = await getGatewayStatus(config, fetchImpl);
  if (!gateway.ok || !gateway.identityOk) throw new Error("Gateway health or model identity failed before queue dispatch");
  const p = await initialize(root);
  const release = await acquireLock(p.lock);
  try {
    const tasks = await readJson(p.tasks, []);
    const catalog = await workerCatalog(root, config);
    const remaining = new Map(catalog.map((worker) => [
      worker.id,
      worker.builtin ? Number.POSITIVE_INFINITY : Math.max(0, worker.taskBudget - worker.tasksUsed)
    ]));
    const candidates = tasks
      .filter((task) => task.status === "queued")
      .sort((a, b) => b.priority - a.priority || a.createdAt.localeCompare(b.createdAt));
    const selected = [];
    const selectionLimit = asInt(maxTasks, config.limits.maxTasksPerRun, 1, config.limits.maxTasksPerRun);
    for (const task of candidates) {
      const worker = findWorker(catalog, task.role);
      if (!worker || !workerIsActive(worker) || (remaining.get(worker.id) || 0) <= 0) continue;
      selected.push(task);
      remaining.set(worker.id, remaining.get(worker.id) - 1);
      if (selected.length >= selectionLimit) break;
    }
    const results = [];
    const concurrency = asInt(config.limits.maxConcurrency, 1, 1, 4);
    let quotaBlocked = false;
    for (let index = 0; index < selected.length; index += concurrency) {
      const batch = selected.slice(index, index + concurrency);
      const reserved = [];
      for (const task of batch) {
        try {
          // Reserve serially so concurrent calls cannot lose quota-ledger updates.
          await consumeLocalQuota(root, config, estimateTaskTokens(config, task, findWorker(catalog, task.role)));
          reserved.push(task);
        } catch (error) {
          if (!String(error.message || error).startsWith("LOCAL_")) throw error;
          quotaBlocked = true;
          break;
        }
      }
      const batchResults = await Promise.all(reserved.map((task) => runOne(
        config,
        task,
        findWorker(catalog, task.role),
        fetchImpl,
        accessToken,
        allowEnlistment
      )));
      for (const result of batchResults) {
        results.push(result);
        const task = tasks.find((entry) => entry.id === result.taskId);
        task.status = result.status;
        task.updatedAt = result.completedAt;
        task.attempts += 1;
        task.resultFile = `results/${task.id}.json`;
        await writeJsonAtomic(path.join(p.results, `${task.id}.json`), result);
        const worker = findWorker(catalog, task.role);
        if (worker && !worker.builtin) worker.tasksUsed += 1;
      }
      await writeJsonAtomic(p.workers, catalog.filter((worker) => !worker.builtin));
      await writeJsonAtomic(p.tasks, tasks);
      if (quotaBlocked) break;
    }
    if (allowEnlistment) {
      let enlistedThisRun = 0;
      for (const result of results) {
        const proposal = result.enlistmentProposal;
        if (!proposal || enlistedThisRun >= config.enlistment.maxEnlistmentsPerRun) continue;
        try {
          if (!proposal.firstTask.trim()) throw new Error("Enlisted worker requires a first task");
          const worker = await enlistWorker(root, config, {
            parent: result.role,
            name: proposal.name,
            baseRole: proposal.baseRole,
            purpose: proposal.purpose,
            taskBudget: proposal.taskBudget,
            lifetimeHours: proposal.lifetimeHours
          });
          const delegatedTask = await addTask(root, config, {
            role: worker.id,
            prompt: proposal.firstTask,
            priority: 50
          });
          result.enlistment = { status: "enlisted", worker: worker.id, delegatedTask: delegatedTask.id };
          enlistedThisRun += 1;
        } catch (error) {
          result.enlistment = { status: "rejected", error: scrubSecrets(String(error.message || error)) };
        }
        await writeJsonAtomic(path.join(p.results, `${result.taskId}.json`), result);
      }
    }
    return results;
  } finally {
    await release();
  }
}

export async function armadaStatus(root, config, { remote = true, fetchImpl = fetch } = {}) {
  const p = await initialize(root);
  const tasks = await readJson(p.tasks, []);
  const quota = await readJson(p.quota, {});
  const workers = await listWorkers(root, config);
  const counts = Object.fromEntries(["queued", "completed", "failed"].map((name) => [name, tasks.filter((task) => task.status === name).length]));
  let gateway = { checked: false };
  if (remote) {
    try {
      gateway = { checked: true, ...(await getGatewayStatus(config, fetchImpl)) };
    } catch (error) {
      gateway = { checked: true, ok: false, identityOk: false, error: scrubSecrets(String(error.message || error)) };
    }
  }
  return {
    service: "Alma Free Cloud Armada",
    architecture: "bounded lineage of logical workers sharing one guarded GPT-OSS 120B gateway",
    roles: Object.keys(config.roles),
    workers: {
      total: workers.length,
      builtIn: workers.filter((worker) => worker.builtin).length,
      enlisted: workers.filter((worker) => !worker.builtin).length,
      active: workers.filter((worker) => worker.active).length,
      lineage: workers.map(({ id, parent, depth, baseRole, active, tasksUsed, taskBudget, expiresAt }) => ({
        id, parent, depth, baseRole, active, tasksUsed, taskBudget, expiresAt
      }))
    },
    counts,
    localQuota: quota,
    limits: config.limits,
    gateway
  };
}

export async function exactMarkerAcceptance(config, { fetchImpl = fetch, accessToken } = {}) {
  const before = await getGatewayStatus(config, fetchImpl);
  if (!before.ok || !before.identityOk) throw new Error("Gateway health or model identity failed");
  const marker = `ARMADA_${randomUUID().replaceAll("-", "").toUpperCase()}`;
  const response = await callGateway(config, [
    { role: "system", content: "Follow the requested output format exactly." },
    { role: "user", content: `Reply with only this exact token: ${marker}` }
  ], { accessToken, temperature: 0, maxCompletionTokens: 128 }, fetchImpl);
  if (response.output.trim() !== marker) throw new Error(`Exact marker mismatch: ${response.output.slice(0, 160)}`);
  return {
    ok: true,
    markerVerified: true,
    runtime: response.runtime,
    provider: response.provider,
    model: response.model,
    testedAt: new Date().toISOString()
  };
}

export const internals = { paths, consumeLocalQuota, readJson };
