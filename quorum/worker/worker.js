/* לזכרה של עלמה ז״ל
 * QUORUM · Worker — one-click browser compute donor for the QUORUM federation.
 *
 * Contract (same origin as the QUORUM server, JSON over POST, optional X-Token):
 *   POST /api/worker/join      {name, caps}                          -> {ok, worker_id, poll_ms?, heartbeat_ms?}
 *   POST /api/worker/heartbeat {worker_id, status, model, model_ready, tasks_done}
 *                                                                    -> {ok} | {ok:false, rejoin:true} | HTTP 404/410
 *   POST /api/worker/pull      {worker_id}                           -> {ok, task:null | {task_id, kind, payload}}
 *   POST /api/worker/result    {worker_id, task_id, ok, output, elapsed_ms, error?} -> {ok}
 *
 * Task kinds this worker executes:
 *   "chat" payload {messages:[{role,content}]} | {prompt}, max_tokens?, temperature?  (needs loaded model)
 *   "echo" payload {message}
 *   "info" payload {}
 *
 * The in-browser model is Gemma via WebLLM (MLC) over WebGPU, loaded from CDN.
 * If WebGPU or the CDN is unavailable the worker still joins with caps.llm=false
 * and serves echo/info tasks — degraded, never dead.
 */
"use strict";

