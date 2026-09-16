// worker_test.mjs — drive the real Worker module with a fake KV and a real wav.
//
//   node worker_test.mjs
//
// `wrangler dev` wants a terminal it does not get here, so this harness imports
// worker.js itself and hands it Request objects. It exercises the code that
// actually ships: routing, the Bearer check, the dim guard, the KV envelope,
// the ear and the lookup. What it does NOT prove is workerd's own limits
// (CPU ceiling, KV latency) — those need a real deploy, which is Iddo's call.

import { readFileSync } from "node:fs";
import { gunzipSync } from "node:zlib";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import worker from "../worker/src/worker.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const ERAN_BRAIN = process.env.ERAN_BRAIN_DIR || resolve(HERE, "..", "..", "eran-brain");
const TOKEN = "local-test-token";
const BASE = "https://federation.test";

const kv = new Map();
const env = {
  FED_PUSH_TOKEN: TOKEN,
  FEDERATION_STATUS: {
    async get(k) { return kv.has(k) ? kv.get(k) : null; },
    async put(k, v) { kv.set(k, v); },
  },
};

let pass = 0, fail = 0;
function check(name, ok, detail = "") {
  console.log(`${ok ? "  ok  " : "  FAIL"}  ${name}${detail ? "  — " + detail : ""}`);
  ok ? pass++ : fail++;
}
const call = (path, init) => worker.fetch(new Request(BASE + path, init), env);

// The payload the fleet's push_brain.py would send, built the same way.
const raw = JSON.parse(gunzipSync(readFileSync(join(ERAN_BRAIN, "state", "brain.json.gz"))).toString("utf-8"));
const snapshot = {
  schema: "eran-brain-public-v1",
  beat: raw.beat,
  heard: raw.heard,
  dim: raw.dim,
  n_protos: raw.protos.length,
  ear: { repr: "cochlea", n_bands: 24, slices: 8, frozen: true },
  learning: "none — the cloud recognises, the fleet learns",
  protos: raw.protos.map((p) => ({
    vec: p.vec.map((x) => Math.round(x * 1e6) / 1e6),
    scar: p.scar, mass: p.mass, birth_step: p.birth_step, last_used: p.last_used,
  })),
};
const body = JSON.stringify(snapshot);
const authed = { "Content-Type": "application/json", Authorization: "Bearer " + TOKEN };

console.log("ERAN cloud lane — worker harness\n");

// --- before anything is pushed ------------------------------------------------
let r = await call("/api/eran/health");
let j = await r.json();
check("health with no brain", r.status === 200 && j.brain === false && j.cloud_ear_dim === 192,
  `HTTP ${r.status} brain=${j.brain} ear_dim=${j.cloud_ear_dim}`);

r = await call("/api/eran/hear", { method: "POST", headers: { "Content-Type": "application/json" }, body: '{"vec":[]}' });
check("hear before a brain is pushed = 503", r.status === 503, `HTTP ${r.status}`);

// --- the push lane ------------------------------------------------------------
r = await call("/api/eran/brain", { method: "POST", headers: { "Content-Type": "application/json" }, body });
check("push without a token = 401", r.status === 401, `HTTP ${r.status}`);

r = await call("/api/eran/brain", {
  method: "POST", body,
  headers: { "Content-Type": "application/json", Authorization: "Bearer wrong-token" },
});
check("push with the wrong token = 401", r.status === 401, `HTTP ${r.status}`);

r = await call("/api/eran/brain", {
  method: "POST", headers: authed,
  body: JSON.stringify({ ...snapshot, dim: 128, protos: [{ vec: new Array(128).fill(0.1), scar: 0 }] }),
});
check("a brain from another ear = 409", r.status === 409, `HTTP ${r.status}`);

r = await call("/api/eran/brain", { method: "POST", headers: authed, body: "not json" });
check("garbage body = 400", r.status === 400, `HTTP ${r.status}`);

r = await call("/api/eran/brain", { method: "POST", headers: authed, body });
j = await r.json();
check("push the real brain", r.status === 200 && j.ok && j.n_protos === raw.protos.length,
  `HTTP ${r.status} ${j.n_protos} prototypes, ${j.stored_bytes.toLocaleString()} bytes`);

