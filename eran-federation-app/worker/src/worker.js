// ERAN Federation Worker — cloud front door.
// POST /api/push          Bearer FED_PUSH_TOKEN -> stores snapshot in KV (401 without).
// GET  /api/federation.json  reads KV, adds age_s. Read-only, CORS open.
// /api/eran/*             ERAN's recognition lane (src/eran.js): a read-only copy
//                         of his prototypes + his frozen cochlea, so the cloud can
//                         answer while the fleet trains. It never learns.
// Static assets (public/) serve the read-only panel; unmatched paths reach this worker.

import { handleEran } from "./eran.js";
import { GridDO } from "./grid.js";

export { GridDO };

const MAX_BODY_BYTES = 512 * 1024; // 512 KiB cap on pushed snapshots
const KV_KEY = "latest";

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
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

// Constant-time string compare (length leak only, values never short-circuit).
function safeEqual(a, b) {
  const enc = new TextEncoder();
  const ab = enc.encode(a);
  const bb = enc.encode(b);
  if (ab.length !== bb.length) return false;
  let diff = 0;
  for (let i = 0; i < ab.length; i++) diff |= ab[i] ^ bb[i];
  return diff === 0;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    if (path.startsWith("/api/eran/")) {
      const res = await handleEran(request, env, url);
      if (res) return res;
      return json({ ok: false, error: "not found" }, 404);
    }

    // ER"N-GRID coordinator lives in one SQLite Durable Object: transactional
    // merges, and none of KV's 1,000-writes/day meter (which v1 hit in its
    // first hour, 2026-08-24).
    if (path.startsWith("/api/grid/")) {
      const id = env.GRID.idFromName("grid");
      return env.GRID.get(id).fetch(request);
    }

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS });
    }

    if (path === "/api/push") {
      if (request.method !== "POST") {
        return json({ ok: false, error: "POST only" }, 405);
      }
      const auth = request.headers.get("Authorization") || "";
      const token = env.FED_PUSH_TOKEN || "";
      // No secret configured => everything is refused (fail closed).
      if (!token || !auth.startsWith("Bearer ") || !safeEqual(auth.slice(7).trim(), token)) {
        return json({ ok: false, error: "unauthorized" }, 401);
      }
      let text;
      try {
        text = await request.text();
      } catch {
        return json({ ok: false, error: "unreadable body" }, 400);
      }
      if (text.length > MAX_BODY_BYTES) {
        return json({ ok: false, error: "snapshot too large" }, 413);
      }
      let snapshot;
      try {
        snapshot = JSON.parse(text);
      } catch {
        return json({ ok: false, error: "body must be JSON" }, 400);
      }
      if (snapshot === null || typeof snapshot !== "object" || Array.isArray(snapshot)) {
        return json({ ok: false, error: "snapshot must be a JSON object" }, 400);
      }
      const envelope = JSON.stringify({
        pushed_at: Math.floor(Date.now() / 1000),
        snapshot,
      });
      await env.FEDERATION_STATUS.put(KV_KEY, envelope);
      return json({ ok: true, stored_bytes: envelope.length });
    }

    if (path === "/api/federation.json") {
      if (request.method !== "GET") {
        return json({ ok: false, error: "GET only" }, 405, CORS);
      }
      const raw = await env.FEDERATION_STATUS.get(KV_KEY);
      if (!raw) {
        return json(
          { ok: false, error: "no snapshot yet", age_s: null, snapshot_state: "gray" },
          200,
          CORS
        );
      }
      let envelope;
      try {
        envelope = JSON.parse(raw);
      } catch {
        return json({ ok: false, error: "corrupt snapshot", age_s: null }, 200, CORS);
      }
      const age_s = Math.max(0, Math.floor(Date.now() / 1000) - (envelope.pushed_at || 0));
      const out = Object.assign({}, envelope.snapshot, {
        ok: true,
        pushed_at: envelope.pushed_at,
        age_s,
        snapshot_state: age_s > 180 ? "stale" : "fresh",
      });
      return json(out, 200, CORS);
    }

    return json({ ok: false, error: "not found" }, 404);
  },
};
