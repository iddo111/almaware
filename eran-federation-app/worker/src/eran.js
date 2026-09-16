// eran.js — the cloud's ERAN lane: recognition while the fleet trains.
//
//   POST /api/eran/brain        Bearer FED_PUSH_TOKEN -> store the prototype
//                               snapshot pushed from the fleet (401 without).
//   GET  /api/eran/brain.json   the snapshot's identity + age. ?vectors=1 for
//                               the prototypes themselves.
//   POST /api/eran/hear         {"vec": [192 floats]}  -> nearest prototype
//                               audio/wav body (<= 2 MiB) -> ear + nearest
//   GET  /api/eran/health       is there a brain up here, and how old is it
//
// WHY THIS EXISTS. The DGX fleet is the only place ERAN learns, and while it
// is training it has nothing left to answer questions with. His perception,
// though, is 91 prototype vectors and a frozen cochlea — kilobytes and a
// dozen lines of DSP. So the cloud carries a read-only copy and answers,
// worldwide, for free, at ~2 ms of CPU, while the fleet gets on with the work.
//
// WHAT IT IS NOT. It does not learn. There is no spawn, no Hebbian pull, no
// scar, no forgetting anywhere in this file. A second ERAN quietly learning in
// a Worker would be a second ERAN, and there is only one.

import { utteranceFromSamples, decodeWav, TooShort, DIM } from "../../cloud-inference/ear.js";
import { Brain } from "../../cloud-inference/brain.js";

const BRAIN_KEY = "eran-brain";
// One prototype costs ~1.9 KB on the wire. The organism's genome caps him at
// MAX_PROTOTYPES = 4096, so a grown brain is ~7.7 MB — the cap is set above
// that on purpose, so the lane does not silently break the day he grows.
const BRAIN_MAX_BYTES = 8 * 1024 * 1024;
const WAV_MAX_BYTES = 2 * 1024 * 1024;      // ~65 s of 16 kHz mono
const STALE_S = 15 * 60;                    // a brain older than this says so

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

function json(obj, status = 200, extra = {}) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      ...extra,
    },
  });
}

// Constant-time compare (length leak only), same as the status lane's.
function safeEqual(a, b) {
  const enc = new TextEncoder();
  const ab = enc.encode(a), bb = enc.encode(b);
  if (ab.length !== bb.length) return false;
  let diff = 0;
  for (let i = 0; i < ab.length; i++) diff |= ab[i] ^ bb[i];
  return diff === 0;
}

function authorised(request, env) {
  const auth = request.headers.get("Authorization") || "";
  const token = env.FED_PUSH_TOKEN || "";
  // No secret configured => everything is refused (fail closed).
  return Boolean(token) && auth.startsWith("Bearer ") &&
    safeEqual(auth.slice(7).trim(), token);
}

// The parsed Brain is cached per isolate: parsing 91x192 floats on every
// request would cost more than the inference does. The snapshot itself lives
// in the grid Durable Object's SQLite, not in KV — KV's 1,000-writes/day free
// quota silently stopped the organism's 10-minute push for 4.7 hours on
// 2026-08-24 while the front page advertised "snapshot stale". A DO has no
// such meter. KV stays as a read-only fallback for the pre-move copy.
const BRAIN_TTL_MS = 30_000;   // he only moves every 10 min; 30 s is plenty
let CACHE = null;              // { at, entry }

function brainStore(env) {
  return env.GRID.get(env.GRID.idFromName("grid"));
}

async function loadBrain(env) {
  if (CACHE && Date.now() - CACHE.at < BRAIN_TTL_MS) return CACHE.entry;
  let raw = null;
  try {
    const res = await brainStore(env).fetch("https://do/do/brain");
    if (res.ok) {
      const text = await res.text();
      if (text && text !== "null") raw = text;
    }
  } catch { /* fall through to KV */ }
  if (!raw) raw = await env.FEDERATION_STATUS.get(BRAIN_KEY);
  if (!raw) { CACHE = { at: Date.now(), entry: null }; return null; }
  const envelope = JSON.parse(raw);
  const snap = envelope.snapshot;
  const entry = {
    raw,
    pushed_at: envelope.pushed_at,
    brain: new Brain(snap),
    meta: {
      schema: snap.schema,
      beat: snap.beat,
      heard: snap.heard,
      dim: snap.dim,
      n_protos: snap.n_protos ?? (snap.protos || []).length,
      ear: snap.ear,
      learning: snap.learning,
      generated_at: snap.generated_at,
      source: snap.source,
    },
    protos: snap.protos,
  };
  CACHE = { at: Date.now(), entry };
  return entry;
}

function ageOf(entry) {
  const age = Math.max(0, Math.floor(Date.now() / 1000) - (entry.pushed_at || 0));
  return { age_s: age, snapshot_state: age > STALE_S ? "stale" : "fresh" };
}

