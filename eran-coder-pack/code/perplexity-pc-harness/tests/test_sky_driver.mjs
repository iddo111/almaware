import assert from "node:assert/strict";
import test from "node:test";

import { SafeSkySession } from "../sky_driver.mjs";


const PNG_BASE64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=";


class FakeSky {
  constructor({ focused = true, mimeType = "png" } = {}) {
    this.focused = focused;
    this.mimeType = mimeType;
    this.generation = 0;
    this.inputs = [];
    this.safeWindow = {
      id: 101,
      app: "process:C:\\safe\\pplx_test_window.exe",
      title: "PPLX-SAFE-TEST-WINDOW",
    };
    this.deniedWindow = {
      id: 202,
      app: "process:C:\\Windows\\System32\\cmd.exe",
      title: "Command Prompt",
    };
  }

  async list_windows() {
    return [this.safeWindow, this.deniedWindow].map((item) => ({ ...item }));
  }

  async get_window({ id, app }) {
    assert.equal(id, this.safeWindow.id);
    assert.equal(app, this.safeWindow.app);
    return { ...this.safeWindow };
  }

  async get_window_state({ window, include_text }) {
    assert.equal(window.id, this.safeWindow.id);
    const suffix = Buffer.from([this.generation]).toString("base64");
    return {
      window: { ...this.safeWindow },
      screenshots: [
        {
          id: `shot-${this.generation}`,
          url: `data:image/${this.mimeType};base64,${PNG_BASE64.slice(0, -2)}${suffix}==`,
          width: 100,
          height: 80,
          originX: 20,
          originY: 30,
          zIndex: 0,
        },
      ],
      accessibility: include_text
        ? {
            tree: "[1] entry [2] button",
            focused_element: this.focused ? "[1] entry" : null,
          }
        : null,
    };
  }

  async activate_window({ window }) {
    this.inputs.push({ action: "focus", window });
    this.generation += 1;
  }

  async click(args) {
    this.inputs.push({ action: "click", ...args });
    this.generation += 1;
  }

  async type_text(args) {
    this.inputs.push({ action: "type_text", ...args });
    this.generation += 1;
  }

  async press_key(args) {
    this.inputs.push({ action: "press_key", ...args });
    this.generation += 1;
  }

  async scroll(args) {
    this.inputs.push({ action: "scroll", ...args });
    this.generation += 1;
  }
}


async function prepared(options = {}) {
  const sky = new FakeSky(options);
  const session = new SafeSkySession(sky, { maxActions: 4 });
  const windows = await session.listWindows();
  const observed = await session.observe(windows[0].id);
  return { sky, session, windows, observed };
}


test("filters denied terminal targets and returns a stable safe ID", async () => {
  const { windows } = await prepared();
  assert.equal(windows.length, 1);
  assert.match(windows[0].id, /pplx_test_window\.exe\|101$/);
});


test("accepts JPEG screenshots returned by the live trusted runtime", async () => {
  const { observed } = await prepared({ mimeType: "jpeg" });
  assert.match(observed.input_image, /^data:image\/jpeg;base64,/);
});


test("requires a one-time grant, performs one click, and refreshes", async () => {
  const { sky, session, observed } = await prepared();
  session.grantOnce({
    windowId: observed.window.id,
    observationId: observed.observation_id,
    action: "click",
    x: 20,
    y: 20,
  });
  const refreshed = await session.act({
    windowId: observed.window.id,
    observationId: observed.observation_id,
    action: "click",
    x: 100,
    y: 20,
    x: 20,
    y: 20,
  });
  assert.equal(sky.inputs.length, 1);
  assert.equal(sky.inputs[0].action, "click");
  assert.notEqual(refreshed.observation_id, observed.observation_id);
  assert.notEqual(refreshed.screenshot_sha256, observed.screenshot_sha256);
});


test("rejects an action without a matching one-time grant", async () => {
  const { session, observed } = await prepared();
  await assert.rejects(
    session.act({
      windowId: observed.window.id,
      observationId: observed.observation_id,
      action: "click",
      x: 20,
      y: 20,
    }),
    /one-time local approval/,
  );
});


test("binds one-time approval to the exact action arguments", async () => {
  const { sky, session, observed } = await prepared();
  session.grantOnce({
    windowId: observed.window.id,
    observationId: observed.observation_id,
    action: "click",
    x: 20,
    y: 20,
  });
  await assert.rejects(
    session.act({
      windowId: observed.window.id,
      observationId: observed.observation_id,
      action: "click",
      x: 21,
      y: 20,
    }),
    /exact arguments/,
  );
  assert.equal(sky.inputs.length, 0);
});


test("rejects coordinates outside the observed screenshot before approval", async () => {
  const { session, observed } = await prepared();
  assert.throws(
    () =>
      session.grantOnce({
      windowId: observed.window.id,
      observationId: observed.observation_id,
      action: "click",
      x: 100,
      y: 20,
      }),
    /outside the fresh screenshot/,
  );
});


test("rechecks focus immediately before typing and fails closed", async () => {
  const { sky, session, observed } = await prepared({ focused: false });
  session.grantOnce({
    windowId: observed.window.id,
    observationId: observed.observation_id,
    action: "type_text",
    text: "SAFE_MARKER",
  });
  await assert.rejects(
    session.act({
      windowId: observed.window.id,
      observationId: observed.observation_id,
      action: "type_text",
      text: "SAFE_MARKER",
    }),
    /outcome is unknown/,
  );
  assert.equal(sky.inputs.length, 0);
});
