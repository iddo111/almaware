import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);

test("ships a Hebrew, self-contained 3D perceptron lab", async () => {
  const [html, css, script] = await Promise.all([
    readFile(new URL("index.html", root), "utf8"),
    readFile(new URL("styles.css", root), "utf8"),
    readFile(new URL("app.js", root), "utf8"),
  ]);

  assert.match(html, /<html lang="he" dir="rtl">/);
  assert.match(html, /id="scene"/);
  assert.match(html, /צעד אימון אחד/);
  assert.match(html, /סף[^<\n]*θ|θ[^<\n]*סף/);
  assert.match(html, /מישור ההחלטה/);
  assert.match(html, /favicon\.svg/);
  assert.doesNotMatch(html, /https?:\/\/[^\s"']+\.(?:js|css)/i);
  assert.match(css, /prefers-reduced-motion/);
  assert.match(css, /#scene:focus-visible|canvas:focus-visible/);
  assert.match(script, /function getDecisionPlanePolygon\(\)/);
  assert.match(script, /function trainStep\(/);
  assert.match(script, /mousedown/);
  assert.match(script, /touchstart/);
  assert.match(script, /keydown/);
});

test("keeps the perceptron update rule mathematically live", async () => {
  const script = await readFile(new URL("app.js", root), "utf8");
  assert.match(script, /w1 \+= eta \* errorVal \* pt\.x\[0\]/);
  assert.match(script, /theta \+= -eta \* errorVal/);
  assert.match(script, /sum >= theta \? 1 : -1/);
  assert.match(script, /errorVal = pt\.target - y/);
});
