"use strict";

const state = {
  config: null,
  status: null,
  validation: null,
  examples: [],
  filename: "untitled.nc",
  toastTimer: null,
};

const $ = (id) => document.getElementById(id);
const SVG_NS = "http://www.w3.org/2000/svg";

async function api(path, method = "GET", body = null) {
  const options = { method, headers: {} };
  if (body !== null) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  const payload = await response.json();
  if (!response.ok || !payload.ok) {
    throw new Error(payload.error || `Request failed: ${response.status}`);
  }
  return payload;
}

function toast(message, error = false) {
  const node = $("toast");
  node.textContent = message;
  node.className = `toast visible${error ? " error" : ""}`;
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => { node.className = "toast"; }, 3800);
}

async function action(path, body = {}) {
  try {
    const payload = await api(path, "POST", body);
    if (payload.machine || payload.job) renderStatus(payload);
    return payload;
  } catch (error) {
    toast(error.message, true);
    throw error;
  }
}

function renderConfig(config) {
  state.config = config;
  $("transportValue").textContent = config.mode;
  $("serialValue").textContent = config.serial_port;
  const e = config.envelope_mm;
  $("envelopeValue").textContent = `${e.x} × ${e.y} × ${e.z} mm`;
  const modeBadge = $("modeBadge");
  if (config.mode === "simulation") {
    modeBadge.className = "safety-cell warning";
    modeBadge.innerHTML = "<b>SIMULATION</b><span>no hardware motion</span>";
  } else {
    modeBadge.className = "safety-cell danger";
    modeBadge.innerHTML = "<b>HARDWARE MODE</b><span>physical motion possible</span>";
  }
}

function renderExamples(examples) {
  state.examples = examples;
  $("exampleCount").textContent = `${examples.length} READY`;
  $("exampleGrid").replaceChildren(...examples.map((example) => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "example-card";
    card.dataset.exampleId = example.id;

    const top = document.createElement("span");
    top.className = "example-card-top";
    const tag = document.createElement("b");
    tag.textContent = example.tag;
    const size = document.createElement("small");
    size.textContent = example.size;
    top.append(tag, size);

    const name = document.createElement("strong");
    name.textContent = example.name;
    const summary = document.createElement("span");
    summary.textContent = example.summary;
    const footer = document.createElement("span");
    footer.className = "example-card-footer";
    footer.textContent = `Load example · F${example.feed_mm_min}`;

    card.append(top, name, summary, footer);
    card.addEventListener("click", () => loadExample(example));
    return card;
  }));
}

async function loadExample(example) {
  state.filename = example.file_name;
  $("programName").textContent = example.file_name;
  $("gcodeSource").value = example.source;
  state.validation = null;
  document.querySelectorAll(".example-card").forEach((card) => {
    card.classList.toggle("selected", card.dataset.exampleId === example.id);
  });
  $("validationSummary").className = "validation-summary neutral";
  $("validationSummary").textContent = "Example loaded — validating";
  resetPreview();
  updateStartEnabled();
  const result = await validate();
  if (result && result.valid) toast(`${example.name} loaded and validated`);
}

function resetPreview() {
  $("toolpathLayer").replaceChildren();
  $("previewEmpty").style.display = "";
  $("previewState").textContent = "VALIDATE TO DRAW";
  $("previewState").className = "";
  $("pathDistance").textContent = "—";
  $("xSpan").textContent = "—";
  $("ySpan").textContent = "—";
  $("programLines").textContent = "—";
}

function parseToolpath(lines) {
  const points = [[0, 0, 0]];
  const segments = [];
  let position = [0, 0, 0];
  let absolute = true;
  let scale = 1;

  lines.forEach((line) => {
    const words = [...line.matchAll(/([A-Z])([+-]?(?:\d+(?:\.\d*)?|\.\d+))/g)];
    const values = {};
    words.forEach((match) => {
      if (!values[match[1]]) values[match[1]] = [];
      values[match[1]].push(Number(match[2]));
    });
    const gCodes = values.G || [];
    if (gCodes.includes(20)) scale = 25.4;
    if (gCodes.includes(21)) scale = 1;
    if (gCodes.includes(90)) absolute = true;
    if (gCodes.includes(91)) absolute = false;
    const rapid = gCodes.includes(0);
    const feedMove = gCodes.includes(1);
    if (!rapid && !feedMove) return;

    const target = [...position];
    ["X", "Y", "Z"].forEach((axis, index) => {
      if (!values[axis]) return;
      const requested = values[axis][values[axis].length - 1] * scale;
      target[index] = absolute ? requested : position[index] + requested;
    });
    if (target.some((value, index) => value !== position[index])) {
      segments.push({ start: [...position], end: [...target], rapid });
      points.push([...target]);
      position = target;
    }
  });
  return { points, segments };
}

