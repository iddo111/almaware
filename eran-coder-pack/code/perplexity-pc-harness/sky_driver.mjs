// Safe trusted-runtime adapter for the existing Perplexity PC harness.
// Import this module only after SKILL.md setup has installed globalThis.sky.

import { createHash } from "node:crypto";
import { access } from "node:fs/promises";

const DENIED_TARGETS = [
  "credential",
  "password",
  "1password",
  "bitwarden",
  "keepass",
  "user account control",
  "windows security",
  "microsoft defender",
  "registry editor",
  "regedit",
  "powershell",
  "command prompt",
  "terminal",
  "cmd.exe",
  "codex",
  "chatgpt",
];

const ALLOWED_KEYS = new Set([
  "Return",
  "Enter",
  "Tab",
  "Escape",
  "BackSpace",
  "Delete",
  "Left",
  "Right",
  "Up",
  "Down",
  "Home",
  "End",
  "Page_Up",
  "Page_Down",
  "space",
]);

const MODIFIERS = new Set([
  "Control",
  "Control_L",
  "Control_R",
  "Ctrl",
  "Alt",
  "Alt_L",
  "Alt_R",
  "Shift",
  "Shift_L",
  "Shift_R",
]);

const CHORD_KEYS = new Set([
  ...ALLOWED_KEYS,
  "a",
  "c",
  "f",
  "l",
  "n",
  "p",
  "s",
  "t",
  "v",
  "w",
  "x",
  "z",
]);

const SECRET_PATTERN =
  /(?:api[_ -]?key|password|passwd|secret|token|bearer)\s*[:=]\s*\S+/i;

function publicWindow(window, screenshot = null) {
  const app = String(window.app ?? "");
  return {
    id: `${app}|${window.id}`,
    native_id: window.id,
    app,
    process_name: app.startsWith("process:")
      ? app.slice("process:".length)
      : app,
    title: String(window.title ?? "").slice(0, 512),
    bounds:
      screenshot?.width != null && screenshot?.height != null
        ? {
            left: Number(screenshot.originX ?? 0),
            top: Number(screenshot.originY ?? 0),
            width: Number(screenshot.width),
            height: Number(screenshot.height),
          }
        : null,
    foreground: null,
    dpi_scale: 1,
  };
}

function decodeDataUrl(url) {
  if (typeof url !== "string") {
    throw new Error("Screenshot URL is missing");
  }
  const match =
    /^data:image\/(?:png|jpeg|webp|gif);base64,([A-Za-z0-9+/=]+)$/.exec(url);
  if (!match) {
    throw new Error(
      "Screenshot must be a supported base64 PNG, JPEG, WEBP, or GIF data URL",
    );
  }
  return Buffer.from(match[1], "base64");
}

function targetDenied(window) {
  const value = `${window.app ?? ""} ${window.title ?? ""}`.toLowerCase();
  return DENIED_TARGETS.some((pattern) => value.includes(pattern));
}

function keyAllowed(key) {
  if (ALLOWED_KEYS.has(key)) return true;
  const parts = key.split("+").map((part) => part.trim());
  return (
    parts.length >= 2 &&
    parts.every(Boolean) &&
    parts.slice(0, -1).every((part) => MODIFIERS.has(part)) &&
    CHORD_KEYS.has(parts.at(-1))
  );
}

function redactText(text) {
  if (SECRET_PATTERN.test(text)) return "[REDACTED_SENSITIVE_TEXT]";
  const compact = text.replace(/\s+/g, " ").trim();
  return compact.length > 80 ? `${compact.slice(0, 79)}…` : compact;
}

export class SafeSkySession {
  constructor(
    skyClient,
    {
      stopPath,
      maxActions = 12,
      maxElapsedMs = 300_000,
      maxScreenshotBytes = 2_000_000,
      maxTextChars = 4_000,
      maxWaitMs = 5_000,
      maxScrollDelta = 2_000,
      maxIdenticalActions = 2,
    } = {},
  ) {
    if (skyClient == null) {
      throw new Error("Trusted sky client is required");
    }
    this.sky = skyClient;
    this.stopPath = stopPath;
    this.maxActions = maxActions;
    this.maxElapsedMs = maxElapsedMs;
    this.maxScreenshotBytes = maxScreenshotBytes;
    this.maxTextChars = maxTextChars;
    this.maxWaitMs = maxWaitMs;
    this.maxScrollDelta = maxScrollDelta;
    this.maxIdenticalActions = maxIdenticalActions;
    this.started = Date.now();
    this.actionCount = 0;
    this.turnCount = 0;
    this.windows = new Map();
    this.observation = null;
    this.grant = null;
    this.history = [];
  }

