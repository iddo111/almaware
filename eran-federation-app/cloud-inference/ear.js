// ear.js — ERAN's FROZEN COCHLEA, ported to JavaScript so the cloud can hear.
//
// This is a PORT, not a redesign. Every constant and every step is copied from
// eran-brain/body/ears.py + body/genome.py at the state they were frozen in
// (EAR_FROZEN = True, 2026-08-21). If the two ever disagree, ears.py is right
// and this file is broken — parity_test.mjs exists to catch exactly that.
//
//   25 ms Hann frames on a 10 ms hop (400 / 160 samples at 16 kHz)
//   |rfft(frame, 512)| + eps, then per-frame level-normalised (a cochlea codes
//   SHAPE, not volume), summed into 24 log-spaced bands 50-8000 Hz, log taken
//   speech span = frames whose rms > 10% of the loudest frame
//   that span cut into 8 fixed slices, each mean-pooled, mean-removed, L2'd
//   192 numbers (8 slices x 24 bands), L2'd once more. That is one percept.
//
// Measured on the 132-item 22-class heldout: 79.55%. Nothing here learns.

export const SAMPLE_RATE = 16000;
export const N_FFT = 512;
export const N_BANDS = 24;
export const EAR_SLICES = 8;
export const EAR_SPEECH_FRAC = 0.10;
export const EAR_EPS = 1e-8;
export const FRAME = 400;            // round(16000 * 25 / 1000)
export const HOP = 160;              // round(16000 * 10 / 1000)
export const FMIN_HZ = 50.0;
export const FMAX_HZ = 8000.0;
export const DIM = EAR_SLICES * N_BANDS;   // 192

// numpy's np.round is round-half-to-EVEN, not JS's round-half-up. The band
// edges are computed with it, so a naive Math.round could shift a band by one
// bin and silently change every vector this ear has ever produced.
function roundHalfEven(x) {
  const f = Math.floor(x);
  const d = x - f;
  if (d > 0.5) return f + 1;
  if (d < 0.5) return f;
  return f % 2 === 0 ? f : f + 1;
}

// Log-spaced band edges 50-8000 Hz mapped to FFT bin ranges [a, b).
// Every band is forced to hold at least one bin (ears.py:_band_slices).
export function bandSlices(nBands = N_BANDS) {
  const bins = N_FFT / 2 + 1;                 // 257
  const hzPerBin = SAMPLE_RATE / N_FFT;       // 31.25
  const idx = new Array(nBands + 1);
  for (let i = 0; i <= nBands; i++) {
    // np.geomspace(FMIN, FMAX, nBands + 1)
    const hz = FMIN_HZ * Math.pow(FMAX_HZ / FMIN_HZ, i / nBands);
    idx[i] = roundHalfEven(hz / hzPerBin);
  }
  idx[0] = Math.max(idx[0], 1);               // skip DC
  for (let i = 1; i <= nBands; i++) idx[i] = Math.max(idx[i], idx[i - 1] + 1);
  for (let i = 0; i <= nBands; i++) idx[i] = Math.min(idx[i], bins);
  const out = [];
  for (let i = 0; i < nBands; i++) out.push([idx[i], idx[i + 1]]);
  return out;
}

// np.hanning(M) — the SYMMETRIC window (denominator M-1), cast to float32 the
// way ears.py stores it.
function hann(M) {
  const w = new Float32Array(M);
  for (let n = 0; n < M; n++) {
    w[n] = Math.fround(0.5 - 0.5 * Math.cos((2 * Math.PI * n) / (M - 1)));
  }
  return w;
}
const WINDOW = hann(FRAME);
const SLICES = bandSlices();

// --- FFT ---------------------------------------------------------------------
// Iterative radix-2 Cooley-Tukey in double precision — the same float64 the
// numpy promotion gives a float32 frame before it transforms it.
//
// The twiddle factors are precomputed ONCE. The first version called
// Math.cos/Math.sin inside the butterfly and cost 10.3 ms of CPU per
// utterance, which is exactly the Cloudflare free-tier per-request CPU limit —
// a cloud ear that only sometimes answers is a broken window, so the table
// stays.
const TW_RE = new Float64Array(N_FFT / 2);
const TW_IM = new Float64Array(N_FFT / 2);
for (let i = 0; i < N_FFT / 2; i++) {
  TW_RE[i] = Math.cos((-2 * Math.PI * i) / N_FFT);
  TW_IM[i] = Math.sin((-2 * Math.PI * i) / N_FFT);
}

