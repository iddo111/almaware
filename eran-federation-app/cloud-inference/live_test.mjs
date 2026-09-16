// live_test.mjs — the REAL acceptance check: the deployed cloud, over the
// internet, against what ERAN's own cochlea says on this machine.
//
//   node live_test.mjs [https://federation.iddoperez.ai] [parity.json]
//
// `health: ok` is not a test. This sends actual wavs to the actual Worker and
// demands the same prototype ERAN picked, plus the guards: a wrong-width
// vector, 40 ms of audio, an unauthorised push. Round-trip latency is
// reported separately from the Worker's own CPU time, because they are not
// the same number and only one of them is ours.

import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { utteranceFromSamples, decodeWav } from "./ear.js";
import { Brain } from "./brain.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const BASE = (process.argv[2] || "https://federation.iddoperez.ai").replace(/\/$/, "");
const TRUTH = process.argv[3] || join(HERE, "parity.json");
const ERAN_BRAIN = process.env.ERAN_BRAIN_DIR || resolve(HERE, "..", "..", "eran-brain");
const FOOD = join(ERAN_BRAIN, "food", "train");

const truth = JSON.parse(readFileSync(TRUTH, "utf-8"));
let pass = 0, fail = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "  ok  " : "  FAIL"}  ${name}${detail ? "  — " + detail : ""}`);
  ok ? pass++ : fail++;
};

console.log(`ERAN cloud lane — LIVE against ${BASE}\n`);

// --- is anybody home ---------------------------------------------------------
let t = Date.now();
let r = await fetch(`${BASE}/api/eran/health`);
let j = await r.json();
check("health", r.ok && j.ok === true,
  `HTTP ${r.status}, brain=${j.brain}, ${j.n_protos ?? 0} prototypes, beat ${j.beat ?? "-"}, ${j.snapshot_state}, ${Date.now() - t} ms round trip`);
check("a brain is actually up there", j.brain === true && j.n_protos > 0,
  j.brain ? `beat ${j.beat}, age ${j.age_s}s` : "no brain pushed");
check("the cloud ear matches the brain's width", j.dim === j.cloud_ear_dim, `${j.dim} = ${j.cloud_ear_dim}`);
check("the cloud says it does not learn", j.learning === "none");

// --- the real thing: hearing --------------------------------------------------
// THE SCAR (2026-08-24). This used to compare the cloud's answer against a
// truth file frozen earlier. It failed 22/24 — and the failure was ERAN, not
// the lane: he had lived 18,000 beats between the file being written and the
// brain being pushed, so two borderline utterances had moved to a neighbouring
// prototype. A frozen expectation cannot judge a living organism.
//
// So the comparison is now anchored to the snapshot the cloud ITSELF holds:
// fetch its prototypes, run the same ear and the same lookup here, and demand
// the deployed Worker agrees with the local code on the SAME brain. What that
// proves is the deployment. That the JS ear equals ERAN's own Python cochlea is
// proved separately and cross-language by parity_test.mjs (396/396).
r = await fetch(`${BASE}/api/eran/brain.json?vectors=1`);
const cloudSnap = await r.json();
check("the cloud hands back the brain it is serving",
  r.ok && Array.isArray(cloudSnap.protos) && cloudSnap.protos.length === cloudSnap.n_protos,
  `${cloudSnap.n_protos} prototypes, beat ${cloudSnap.beat}`);
const localBrain = new Brain(cloudSnap);

let ok = 0, bad = 0, worstSim = 0, slowestRT = 0;
const rts = [];
for (const item of truth.items) {
  const wav = readFileSync(join(FOOD, item.file));
  const expect = localBrain.nearest(utteranceFromSamples(decodeWav(wav)));
  const t0 = Date.now();
  const res = await fetch(`${BASE}/api/eran/hear`, {
    method: "POST", headers: { "Content-Type": "audio/wav" }, body: wav,
  });
  const rt = Date.now() - t0;
  rts.push(rt);
  const got = await res.json();
  if (res.status === 200 && got.nearest === expect.index) ok++;
  else { bad++; console.log(`     ${item.file}: cloud ${got.nearest ?? got.error}, local ${expect.index}`); }
  if (got.sim !== undefined) worstSim = Math.max(worstSim, Math.abs(got.sim - expect.sim));
  slowestRT = Math.max(slowestRT, rt);
}
rts.sort((a, b) => a - b);
check("the deployed Worker agrees with local code on its own brain", bad === 0,
  `${ok}/${ok + bad} identical, worst cosine drift ${worstSim.toExponential(2)}`);
check("latency", true,
  `p50 ${rts[Math.floor(rts.length / 2)]} ms round trip, worst ${slowestRT} ms (network + Cloudflare, NOT the ear: that is 2 ms on the bench)`);

// --- the guards, live ---------------------------------------------------------
r = await fetch(`${BASE}/api/eran/hear`, {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ vec: truth.items[0].vec }),
});
j = await r.json();
const expect0 = localBrain.nearest(Float64Array.from(truth.items[0].vec));
check("a 192-vector gets the same answer as the wav path", j.ok && j.nearest === expect0.index,
  `proto ${j.nearest}, sim ${j.sim?.toFixed(6)}`);

r = await fetch(`${BASE}/api/eran/hear`, {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ vec: new Array(64).fill(0.1) }),
});
check("a vector of the wrong width is refused", r.status === 400, `HTTP ${r.status}`);

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
r = await fetch(`${BASE}/api/eran/hear`, { method: "POST", headers: { "Content-Type": "audio/wav" }, body: shortWav });
j = await r.json();
check("40 ms of audio is refused in words, not NaN", r.status === 400 && /too short/.test(j.error || ""), j.error);

r = await fetch(`${BASE}/api/eran/brain`, {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ dim: 192, protos: [{ vec: new Array(192).fill(0.05), scar: 0 }] }),
});
check("an unauthorised push is refused", r.status === 401, `HTTP ${r.status}`);

// --- the status lane must not have been collateral damage ---------------------
r = await fetch(`${BASE}/api/federation.json`);
j = await r.json();
check("the federation status lane still works", r.ok && j.ok && Array.isArray(j.nodes),
  `${j.nodes?.length ?? 0} public nodes, age ${j.age_s}s, ${j.snapshot_state}`);

console.log(`\n${fail === 0 ? "ALL PASS" : "FAILED"} — ${pass} passed, ${fail} failed`);
process.exit(fail === 0 ? 0 : 1);