function svgNode(name, attributes = {}) {
  const node = document.createElementNS(SVG_NS, name);
  Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, value));
  return node;
}

function drawPreview(result) {
  const layer = $("toolpathLayer");
  layer.replaceChildren();
  const { points, segments } = parseToolpath(result.normalized_lines);
  if (!segments.length) {
    resetPreview();
    $("previewState").textContent = "NO XY MOTION";
    return;
  }

  const xs = points.map((point) => point[0]);
  const ys = points.map((point) => point[1]);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const spanX = Math.max(maxX - minX, 1);
  const spanY = Math.max(maxY - minY, 1);
  const padding = 46;
  const width = 640 - padding * 2;
  const height = 400 - padding * 2;
  const scale = Math.min(width / spanX, height / spanY);
  const contentWidth = spanX * scale;
  const contentHeight = spanY * scale;
  const offsetX = padding + (width - contentWidth) / 2;
  const offsetY = padding + (height - contentHeight) / 2;
  const mapPoint = (point) => [
    offsetX + (point[0] - minX) * scale,
    400 - (offsetY + (point[1] - minY) * scale),
  ];

  segments.forEach((segment) => {
    const start = mapPoint(segment.start);
    const end = mapPoint(segment.end);
    layer.append(svgNode("line", {
      x1: start[0],
      y1: start[1],
      x2: end[0],
      y2: end[1],
      class: segment.rapid ? "preview-rapid" : "preview-cut",
    }));
  });

  const start = mapPoint(points[0]);
  const end = mapPoint(points[points.length - 1]);
  layer.append(svgNode("circle", { cx: start[0], cy: start[1], r: 7, class: "preview-start" }));
  layer.append(svgNode("circle", { cx: end[0], cy: end[1], r: 5, class: "preview-end" }));
  $("previewEmpty").style.display = "none";
  $("previewState").textContent = "VALIDATED";
  $("previewState").className = "valid";
  $("pathDistance").textContent = `${Number(result.distance_mm).toFixed(1)} mm`;
  $("xSpan").textContent = `${(result.extents.x[1] - result.extents.x[0]).toFixed(1)} mm`;
  $("ySpan").textContent = `${(result.extents.y[1] - result.extents.y[0]).toFixed(1)} mm`;
  $("programLines").textContent = String(result.normalized_lines.length);
}