(function () {
  const WEBLLM_CDN = "https://esm.run/@mlc-ai/web-llm";
  const MAX_OUTPUT_CHARS = 65536;
  const $ = (id) => document.getElementById(id);

  const state = {
    hub: "",             // "" = same origin
    token: "",
    name: "",
    workerId: null,
    running: false,
    stopping: false,
    pollMs: 3000,
    heartbeatMs: 20000,
    backoffMs: 0,
    hbTimer: null,
    upTimer: null,
    startedAt: 0,
    tasksDone: 0,
    tasksFailed: 0,
    tokens: 0,
    engine: null,
    modelId: null,
    modelReady: false,
    modelLoading: false,
    webgpu: false,
    busy: false,
  };

  // ── tiny utils ─────────────────────────────────────────────────────────────
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function log(msg, cls) {
    const el = $("log");
    const t = new Date().toTimeString().slice(0, 8);
    const line = document.createElement("div");
    line.textContent = "[" + t + "] " + msg;
    if (cls === "err") line.style.color = "#ff9d9d";
    if (cls === "ok") line.style.color = "#9dffb0";
    el.appendChild(line);
    while (el.childElementCount > 300) el.removeChild(el.firstChild);
    el.scrollTop = el.scrollHeight;
  }

  function chip(id, text, cls) {
    const el = $(id);
    el.textContent = text;
    el.className = "chip" + (cls ? " " + cls : "");
  }

  function stats() {
    $("s-done").textContent = String(state.tasksDone);
    $("s-fail").textContent = String(state.tasksFailed);
    $("s-tok").textContent = String(state.tokens);
  }

  function uptime() {
    if (!state.startedAt) { $("s-up").textContent = "—"; return; }
    const s = Math.floor((Date.now() - state.startedAt) / 1000);
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
    $("s-up").textContent = (h ? h + "h " : "") + m + "m " + (s % 60) + "s";
  }

  function progress(frac, label) {
    $("barfill").style.width = Math.round(Math.max(0, Math.min(1, frac)) * 100) + "%";
    const bl = $("barlabel");
    if (label) { bl.style.display = ""; bl.textContent = label; }
    else bl.style.display = "none";
  }

  function persist() {
    try {
      localStorage.setItem("qworker", JSON.stringify({
        hub: $("hub").value.trim(),
        token: $("token").value,
        name: $("wname").value.trim(),
        model: $("model").value,
        auto: state.running,
      }));
    } catch (e) { /* storage may be unavailable; run stateless */ }
  }

  function restore() {
    let saved = null;
    try { saved = JSON.parse(localStorage.getItem("qworker") || "null"); } catch (e) { saved = null; }
    if (saved) {
      if (saved.hub) $("hub").value = saved.hub;
      if (saved.token) $("token").value = saved.token;
      if (saved.name) $("wname").value = saved.name;
      if (saved.model) {
        const sel = $("model");
        for (const o of sel.options) if (o.value === saved.model) sel.value = saved.model;
      }
    }
    if (!$("wname").value.trim()) {
      $("wname").value = "web-" + Math.random().toString(36).slice(2, 8);
    }
    return saved;
  }

  // ── API ────────────────────────────────────────────────────────────────────
  function hubBase() {
    const raw = $("hub").value.trim().replace(/\/+$/, "");
    return raw; // "" = same origin
  }

  async function api(path, body) {
    const headers = { "Content-Type": "application/json" };
    if (state.token) headers["X-Token"] = state.token;
    const res = await fetch(state.hub + path, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const err = new Error("HTTP " + res.status + " at " + path);
      err.status = res.status;
      throw err;
    }
    return res.json();
  }

  function caps() {
    let mem = null;
    try { mem = navigator.deviceMemory || null; } catch (e) { mem = null; }
    return {
      llm: state.modelReady,
      model: state.modelReady ? state.modelId : null,
      webgpu: state.webgpu,
      cores: navigator.hardwareConcurrency || null,
      memory_gb: mem,
      ua: navigator.userAgent.slice(0, 200),
      kinds: state.modelReady ? ["chat", "echo", "info"] : ["echo", "info"],
    };
  }

  async function join() {
    const r = await api("/api/worker/join", { name: state.name, caps: caps() });
    if (!r || r.ok === false || !r.worker_id) {
      throw new Error("join refused: " + JSON.stringify(r).slice(0, 200));
    }
    state.workerId = r.worker_id;
    if (Number.isFinite(r.poll_ms) && r.poll_ms >= 500) state.pollMs = r.poll_ms;
    if (Number.isFinite(r.heartbeat_ms) && r.heartbeat_ms >= 5000) state.heartbeatMs = r.heartbeat_ms;
    chip("conn", "מחובר · " + state.workerId, "ok");
    log("joined as " + state.workerId + " (poll " + state.pollMs + "ms, hb " + state.heartbeatMs + "ms)", "ok");
  }

  async function heartbeat() {
    if (!state.running || !state.workerId) return;
    try {
      const r = await api("/api/worker/heartbeat", {
        worker_id: state.workerId,
        status: state.busy ? "busy" : (state.modelLoading ? "loading" : "idle"),
        model: state.modelId,
        model_ready: state.modelReady,
        tasks_done: state.tasksDone,
      });
      if (r && r.ok === false && r.rejoin) throw Object.assign(new Error("rejoin"), { status: 410 });
    } catch (e) {
      if (e.status === 404 || e.status === 410) {
        log("hub forgot us — rejoining", "err");
        try { await join(); } catch (e2) { log("rejoin failed: " + e2.message, "err"); }
      }
      // other errors: the poll loop's backoff already covers outages
    }
  }

  // ── model ──────────────────────────────────────────────────────────────────
  async function detectWebGPU() {
    try {
      if (!navigator.gpu) return false;
      const adapter = await navigator.gpu.requestAdapter();
      return !!adapter;
    } catch (e) { return false; }
  }

  async function loadModel() {
    const want = $("model").value;
    if (want === "none") {
      log("model disabled by choice — echo/info tasks only");
      return;
    }
    if (!state.webgpu) {
      log("WebGPU unavailable — joining without a local model", "err");
      return;
    }
    state.modelLoading = true;
    progress(0, "טוען מודל…");
    try {
      const webllm = await import(WEBLLM_CDN);
      log("WebLLM library loaded, fetching " + want + " …");
      state.engine = await webllm.CreateMLCEngine(want, {
        initProgressCallback: (p) => {
          progress(p.progress || 0, (p.text || "").slice(0, 80));
        },
      });
      state.modelId = want;
      state.modelReady = true;
      progress(1, "מודל מוכן ✓");
      log("model READY: " + want, "ok");
    } catch (e) {
      log("model load failed (" + (e && e.message ? e.message : e) + ") — continuing without LLM", "err");
      progress(0);
    } finally {
      state.modelLoading = false;
    }
  }

  async function generate(payload) {
    if (!state.modelReady || !state.engine) {
      throw new Error("llm-not-loaded");
    }
    let messages = Array.isArray(payload.messages) ? payload.messages : null;
    if (!messages) {
      messages = [{ role: "user", content: String(payload.prompt || "") }];
    }
    messages = messages
      .filter((m) => m && typeof m.content === "string")
      .map((m) => ({
        role: (m.role === "system" || m.role === "assistant") ? m.role : "user",
        content: m.content.slice(0, 32768),
      }));
    if (!messages.length) throw new Error("empty messages");
    const req = {
      messages,
      temperature: Number.isFinite(payload.temperature) ? payload.temperature : 0.7,
      max_tokens: Number.isFinite(payload.max_tokens)
        ? Math.max(1, Math.min(2048, payload.max_tokens)) : 512,
    };
    const out = await state.engine.chat.completions.create(req);
    const text = (out && out.choices && out.choices[0] && out.choices[0].message
      && out.choices[0].message.content) || "";
    if (out && out.usage && Number.isFinite(out.usage.completion_tokens)) {
      state.tokens += out.usage.completion_tokens;
    }
    return text;
  }

  // ── task execution ─────────────────────────────────────────────────────────
  async function runTask(task) {
    const t0 = Date.now();
    state.busy = true;
    let ok = true, output = "", error = null;
    try {
      const kind = task.kind;
      const payload = task.payload || {};
      if (kind === "chat") {
        log("task " + task.task_id + " chat → local " + state.modelId);
        output = await generate(payload);
      } else if (kind === "echo") {
        output = String(payload.message == null ? "" : payload.message);
      } else if (kind === "info") {
        output = JSON.stringify({
          name: state.name,
          caps: caps(),
          tasks_done: state.tasksDone,
          uptime_s: state.startedAt ? Math.floor((Date.now() - state.startedAt) / 1000) : 0,
        });
      } else {
        ok = false;
        error = "unknown task kind: " + String(kind).slice(0, 40);
      }
    } catch (e) {
      ok = false;
      error = (e && e.message ? e.message : String(e)).slice(0, 300);
    }
    state.busy = false;
    const elapsed = Date.now() - t0;
    if (ok) { state.tasksDone += 1; } else { state.tasksFailed += 1; }
    stats();
    const body = {
      worker_id: state.workerId,
      task_id: String(task.task_id),
      ok,
      output: String(output).slice(0, MAX_OUTPUT_CHARS),
      elapsed_ms: elapsed,
    };
    if (error) body.error = error;
    try {
      await api("/api/worker/result", body);
      log("task " + task.task_id + " " + (ok ? "done" : "FAILED (" + error + ")")
        + " in " + elapsed + "ms", ok ? "ok" : "err");
    } catch (e) {
      // one retry, then drop with a log line — the hub will re-queue on timeout
      try {
        await sleep(1500);
        await api("/api/worker/result", body);
        log("task " + task.task_id + " result delivered on retry", "ok");
      } catch (e2) {
        log("could not deliver result for " + task.task_id + ": " + e2.message, "err");
      }
    }
  }

  async function pollLoop() {
    while (state.running) {
      let task = null;
      try {
        const r = await api("/api/worker/pull", { worker_id: state.workerId });
        state.backoffMs = 0;
        if (r && r.task && r.task.task_id != null) task = r.task;
      } catch (e) {
        if (e.status === 404 || e.status === 410) {
          try { await join(); } catch (e2) { /* keep backing off */ }
        }
        state.backoffMs = Math.min((state.backoffMs || state.pollMs) * 2, 30000);
        chip("conn", "מנסה שוב… (" + Math.round(state.backoffMs / 1000) + "s)", "warn");
      }
      if (!state.running) break;
      if (task) {
        await runTask(task);
      } else {
        await sleep(state.backoffMs || state.pollMs);
      }
      if (state.backoffMs === 0 && state.workerId) {
        chip("conn", "מחובר · " + state.workerId, "ok");
      }
    }
    chip("conn", "מנותק");
  }

  // ── start / stop ───────────────────────────────────────────────────────────
  async function start() {
    if (state.running) return;
    state.hub = hubBase();
    state.token = $("token").value;
    state.name = $("wname").value.trim() || "web-" + Math.random().toString(36).slice(2, 8);
    $("wname").value = state.name;
    state.running = true;
    state.stopping = false;
    state.startedAt = Date.now();
    $("go").disabled = true;
    $("halt").disabled = false;
    persist();

    chip("conn", "מתחבר…", "warn");
    try {
      await join();
    } catch (e) {
      log("join failed: " + e.message + " — will keep retrying in the loop", "err");
      chip("conn", "המרכז לא זמין — ממשיך לנסות", "warn");
      // enter the loop anyway; pull will 404/fail and trigger rejoin+backoff
      state.workerId = state.workerId || null;
    }

    // heartbeat + uptime tickers
    state.hbTimer = setInterval(heartbeat, state.heartbeatMs);
    state.upTimer = setInterval(uptime, 1000);

    // load the local model AFTER joining so the hub sees us immediately;
    // heartbeats flip model_ready when it lands.
    await loadModel();

    if (state.workerId == null) {
      // never joined — retry join with backoff until it works or we stop
      let wait = state.pollMs;
      while (state.running && state.workerId == null) {
        await sleep(wait);
        try { await join(); } catch (e) {
          wait = Math.min(wait * 2, 30000);
          log("join retry failed: " + e.message, "err");
        }
      }
    }
    if (state.running) await pollLoop();
  }

  function stop() {
    state.running = false;
    state.stopping = true;
    if (state.hbTimer) { clearInterval(state.hbTimer); state.hbTimer = null; }
    if (state.upTimer) { clearInterval(state.upTimer); state.upTimer = null; }
    $("go").disabled = false;
    $("halt").disabled = true;
    persist();
    log("stopped by user");
  }

  // ── local self-test (proves the model without the hub) ─────────────────────
  async function localTest() {
    const q = $("testq").value.trim();
    if (!q) return;
    const out = $("testout");
    if (!state.modelReady) {
      if (!state.webgpu) { out.textContent = "אין WebGPU בדפדפן הזה — אין מודל מקומי."; return; }
      out.textContent = "המודל עדיין לא נטען — לחץ ▶ התחל לעבוד, וחכה ל'מודל מוכן'.";
      return;
    }
    out.textContent = "חושב…";
    try {
      const text = await generate({ prompt: q, max_tokens: 400 });
      out.textContent = text || "(תשובה ריקה)";
      stats();
    } catch (e) {
      out.textContent = "שגיאה: " + (e && e.message ? e.message : e);
    }
  }

  // ── boot ───────────────────────────────────────────────────────────────────
  async function boot() {
    // PWA: register the service worker (best-effort; file:// or http w/o SW support just skips)
    try {
      if ("serviceWorker" in navigator) {
        await navigator.serviceWorker.register("sw.js");
        log("service worker registered — installable + offline shell");
      }
    } catch (e) {
      log("service worker not registered (" + (e && e.message ? e.message : e) + ")");
    }

    const saved = restore();
    state.webgpu = await detectWebGPU();
    chip("gpu", state.webgpu ? "WebGPU ✓" : "אין WebGPU — ללא מודל מקומי",
      state.webgpu ? "ok" : "err");
    log("QUORUM worker ready. WebGPU=" + state.webgpu
      + " cores=" + (navigator.hardwareConcurrency || "?"));

    $("go").addEventListener("click", () => { start(); });
    $("halt").addEventListener("click", stop);
    $("testgo").addEventListener("click", localTest);
    $("testq").addEventListener("keydown", (e) => {
      if (e.key === "Enter" && e.ctrlKey) localTest();
    });

    // one-click / zero-click: ?auto=1 or a previous running session auto-resumes
    const auto = new URLSearchParams(location.search).get("auto");
    if (auto === "1" || (saved && saved.auto)) {
      log("auto-start engaged");
      start();
    }
  }

  boot();
})();