export async function handleEran(request, env, url) {
  const path = url.pathname;

  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: CORS });
  }

  // --- the fleet pushes a new brain ------------------------------------------
  if (path === "/api/eran/brain" && request.method === "POST") {
    if (!authorised(request, env)) return json({ ok: false, error: "unauthorized" }, 401);
    const text = await request.text();
    if (text.length > BRAIN_MAX_BYTES) {
      return json({ ok: false, error: "brain snapshot too large", cap_bytes: BRAIN_MAX_BYTES }, 413);
    }
    let snap;
    try {
      snap = JSON.parse(text);
    } catch {
      return json({ ok: false, error: "body must be JSON" }, 400);
    }
    if (!snap || typeof snap !== "object" || !Array.isArray(snap.protos)) {
      return json({ ok: false, error: "snapshot needs a protos array" }, 400);
    }
    if (snap.dim && snap.dim !== DIM) {
      // The cloud ear is frozen at 8 slices x 24 bands. A brain of another
      // width was grown by an ear this Worker does not have, and answering
      // for it would be a guess wearing ERAN's name.
      return json({
        ok: false,
        error: `brain dim ${snap.dim} does not match this cloud ear (${DIM})`,
      }, 409);
    }
    try {
      new Brain(snap);                     // refuse a snapshot we cannot think with
    } catch (e) {
      return json({ ok: false, error: "unusable snapshot: " + e.message }, 400);
    }
    const res = await brainStore(env).fetch("https://do/do/brain", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pushed_at: Math.floor(Date.now() / 1000), snapshot: snap }),
    });
    if (!res.ok) {
      return json({ ok: false, error: "snapshot store refused the write" }, 502);
    }
    CACHE = null;
    return json({ ok: true, stored_bytes: text.length, n_protos: snap.protos.length,
                  beat: snap.beat ?? null });
  }

  // --- what brain is up here -------------------------------------------------
  if (path === "/api/eran/brain.json" && request.method === "GET") {
    const entry = await loadBrain(env);
    if (!entry) {
      return json({ ok: false, error: "no brain pushed yet", snapshot_state: "gray" }, 200, CORS);
    }
    const out = { ok: true, ...entry.meta, ...ageOf(entry) };
    if (url.searchParams.get("vectors") === "1") out.protos = entry.protos;
    return json(out, 200, CORS);
  }

  if (path === "/api/eran/health" && request.method === "GET") {
    const entry = await loadBrain(env);
    return json(entry
      ? { ok: true, brain: true, beat: entry.meta.beat, n_protos: entry.meta.n_protos,
          dim: entry.meta.dim, cloud_ear_dim: DIM, learning: "none", ...ageOf(entry) }
      : { ok: true, brain: false, cloud_ear_dim: DIM, snapshot_state: "gray",
          note: "the ear is here; no brain has been pushed" },
      200, CORS);
  }

  // --- hear something --------------------------------------------------------
  if (path === "/api/eran/hear" && request.method === "POST") {
    const entry = await loadBrain(env);
    if (!entry) {
      return json({ ok: false, error: "no brain pushed yet — the cloud has an ear but nothing to recognise with" }, 503, CORS);
    }
    const ctype = (request.headers.get("Content-Type") || "").toLowerCase();
    let vec = null;
    let heard = null;

    if (ctype.includes("audio/") || ctype.includes("application/octet-stream")) {
      const buf = await request.arrayBuffer();
      if (buf.byteLength > WAV_MAX_BYTES) {
        return json({ ok: false, error: "audio too large", cap_bytes: WAV_MAX_BYTES }, 413, CORS);
      }
      let samples;
      try {
        samples = decodeWav(buf);
      } catch (e) {
        return json({ ok: false, error: "cannot read wav: " + e.message }, 400, CORS);
      }
      try {
        vec = utteranceFromSamples(samples);
      } catch (e) {
        if (e instanceof TooShort) return json({ ok: false, error: e.message }, 400, CORS);
        throw e;
      }
      heard = { samples: samples.length, seconds: +(samples.length / 16000).toFixed(3) };
    } else {
      let body;
      try {
        body = await request.json();
      } catch {
        return json({ ok: false, error: "body must be JSON {vec:[...]} or audio/wav bytes" }, 400, CORS);
      }
      if (!Array.isArray(body.vec)) {
        return json({ ok: false, error: "expected {vec: [...]}" }, 400, CORS);
      }
      if (body.vec.length !== entry.brain.dim) {
        return json({ ok: false,
          error: `vec has ${body.vec.length} dims, this brain wants ${entry.brain.dim}` }, 400, CORS);
      }
      vec = Float64Array.from(body.vec, Number);
      let n = 0;
      for (let i = 0; i < vec.length; i++) n += vec[i] * vec[i];
      n = Math.sqrt(n);
      if (!(n > 0)) return json({ ok: false, error: "vec is all zeros" }, 400, CORS);
      // The organism only ever compares unit vectors; normalise rather than
      // return a cosine that is quietly a dot product of the wrong length.
      if (Math.abs(n - 1) > 1e-6) for (let i = 0; i < vec.length; i++) vec[i] /= n;
    }

    const got = entry.brain.nearest(vec);
    return json({
      ok: true,
      nearest: got.index,
      sim: got.sim,
      attraction: got.att,
      surprise: got.surprise,
      top: got.top,
      heard,
      brain: { beat: entry.meta.beat, n_protos: entry.meta.n_protos, ...ageOf(entry) },
      ear: "cochlea, frozen — byte-parity with eran-brain/body/ears.py",
      learning: "none — this answer changed nothing",
      // No timing field here on purpose. Workers freeze Date.now() during
      // synchronous execution, so a `ms` measured inside the Worker is always
      // 0 and would be a lie dressed as a metric. The CPU cost is measured on
      // the bench instead (cloud-inference/README.md), and the caller can time
      // its own round trip, which is the number it actually cares about.
    }, 200, CORS);
  }

  return null;   // not an ERAN route; let the caller carry on
}