function renderStatus(payload) {
  state.status = payload;
  const machine = payload.machine;
  const connected = payload.connected;
  $("connectionBadge").className = `safety-cell${connected ? " active" : ""}`;
  $("connectionBadge").innerHTML = `<b>${connected ? "CONNECTED" : "DISCONNECTED"}</b><span>controller link</span>`;
  $("connectButton").disabled = connected;
  $("disconnectButton").disabled = !connected;
  $("unlockButton").disabled = !connected || !["Idle", "Alarm"].includes(machine.state);
  $("setZeroButton").disabled = !connected || machine.state !== "Idle";
  $("homeButton").disabled = !connected || !["Idle", "Alarm"].includes(machine.state);
  document.querySelectorAll(".jog-button").forEach((button) => {
    button.disabled = !connected || !["Idle", "Jog"].includes(machine.state);
  });

  const machineState = $("machineState");
  machineState.textContent = machine.state;
  machineState.className = "state-pill";
  if (["Run", "Jog", "Home"].includes(machine.state)) machineState.classList.add("running");
  if (machine.state === "Alarm") machineState.classList.add("alarm");

  const pos = machine.work_position || [0, 0, 0];
  $("posX").textContent = Number(pos[0]).toFixed(3);
  $("posY").textContent = Number(pos[1]).toFixed(3);
  $("posZ").textContent = Number(pos[2]).toFixed(3);
  $("feedValue").textContent = `${Number(machine.feed || 0).toFixed(0)} mm/min`;
  $("spindleValue").textContent = `${Number(machine.spindle || 0).toFixed(0)} rpm`;
  $("pinValue").textContent = machine.pins || "—";

  if (state.config) {
    const e = state.config.envelope_mm;
    const xPercent = Math.max(2, Math.min(98, (Number(pos[0]) / e.x) * 100));
    const yPercent = Math.max(2, Math.min(98, (Number(pos[1]) / e.y) * 100));
    $("crosshair").style.left = `${xPercent}%`;
    $("crosshair").style.bottom = `${yPercent}%`;
  }

  const job = payload.job;
  const percent = job.total ? (job.progress / job.total) * 100 : 0;
  $("jobProgress").style.width = `${percent}%`;
  $("jobStatus").textContent = job.state === "none"
    ? "No job loaded."
    : `${job.name} — ${job.state} — ${job.progress}/${job.total} lines`;
  $("pauseButton").disabled = job.state !== "running";
  $("resumeButton").disabled = !connected
    || (!["paused", "Hold"].includes(job.state) && machine.state !== "Hold");
  $("abortButton").disabled = !["running", "paused"].includes(job.state);

  renderEvents(payload.events || []);
  updateStartEnabled();
}

function renderEvents(events) {
  const log = $("eventLog");
  log.replaceChildren(...events.map((event) => {
    const row = document.createElement("div");
    row.className = `event-line ${event.level}`;
    const timestamp = document.createElement("span");
    timestamp.className = "time";
    timestamp.textContent = event.time;
    const level = document.createElement("span");
    level.className = "level";
    level.textContent = event.level;
    const message = document.createElement("span");
    message.textContent = event.message;
    row.append(timestamp, level, message);
    return row;
  }));
}

function approvalValues() {
  return Object.fromEntries(
    [...document.querySelectorAll("[data-approval]")].map((input) => [input.dataset.approval, input.checked])
  );
}

function updateStartEnabled() {
  const allApproved = Object.values(approvalValues()).every(Boolean);
  const connected = Boolean(state.status && state.status.connected);
  const idle = Boolean(state.status && state.status.machine.state === "Idle");
  const noActiveJob = !state.status || !["running", "paused"].includes(state.status.job.state);
  $("startButton").disabled = !(state.validation && state.validation.valid && allApproved && connected && idle && noActiveJob);
}

async function validate() {
  try {
    const payload = await action("/api/job/validate", { source: $("gcodeSource").value });
    state.validation = payload.validation;
    const result = payload.validation;
    const errors = result.issues.filter((issue) => issue.severity === "error").length;
    const warnings = result.issues.filter((issue) => issue.severity === "warning").length;
    $("validationSummary").className = `validation-summary ${result.valid ? "valid" : "invalid"}`;
    $("validationSummary").textContent = result.valid
      ? `PASS / ${result.normalized_lines.length} lines / ${warnings} warning(s)`
      : `BLOCKED / ${errors} error(s) / ${warnings} warning(s)`;
    $("validationIssues").replaceChildren(...result.issues.map((issue) => {
      const item = document.createElement("li");
      item.className = issue.severity;
      item.textContent = `${issue.line ? `Line ${issue.line}: ` : ""}${issue.message}`;
      return item;
    }));
    if (result.valid) {
      drawPreview(result);
    } else {
      resetPreview();
      $("previewState").textContent = "BLOCKED";
      $("previewState").className = "invalid";
    }
    updateStartEnabled();
    return result;
  } catch (_) {
    return null;
  }
}

async function poll() {
  try {
    renderStatus(await api("/api/status"));
  } catch (error) {
    toast(`Status unavailable: ${error.message}`, true);
  }
}

