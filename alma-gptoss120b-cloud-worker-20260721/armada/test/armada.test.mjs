import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import {
  addTask,
  armadaStatus,
  enlistWorker,
  exactMarkerAcceptance,
  extractEnlistmentProposal,
  internals,
  listWorkers,
  loadConfig,
  parseSse,
  runQueue,
  scrubSecrets
} from "../lib.mjs";

const sourceConfig = JSON.parse(await (await import("node:fs/promises")).readFile(new URL("../armada.config.json", import.meta.url), "utf8"));

async function fixture() {
  const root = await mkdtemp(path.join(os.tmpdir(), "alma-armada-"));
  await writeFile(path.join(root, "armada.config.json"), JSON.stringify(sourceConfig));
  return { root, config: await loadConfig(root) };
}

function gatewayFetch() {
  return async (url, init = {}) => {
    if (String(url).endsWith("/api/status")) {
      return new Response(JSON.stringify({
        ok: true,
        runtime: "cloudflare-worker",
        provider: "groq",
        model: "openai/gpt-oss-120b",
        localFallback: false,
        dgxFallback: false
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    const body = JSON.parse(init.body);
    const marker = body.messages.at(-1).content.match(/ARMADA_[A-Z0-9]+/)?.[0];
    const content = marker || `done:${body.messages.at(-1).content}`;
    return new Response(`data: ${JSON.stringify({ choices: [{ delta: { content } }] })}\n\ndata: [DONE]\n\n`, {
      status: 200,
      headers: {
        "Content-Type": "text/event-stream",
        "X-Alma-Runtime": "cloudflare-worker",
        "X-Alma-Provider": "groq",
        "X-Alma-Model": "openai/gpt-oss-120b",
        "X-Alma-Local-Fallback": "false"
      }
    });
  };
}

test("SSE parser and secret scrubber keep persisted evidence safe", () => {
  assert.equal(parseSse('data: {"choices":[{"delta":{"content":"HELLO"}}]}\n\ndata: [DONE]\n'), "HELLO");
  assert.equal(scrubSecrets("Bearer abcdef and gsk_1234567890123456"), "Bearer [REDACTED_SECRET] and [REDACTED_SECRET]");
});

test("four role tasks share one pinned gateway and persist results", async () => {
  const { root, config } = await fixture();
  try {
    for (const role of Object.keys(config.roles)) {
      await addTask(root, config, { role, prompt: `work for ${role}` });
    }
    const results = await runQueue(root, config, { fetchImpl: gatewayFetch(), maxTasks: 4, accessToken: "not-persisted" });
    assert.equal(results.length, 4);
    assert.ok(results.every((result) => result.status === "completed"));
    assert.ok(results.every((result) => result.model === "openai/gpt-oss-120b"));
    const status = await armadaStatus(root, config, { remote: false });
    assert.deepEqual(status.counts, { queued: 0, completed: 4, failed: 0 });
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("scheduler never exceeds configured concurrency", async () => {
  const { root, config } = await fixture();
  let active = 0;
  let maximum = 0;
  const baseFetch = gatewayFetch();
  const measuredFetch = async (url, init) => {
    if (String(url).endsWith("/api/status")) return baseFetch(url, init);
    active += 1;
    maximum = Math.max(maximum, active);
    await new Promise((resolve) => setTimeout(resolve, 15));
    const response = await baseFetch(url, init);
    active -= 1;
    return response;
  };
  try {
    for (let index = 0; index < 4; index += 1) {
      await addTask(root, config, { role: "qa", prompt: `concurrency task ${index}` });
    }
    const results = await runQueue(root, config, { fetchImpl: measuredFetch, maxTasks: 4, accessToken: "not-persisted" });
    assert.equal(results.length, 4);
    assert.equal(maximum, 2);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("local quota blocks before the shared gateway ceiling", async () => {
  const { root, config } = await fixture();
  try {
    config.limits.minuteRequests = 1;
    await internals.consumeLocalQuota(root, config, 100);
    await assert.rejects(() => internals.consumeLocalQuota(root, config, 100), /LOCAL_MINUTE_REQUEST_QUOTA/);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("exact-marker acceptance proves health and generation identity", async () => {
  const { root, config } = await fixture();
  try {
    const result = await exactMarkerAcceptance(config, { fetchImpl: gatewayFetch(), accessToken: "not-persisted" });
    assert.equal(result.ok, true);
    assert.equal(result.markerVerified, true);
    assert.equal(result.model, "openai/gpt-oss-120b");
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("enlisted workers have bounded lineage, lifetime, and task budgets", async () => {
  const { root, config } = await fixture();
  try {
    const child = await enlistWorker(root, config, {
      parent: "engineering",
      name: "security-qa",
      baseRole: "qa",
      purpose: "Test security boundaries and deterministic failure cases.",
      taskBudget: 1,
      lifetimeHours: 2
    });
    assert.equal(child.depth, 1);
    assert.equal(child.taskBudget, 1);
    await addTask(root, config, { role: child.id, prompt: "test boundary one" });
    await addTask(root, config, { role: child.id, prompt: "test boundary two" });
    const results = await runQueue(root, config, {
      fetchImpl: gatewayFetch(),
      maxTasks: 2,
      accessToken: "not-persisted"
    });
    assert.equal(results.length, 1);
    const workers = await listWorkers(root, config);
    const updated = workers.find((worker) => worker.id === child.id);
    assert.equal(updated.tasksUsed, 1);
    assert.equal(updated.active, false);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("worker-requested enlistment creates one validated child and queues its first task", async () => {
  const { root, config } = await fixture();
  const baseFetch = gatewayFetch();
  const enlistingFetch = async (url, init) => {
    if (String(url).endsWith("/api/status")) return baseFetch(url, init);
    const proposal = 'ENLIST_WORKER_JSON: {"name":"release-auditor","baseRole":"qa","purpose":"Audit release evidence and deterministic acceptance gates.","firstTask":"Review the current release acceptance evidence."}';
    return new Response(`data: ${JSON.stringify({ choices: [{ delta: { content: proposal } }] })}\n\ndata: [DONE]\n\n`, {
      status: 200,
      headers: {
        "X-Alma-Runtime": "cloudflare-worker",
        "X-Alma-Provider": "groq",
        "X-Alma-Model": "openai/gpt-oss-120b",
        "X-Alma-Local-Fallback": "false"
      }
    });
  };
  try {
    await addTask(root, config, { role: "engineering", prompt: "Prepare a release." });
    const results = await runQueue(root, config, {
      fetchImpl: enlistingFetch,
      maxTasks: 1,
      accessToken: "not-persisted",
      allowEnlistment: true
    });
    assert.equal(results[0].enlistment.status, "enlisted");
    assert.equal(results[0].enlistment.worker, "release-auditor");
    const status = await armadaStatus(root, config, { remote: false });
    assert.equal(status.workers.enlisted, 1);
    assert.equal(status.counts.queued, 1);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("malformed enlistment output and excessive lineage cannot replicate", async () => {
  assert.equal(extractEnlistmentProposal("ENLIST_WORKER_JSON: not-json"), null);
  const { root, config } = await fixture();
  try {
    const first = await enlistWorker(root, config, {
      parent: "ops",
      name: "recovery-planner",
      baseRole: "ops",
      purpose: "Plan bounded recovery steps and rollback gates."
    });
    const second = await enlistWorker(root, config, {
      parent: first.id,
      name: "rollback-checker",
      baseRole: "qa",
      purpose: "Check rollback instructions for deterministic safety."
    });
    await assert.rejects(() => enlistWorker(root, config, {
      parent: second.id,
      name: "too-deep-worker",
      baseRole: "qa",
      purpose: "This worker must be rejected by the depth ceiling."
    }), /ENLISTMENT_DEPTH_LIMIT/);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
