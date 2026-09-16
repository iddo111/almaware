// parity_test.mjs — the acceptance check for the cloud ear.
//
// Runs the JavaScript cochlea (ear.js) over the same wavs parity_dump.py just
// ran ERAN's real cochlea over, and compares every one of the 192 numbers.
// Also replays the nearest-prototype lookup and demands the SAME prototype.
//
//   node parity_test.mjs [parity.json] [brain.json.gz]
//
// Exit 0 = the cloud hears what ERAN hears. Exit 1 = it does not, and the
// output names the file, the dimension and the size of the drift.

import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { utteranceFromSamples, decodeWav, bandSlices, DIM } from "./ear.js";
import { Brain } from "./brain.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const ERAN_BRAIN = process.env.ERAN_BRAIN_DIR || resolve(HERE, "..", "..", "eran-brain");
const FOOD = join(ERAN_BRAIN, "food", "train");

// Tolerances. The JS ear runs its FFT in float64 and numpy runs pocketfft in
// float64 too, but the two sum in different orders, so the vectors agree to
// ~1e-7 per dimension and never bit-for-bit. The cosine is a dot product of
// those vectors, so its error inherits the same order — an earlier 1e-9 bar
// here was the TEST being wrong, not the ear. What must be exact is the
// DECISION: the same prototype, every time.
const VEC_TOL = 1e-6;      // per-dimension absolute drift we tolerate
const SIM_TOL = 1e-6;      // cosine against a prototype (inherits VEC_TOL)

const truthPath = process.argv[2] || join(HERE, "parity.json");
const truth = JSON.parse(readFileSync(truthPath, "utf-8"));

let failures = 0;
const note = (msg) => { console.log(msg); };

// --- 1. the band table -------------------------------------------------------
const mine = bandSlices(truth.ear.n_bands);
const theirs = truth.ear.slices;
let bandBad = 0;
for (let i = 0; i < theirs.length; i++) {
  if (mine[i][0] !== theirs[i][0] || mine[i][1] !== theirs[i][1]) {
    note(`  BAND ${i}: js [${mine[i]}] vs py [${theirs[i]}]`);
    bandBad++;
  }
}
note(bandBad === 0
  ? `band table            OK   ${theirs.length} bands, identical bin ranges`
  : `band table            FAIL ${bandBad}/${theirs.length} bands differ`);
failures += bandBad ? 1 : 0;

if (DIM !== truth.ear.dim) {
  note(`dim                   FAIL js ${DIM} vs py ${truth.ear.dim}`);
  failures++;
}

// --- 2. every vector ---------------------------------------------------------
let worstVec = 0, worstFile = null, worstDim = -1;
let brain = null;
// The brain to check against must be the one parity_dump.py scored, not
// whatever happens to sit in the local state/ — on the PC that is a COPY and
// was 50 million beats behind the organism living on eran1 (found 2026-08-24).
const brainPath = process.argv[3] || join(ERAN_BRAIN, "state", "brain.json.gz");
if (truth.brain) {
  const { gunzipSync } = await import("node:zlib");
  const snap = JSON.parse(gunzipSync(readFileSync(brainPath)).toString("utf-8"));
  brain = new Brain({ beat: snap.beat, dim: snap.dim, protos: snap.protos });
  if (brain.n !== truth.brain.n_protos) {
    note(`brain                 FAIL js ${brain.n} protos vs py ${truth.brain.n_protos}`);
    failures++;
  }
}

let nearestBad = 0, worstSim = 0;
for (const item of truth.items) {
  const buf = readFileSync(join(FOOD, item.file));
  const samples = decodeWav(buf);
  const v = utteranceFromSamples(samples);
  for (let d = 0; d < truth.ear.dim; d++) {
    const diff = Math.abs(v[d] - item.vec[d]);
    if (diff > worstVec) { worstVec = diff; worstFile = item.file; worstDim = d; }
  }
  if (brain && item.nearest) {
    const got = brain.nearest(v);
    if (got.index !== item.nearest.index) {
      note(`  NEAREST ${item.file}: js proto ${got.index} vs py ${item.nearest.index}`);
      nearestBad++;
    }
    const sd = Math.abs(got.sim - item.nearest.sim);
    if (sd > worstSim) worstSim = sd;
  }
}

const vecOK = worstVec <= VEC_TOL;
note(vecOK
  ? `utterance vectors     OK   ${truth.items.length} wavs x ${truth.ear.dim} dims, worst drift ${worstVec.toExponential(2)} (tol ${VEC_TOL})`
  : `utterance vectors     FAIL worst drift ${worstVec.toExponential(2)} at ${worstFile} dim ${worstDim} (tol ${VEC_TOL})`);
failures += vecOK ? 0 : 1;

if (brain) {
  const simOK = nearestBad === 0 && worstSim <= SIM_TOL;
  note(simOK
    ? `nearest prototype     OK   ${truth.items.length}/${truth.items.length} identical, worst cosine drift ${worstSim.toExponential(2)}`
    : `nearest prototype     FAIL ${nearestBad} mismatched, worst cosine drift ${worstSim.toExponential(2)}`);
  failures += simOK ? 0 : 1;
} else {
  note(`nearest prototype     SKIP no brain snapshot in ${truthPath}`);
}

console.log("");
console.log(failures === 0
  ? `PARITY OK — the cloud ear hears what ERAN hears (${truth.items.length} utterances).`
  : `PARITY FAILED — ${failures} check(s). ears.py is right; ear.js is wrong.`);
process.exit(failures === 0 ? 0 : 1);
