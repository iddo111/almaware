// grid.js — ER"N-GRID coordinator: the missing piece, built 2026-08-24,
// HARDENED the same night after an adversarial review found it destroyable.
//
// Iddo's /goal (2026-08-24 21:18): "fix eran federation so with one click
// anyone can become a member and help run and train eran on cloud."
//
// WHAT THIS IS. The volunteer-training lane. Members (a browser tab on /join,
// or eran-cloud/join.py) pull the STUDENT brain + a curated shard of real
// utterance vectors, run H inner steps of prototype refinement locally, and
// push the delta back. This class runs the outer step: merge, gate, bump
// version. DiLoCo-shaped, tiny on purpose.
//
// WHY A DURABLE OBJECT. v1 lived in KV and died the same hour: the free tier
// allows 1,000 KV writes/day and the organism's own 10-minute brain pushes had
// already spent them (Error 1101). A SQLite-backed DO has no such meter and —
// the real win — it is single-threaded and input-gated, so two volunteers
// landing deltas in the same millisecond serialize instead of one vanishing.
//
// THE HARDENING (after the 21:40 review — three attacks were real and live):
//   1. Poisoning: the merge used to gate each prototype against its OWN
//      previous value, so N repeated indices in ONE anonymous POST compounded
//      into an arbitrary rotation (18 repeats inverted a prototype). FIXED:
//      indices are de-duplicated per request, AND every candidate is gated
//      against the FROZEN SEED (state.seed), never against its moving self —
//      a total-distance cone, not a per-step speed limit. No sequence of
//      merges from any number of members can move a prototype more than
//      acos(COS_GATE) from where ERAN's snapshot put it.
//   2. Freeze: the version used to bump on EVERY post, so a 60-byte all-gated
//      delta advanced the version and made every honest round "stale" forever.
//      FIXED: the version bumps only when a prototype actually moved.
//   3. Abuse: registration and delta were unauthenticated and unbounded.
//      FIXED: register mints a member_secret (returned once, stored only as a
//      SHA-256 hash); /delta requires a known member + its secret + a
//      per-member cooldown; /task requires a known member (no anonymous
//      177 KB amplifier); registration is capped and counted without scanning.
//
// THE ONE-ERAN LAW STILL HOLDS. The grid trains a separate STUDENT brain
// seeded from the organism's read-only snapshot (KV "eran-brain", pushed from
// eran1). The organism is never touched; the student is offered BACK at
// /api/grid/brain.json for the fleet to pull, eat through its own gates, or
// ignore. There is one ERAN; the student is homework the world does for him.
//
// DATA LAW (SPEC §3 + the synthetic-corpus scar of 08-23). Shards must be REAL
// human voice that is ALREADY PUBLIC (currently: Wikimedia Commons Hebrew
// pronunciations, CC, attributed). Synthetic clips are banned — measured 08-23
// they transfer to a real mouth at chance. Sacred/private recordings (e.g. the
// Cafe-Claude episode, ruled DO-NOT-PUBLISH) never leave the fleet, and neither
// do their embeddings.

const ORGANISM_KEY = "eran-brain";          // eran.js's KV key — READ ONLY here.

const DIM = 192;
const H_DEFAULT = 200;
const ETA_INNER = 0.05;
const OUTER_LR = 0.5;
const MAX_DELTA_NORM = 0.35;
const COS_GATE = 0.86;                       // ~30.7° cone around the SEED prototype
const MAX_BODY = 2 * 1024 * 1024;
const MAX_SHARD_VECS = 400;
const MAX_MEMBERS = 5000;                    // hobby-scale ceiling; refuse past it
const MIN_DELTA_GAP_MS = 3000;               // per-member cooldown (browser loops at 8 s)
const RESEED_BEATS = 1_000_000;              // organism beats (~80 min of life) per student cycle
const STATUS_CACHE_S = 10;                   // collapse the /join 7 s poll fan-out
const ROUND6 = (x) => Math.round(x * 1e6) / 1e6;

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization",
};

function json(obj, status = 200, extra = {}) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      ...CORS,
      ...extra,
    },
  });
}

function safeEqual(a, b) {
  const enc = new TextEncoder();
  const ab = enc.encode(a), bb = enc.encode(b);
  if (ab.length !== bb.length) return false;
  let diff = 0;
  for (let i = 0; i < ab.length; i++) diff |= ab[i] ^ bb[i];
  return diff === 0;
}