$("connectButton").addEventListener("click", async () => {
  try {
    await action("/api/connect");
    toast("Controller connected");
  } catch (_) {}
});
$("disconnectButton").addEventListener("click", async () => {
  try { await action("/api/disconnect"); } catch (_) {}
});
$("holdButton").addEventListener("click", async () => {
  try {
    await action("/api/realtime", { action: "hold" });
    toast("Feed hold sent. Use the physical E-stop for an emergency.");
  } catch (_) {}
});
$("resumeButton").addEventListener("click", async () => {
  try {
    if (state.status && state.status.job.state === "paused") {
      await action("/api/job/resume");
    } else {
      await action("/api/realtime", { action: "resume" });
    }
  } catch (_) {}
});
$("softResetButton").addEventListener("click", async () => {
  if (!window.confirm("Soft reset clears the GRBL planner and may lose position confidence. Continue?")) return;
  try { await action("/api/realtime", { action: "soft_reset" }); } catch (_) {}
});
$("unlockButton").addEventListener("click", async () => {
  if (!window.confirm("Unlock GRBL alarm? Machine position may be untrusted until homing.")) return;
  try {
    await action("/api/unlock");
    toast("Alarm unlock requested");
  } catch (_) {}
});
$("setZeroButton").addEventListener("click", async () => {
  if (!window.confirm("Make the current position X0 Y0 Z0 in the active work coordinate system?")) return;
  try {
    await action("/api/work-zero", { confirm: true });
    toast("Current position set as XYZ work zero");
  } catch (_) {}
});
$("homeButton").addEventListener("click", async () => {
  if (!window.confirm("Homing will move all axes. Are the limit switches verified and the work area clear?")) return;
  try { await action("/api/home", { confirm: true }); } catch (_) {}
});

document.querySelectorAll(".jog-button").forEach((button) => {
  button.addEventListener("click", async () => {
    const step = Number($("jogStep").value) * Number(button.dataset.sign);
    try {
      await action("/api/jog", {
        axis: button.dataset.axis,
        distance_mm: step,
        feed_mm_min: Number($("jogFeed").value),
      });
    } catch (_) {}
  });
});

$("fileInput").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  if (file.size > 2 * 1024 * 1024) {
    toast("File is larger than the 2 MiB safety limit", true);
    return;
  }
  state.filename = file.name;
  $("programName").textContent = file.name;
  $("gcodeSource").value = await file.text();
  document.querySelectorAll(".example-card").forEach((card) => card.classList.remove("selected"));
  state.validation = null;
  $("validationSummary").className = "validation-summary neutral";
  $("validationSummary").textContent = "Changed — validate again";
  resetPreview();
  updateStartEnabled();
});

$("gcodeSource").addEventListener("input", () => {
  document.querySelectorAll(".example-card").forEach((card) => card.classList.remove("selected"));
  state.validation = null;
  $("validationSummary").className = "validation-summary neutral";
  $("validationSummary").textContent = "Changed — validate again";
  resetPreview();
  updateStartEnabled();
});
$("validateButton").addEventListener("click", validate);
document.querySelectorAll("[data-approval]").forEach((input) => input.addEventListener("change", updateStartEnabled));

$("startButton").addEventListener("click", async () => {
  const result = await validate();
  if (!result || !result.valid) return;
  if (!window.confirm("Start validated DRY MOTION now? Keep the spindle physically isolated and stay at the E-stop.")) return;
  try {
    await action("/api/job/start", {
      name: state.filename,
      source: $("gcodeSource").value,
      approvals: approvalValues(),
    });
  } catch (_) {}
});
$("pauseButton").addEventListener("click", async () => {
  try { await action("/api/job/pause"); } catch (_) {}
});
$("abortButton").addEventListener("click", async () => {
  try { await action("/api/job/abort"); } catch (_) {}
});

async function initialize() {
  try {
    const [configPayload, examplesPayload] = await Promise.all([
      api("/api/config"),
      api("/api/examples"),
    ]);
    renderConfig(configPayload.config);
    renderExamples(examplesPayload.examples);
    await poll();
    setInterval(poll, 500);
    const updateClock = () => {
      $("utcClock").textContent = `${new Date().toISOString().slice(11, 19)} UTC`;
    };
    updateClock();
    setInterval(updateClock, 1000);
  } catch (error) {
    toast(`Initialization failed: ${error.message}`, true);
  }
}

initialize();
