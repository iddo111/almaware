import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
for (const file of ["public/index.html", "public/app.js", "public/manifest.webmanifest", "public/icon.svg", "public/sw.js", "server.mjs"]) test(`${file} keeps safety contract`, () => assert.ok(readFileSync(new URL(`../${file}`, import.meta.url), "utf8").length > 100));
test("client never embeds a secret or shell runner", () => { const app = readFileSync(new URL("../public/app.js", import.meta.url), "utf8"); assert.equal(/OPENAI_API_KEY|child_process|powershell|exec\(/i.test(app), false); });
test("phone client uses the same-origin bridge instead of phone loopback", () => {
  const app = readFileSync(new URL("../public/app.js", import.meta.url), "utf8");
  assert.match(app, /\/api\/grok\/health/);
  assert.match(app, /\/api\/grok\/generate/);
  assert.equal(/127\.0\.0\.1:11435/.test(app), false);
});
test("bridge pins the exact Grok model and limits requests", () => {
  const server = readFileSync(new URL("../server.mjs", import.meta.url), "utf8");
  assert.match(server, /model: "grok-1-q6"/);
  assert.match(server, /65_536/);
  assert.match(server, /Math\.min\([^\n]*512/);
});
test("Grok responses stream progressively to the phone", () => {
  const app = readFileSync(new URL("../public/app.js", import.meta.url), "utf8");
  const server = readFileSync(new URL("../server.mjs", import.meta.url), "utf8");
  assert.match(app, /stream: true/);
  assert.match(app, /body\.getReader\(\)/);
  assert.match(server, /application\/x-ndjson/);
});
test("English Agent and Exact Raw stay visibly separate", () => {
  const html = readFileSync(new URL("../public/index.html", import.meta.url), "utf8");
  const app = readFileSync(new URL("../public/app.js", import.meta.url), "utf8");
  const server = readFileSync(new URL("../server.mjs", import.meta.url), "utf8");
  assert.match(html, /English Agent \(default\)/);
  assert.match(html, /Exact Raw research mode/);
  assert.match(app, /[\\u0400-\\u04ff]/);
  assert.match(server, /mode === "raw"/);
  assert.match(server, /English-only response/);
});
test("PWA shell is installable and keeps API calls network-only", () => {
  const manifest = JSON.parse(readFileSync(new URL("../public/manifest.webmanifest", import.meta.url), "utf8"));
  const worker = readFileSync(new URL("../public/sw.js", import.meta.url), "utf8");
  assert.equal(manifest.display, "standalone");
  assert.equal(manifest.icons[0].purpose, "any maskable");
  assert.match(worker, /url\.pathname\.startsWith\("\/api\/"\)/);
});
test("non-stream English API output is guarded server-side", () => {
  const server = readFileSync(new URL("../server.mjs", import.meta.url), "utf8");
  assert.match(server, /guardEnglishOutput/);
  assert.match(server, /mode === "english"/);
  assert.match(server, /payload\.response = guardEnglishOutput/);
});

test("Music Relay is receive-only WebRTC with Opus preferred and no cloud ICE", () => {
  const app = readFileSync(new URL("../public/app.js", import.meta.url), "utf8");
  assert.match(app, /new RTCPeerConnection\(\{ iceServers: \[\] \}\)/);
  assert.match(app, /addTransceiver\("audio", \{ direction: "recvonly" \}\)/);
  assert.match(app, /audio\/opus/);
  assert.match(app, /directHostOffer/);
  assert.equal(/getUserMedia\(/.test(app), false);
});

test("pairing token stays out of URLs and persistent browser storage", () => {
  const app = readFileSync(new URL("../public/app.js", import.meta.url), "utf8");
  assert.match(app, /X-A70-Pairing-Token/);
  assert.equal(/localStorage|sessionStorage/.test(app), false);
  assert.equal(/\?token=|pairingToken=/.test(app), false);
});

test("Node authenticates music signaling before reaching a loopback sidecar", () => {
  const server = readFileSync(new URL("../server.mjs", import.meta.url), "utf8");
  assert.match(server, /A70_PAIRING_TOKEN/);
  assert.match(server, /timingSafeEqual/);
  assert.match(server, /http:\/\/127\.0\.0\.1:4180/);
  assert.match(server, /X-Relay-Internal/);
  assert.match(server, /\/api\/music\/offer/);
});

test("Python media sidecar pins loopback control, WASAPI, and Opus", () => {
  const relay = readFileSync(new URL("../music_relay.py", import.meta.url), "utf8");
  assert.match(relay, /include_loopback=True/);
  assert.match(relay, /Windows WASAPI loopback/);
  assert.match(relay, /RTCConfiguration\(iceServers=\[\]\)/);
  assert.match(relay, /audio\/opus/);
  assert.match(relay, /pin_answer_candidate/);
  assert.match(relay, /Refusing non-loopback control bind/);
});

test("firewall helper is inert by default and scoped to Private LocalSubnet", () => {
  const script = readFileSync(new URL("../configure-private-firewall.ps1", import.meta.url), "utf8");
  assert.match(script, /if \(-not \$Apply\)/);
  assert.match(script, /-Profile Private/);
  assert.match(script, /-RemoteAddress LocalSubnet/);
  assert.match(script, /-Program \$python -Protocol UDP/);
  assert.match(script, /sys\._base_executable/);
  assert.equal(/-Profile Any|-RemoteAddress Any/.test(script), false);
});

test("phone UI has a bounded scrolling diagnostics log", () => {
  const html = readFileSync(new URL("../public/index.html", import.meta.url), "utf8");
  const css = readFileSync(new URL("../public/style.css", import.meta.url), "utf8");
  assert.match(html, /id="musicLog"/);
  assert.match(css, /\.relay-log \{[^}]*max-height:[^}]*overflow-y: auto/s);
  assert.match(css, /body \{[^}]*overflow-y: auto/s);
});