async function sha256hex(str) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(str));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function l2norm(v) {
  let s = 0;
  for (let i = 0; i < v.length; i++) s += v[i] * v[i];
  return Math.sqrt(s);
}

function finiteVec(v, len) {
  if (!Array.isArray(v) || v.length !== len) return false;
  for (let i = 0; i < len; i++) {
    if (typeof v[i] !== "number" || !Number.isFinite(v[i])) return false;
  }
  return true;
}

function fnv(str) {
  let h = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = (h * 0x01000193) >>> 0;
  }
  return h >>> 0;
}

export class GridDO {
  constructor(ctx, env) {
    this.env = env;
    this.sql = ctx.storage.sql;
    this.sql.exec("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT)");
  }

  kvGet(k) {
    const rows = this.sql.exec("SELECT v FROM kv WHERE k = ?", k).toArray();
    return rows.length ? JSON.parse(rows[0].v) : null;
  }
  kvPut(k, obj) {
    this.sql.exec(
      "INSERT INTO kv (k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v",
      k, JSON.stringify(obj));
  }
  memberCount() {
    const r = this.sql.exec("SELECT COUNT(*) AS n FROM kv WHERE k LIKE 'member:%'").toArray();
    return r.length ? r[0].n : 0;
  }

  authorised(request) {
    const auth = request.headers.get("Authorization") || "";
    const token = this.env.FED_PUSH_TOKEN || "";
    return Boolean(token) && auth.startsWith("Bearer ") &&
      safeEqual(auth.slice(7).trim(), token);
  }

  // Seed the STUDENT from the organism's current pushed snapshot. Keeps BOTH a
  // frozen `seed` (the immovable reference every merge is gated against) and a
  // working `protos` copy the grid actually refines. The organism entry is not
  // modified — this is a copy taking its first day of school.
  async seedFromOrganism() {
    // The organism's snapshot now lives in this DO's own SQLite (see /do/brain).
    // KV is only the transitional fallback, for the copy pushed before the move.
    const row = this.sql.exec("SELECT v FROM kv WHERE k = 'organism'").toArray();
    const raw = row.length ? row[0].v : await this.env.FEDERATION_STATUS.get(ORGANISM_KEY);
    if (!raw) return null;
    const snap = JSON.parse(raw).snapshot;
    if (!snap || !Array.isArray(snap.protos) || !snap.protos.length) return null;
    const vecs = snap.protos.map((p) => p.vec.map(ROUND6));
    const now = Math.floor(Date.now() / 1000);
    const state = {
      version: 1, rounds_merged: 0, gated_total: 0, clipped_total: 0,
      seeded_from_beat: snap.beat ?? null, seeded_at: now, updated_at: now,
      dim: snap.dim || DIM,
      seed: vecs.map((v) => v.slice()),          // frozen reference
      protos: vecs.map((v) => v.slice()),        // working copy
    };
    this.kvPut("state", state);
    return state;
  }

  async readJson(request) {
    const text = await request.text();
    if (text.length > MAX_BODY) throw new RangeError("body too large");
    return JSON.parse(text);
  }