// --- what is up there ---------------------------------------------------------
r = await call("/api/eran/brain.json");
j = await r.json();
check("brain.json is metadata only by default", j.ok && j.protos === undefined && j.n_protos === raw.protos.length,
  `beat ${j.beat}, ${j.n_protos} prototypes, age ${j.age_s}s, ${j.snapshot_state}`);
check("brain.json says it never learns", j.learning === "none — the cloud recognises, the fleet learns");

r = await call("/api/eran/brain.json?vectors=1");
j = await r.json();
check("?vectors=1 returns the prototypes", Array.isArray(j.protos) && j.protos.length === raw.protos.length,
  `${j.protos.length} x ${j.protos[0].vec.length}`);

// --- hearing ------------------------------------------------------------------
// The truth file parity_dump.py wrote: same wavs, ERAN's own cochlea's answer.
const truth = JSON.parse(readFileSync(join(HERE, "parity.json"), "utf-8"));
let wavOK = 0, wavBad = 0, worst = 0, slowest = 0;
for (const item of truth.items.slice(0, 12)) {
  const wav = readFileSync(join(ERAN_BRAIN, "food", "train", item.file));
  const res = await call("/api/eran/hear", {
    method: "POST", headers: { "Content-Type": "audio/wav" }, body: wav,
  });
  const got = await res.json();
  if (res.status === 200 && got.nearest === item.nearest.index) wavOK++;
  else { wavBad++; console.log(`     ${item.file}: got ${got.nearest}, ERAN says ${item.nearest.index}`); }
  worst = Math.max(worst, Math.abs(got.sim - item.nearest.sim));
  slowest = Math.max(slowest, got.ms);
}
check("POST a wav -> the prototype ERAN would pick", wavBad === 0,
  `${wavOK}/${wavOK + wavBad} identical, worst cosine drift ${worst.toExponential(2)}, slowest ${slowest} ms`);

// A caller who did the ear themselves (browser, phone, fleet) sends the vector.
r = await call("/api/eran/hear", {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ vec: truth.items[0].vec }),
});
j = await r.json();
check("POST a 192-vector -> the same answer", j.ok && j.nearest === truth.items[0].nearest.index,
  `proto ${j.nearest}, sim ${j.sim.toFixed(6)}, surprise ${j.surprise.toFixed(4)}`);

r = await call("/api/eran/hear", {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ vec: new Array(64).fill(0.1) }),
});
check("a vector of the wrong width = 400", r.status === 400, `HTTP ${r.status}`);

// 40 ms of audio: fewer than the 8 frames a cochlea needs. Python would have
// produced a vector of NaN here; the cloud must refuse in words.
const shortWav = (() => {
  const n = 640, buf = Buffer.alloc(44 + n * 2);
  buf.write("RIFF", 0); buf.writeUInt32LE(36 + n * 2, 4); buf.write("WAVE", 8);
  buf.write("fmt ", 12); buf.writeUInt32LE(16, 16); buf.writeUInt16LE(1, 20);
  buf.writeUInt16LE(1, 22); buf.writeUInt32LE(16000, 24); buf.writeUInt32LE(32000, 28);
  buf.writeUInt16LE(2, 32); buf.writeUInt16LE(16, 34);
  buf.write("data", 36); buf.writeUInt32LE(n * 2, 40);
  for (let i = 0; i < n; i++) buf.writeInt16LE(Math.round(8000 * Math.sin(i / 4)), 44 + i * 2);
  return buf;
})();
r = await call("/api/eran/hear", { method: "POST", headers: { "Content-Type": "audio/wav" }, body: shortWav });
j = await r.json();
check("40 ms of audio is refused, not NaN", r.status === 400 && /too short/.test(j.error), j.error);

// --- the status lane must be untouched ---------------------------------------
r = await call("/api/federation.json");
j = await r.json();
check("the status lane still answers", r.status === 200 && j.error === "no snapshot yet",
  `HTTP ${r.status} (empty KV, as expected in this harness)`);

r = await call("/api/eran/nonsense");
check("an unknown eran route = 404", r.status === 404, `HTTP ${r.status}`);

console.log(`\n${fail === 0 ? "ALL PASS" : "FAILED"} — ${pass} passed, ${fail} failed`);
process.exit(fail === 0 ? 0 : 1);