  async checkStop({ action = false } = {}) {
    if (this.stopPath) {
      try {
        await access(this.stopPath);
        throw new Error(`Kill switch present: ${this.stopPath}`);
      } catch (error) {
        if (error?.code !== "ENOENT") throw error;
      }
    }
    if (Date.now() - this.started > this.maxElapsedMs) {
      throw new Error("Computer-use elapsed-time limit exceeded");
    }
    if (action && this.actionCount >= this.maxActions) {
      throw new Error("Computer-use action limit exceeded");
    }
  }

  async listWindows() {
    await this.checkStop();
    const returned = await this.sky.list_windows();
    const safe = returned.filter((window) => !targetDenied(window));
    const next = new Map();
    for (const window of safe) {
      const item = publicWindow(window);
      if (next.has(item.id)) {
        throw new Error("Window list did not produce unique stable IDs");
      }
      next.set(item.id, { returned: window, public: item });
    }
    this.windows = next;
    this.turnCount += 1;
    return [...next.values()].map((item) => item.public);
  }

  async observe(windowId, { includeText = true } = {}) {
    await this.checkStop();
    const selected = this.windows.get(windowId);
    if (!selected) throw new Error("Unknown window ID; list windows again");
    const live = await this.sky.get_window({
      id: selected.returned.id,
      app: selected.returned.app,
    });
    if (
      live.id !== selected.returned.id ||
      live.app !== selected.returned.app ||
      targetDenied(live)
    ) {
      throw new Error("Target window identity changed or is blocked");
    }
    const state = await this.sky.get_window_state({
      window: live,
      include_screenshot: true,
      include_text: Boolean(includeText),
    });
    if (state.window.id !== live.id || state.window.app !== live.app) {
      throw new Error("Observed window identity changed");
    }
    if (!Array.isArray(state.screenshots) || state.screenshots.length !== 1) {
      throw new Error(
        `Expected exactly one bounded screenshot; got ${state.screenshots?.length ?? 0}`,
      );
    }
    const screenshot = state.screenshots[0];
    const raw = decodeDataUrl(screenshot.url);
    if (raw.length > this.maxScreenshotBytes) {
      throw new Error("Screenshot exceeds configured byte limit");
    }
    const screenshotSha256 = createHash("sha256").update(raw).digest("hex");
    const observationId = createHash("sha256")
      .update(`${windowId}:${screenshot.id}:${screenshotSha256}:${this.turnCount}`)
      .digest("hex")
      .slice(0, 24);
    const currentWindow = publicWindow(state.window, screenshot);
    this.windows.set(windowId, { returned: state.window, public: currentWindow });
    this.observation = {
      windowId,
      observationId,
      screenshotId: screenshot.id,
      screenshotSha256,
      screenshotBytes: raw.length,
      screenshot,
      state,
      window: state.window,
      publicWindow: currentWindow,
    };
    this.turnCount += 1;
    return {
      ok: true,
      window: currentWindow,
      observation_id: observationId,
      screenshot_sha256: screenshotSha256,
      screenshot_bytes: raw.length,
      image_width: Number(screenshot.width ?? 0),
      image_height: Number(screenshot.height ?? 0),
      dpi_scale: 1,
      accessibility: state.accessibility ?? null,
      input_image: screenshot.url,
    };
  }

  grantOnce(args) {
    if (!this.observation) throw new Error("Observe before granting an action");
    if (
      this.observation.windowId !== args.windowId ||
      this.observation.observationId !== args.observationId
    ) {
      throw new Error("Cannot grant a stale or mismatched observation");
    }
    const normalized = this.validateAction(args, this.observation);
    const actionSignature = createHash("sha256")
      .update(JSON.stringify(normalized))
      .digest("hex");
    this.grant = {
      windowId: args.windowId,
      observationId: args.observationId,
      action: args.action,
      actionSignature,
      nonce: createHash("sha256")
        .update(`${Date.now()}:${Math.random()}`)
        .digest("hex"),
    };
    const publicAction = { ...normalized };
    delete publicAction.text;
    return {
      target: this.observation.publicWindow,
      observation_id: args.observationId,
      requested_action: publicAction,
      risk_class:
        args.action === "type_text" ? "text_transmission" : "ui_mutation",
    };
  }