function fft512(re, im) {
  const n = re.length;
  for (let i = 1, j = 0; i < n; i++) {           // bit-reversal permutation
    let bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) {
      let t = re[i]; re[i] = re[j]; re[j] = t;
      t = im[i]; im[i] = im[j]; im[j] = t;
    }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const half = len >> 1;
    const stride = n / len;
    for (let i = 0; i < n; i += len) {
      for (let k = 0; k < half; k++) {
        const w = k * stride;
        const wr = TW_RE[w], wi = TW_IM[w];
        const ur = re[i + k], ui = im[i + k];
        const xr = re[i + k + half], xi = im[i + k + half];
        const vr = xr * wr - xi * wi;
        const vi = xr * wi + xi * wr;
        re[i + k] = ur + vr; im[i + k] = ui + vi;
        re[i + k + half] = ur - vr; im[i + k + half] = ui - vi;
      }
    }
  }
}

// --- frames ------------------------------------------------------------------
// (n_frames x 24) log-band features + (n_frames) frame rms.
// ears.py:_frames_from_samples
export function frames(samples) {
  let s = samples;
  if (s.length < FRAME) {
    const p = new Float32Array(FRAME);          // np.pad with zeros
    p.set(s);
    s = p;
  }
  const count = 1 + Math.floor((s.length - FRAME) / HOP);
  const feats = [];
  const rms = new Float32Array(count);
  const re = new Float64Array(N_FFT);
  const im = new Float64Array(N_FFT);
  const bins = N_FFT / 2 + 1;
  const mag = new Float64Array(bins);
  for (let f = 0; f < count; f++) {
    const start = HOP * f;
    re.fill(0); im.fill(0);
    let sq = 0;
    for (let i = 0; i < FRAME; i++) {
      const x = Math.fround(Math.fround(s[start + i]) * WINDOW[i]);   // float32 product
      re[i] = x;
      sq += x * x;
    }
    rms[f] = Math.sqrt(sq / FRAME + EAR_EPS);
    fft512(re, im);
    let total = 0;
    for (let b = 0; b < bins; b++) {
      mag[b] = Math.sqrt(re[b] * re[b] + im[b] * im[b]) + EAR_EPS;
      total += mag[b];
    }
    const row = new Float64Array(N_BANDS);
    for (let b = 0; b < N_BANDS; b++) {
      const a = SLICES[b][0], z = SLICES[b][1];
      let acc = 0;
      for (let k = a; k < z; k++) acc += mag[k] / total;     // level-free spectrum
      row[b] = Math.log(acc + EAR_EPS);
    }
    feats.push(row);
  }
  return { feats, rms };
}

// np.array_split(seg, 8): the first (len % 8) pieces get one extra element.
function arraySplit(len, sections) {
  const base = Math.floor(len / sections);
  const extra = len % sections;
  const out = [];
  let at = 0;
  for (let i = 0; i < sections; i++) {
    const n = base + (i < extra ? 1 : 0);
    out.push([at, at + n]);
    at += n;
  }
  return out;
}

export class TooShort extends Error {}

