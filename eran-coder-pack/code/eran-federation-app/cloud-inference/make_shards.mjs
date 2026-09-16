// make_shards.mjs — curated real-voice shards for the ER"N-GRID coordinator.
//
// DATA LAW: input must be REAL human voice that is ALREADY PUBLIC. First real
// use (2026-08-24): Wikimedia Commons "Hebrew pronunciation" recordings —
// thousands of single words spoken by real people, CC-licensed, attributed in
// the shard's source field. (The Cafe-Claude episode was the first candidate
// and was STOPPED by its own CONTENT-REVIEW.md: private phone call inside —
// DO NOT PUBLISH. It stays private, and so do its embeddings.)
// Synthetic audio is banned as training data — the 08-23 scar measured it
// transferring to a real mouth at chance.
//
//   node make_shards.mjs <wav-file-or-dir> <shard-prefix> "<source label>" [--push]
//
// A single wav is cut into 1.2 s windows (1.0 s hop). A DIRECTORY is treated
// as one-utterance-per-file (Commons pronunciation words are exactly that).
// Every voiced utterance goes through the frozen cochlea (ear.js — the SAME
// code the cloud ear runs) into shards of up to 200 vectors. --push sends
// them to the coordinator with the Bearer token from ../panel/.fed_push_token.

import { readFileSync, writeFileSync, readdirSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { decodeWav, utteranceFromSamples, TooShort, SAMPLE_RATE } from "./ear.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const TOKEN_PATH = join(HERE, "..", "panel", ".fed_push_token");
const COORD = "https://federation.iddoperez.ai";

const WIN_S = 1.2, HOP_S = 1.0;
const QUIET_PEAK = 0.02;          // peak below this = silence/noise floor
const MAX_PER_SHARD = 200;
const MAX_TOTAL = 400;

const [, , input, prefix, sourceLabel, ...flags] = process.argv;
if (!input || !prefix || !sourceLabel) {
  console.error('usage: node make_shards.mjs <wav-file-or-dir> <shard-prefix> "<source label>" [--push]');
  process.exit(2);
}

function loadWav(path) {
  const buf = readFileSync(path);
  return decodeWav(buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength));
}

function voicedVec(chunk) {
  let peak = 0;
  for (let i = 0; i < chunk.length; i++) { const a = Math.abs(chunk[i]); if (a > peak) peak = a; }
  if (peak < QUIET_PEAK) return null;
  try {
    const v = utteranceFromSamples(chunk);
    return Array.from(v, (x) => Math.round(x * 1e6) / 1e6);
  } catch (e) {
    if (e instanceof TooShort) return null;
    throw e;
  }
}

const vecs = [];
let skipped = 0;
if (statSync(input).isDirectory()) {
  const files = readdirSync(input).filter((f) => f.toLowerCase().endsWith(".wav"));
  for (const f of files) {
    try {
      const v = voicedVec(loadWav(join(input, f)));
      if (v) vecs.push(v); else skipped++;
    } catch { skipped++; }
  }
  console.log(`${files.length} files -> ${vecs.length} vectors (${skipped} skipped)`);
} else {
  const samples = loadWav(input);
  console.log(`decoded ${samples.length} samples (${(samples.length / SAMPLE_RATE).toFixed(1)} s)`);
  const win = Math.round(WIN_S * SAMPLE_RATE);
  const hop = Math.round(HOP_S * SAMPLE_RATE);
  for (let at = 0; at + win <= samples.length; at += hop) {
    const v = voicedVec(samples.subarray(at, at + win));
    if (v) vecs.push(v); else skipped++;
  }
  console.log(`${vecs.length} voiced vectors (${skipped} chunks skipped)`);
}

// Spread the keep-set across the whole input, deterministically.
let keep = vecs;
if (vecs.length > MAX_TOTAL) {
  keep = [];
  for (let i = 0; i < MAX_TOTAL; i++) keep.push(vecs[Math.floor((i * vecs.length) / MAX_TOTAL)]);
}

const shards = [];
for (let i = 0; i < keep.length; i += MAX_PER_SHARD) {
  const id = `${prefix}-${String(shards.length + 1).padStart(2, "0")}`;
  const shard = { id, source: sourceLabel, vecs: keep.slice(i, i + MAX_PER_SHARD) };
  const out = join(HERE, `shard-${id}.json`);
  writeFileSync(out, JSON.stringify(shard));
  console.log(`wrote ${out} (${shard.vecs.length} vecs)`);
  shards.push(shard);
}

if (flags.includes("--push")) {
  const token = readFileSync(TOKEN_PATH, "utf-8").trim();
  for (const shard of shards) {
    const res = await fetch(`${COORD}/api/grid/shard`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}`,
                 "User-Agent": "eran-grid-shard-pusher/1.0" },
      body: JSON.stringify(shard),
    });
    console.log(`push ${shard.id}: ${res.status} ${(await res.text()).slice(0, 200)}`);
  }
}