  async fetch(request) {
    const url = new URL(request.url);
    const path = url.pathname;

    // -- internal: the organism's snapshot store ------------------------------
    // NOT publicly routed (worker.js only forwards /api/grid/*). It lives here
    // because KV's 1,000-writes/day free quota killed the organism's own
    // 10-minute push for 4.7 hours on 2026-08-24 — the front page said
    // "snapshot stale" while eran1 had moved 3.7M beats ahead. SQLite in a DO
    // has no such meter. eran.js reads and writes it through this route.
    if (path === "/do/brain") {
      if (request.method === "PUT") {
        const text = await request.text();
        if (text.length > 16 * 1024 * 1024) {
          return new Response("too large", { status: 413 });
        }
        this.sql.exec(
          "INSERT INTO kv (k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v",
          "organism", text);
        // RESEED CYCLE (2026-08-25, the deadlock Iddo heard as "לא עובדת טוב"):
        // the student had converged to the EDGE of the COS_GATE cone around a
        // seed frozen at beat 65.5M while the organism lived on to 70.7M —
        // measured that night: an honest browser round posted 200 and got
        // gated:10 moved:0, every time, forever. A cone around a corpse
        // strangles the living. So each time the organism's pushed snapshot
        // has moved RESEED_BEATS past the student's seed, the student starts
        // a fresh cycle FROM that snapshot: seed AND protos re-anchored to
        // where ERAN actually is. version stays monotonic so in-flight
        // rounds go "stale" and re-pull instead of merging across cycles.
        try {
          const snap = JSON.parse(text)?.snapshot;
          const state = this.kvGet("state");
          if (state && snap && Array.isArray(snap.protos) && snap.protos.length &&
              Number.isFinite(snap.beat) && Number.isFinite(state.seeded_from_beat) &&
              snap.beat - state.seeded_from_beat >= RESEED_BEATS) {
            const vecs = snap.protos.map((p) => p.vec.map(ROUND6));
            state.seed = vecs.map((v) => v.slice());
            state.protos = vecs.map((v) => v.slice());
            state.dim = snap.dim || state.dim;
            state.seeded_from_beat = snap.beat;
            state.seeded_at = Math.floor(Date.now() / 1000);
            state.updated_at = state.seeded_at;
            state.version += 1;
            this.kvPut("state", state);
          }
        } catch { /* a malformed snapshot must never break the organism's push */ }
        return new Response("ok");
      }
      const row = this.sql.exec("SELECT v FROM kv WHERE k = 'organism'").toArray();
      return new Response(row.length ? row[0].v : "null",
        { headers: { "Content-Type": "application/json" } });
    }

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS });
    }

    // -- one click: become a member ------------------------------------------
    if (path === "/api/grid/register" && request.method === "POST") {
      if (this.memberCount() >= MAX_MEMBERS) {
        return json({ ok: false, error: "grid is full tonight (hobby-scale cap); try later" }, 503);
      }
      let body = {};
      try { body = await this.readJson(request); } catch { body = {}; }
      const member_id = "m-" + crypto.randomUUID().slice(0, 13);
      const member_secret = crypto.randomUUID() + crypto.randomUUID().slice(0, 8);
      const provider = String(body.provider || "web").slice(0, 24);
      const now = Date.now();
      this.kvPut("member:" + member_id, {
        joined_at: Math.floor(now / 1000),
        provider, rounds: 0,
        last_seen: Math.floor(now / 1000),
        last_delta_ms: 0,
        secret_hash: await sha256hex(member_secret),
      });
      let state = this.kvGet("state");
      if (!state) state = await this.seedFromOrganism();
      return json({
        ok: true, member_id, member_secret,
        version: state ? state.version : null,
        note: state
          ? "welcome. keep member_secret — it signs your deltas. you train ERAN's cloud STUDENT brain; the organism on eran1 stays sovereign."
          : "welcome. no student brain yet (the organism has not pushed a snapshot); tasks will say so.",
      });
    }

    // -- pull work: student brain + a real-voice shard (members only) ---------
    if ((path === "/api/grid/task" || path === "/api/grid/global") && request.method === "GET") {
      const member = url.searchParams.get("member") || url.searchParams.get("node") || "";
      if (!member) return json({ ok: false, error: "member (or node) query param required" }, 400);
      const mrow = this.kvGet("member:" + member);
      if (!mrow) return json({ ok: false, error: "unknown member — register first at /api/grid/register" }, 403);

      let state = this.kvGet("state");
      if (!state) state = await this.seedFromOrganism();
      if (!state) return json({ ok: false, error: "no student brain: the organism has not pushed a snapshot yet" }, 503);
      const idx = this.kvGet("shards") || { list: [] };
      if (!idx.list.length) {
        return json({ ok: false, error: "no shards yet: training data must be curated real human voice, pushed with the token" }, 503);
      }
      const pick = idx.list[(fnv(member) + state.version) % idx.list.length];
      const shard = this.kvGet("shard:" + pick.id);
      if (!shard) return json({ ok: false, error: "shard index points at a missing shard" }, 500);
      return json({
        ok: true, version: state.version, dim: state.dim,
        protos: state.protos, shard_id: shard.id,
        shard: { id: shard.id, source: shard.source || "", vecs: shard.vecs },
        H: H_DEFAULT, eta: ETA_INNER,
        rule: "for each step: x = shard.vecs[perm[t]]; winner = argmax dot(proto, x); winner = l2normalize((1-eta)*winner + eta*x). delta[i] = local[i] - global[i].",
      });
    }

    // -- push a delta: the outer step (members only, signed, rate-limited) ----
    if (path === "/api/grid/delta" && request.method === "POST") {
      let body;
      try { body = await this.readJson(request); } catch (e) {
        return json({ ok: false, error: "bad body: " + e.message }, 400);
      }
      const member = String(body.member_id || body.node_id || "");
      const secret = String(body.member_secret || "");
      if (!member) return json({ ok: false, error: "member_id required" }, 400);
      const mrow = this.kvGet("member:" + member);
      if (!mrow) return json({ ok: false, error: "unknown member — register first" }, 403);
      if (!secret || (await sha256hex(secret)) !== mrow.secret_hash) {
        return json({ ok: false, error: "bad member_secret" }, 403);
      }
      const now = Date.now();
      if (now - (mrow.last_delta_ms || 0) < MIN_DELTA_GAP_MS) {
        return json({ ok: true, accepted: false, reason: "too_fast",
          retry_after_ms: MIN_DELTA_GAP_MS - (now - mrow.last_delta_ms) }, 429);
      }

      const deltas = body.deltas || (body.delta && body.delta.deltas);
      if (!Array.isArray(deltas) || !deltas.length) {
        return json({ ok: false, accepted: false, error: "deltas array required" }, 400);
      }

      const state = this.kvGet("state");
      if (!state) return json({ ok: false, error: "no student brain yet" }, 503);
      // Backfill a seed for any pre-hardening state so the gate has a reference.
      if (!Array.isArray(state.seed)) state.seed = state.protos.map((v) => v.slice());
      if (deltas.length > state.protos.length) {
        return json({ ok: false, accepted: false, error: "more deltas than prototypes" }, 400);
      }
      if (Number(body.base_version) !== state.version) {
        return json({ ok: true, accepted: false, reason: "stale",
          base_version: Number(body.base_version), new_version: state.version,
          note: "pull a fresh task and go again" });
      }

      let moved = 0, gated = 0, clipped = 0;
      const seen = new Set();                       // de-dup indices IN this request
      for (const d of deltas) {
        const i = d.i;
        if (!Number.isInteger(i) || i < 0 || i >= state.protos.length) { gated++; continue; }
        if (seen.has(i)) { gated++; continue; }     // no compounding one index
        seen.add(i);
        const dv = d.dv;
        if (!finiteVec(dv, state.dim)) { gated++; continue; }
        const n = l2norm(dv);
        if (n === 0) continue;
        if (n > MAX_DELTA_NORM) clipped++;
        const scale = (n > MAX_DELTA_NORM ? MAX_DELTA_NORM / n : 1) * OUTER_LR;
        const p = state.protos[i];
        const seed = state.seed[i];
        const cand = new Array(state.dim);
        for (let k = 0; k < state.dim; k++) cand[k] = p[k] + dv[k] * scale;
        const cn = l2norm(cand);
        if (cn === 0) { gated++; continue; }
        // Gate against the FROZEN SEED, not against p: a hard cone around where
        // ERAN put this prototype, unbeatable by any number of small merges.
        let cos = 0;
        for (let k = 0; k < state.dim; k++) cos += (cand[k] / cn) * seed[k];
        if (cos < COS_GATE) { gated++; continue; }
        for (let k = 0; k < state.dim; k++) p[k] = ROUND6(cand[k] / cn);
        moved++;
      }

      // Version advances ONLY when work landed — an all-gated push cannot freeze
      // honest volunteers by making their in-flight rounds stale.
      if (moved > 0) {
        state.version += 1;
        state.rounds_merged += 1;
      }
      state.gated_total = (state.gated_total || 0) + gated;
      state.clipped_total = (state.clipped_total || 0) + clipped;
      state.updated_at = Math.floor(now / 1000);
      this.kvPut("state", state);

      mrow.rounds += 1;
      mrow.last_seen = Math.floor(now / 1000);
      mrow.last_delta_ms = now;
      this.kvPut("member:" + member, mrow);

      return json({ ok: true, accepted: moved > 0, new_version: state.version, moved, gated, clipped });
    }

    // -- heartbeat -------------------------------------------------------------
    if (path === "/api/grid/heartbeat" && request.method === "POST") {
      let body = {};
      try { body = await this.readJson(request); } catch { body = {}; }
      const member = String(body.member_id || body.node_id || "");
      if (member) {
        const m = this.kvGet("member:" + member);
        if (m) { m.last_seen = Math.floor(Date.now() / 1000); this.kvPut("member:" + member, m); }
      }
      return json({ ok: true });
    }

    // -- status (cached, no member scan) --------------------------------------
    if (path === "/api/grid/status" && request.method === "GET") {
      const state = this.kvGet("state");
      const idx = this.kvGet("shards") || { list: [] };
      return json({
        ok: true,
        student: state ? {
          version: state.version, rounds_merged: state.rounds_merged,
          gated_total: state.gated_total || 0, clipped_total: state.clipped_total || 0,
          n_protos: state.protos.length, dim: state.dim,
          seeded_from_beat: state.seeded_from_beat, updated_at: state.updated_at,
        } : null,
        n_members: this.memberCount(),
        n_shards: idx.list.length,
        shards: idx.list.map((s) => ({ id: s.id, n: s.n, source: s.source })),
        truth: "the student is a proposal; the organism on eran1 is the only ERAN",
      }, 200, { "Cache-Control": `public, max-age=${STATUS_CACHE_S}` });
    }

    // -- the student snapshot, for the fleet to pull ---------------------------
    if (path === "/api/grid/brain.json" && request.method === "GET") {
      const state = this.kvGet("state");
      if (!state) return json({ ok: false, error: "no student brain yet" }, 503);
      const out = {
        ok: true, schema: "eran-grid-student-v1",
        version: state.version, rounds_merged: state.rounds_merged,
        seeded_from_beat: state.seeded_from_beat, dim: state.dim,
        n_protos: state.protos.length, updated_at: state.updated_at,
      };
      if (url.searchParams.get("vectors") === "1") out.protos = state.protos;
      return json(out);
    }

    // -- curated shard push (token) --------------------------------------------
    if (path === "/api/grid/shard" && request.method === "POST") {
      if (!this.authorised(request)) return json({ ok: false, error: "unauthorized" }, 401);
      let body;
      try { body = await this.readJson(request); } catch (e) {
        return json({ ok: false, error: "bad body: " + e.message }, 400);
      }
      const id = String(body.id || "").replace(/[^a-zA-Z0-9_-]/g, "").slice(0, 40);
      if (!id) return json({ ok: false, error: "shard id required" }, 400);
      const vecs = body.vecs;
      if (!Array.isArray(vecs) || !vecs.length || vecs.length > MAX_SHARD_VECS) {
        return json({ ok: false, error: `vecs must be 1..${MAX_SHARD_VECS} vectors` }, 400);
      }
      for (const v of vecs) {
        if (!finiteVec(v, DIM)) return json({ ok: false, error: "every vec must be 192 finite floats" }, 400);
      }
      const source = String(body.source || "").slice(0, 200);
      this.kvPut("shard:" + id, {
        id, source, pushed_at: Math.floor(Date.now() / 1000),
        vecs: vecs.map((v) => v.map(ROUND6)),
      });
      const idx = this.kvGet("shards") || { list: [] };
      const entry = { id, n: vecs.length, source };
      const at = idx.list.findIndex((s) => s.id === id);
      if (at >= 0) idx.list[at] = entry; else idx.list.push(entry);
      this.kvPut("shards", idx);
      return json({ ok: true, id, n: vecs.length, n_shards: idx.list.length });
    }

    // -- re-seed the student from the organism's current snapshot (token) ------
    if (path === "/api/grid/reset" && request.method === "POST") {
      if (!this.authorised(request)) return json({ ok: false, error: "unauthorized" }, 401);
      const state = await this.seedFromOrganism();
      if (!state) return json({ ok: false, error: "organism has no pushed snapshot to seed from" }, 503);
      return json({ ok: true, version: state.version, n_protos: state.protos.length,
                    seeded_from_beat: state.seeded_from_beat });
    }

    return json({ ok: false, error: "not found" }, 404);
  }
}