// --- pool --------------------------------------------------------------------
// The frozen cochlea's pooling. ears.py:pool, repr == "cochlea".
export function pool(feats, rms) {
  const n = rms.length;
  let peak = 0;
  for (let i = 0; i < n; i++) if (rms[i] > peak) peak = rms[i];
  const bar = n ? peak * EAR_SPEECH_FRAC : 0.0;
  let idx = [];
  for (let i = 0; i < n; i++) if (rms[i] > bar) idx.push(i);
  if (idx.length < EAR_SLICES) {                 // ears.py falls back to everything
    idx = [];
    for (let i = 0; i < n; i++) idx.push(i);
  }
  // Python would hand np.array_split a segment shorter than 8 and mean an
  // EMPTY slice -> NaN. The organism never gets there (its utterances are
  // ~0.3 s); the cloud can be handed anything, so it refuses instead of
  // serving a vector of NaN.
  if (idx.length < EAR_SLICES) {
    throw new TooShort(
      "utterance too short: " + n + " frame(s), the cochlea needs " +
      EAR_SLICES + " (~95 ms of audio)");
  }
  const lo = idx[0], hi = idx[idx.length - 1];   // seg = feats[idx[0]:idx[-1]+1]
  const seg = feats.slice(lo, hi + 1);
  const v = new Float64Array(DIM);
  const parts = arraySplit(seg.length, EAR_SLICES);
  for (let sIdx = 0; sIdx < EAR_SLICES; sIdx++) {
    const a = parts[sIdx][0], z = parts[sIdx][1];
    const m = new Float64Array(N_BANDS);
    for (let r = a; r < z; r++) {
      for (let b = 0; b < N_BANDS; b++) m[b] += seg[r][b];
    }
    const cnt = z - a;
    for (let b = 0; b < N_BANDS; b++) m[b] /= cnt;
    let mean = 0;
    for (let b = 0; b < N_BANDS; b++) mean += m[b];
    mean /= N_BANDS;
    let nrm = 0;
    for (let b = 0; b < N_BANDS; b++) { m[b] -= mean; nrm += m[b] * m[b]; }
    nrm = Math.sqrt(nrm);
    const d = nrm > 0 ? nrm : 1.0;
    for (let b = 0; b < N_BANDS; b++) v[sIdx * N_BANDS + b] = m[b] / d;
  }
  let vn = 0;
  for (let i = 0; i < DIM; i++) vn += v[i] * v[i];
  vn = Math.sqrt(vn);
  if (vn > 0) for (let i = 0; i < DIM; i++) v[i] /= vn;
  return v;
}

// One utterance of raw samples -> one L2-normalised 192-vector.
export function utteranceFromSamples(samples) {
  const f = frames(samples);
  return pool(f.feats, f.rms);
}

// --- wav ---------------------------------------------------------------------
// 16-bit mono PCM only, matching ears.py:read_wav (including its linear
// resample to 16 kHz, np.interp over linspace(endpoint=False)).
export function decodeWav(buf) {
  const dv = buf instanceof DataView
    ? buf
    : new DataView(buf instanceof ArrayBuffer ? buf : buf.buffer, buf.byteOffset || 0, buf.byteLength);
  if (dv.byteLength < 44) throw new Error("not a wav: too short");
  const tag = (o) => String.fromCharCode(
    dv.getUint8(o), dv.getUint8(o + 1), dv.getUint8(o + 2), dv.getUint8(o + 3));
  if (tag(0) !== "RIFF" || tag(8) !== "WAVE") throw new Error("not a RIFF/WAVE file");
  let pos = 12, fmt = null, data = null;
  while (pos + 8 <= dv.byteLength) {
    const id = tag(pos);
    const size = dv.getUint32(pos + 4, true);
    const body = pos + 8;
    if (id === "fmt ") {
      fmt = {
        format: dv.getUint16(body, true),
        channels: dv.getUint16(body + 2, true),
        rate: dv.getUint32(body + 4, true),
        bits: dv.getUint16(body + 14, true),
      };
    } else if (id === "data") {
      data = { at: body, size: Math.min(size, dv.byteLength - body) };
    }
    pos = body + size + (size % 2);
  }
  if (!fmt || !data) throw new Error("wav missing fmt/data chunk");
  if (fmt.channels !== 1 || fmt.bits !== 16) throw new Error("expected mono 16-bit PCM");
  const n = Math.floor(data.size / 2);
  let samples = new Float32Array(n);
  for (let i = 0; i < n; i++) samples[i] = dv.getInt16(data.at + 2 * i, true) / 32768.0;
  if (fmt.rate !== SAMPLE_RATE) {
    const m = Math.max(1, Math.round((n * SAMPLE_RATE) / fmt.rate));
    const out = new Float32Array(m);
    for (let i = 0; i < m; i++) {
      const t = (i / m) * n;                  // linspace(0,1,m,endpoint=False) * n
      const j = Math.floor(t);
      const frac = t - j;
      const a = samples[Math.min(j, n - 1)];
      const b = samples[Math.min(j + 1, n - 1)];
      out[i] = Math.fround(a + frac * (b - a));
    }
    samples = out;
  }
  return samples;
}