  async act(args) {
    await this.checkStop({ action: true });
    const observation = this.observation;
    if (!observation) throw new Error("Fresh observation required before action");
    if (
      args.windowId !== observation.windowId ||
      args.observationId !== observation.observationId
    ) {
      throw new Error("Action target or observation is stale");
    }
    const action = this.validateAction(args, observation);
    const signature = createHash("sha256")
      .update(JSON.stringify(action))
      .digest("hex");
    if (
      !this.grant ||
      this.grant.windowId !== args.windowId ||
      this.grant.observationId !== args.observationId ||
      this.grant.action !== args.action ||
      this.grant.actionSignature !== signature
    ) {
      throw new Error(
        "A matching one-time local approval grant for the exact arguments is required",
      );
    }
    this.grant = null;
    const pair = `${observation.screenshotSha256}:${signature}`;
    const repeats = this.history
      .slice(-this.maxIdenticalActions)
      .filter((item) => item === pair).length;
    if (repeats >= this.maxIdenticalActions) {
      throw new Error("No-progress loop detected");
    }
    this.history.push(pair);

    const rebound = await this.sky.get_window({
      id: observation.window.id,
      app: observation.window.app,
    });
    if (
      rebound.id !== observation.window.id ||
      rebound.app !== observation.window.app ||
      targetDenied(rebound)
    ) {
      throw new Error("Target window changed before action");
    }

    this.observation = null;
    try {
      await this.performOne(rebound, observation, action);
    } catch (error) {
      throw new Error(
        "Input outcome is unknown; re-list and re-observe before retrying",
        { cause: error },
      );
    }
    this.actionCount += 1;
    const refreshed = await this.observe(args.windowId, { includeText: true });
    refreshed.action = args.action;
    refreshed.risk_class =
      args.action === "type_text" ? "text_transmission" : "ui_mutation";
    return refreshed;
  }

  validateAction(args, observation) {
    const allowed = new Set([
      "focus",
      "click",
      "double_click",
      "right_click",
      "type_text",
      "press_key",
      "scroll",
      "wait",
    ]);
    if (!allowed.has(args.action)) throw new Error("Action is not allowlisted");
    const action = { action: args.action };
    if (
      ["click", "double_click", "right_click", "scroll"].includes(args.action)
    ) {
      for (const key of ["x", "y"]) {
        if (!Number.isInteger(args[key])) {
          throw new Error("Coordinates must be integers");
        }
      }
      const width = Number(observation.screenshot.width ?? 0);
      const height = Number(observation.screenshot.height ?? 0);
      if (
        args.x < 0 ||
        args.y < 0 ||
        args.x >= width ||
        args.y >= height
      ) {
        throw new Error("Coordinates are outside the fresh screenshot");
      }
      action.x = args.x;
      action.y = args.y;
    }
    if (args.action === "type_text") {
      if (
        typeof args.text !== "string" ||
        !args.text ||
        args.text.length > this.maxTextChars
      ) {
        throw new Error("Text is empty or exceeds the configured limit");
      }
      if (SECRET_PATTERN.test(args.text)) {
        throw new Error("Sensitive-looking text is blocked");
      }
      action.text = args.text;
      action.text_preview = redactText(args.text);
    }
    if (args.action === "press_key") {
      if (typeof args.key !== "string" || !keyAllowed(args.key)) {
        throw new Error("Key or chord is not allowlisted");
      }
      action.key = args.key;
    }
    if (args.action === "scroll") {
      for (const key of ["scrollX", "scrollY"]) {
        const value = args[key] ?? 0;
        if (
          !Number.isInteger(value) ||
          Math.abs(value) > this.maxScrollDelta
        ) {
          throw new Error("Scroll delta is invalid");
        }
        action[key] = value;
      }
      if (action.scrollX === 0 && action.scrollY === 0) {
        throw new Error("At least one scroll delta must be non-zero");
      }
    }
    if (args.action === "wait") {
      if (
        !Number.isInteger(args.durationMs) ||
        args.durationMs < 0 ||
        args.durationMs > this.maxWaitMs
      ) {
        throw new Error("Wait duration is invalid");
      }
      action.durationMs = args.durationMs;
    }
    return action;
  }

  async performOne(window, observation, action) {
    switch (action.action) {
      case "focus":
        await this.sky.activate_window({ window });
        return;
      case "click":
      case "double_click":
      case "right_click":
        await this.sky.click({
          window,
          screenshotId: observation.screenshotId,
          x: action.x,
          y: action.y,
          click_count: action.action === "double_click" ? 2 : 1,
          mouse_button: action.action === "right_click" ? "right" : "left",
        });
        return;
      case "type_text": {
        const focusState = await this.sky.get_window_state({
          window,
          include_screenshot: true,
          include_text: true,
        });
        if (focusState.accessibility?.focused_element == null) {
          throw new Error("No focused element; refusing to type");
        }
        await this.sky.type_text({ window: focusState.window, text: action.text });
        return;
      }
      case "press_key":
        await this.sky.press_key({ window, key: action.key });
        return;
      case "scroll":
        await this.sky.scroll({
          window,
          screenshotId: observation.screenshotId,
          x: action.x,
          y: action.y,
          scrollX: action.scrollX,
          scrollY: action.scrollY,
        });
        return;
      case "wait":
        await new Promise((resolve) => setTimeout(resolve, action.durationMs));
        return;
      default:
        throw new Error("Unsupported action");
    }
  }

  summary() {
    return {
      actions: this.actionCount,
      turns: this.turnCount,
      elapsed_ms: Date.now() - this.started,
      last_screenshot_sha256: this.observation?.screenshotSha256 ?? null,
    };
  }
}
