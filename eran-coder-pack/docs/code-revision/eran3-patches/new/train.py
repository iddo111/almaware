#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Full-weight continued pretraining of Qwen3.5-4B-Base on OUR code.

Not LoRA. Every parameter is trainable. bf16 compute, fp32 master weights,
gradient checkpointing, AdamW, cosine schedule with warmup.

THE HOLD-OUT CONTRACT (the one rule that makes the baseline mean anything)
-------------------------------------------------------------------------
    int(sha1(relpath).hexdigest()[:8], 16) % 20 == 7   ->   HELD OUT

`relpath` is the forward-slash path relative to D:\\CLAUDE exactly as
`git ls-files` prints it -- that is what make_heldout.py hashed, and the
baseline (CE 0.9386 nats, ppl 2.557, top-1 78.93%) was measured on the files
it selected. If one of those files enters training, the baseline is worthless
and every "improvement" we report afterwards is a lie.

This script therefore does FOUR independent things about it, and any one of
them failing aborts the run:

  1. SELF-TEST (always on, cannot be disabled). Before touching any data it
     loads heldout.jsonl and asserts that is_heldout() classifies all 400 of
     its paths as held out. That proves this file's filter is the same rule
     that produced the baseline.
  2. FILTER. Every corpus row whose path hashes to residue 7 is dropped and
     counted, in both the domain corpus and the replay corpus.
  3. SET CHECK. After tokenising, the set of kept paths is intersected with
     the 400 held-out paths. Non-empty -> abort.
  4. CONTENT CHECK. Held-out files are often vendored (the held-out set is
     full of .codex_deps/... copies of Pillow etc.), so the SAME BYTES can
     sit at a path that is not held out. Any document whose normalised text
     sha256 matches a held-out document's is dropped too.

Written to be restarted by a watchdog at any moment: --resume auto restores
model, optimizer, scheduler, LR position, both dataloader cursors and the RNG.

Usage lives in README.md next to this file.
"""

import argparse
import contextlib
import gc
import hashlib
import json
import math
import os
import random
import shutil
import signal
import sys
import threading
import time
from fractions import Fraction

import numpy as np
import torch

# --------------------------------------------------------------------------
# Constants of the experiment. Changing any of these invalidates the baseline.
# --------------------------------------------------------------------------
REPO = "Qwen/Qwen3.5-4B-Base"
REVISION = "1001bb4d826a52d1f399e183466143f4da7b741b"
HELDOUT_MODULUS = 20
HELDOUT_RESIDUE = 7
PREPARE_FORMAT_VERSION = 3        # bump to invalidate every cached .bin

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_HELDOUT = os.path.expanduser("~/coder-base-logs/heldout.jsonl")

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_OOM = 4
EXIT_NONFINITE = 3                # watchdog: do NOT restart blindly on this
EXIT_LEAK = 5                     # hold-out contract violated
EXIT_SAVE = 6                     # CODER-11: checkpoint save failed (disk/IO).
                                  # A restart cannot make room; a human must.


# ==========================================================================
# 0. Small utilities
# ==========================================================================

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def die(code, msg):
    print("", flush=True)
    print("=" * 74, flush=True)
    print(f"FATAL ({code}): {msg}", flush=True)
    print("=" * 74, flush=True)
    sys.exit(code)


def gb(nbytes):
    return round(nbytes / 1024 ** 3, 2)


def atomic_write_json(path, obj):
    tmp = path + f".tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


# ==========================================================================
# 1. The hold-out contract
# ==========================================================================

def norm_relpath(p):
    """Canonical form of a repo-relative path, matching make_heldout.py.

    make_heldout.py hashed the raw `git ls-files` output (already forward
    slashes) and then stored `rel.replace('\\\\', '/')`. So: forward slashes,
    no leading './', no surrounding whitespace. Case is NOT touched -- sha1
    is case sensitive and git preserves case.
    """
    p = p.strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p.lstrip("/")


def is_heldout(relpath):
    h = hashlib.sha1(norm_relpath(relpath).encode("utf-8")).hexdigest()
    return int(h[:8], 16) % HELDOUT_MODULUS == HELDOUT_RESIDUE


def norm_text_for_hash(t):
    """Line-ending and trailing-whitespace insensitive normalisation.

    A vendored copy of a held-out file checked out on Windows differs from the
    held-out copy only by CRLF. Without this it would slip past the content
    check.
    """
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in t.split("\n")).strip()


def text_fingerprint(t):
    return hashlib.sha256(norm_text_for_hash(t).encode("utf-8")).hexdigest()


def load_heldout(path):
    """Returns (set_of_paths, set_of_text_fingerprints) and runs the self-test."""
    if not os.path.exists(path):
        die(EXIT_LEAK, f"hold-out set not found at {path}. Refusing to train "
                       f"without the contract. Pass --heldout-jsonl.")
    paths, prints_ = set(), set()
    bad = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            rel = norm_relpath(r["path"])
            paths.add(rel)
            prints_.add(text_fingerprint(r["text"]))
            if not is_heldout(rel):
                bad.append(rel)
    if not paths:
        die(EXIT_LEAK, f"{path} is empty -- no hold-out contract to enforce.")
    if bad:
        die(EXIT_LEAK,
            "HOLD-OUT SELF-TEST FAILED. is_heldout() does not reproduce the "
            f"rule that built {path}: {len(bad)}/{len(paths)} of its paths are "
            f"NOT classified as held out. First offenders: {bad[:5]}. "
            "The baseline cannot be compared against anything trained by this "
            "script until that is fixed.")
    log(f"hold-out self-test OK: {len(paths)} paths, all satisfy "
        f"sha1(relpath)[:8] %% {HELDOUT_MODULUS} == {HELDOUT_RESIDUE}; "
        f"{len(prints_)} distinct content fingerprints")
    return paths, prints_


# ==========================================================================
# 2. Corpus preparation: JSONL -> flat uint32 token file
# ==========================================================================
# Why pre-tokenise instead of streaming JSON at train time:
#   * O(1) resume. The dataloader position is an integer index into a memmap,
#     not "re-read and re-tokenise 4 million documents to get back to where
#     we were". A watchdog restart costs seconds, not hours.
#   * Exact reproducibility. Sequence i is a pure function of (seed, epoch, i).
#   * The hold-out filter runs once, is recorded in the .meta.json, and can be
#     audited afterwards without re-reading the corpus.

def iter_jsonl(paths):
    for p in paths:
        with open(p, "r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield p, lineno, json.loads(line)
                except json.JSONDecodeError:
                    yield p, lineno, None


def expand_corpus_arg(arg):
    """A corpus argument is a file, a directory of .jsonl, or a comma list."""
    out = []
    for part in str(arg).split(","):
        part = os.path.expanduser(part.strip())
        if not part:
            continue
        if os.path.isdir(part):
            out.extend(sorted(os.path.join(part, n) for n in os.listdir(part)
                              if n.endswith(".jsonl")))
        else:
            out.append(part)
    for p in out:
        if not os.path.exists(p):
            die(EXIT_ERROR, f"corpus file not found: {p}")
    if not out:
        die(EXIT_ERROR, f"corpus argument matched nothing: {arg}")
    return out


def row_relpath(row):
    """Corpus rows are {'text':..., 'source':...}; older tools wrote 'path'."""
    for k in ("path", "source", "relpath", "file"):
        v = row.get(k)
        if isinstance(v, str) and v.strip():
            return norm_relpath(v)
    return None


def corpus_signature(files, extra):
    h = hashlib.sha256()
    h.update(json.dumps(extra, sort_keys=True).encode())
    for p in files:
        st = os.stat(p)
        h.update(f"{os.path.abspath(p)}|{st.st_size}|{int(st.st_mtime)}".encode())
    return h.hexdigest()[:16]


def prepare_corpus(name, corpus_arg, tok, heldout_paths, heldout_prints, args,
                   require_path):
    """Tokenise a corpus to <data_dir>/<name>.bin (+ .idx.npy, .meta.json).

    Cached: if the meta's signature matches the inputs, nothing is redone.
    """
    files = expand_corpus_arg(corpus_arg)
    data_dir = args.data_dir
    os.makedirs(data_dir, exist_ok=True)
    bin_path = os.path.join(data_dir, f"{name}.bin")
    idx_path = os.path.join(data_dir, f"{name}.idx.npy")
    meta_path = os.path.join(data_dir, f"{name}.meta.json")

    sig = corpus_signature(files, {
        "v": PREPARE_FORMAT_VERSION,
        "repo": REPO, "rev": REVISION,
        "eos": int(tok.eos_token_id),
        "content_check": bool(args.content_leak_check),
        "min_doc_tokens": args.min_doc_tokens,
        "heldout": os.path.abspath(args.heldout_jsonl),
        "n_heldout": len(heldout_paths),
    })

    if os.path.exists(meta_path) and os.path.exists(bin_path):
        try:
            meta = json.load(open(meta_path, encoding="utf-8"))
            if meta.get("signature") == sig and meta.get("ok") is True:
                log(f"[{name}] cached: {meta['n_tokens']:,} tokens, "
                    f"{meta['n_docs']:,} docs "
                    f"(dropped {meta['dropped_heldout_path']} by path, "
                    f"{meta['dropped_heldout_content']} by content)")
                return meta
        except Exception:
            pass

    log(f"[{name}] preparing from {len(files)} file(s): "
        + ", ".join(os.path.basename(f) for f in files[:4])
        + (" ..." if len(files) > 4 else ""))

    eos = int(tok.eos_token_id)
    kept_paths = set()
    n_docs = n_tokens = 0
    dropped_path = dropped_content = dropped_short = dropped_empty = 0
    dropped_nopath = bad_json = 0
    dropped_path_list = []
    per_source = {}
    buf = []
    offsets = [0]
    t0 = time.time()

    tmp_bin = bin_path + f".tmp.{os.getpid()}"
    with open(tmp_bin, "wb") as fbin:
        def flush():
            nonlocal buf
            if buf:
                np.asarray(buf, dtype=np.uint32).tofile(fbin)
                buf = []

        for fpath, lineno, row in iter_jsonl(files):
            if row is None:
                bad_json += 1
                continue
            text = row.get("text")
            if not isinstance(text, str) or not text.strip():
                dropped_empty += 1
                continue
            rel = row_relpath(row)

            # ---- hold-out filter, step 2 of 4 -------------------------
            if rel is None:
                if require_path:
                    die(EXIT_LEAK,
                        f"[{name}] {fpath}:{lineno} has no 'source'/'path' "
                        "field, so the hold-out rule cannot be applied to it. "
                        "Refusing to train on data whose provenance is "
                        "unknown. Add the field, or pass "
                        f"--{name}-require-path 0 if this corpus provably "
                        "contains nothing from D:\\CLAUDE.")
                dropped_nopath += 1
            elif is_heldout(rel):
                if args.strict:
                    die(EXIT_LEAK,
                        f"[{name}] --strict: held-out file present in the "
                        f"corpus at {fpath}:{lineno} -> {rel}")
                dropped_path += 1
                if len(dropped_path_list) < 20000:
                    dropped_path_list.append(rel)
                continue

            if args.content_leak_check and text_fingerprint(text) in heldout_prints:
                dropped_content += 1
                continue

            ids = tok(text, add_special_tokens=False).input_ids
            if len(ids) < args.min_doc_tokens:
                dropped_short += 1
                continue
            ids.append(eos)                   # document separator

            buf.extend(ids)
            n_tokens += len(ids)
            n_docs += 1
            offsets.append(n_tokens)
            if rel is not None:
                kept_paths.add(rel)
            src = row.get("bucket")
            if not src:
                src = os.path.splitext(rel)[1].lower() if rel else "(no path)"
            per_source[src] = per_source.get(src, 0) + len(ids)

            if len(buf) >= 4_000_000:
                flush()
            if n_docs % 5000 == 0 and n_docs:
                log(f"[{name}]   {n_docs:,} docs, {n_tokens:,} tokens, "
                    f"{time.time()-t0:.0f}s")
        flush()
        fbin.flush()
        os.fsync(fbin.fileno())
    os.replace(tmp_bin, bin_path)

    # ---- hold-out filter, step 3 of 4: the set check ----------------------
    leak = kept_paths & heldout_paths
    if leak:
        die(EXIT_LEAK,
            f"[{name}] HOLD-OUT LEAK: {len(leak)} held-out file(s) survived "
            f"the filter and were tokenised into {bin_path}. "
            f"Examples: {sorted(leak)[:5]}. The .bin has been written but MUST "
            "NOT be trained on -- delete it. This means is_heldout() and the "
            "hold-out set disagree, which the self-test should have caught.")

    np.asarray(offsets, dtype=np.int64).tofile(idx_path)

    meta = {
        "name": name,
        "signature": sig,
        "ok": True,
        "files": [os.path.abspath(p) for p in files],
        "bin": bin_path,
        "idx": idx_path,
        "n_docs": n_docs,
        "n_tokens": n_tokens,
        "eos_token_id": eos,
        "tokenizer": REPO,
        "revision": REVISION,
        "heldout_rule": f"int(sha1(relpath)[:8],16) %% {HELDOUT_MODULUS} == {HELDOUT_RESIDUE}",
        "heldout_jsonl": os.path.abspath(args.heldout_jsonl),
        "heldout_paths_known": len(heldout_paths),
        "dropped_heldout_path": dropped_path,
        "dropped_heldout_content": dropped_content,
        "dropped_heldout_path_sha256":
            hashlib.sha256("\n".join(sorted(dropped_path_list)).encode()).hexdigest(),
        "dropped_heldout_path_list_truncated": len(dropped_path_list) < dropped_path,
        "dropped_heldout_path_examples": sorted(dropped_path_list)[:5],
        "dropped_short": dropped_short,
        "dropped_empty": dropped_empty,
        "dropped_no_path": dropped_nopath,
        "bad_json_lines": bad_json,
        "kept_paths": len(kept_paths),
        "leak_check": "PASS (kept_paths INTERSECT heldout_paths == empty)",
        "top_extensions": dict(sorted(per_source.items(), key=lambda x: -x[1])[:15]),
        "seconds": round(time.time() - t0, 1),
    }
    atomic_write_json(meta_path, meta)
    log(f"[{name}] done: {n_docs:,} docs / {n_tokens:,} tokens in "
        f"{meta['seconds']}s | dropped: {dropped_path} held-out-by-path, "
        f"{dropped_content} held-out-by-content, {dropped_short} too-short, "
        f"{dropped_nopath} no-path, {bad_json} bad-json")
    return meta


# ==========================================================================
# 3. Deterministic sequence streams
# ==========================================================================

class TokenStream:
    """A reproducible, O(1)-seekable stream of fixed-length token sequences.

    pack_mode 'concat' (default, fast):
        Documents were written back to back with an EOS after each. A sequence
        is a contiguous seq_len window of that flat array, in a seeded random
        order. Windows therefore span document boundaries.

        CROSS-DOCUMENT ATTENTION: yes, within a window, and we do NOT prevent
        it. See README "Cross-document attention" -- with 24 of this model's
        32 layers being recurrent linear-attention (gated delta net), an
        attention mask cannot isolate documents anyway; only varlen kernels
        could, and the fla fast path is not installed on this box. EOS between
        documents is the separator, which is what Llama/GPT-3/OLMo also do.

    pack_mode 'doc' (slow, zero leakage):
        One document per sequence, truncated to seq_len, right-padded with EOS
        and label -100 on the padding. No window ever contains two documents.
    """

    def __init__(self, meta, seq_len, seed, tag, pack_mode):
        self.meta = meta
        self.seq_len = seq_len
        self.seed = seed
        self.tag = tag
        self.pack_mode = pack_mode
        self.data = np.memmap(meta["bin"], dtype=np.uint32, mode="r")
        self.eos = meta["eos_token_id"]
        if pack_mode == "concat":
            self.n_units = meta["n_tokens"] // seq_len
            self.offsets = None
        else:
            self.offsets = np.fromfile(meta["idx"], dtype=np.int64)
            self.n_units = max(0, len(self.offsets) - 1)
        if self.n_units == 0:
            die(EXIT_ERROR,
                f"corpus '{meta['name']}' yields 0 sequences at seq_len="
                f"{seq_len} ({meta['n_tokens']:,} tokens). Use a bigger corpus "
                "or a smaller --seq-len.")
        self._epoch = -1
        self._perm = None

    def _perm_for(self, epoch):
        if epoch != self._epoch:
            rng = np.random.default_rng(
                [self.seed, epoch, int.from_bytes(self.tag.encode()[:8], "little")])
            self._perm = rng.permutation(self.n_units)
            self._epoch = epoch
        return self._perm

    def get(self, i):
        """Sequence i of an infinite, deterministic stream. Returns (ids, labels)."""
        epoch, j = divmod(int(i), self.n_units)
        u = int(self._perm_for(epoch)[j])
        L = self.seq_len
        if self.pack_mode == "concat":
            ids = np.array(self.data[u * L:(u + 1) * L], dtype=np.int64)
            labels = ids.copy()
        else:
            a, b = int(self.offsets[u]), int(self.offsets[u + 1])
            chunk = np.array(self.data[a:min(b, a + L)], dtype=np.int64)
            n = len(chunk)
            ids = np.full(L, self.eos, dtype=np.int64)
            labels = np.full(L, -100, dtype=np.int64)
            ids[:n] = chunk
            labels[:n] = chunk
        return ids, labels


class MixedLoader:
    """Interleaves the domain stream and the replay stream at an EXACT ratio.

    The ratio is integer arithmetic on a Fraction, never a float comparison:
    sequence i (0-based, global) is a replay sequence iff

        ((i+1)*num) // den  >  (i*num) // den

    which makes the number of replay sequences among the first n exactly
    floor(n * num/den) -- no drift, no rounding, for any n. That pattern is
    perfectly regular, so within each optimizer step (block_size sequences)
    the flags are permuted by an RNG seeded from (seed, block index). Order
    inside the block changes; the count does not.

    Resume state is two integers: how many sequences each stream has served.
    """

    def __init__(self, domain, replay, replay_frac, block_size, seed):
        self.domain = domain
        self.replay = replay
        self.block_size = block_size
        self.seed = seed
        fr = Fraction(str(replay_frac)).limit_denominator(1_000_000)
        if not (0 <= fr <= 1):
            die(EXIT_ERROR, f"--replay must be in [0,1], got {replay_frac}")
        if fr > 0 and replay is None:
            die(EXIT_ERROR, "--replay > 0 but no --replay-corpus was given.")
        self.num, self.den = fr.numerator, fr.denominator
        self.frac = fr
        self.dom_cursor = 0
        self.rep_cursor = 0
        self.seq_index = 0            # global sequence counter

    def _flags(self, block_idx):
        s = block_idx * self.block_size
        flags = [((i + 1) * self.num) // self.den > (i * self.num) // self.den
                 for i in range(s, s + self.block_size)]
        if self.num == 0 or self.num == self.den:
            return flags
        rng = np.random.default_rng([self.seed, 0x5245504C, block_idx])
        perm = rng.permutation(self.block_size)
        return [flags[k] for k in perm]

    def block(self, block_idx):
        """Yields (ids, labels, is_replay) for one optimizer step, and advances."""
        out = []
        for is_rep in self._flags(block_idx):
            if is_rep:
                ids, lab = self.replay.get(self.rep_cursor)
                self.rep_cursor += 1
            else:
                ids, lab = self.domain.get(self.dom_cursor)
                self.dom_cursor += 1
            self.seq_index += 1
            out.append((ids, lab, is_rep))
        return out

    def seek(self, block_idx):
        """Restore cursors for an arbitrary block without touching the data."""
        n = block_idx * self.block_size
        rep = (n * self.num) // self.den
        self.rep_cursor = rep
        self.dom_cursor = n - rep
        self.seq_index = n

    def check_exact(self):
        want = (self.seq_index * self.num) // self.den
        if self.rep_cursor != want:
            die(EXIT_ERROR,
                f"replay ratio drifted: served {self.rep_cursor} replay of "
                f"{self.seq_index} sequences, exact value is {want}")
        return want


# ==========================================================================
# 4. Optimizer with fp32 master weights
# ==========================================================================

def load_optimizer_state_inplace(opt, sd):
    """Restore AdamW state WITHOUT torch's deepcopy of the whole state dict.

    `torch.optim.Optimizer.load_state_dict` begins with
    `deepcopy(state_dict)`, which materialises every moment tensor a second
    time in host RAM. For 4.2058 B parameters that is an extra 33.6 GB on top
    of the 47 GB already read from disk -- and on GB10 the CPU and the GPU
    share one 121 GB pool. That is not a theory: the first attempt at resuming
    this way was SIGKILLed by the kernel OOM killer right after
    "training steps 5 -> 6", with no traceback.

    So: hand the optimizer the param_groups with an EMPTY state (cheap), then
    fill the state one tensor at a time, dropping each source reference as we
    go. Peak extra memory is one tensor, not one model.
    """
    opt.load_state_dict({"state": {}, "param_groups": sd["param_groups"]})
    params = [p for g in opt.param_groups for p in g["params"]]
    src = sd["state"]
    for key in list(src.keys()):
        entry = src[key]
        p = params[int(key)]
        new = {}
        for k, v in entry.items():
            if not torch.is_tensor(v):
                new[k] = v
            elif k == "step":
                new[k] = v.detach().clone()          # 0-dim, stays on CPU
            else:
                new[k] = v.to(device=p.device, copy=True)
        opt.state[p] = new
        entry.clear()
        del src[key]


class MasterAdamW:
    """AdamW over fp32 master copies of bf16 parameters.

    WHY THIS EXISTS. bf16 has 8 mantissa bits: about 3 decimal digits. A weight
    of magnitude 1e-2 has a bf16 spacing of ~8e-5. At lr 1e-5 a typical Adam
    update is ~1e-5 in absolute terms -- smaller than the spacing, so
    `p += update` in bf16 rounds straight back to p and the weight NEVER MOVES.
    Pure-bf16 full-weight training at these learning rates silently does
    nothing to most of the network. fp32 masters cost memory and fix it.

    Memory (4.2058 B params): bf16 params 8.4 GB + fp32 masters 16.8 GB +
    fp32 grads 16.8 GB + fp32 Adam moments 33.7 GB + activations.
    Use --precision pure-bf16 (39.6 GB measured) only for smoke tests.
    """

    def __init__(self, named_params, lr, betas, eps, weight_decay, foreach):
        decay, no_decay = [], []
        self.pairs = []
        for name, p in named_params:
            if not p.requires_grad:
                continue
            m = p.detach().clone().float()
            m.requires_grad_(True)
            self.pairs.append((p, m))
            # No weight decay on 1-D tensors: biases, RMSNorm gains, and the
            # gated-delta-net per-head scalars. Decaying those hurts.
            (decay if p.ndim >= 2 else no_decay).append(m)
        groups = [{"params": decay, "weight_decay": weight_decay},
                  {"params": no_decay, "weight_decay": 0.0}]
        self.opt = torch.optim.AdamW(groups, lr=lr, betas=betas, eps=eps,
                                     foreach=foreach, fused=False)
        self.n_decay, self.n_no_decay = len(decay), len(no_decay)

    def master_params(self):
        return [m for _, m in self.pairs]

    def sync_grads(self):
        """bf16 grad -> fp32 master grad, freeing each bf16 grad as we go.

        Freeing incrementally keeps the transient peak near max(bf16, fp32)
        grads rather than their sum.
        """
        missing = 0
        for p, m in self.pairs:
            if p.grad is None:
                m.grad = None
                missing += 1
                continue
            if m.grad is None:
                m.grad = p.grad.to(torch.float32)
            else:
                m.grad.copy_(p.grad)
            p.grad = None
        return missing

    def step(self):
        self.opt.step()

    def zero_grad(self):
        self.opt.zero_grad(set_to_none=True)

    def copy_back(self):
        with torch.no_grad():
            for p, m in self.pairs:
                p.data.copy_(m.data)

    def state_dict(self):
        # Left on-device on purpose: torch.save streams one storage at a time,
        # so peak host RAM stays small. Moving 16.8 GB of masters to CPU first
        # would double the footprint for nothing.
        return {"opt": self.opt.state_dict(),
                "master": [m.detach() for _, m in self.pairs]}

    def load_state_dict(self, sd):
        with torch.no_grad():
            for (p, m), saved in zip(self.pairs, sd["master"]):
                m.data.copy_(saved)      # copy_ crosses cpu->cuda by itself
                p.data.copy_(m.data)
        sd["master"] = None              # drop the references before the moments
        load_optimizer_state_inplace(self.opt, sd["opt"])


class PlainAdamW:
    """Pure-bf16 fallback: AdamW straight on the bf16 parameters.

    This is the configuration the smoke test measured (39.57 GB peak). It is
    here so the memory number stays reproducible and so a smoke run is cheap.
    See MasterAdamW's docstring for why it is a bad idea for a real run.
    """

    def __init__(self, named_params, lr, betas, eps, weight_decay, foreach):
        decay, no_decay = [], []
        self.params = []
        for name, p in named_params:
            if not p.requires_grad:
                continue
            self.params.append(p)
            (decay if p.ndim >= 2 else no_decay).append(p)
        groups = [{"params": decay, "weight_decay": weight_decay},
                  {"params": no_decay, "weight_decay": 0.0}]
        self.opt = torch.optim.AdamW(groups, lr=lr, betas=betas, eps=eps,
                                     foreach=foreach, fused=False)
        self.n_decay, self.n_no_decay = len(decay), len(no_decay)

    def master_params(self):
        return self.params

    def sync_grads(self):
        return sum(1 for p in self.params if p.grad is None)

    def step(self):
        self.opt.step()

    def zero_grad(self):
        self.opt.zero_grad(set_to_none=True)

    def copy_back(self):
        pass

    def state_dict(self):
        return {"opt": self.opt.state_dict(), "master": None}

    def load_state_dict(self, sd):
        load_optimizer_state_inplace(self.opt, sd["opt"])


def grad_global_norm_and_clip_(params, clip):
    """Global L2 norm computed in fp32, then in-place rescale. Returns pre-clip norm.

    torch.nn.utils.clip_grad_norm_ accumulates in the parameter dtype; on a
    bf16 model that sum over 4.2e9 elements loses most of its significance.
    vector_norm(..., dtype=float32) accumulates in fp32 without materialising
    an fp32 copy of the whole gradient.
    """
    total = None
    for p in params:
        if p.grad is None:
            continue
        n = torch.linalg.vector_norm(p.grad, 2, dtype=torch.float32)
        total = n * n if total is None else total + n * n
    if total is None:
        return 0.0
    norm = total.sqrt()
    nf = float(norm)
    if clip > 0 and math.isfinite(nf) and nf > clip:
        scale = clip / (nf + 1e-6)
        for p in params:
            if p.grad is not None:
                p.grad.mul_(scale)
    return nf


# ==========================================================================
# 5. Checkpointing
# ==========================================================================

class Heartbeat:
    """Keeps status.json fresh while a long blocking operation runs.

    A `master-fp32` checkpoint is ~50 GB and takes minutes -- longer than that
    if something else on the box is hammering the disk. watchdog.py declares a
    live process HUNG when status.json goes stale (STALE_SECONDS = 15 min) and
    SIGKILLs it, which would kill the trainer in the middle of writing a
    checkpoint, forever. This thread rewrites status.json with a fresh
    timestamp every `period` seconds until the save finishes, so a slow
    checkpoint can never be mistaken for a hang.
    """

    def __init__(self, path, base, period=30.0):
        self.path, self.base, self.period = path, dict(base), period
        self._stop = threading.Event()
        self._t = None

    def _run(self):
        t0 = time.time()
        while not self._stop.wait(self.period):
            s = dict(self.base)
            s["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            s["unix"] = round(time.time(), 1)
            s["checkpoint_elapsed_s"] = round(time.time() - t0, 1)
            try:
                atomic_write_json(self.path, s)
            except Exception:
                pass

    def __enter__(self):
        atomic_write_json(self.path, self.base)
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        if self._t:
            self._t.join(timeout=2.0)
        return False


CKPT_REQUIRED = ("COMPLETE", "train_state.json", "optim.pt", "rng.pt")


def ckpt_missing(d):
    """Which required files a checkpoint directory lacks.

    COMPLETE alone is not proof: a directory can be swept, truncated, or
    partially deleted by something else on a shared box between the moment
    resume picks it and the moment it reads it. (That happened during
    development -- another agent removed the directory mid-test and the run
    died on a raw FileNotFoundError.) So validate before trusting it, and let
    --resume auto fall back to an older checkpoint instead of crashing.
    """
    missing = [n for n in CKPT_REQUIRED if not os.path.exists(os.path.join(d, n))]
    if not os.path.exists(os.path.join(d, "optim.pt")):
        return missing
    try:
        state = json.load(open(os.path.join(d, "train_state.json"), encoding="utf-8"))
        if state.get("precision") != "master-fp32" and                 not os.path.exists(os.path.join(d, "weights.pt")):
            missing.append("weights.pt")
    except Exception:
        missing.append("train_state.json(unreadable)")
    return missing


def ckpt_dirs(root, verbose=False):
    if not os.path.isdir(root):
        return []
    out = []
    for n in sorted(os.listdir(root)):
        if not n.startswith("step_"):
            continue
        d = os.path.join(root, n)
        try:
            step = int(n[5:])
        except ValueError:
            continue
        miss = ckpt_missing(d)
        if miss:
            if verbose:
                log(f"  ignoring {d}: incomplete, missing {miss}")
            continue
        out.append((step, d))
    return sorted(out)


def should_save_periodic(done, save_every, last_saved_step):
    """The periodic save-every-N decision, as one testable expression."""
    return save_every > 0 and done % save_every == 0 and done != last_saved_step


def should_save_on_stop(done, last_saved_step):
    """CODER-07: a SIGTERM landing ON a save-every step used to write the SAME
    47 GB checkpoint twice -- once for `done % save_every == 0` and again for the
    stop flag a few lines below. Measured 2026-09-06 01:25:09 and 01:32:04: two
    identical writes of ckpt2/step_00000020, 365.6 s + 415.0 s = 13 minutes of a
    900 s TimeoutStopSec spent producing a file that already existed. The stop
    still writes a checkpoint whenever the step has not just been saved.
    """
    return done != last_saved_step


def tmp_dirs_to_sweep(entries, max_age_s=3600, now=None):
    """Names of ORPHANED checkpoint temp dirs. entries = [(name, mtime), ...].

    CODER-11: save_checkpoint writes to `.tmp_step_NNNNNNNN.<pid>` and renames on
    success, and the only cleanup path is `if os.path.exists(tmp)` inside the same
    process -- which matches only a tmp dir carrying that process's OWN pid. After
    a crash or a SIGKILL the orphan (up to 47 GB) is never swept by anyone, on a
    disk that is already 84% full. Sweep at startup: anything older than max_age_s
    cannot belong to a save this process is about to do.
    """
    now = time.time() if now is None else now
    out = []
    for name, mtime in entries:
        if not name.startswith(".tmp_step_"):
            continue
        if now - mtime > max_age_s:
            out.append(name)
    return sorted(out)


def sweep_orphan_tmp(root, max_age_s=3600):
    """Delete orphaned .tmp_step_* dirs under root. Returns the names removed."""
    try:
        entries = [(n, os.path.getmtime(os.path.join(root, n)))
                   for n in os.listdir(root)]
    except OSError:
        return []
    removed = []
    for name in tmp_dirs_to_sweep(entries, max_age_s):
        try:
            shutil.rmtree(os.path.join(root, name), ignore_errors=True)
            removed.append(name)
        except OSError:
            pass
    return removed


CONFIG_DRIFT_KEYS = ("lr", "warmup", "max_steps", "min_lr_ratio", "weight_decay",
                     "clip", "replay", "corpus", "replay_corpus", "seed",
                     "grad_accum", "micro_batch")


def config_drift(prev_args, cur_args, keys=CONFIG_DRIFT_KEYS):
    """Settings that changed between the checkpoint and this launch.

    Returns [(key, old, new), ...].

    CODER-12: on resume only precision, seq_len and block_size are compared. lr,
    warmup, max_steps, weight_decay, clip and even the CORPUS PATHS are re-read
    from train.config.json on every start -- and the watchdog restarts this run
    with a fixed command line, so a config edit between two restarts silently
    reshapes the cosine schedule or swaps the food, with nothing but the boot-time
    config echo in train.out as a trace. The config WAS edited mid-life once
    (2026-09-05 14:36: grad-accum 8 -> 128, lr 1e-5 -> 4e-5, max-steps 8000 ->
    1600) -- correctly that time, with a fresh ckpt-dir, but by discipline only.
    """
    prev_args = prev_args or {}
    out = []
    for k in keys:
        if k not in prev_args:
            continue                      # older checkpoint did not record it
        old = prev_args.get(k)
        new = getattr(cur_args, k, None) if not isinstance(cur_args, dict) \
            else cur_args.get(k)
        if isinstance(old, float) or isinstance(new, float):
            try:
                if abs(float(old) - float(new)) <= 1e-12:
                    continue
            except (TypeError, ValueError):
                pass
        if old != new:
            out.append((k, old, new))
    return out


def prune_export_dirs(root, keep):
    """CODER-04: keep only the newest `keep` HF exports. Returns names removed."""
    try:
        names = sorted(n for n in os.listdir(root) if n.startswith("step_"))
    except OSError:
        return []
    if keep <= 0 or len(names) <= keep:
        return []
    removed = []
    for n in names[:len(names) - keep]:
        shutil.rmtree(os.path.join(root, n), ignore_errors=True)
        removed.append(n)
    return removed


def save_checkpoint(root, step, model, optim, sched, loader, args, extra,
                    status_base=None):
    os.makedirs(root, exist_ok=True)
    tmp = os.path.join(root, f".tmp_step_{step:08d}.{os.getpid()}")
    final = os.path.join(root, f"step_{step:08d}")
    if os.path.exists(tmp):
        shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    t0 = time.time()

    hb = (Heartbeat(args.status_path, status_base) if status_base
          else contextlib.nullcontext())
    with hb:
        # In master-fp32 mode the fp32 masters ARE the weights; the bf16 model
        # is a cast of them, so saving the bf16 copy too would waste 8.4 GB per
        # checkpoint for nothing.
        osd = optim.state_dict()
        if osd["master"] is None:
            torch.save({k: v.detach().cpu() for k, v in model.state_dict().items()},
                       os.path.join(tmp, "weights.pt"))
        # The scheduler rides in optim.pt rather than train_state.json: its
        # state_dict contains lr_lambdas entries that are not guaranteed to be
        # JSON-serialisable across torch versions.
        osd["sched"] = sched.state_dict()
        torch.save(osd, os.path.join(tmp, "optim.pt"))
        torch.save({
            "torch": torch.get_rng_state(),
            "cuda": torch.cuda.get_rng_state_all(),
            "python": random.getstate(),
            "numpy": np.random.get_state(),
        }, os.path.join(tmp, "rng.pt"))

    state = {
        "step": step,
        "precision": args.precision,
        "dom_cursor": loader.dom_cursor,
        "rep_cursor": loader.rep_cursor,
        "seq_index": loader.seq_index,
        "replay_num": loader.num, "replay_den": loader.den,
        "block_size": loader.block_size,
        "seq_len": args.seq_len,
        "seed": args.seed,
        "model": REPO, "revision": REVISION,
        "args": {k: (v if isinstance(v, (int, float, str, bool, type(None))) else str(v))
                 for k, v in vars(args).items()},
    }
    state.update(extra)
    with open(os.path.join(tmp, "train_state.json"), "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    with open(os.path.join(tmp, "COMPLETE"), "w") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%S") + "\n")

    if os.path.exists(final):
        shutil.rmtree(final, ignore_errors=True)
    os.rename(tmp, final)          # <- the atomic commit
    size = sum(os.path.getsize(os.path.join(final, n)) for n in os.listdir(final))
    log(f"checkpoint step {step} -> {final}  ({gb(size)} GB, {time.time()-t0:.1f}s)")

    keep = args.keep_ckpt
    if keep > 0:
        for s, d in ckpt_dirs(root)[:-keep]:
            shutil.rmtree(d, ignore_errors=True)
            log(f"  pruned old checkpoint step {s}")
    return final


def load_ckpt_file(path, weights_only=False):
    """torch.load with mmap where possible.

    A master-fp32 checkpoint is ~47 GB. Loading it the ordinary way
    materialises all of that in anonymous host memory on top of the ~84 GB the
    CUDA allocator already reserves -- and on GB10 the GPU and the CPU share
    one 121 GB pool. The first resume measured 118/121 GB used. mmap keeps the
    tensors as file-backed (reclaimable) page cache instead, so the peak stays
    bounded. Falls back to a plain load if the file predates zipfile
    serialisation.
    """
    try:
        return torch.load(path, map_location="cpu", mmap=True,
                          weights_only=weights_only)
    except Exception as e:
        log(f"  (mmap load unavailable for {os.path.basename(path)}: "
            f"{type(e).__name__}; falling back to a full read)")
        return torch.load(path, map_location="cpu", weights_only=weights_only)


def load_checkpoint(path, model, optim, sched, loader, args):
    log(f"resuming from {path}")
    miss = ckpt_missing(path)
    if miss:
        die(EXIT_ERROR,
            f"checkpoint {path} lost files between selection and load: {miss}. "
            "Something else on this box is deleting checkpoints. Re-run to fall "
            "back to an older one.")
    state = json.load(open(os.path.join(path, "train_state.json"), encoding="utf-8"))
    if state.get("precision") != args.precision:
        die(EXIT_ERROR, f"checkpoint was written with --precision "
                        f"{state.get('precision')}, you asked for {args.precision}.")
    if state.get("seq_len") != args.seq_len or state.get("block_size") != loader.block_size:
        die(EXIT_ERROR,
            "checkpoint geometry differs from the current flags "
            f"(ckpt seq_len={state.get('seq_len')} block={state.get('block_size')} vs "
            f"now seq_len={args.seq_len} block={loader.block_size}). Resuming would "
            "silently change what a 'step' means and corrupt tokens_seen.")

    # CODER-11: an orphaned .tmp_step_* from a killed save can hold 47 GB forever.
    swept = sweep_orphan_tmp(os.path.dirname(os.path.abspath(path)))
    if swept:
        log(f"swept {len(swept)} orphaned checkpoint temp dir(s): {swept}")

    # CODER-12: the hyperparameters and the corpus are NOT part of the geometry
    # check above, so they used to change on a resume with no complaint at all.
    drift = config_drift(state.get("args"), args)
    if drift:
        lines = "; ".join(f"{k}: {o!r} -> {n!r}" for k, o, n in drift)
        if getattr(args, "accept_config_change", False):
            log(f"CONFIG CHANGED since the checkpoint (accepted): {lines}")
        else:
            die(EXIT_ERROR,
                "CONFIG DRIFT on resume: " + lines + ".\n"
                "This resume would continue one run under another run's settings "
                "-- a different cosine horizon, or different food -- with nothing "
                "in the checkpoint to show it later. Either restore "
                "train.config.json, or start a NEW --ckpt-dir, or pass "
                "--accept-config-change to say you meant it.")

    osd = load_ckpt_file(os.path.join(path, "optim.pt"))
    if osd["master"] is None:
        sd = load_ckpt_file(os.path.join(path, "weights.pt"), weights_only=True)
        model.load_state_dict(sd)
        del sd
        gc.collect()
    sched.load_state_dict(osd.pop("sched"))
    optim.load_state_dict(osd)     # in master mode this also refills the bf16 model
    del osd
    gc.collect()

    rng = load_ckpt_file(os.path.join(path, "rng.pt"))
    torch.set_rng_state(rng["torch"])
    try:
        torch.cuda.set_rng_state_all(rng["cuda"])
    except Exception as e:
        log(f"  (cuda RNG not restored: {e})")
    random.setstate(rng["python"])
    np.random.set_state(rng["numpy"])

    loader.dom_cursor = state["dom_cursor"]
    loader.rep_cursor = state["rep_cursor"]
    loader.seq_index = state["seq_index"]
    log(f"  resumed at step {state['step']}, tokens_seen "
        f"{state.get('tokens_seen', 0):,}, cursors dom={loader.dom_cursor} "
        f"rep={loader.rep_cursor}")
    return state


# ==========================================================================
# 6. Main
# ==========================================================================

def build_args():
    p = argparse.ArgumentParser(
        description="Full-weight continued pretraining of Qwen3.5-4B-Base.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    g = p.add_argument_group("data")
    g.add_argument("--corpus", default=os.path.join(HERE, "corpus", "code.jsonl"),
                   help="domain JSONL {'text','source'}; file, dir of .jsonl, or comma list")
    g.add_argument("--replay-corpus", default=None,
                   help="general/original-distribution JSONL, same schema")
    g.add_argument("--replay", default="0.10",
                   help="exact fraction of sequences drawn from --replay-corpus")
    g.add_argument("--heldout-jsonl", default=DEFAULT_HELDOUT,
                   help="the hold-out contract; the run aborts without it")
    g.add_argument("--data-dir", default=os.path.join(HERE, "data"),
                   help="where the tokenised .bin caches live")
    g.add_argument("--content-leak-check", type=int, default=1,
                   help="also drop docs whose text matches a held-out doc (vendored copies)")
    g.add_argument("--corpus-require-path", type=int, default=1,
                   help="abort if a domain row has no source/path (cannot apply the rule)")
    g.add_argument("--replay-require-path", type=int, default=0,
                   help="same for the replay corpus; off because general data has no repo path")
    g.add_argument("--min-doc-tokens", type=int, default=32)
    g.add_argument("--pack-mode", choices=["concat", "doc"], default="concat")
    g.add_argument("--strict", action="store_true",
                   help="abort instead of dropping when a held-out path is seen")

    g = p.add_argument_group("model / optimisation")
    g.add_argument("--seq-len", type=int, default=4096)
    g.add_argument("--micro-batch", type=int, default=1)
    g.add_argument("--grad-accum", type=int, default=8,
                   help="optimizer step = micro_batch * grad_accum sequences")
    g.add_argument("--lr", type=float, default=1e-5)
    g.add_argument("--min-lr-ratio", type=float, default=0.1)
    g.add_argument("--warmup", type=int, default=100)
    g.add_argument("--max-steps", type=int, default=20000)
    g.add_argument("--weight-decay", type=float, default=0.1)
    g.add_argument("--beta1", type=float, default=0.9)
    g.add_argument("--beta2", type=float, default=0.95)
    g.add_argument("--eps", type=float, default=1e-8)
    # 1.0 is the standard for continued pretraining (GPT-3, Llama, OLMo all use
    # it). The smoke measured grad_global_norm 46.6, but that was on a batch of
    # UNIFORM RANDOM TOKEN IDS -- maximally out of distribution, loss 13.2 nats
    # against a real-data loss of 0.94. It is an upper bound, not a target. On
    # real code the first steps should land far below it; status.json logs the
    # PRE-clip norm every step, so if it sits above 1.0 persistently we will see
    # it and can retune rather than guess now.
    g.add_argument("--clip", type=float, default=1.0)
    g.add_argument("--precision", choices=["master-fp32", "pure-bf16"],
                   default="master-fp32")
    g.add_argument("--optim-foreach", type=int, default=0,
                   help="AdamW foreach; 0 keeps peak memory down on a 4.2B model")
    g.add_argument("--attn", default="sdpa")
    g.add_argument("--mem-frac", type=float, default=0.85,
                   help="cap on GPU memory so a blow-up is a clean CUDA OOM")
    g.add_argument("--seed", type=int, default=1337)

    g = p.add_argument_group("run control")
    g.add_argument("--out", default=HERE)
    g.add_argument("--ckpt-dir", default=None)
    g.add_argument("--status-path", default=None)
    g.add_argument("--save-every", type=int, default=200)
    g.add_argument("--keep-ckpt", type=int, default=2)
    g.add_argument("--save-hf-every", type=int, default=0,
                   help="also export a plain bf16 HF model every N steps (0 = never)")
    g.add_argument("--accept-config-change", action="store_true",
                   help="CODER-12: allow a resume whose lr/warmup/max-steps/"
                        "corpus differ from the checkpoint's. Off by default: a "
                        "silent change of the schedule or the food is exactly the "
                        "kind of drift nobody notices for 14 hours.")
    g.add_argument("--resume", default="auto",
                   help="'auto' = newest complete checkpoint, 'none', or a path")
    g.add_argument("--init-weights", default=None,
                   help="Start a FRESH run (step 0, fresh optimiser moments, fresh "
                        "warmup) from a name->tensor weights file, e.g. one produced "
                        "by extract_masters.py from a master-fp32 checkpoint. This is "
                        "the supported way to change --micro-batch/--grad-accum/"
                        "--replay, which --resume deliberately refuses to do because "
                        "the dataloader cursors would no longer line up. Use it with "
                        "--resume none and a FRESH --ckpt-dir.")
    g.add_argument("--log-every", type=int, default=1)
    g.add_argument("--dry-run", action="store_true",
                   help="3 optimizer steps then exit; validates the whole path")
    g.add_argument("--prepare-only", action="store_true")
    g.add_argument("--verify-corpus", action="store_true",
                   help="check the hold-out contract against the corpora and exit")
    return p


STOP = {"flag": False}


def _on_signal(signum, frame):
    STOP["flag"] = True
    log(f"signal {signum} received -- will checkpoint after this step and exit 0")


def verify_only(args, heldout_paths, heldout_prints):
    """Paths-only scan: no tokenizer, no GPU. Answers 'would anything leak?'."""
    bad_total = 0
    for label, arg in (("corpus", args.corpus),
                       ("replay", args.replay_corpus)):
        if not arg:
            continue
        files = expand_corpus_arg(arg)
        n = held = nopath = content = 0
        offenders = []
        for fpath, lineno, row in iter_jsonl(files):
            if row is None:
                continue
            n += 1
            rel = row_relpath(row)
            if rel is None:
                nopath += 1
            elif is_heldout(rel):
                held += 1
                if len(offenders) < 10:
                    offenders.append(rel)
            t = row.get("text")
            if args.content_leak_check and isinstance(t, str) and \
                    text_fingerprint(t) in heldout_prints:
                content += 1
        log(f"[{label}] {n:,} rows | {held} held-out by path (would be DROPPED) | "
            f"{content} held-out by content (would be DROPPED) | {nopath} without a path")
        if offenders:
            log(f"[{label}] examples: {offenders}")
        bad_total += held + content
        if args.strict and (held or content):
            die(EXIT_LEAK, f"[{label}] --strict: {held + content} held-out "
                           "documents present in the corpus.")
    log(f"VERIFY DONE: {bad_total} held-out documents found; with the filter on "
        "they are dropped before tokenisation.")
    return 0


def apply_config_file(parser, args, path):
    """train.config.json supplies the run's settings; explicit CLI flags win.

    watchdog.py restarts the trainer with a fixed command line
    (`python3 train.py --resume auto`), so the corpus paths, learning rate and
    the rest have to live somewhere it does not need to know about. They live
    here. Precedence: command line > train.config.json > argparse defaults.
    """
    if not os.path.exists(path):
        return []
    cfg = json.load(open(path, encoding="utf-8"))
    applied, keys = [], set()
    for k, v in cfg.items():
        key = k.replace("-", "_").lstrip("_")
        if not hasattr(args, key):
            die(EXIT_ERROR, f"{path}: unknown option '{k}'")
        if getattr(args, key) == parser.get_default(key):     # not set on the CLI
            setattr(args, key, v)
            applied.append(f"{key}={v}")
            keys.add(key)
    return applied, keys


def main():
    parser = build_args()
    args = parser.parse_args()
    cfg_path = os.path.expanduser(os.path.join(args.out, "train.config.json"))
    applied, cfg_keys = apply_config_file(parser, args, cfg_path)
    if applied:
        log(f"train.config.json: {', '.join(applied)}")

    def from_cli(name):
        """True only if the user typed this flag; config-file values do not count."""
        return getattr(args, name) != parser.get_default(name) and name not in cfg_keys
    args.out = os.path.expanduser(args.out)
    args.data_dir = os.path.expanduser(args.data_dir)
    args.heldout_jsonl = os.path.expanduser(args.heldout_jsonl)
    # CODER-13: the old default silently pointed at ~/coder-train/ckpt -- the
    # ABANDONED batch-8 run (95 GB, last step 1017). `train.py --resume auto` with
    # any config lacking ckpt-dir (train.config.json.bak-mb1ga8 is exactly that)
    # would have resumed that dead run at step 1017 with block 8 and called it
    # normal. A checkpoint directory is never a thing to guess.
    if not args.ckpt_dir:
        die(EXIT_ERROR,
            "--ckpt-dir is required (or a 'ckpt-dir' key in train.config.json). "
            "There is no safe default: falling back to <out>/ckpt would resume "
            "whatever abandoned run happens to live there.")
    args.ckpt_dir = os.path.expanduser(args.ckpt_dir)
    args.status_path = os.path.expanduser(args.status_path or
                                          os.path.join(args.out, "status.json"))
    os.makedirs(args.out, exist_ok=True)

    # --dry-run shrinks the schedule, but only where the user did not say
    # otherwise -- an explicit --max-steps 5 must still mean 5.
    if args.dry_run:
        # A value that came from train.config.json must NOT stop --dry-run from
        # shrinking the schedule: the config exists so the watchdog can launch a
        # 8000-step production run, and "--dry-run" must still mean 3 steps.
        if not from_cli("max_steps"):
            args.max_steps = 3
        if not from_cli("save_every"):
            args.save_every = 2
        if not from_cli("warmup"):
            args.warmup = 2

    log("=" * 70)
    log(f"train.py | {REPO} @ {REVISION[:12]} | precision={args.precision} "
        f"| seq_len={args.seq_len} | mb={args.micro_batch} x accum={args.grad_accum}"
        + (" | DRY RUN" if args.dry_run else ""))
    log("=" * 70)

    # ---- hold-out contract, step 1 of 4 ---------------------------------
    heldout_paths, heldout_prints = load_heldout(args.heldout_jsonl)

    if args.verify_corpus:
        sys.exit(verify_only(args, heldout_paths, heldout_prints))

    random.seed(args.seed)
    np.random.seed(args.seed % (2 ** 32))
    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)

    from transformers import AutoTokenizer, AutoModelForCausalLM

    tok = AutoTokenizer.from_pretrained(REPO, revision=REVISION)
    if tok.eos_token_id is None:
        die(EXIT_ERROR, "tokenizer has no eos_token_id; cannot separate documents.")

    dom_meta = prepare_corpus("domain", args.corpus, tok, heldout_paths,
                              heldout_prints, args,
                              require_path=bool(args.corpus_require_path))
    rep_meta = None
    if args.replay_corpus and Fraction(str(args.replay)) > 0:
        rep_meta = prepare_corpus("replay", args.replay_corpus, tok, heldout_paths,
                                  heldout_prints, args,
                                  require_path=bool(args.replay_require_path))
    if args.prepare_only:
        log("PREPARE_ONLY done.")
        return

    block_size = args.micro_batch * args.grad_accum
    dom_stream = TokenStream(dom_meta, args.seq_len, args.seed, "domain", args.pack_mode)
    rep_stream = (TokenStream(rep_meta, args.seq_len, args.seed, "replay", args.pack_mode)
                  if rep_meta else None)
    loader = MixedLoader(dom_stream, rep_stream, args.replay, block_size, args.seed)
    log(f"streams: domain {dom_stream.n_units:,} seq/epoch, replay "
        f"{rep_stream.n_units if rep_stream else 0:,} seq/epoch | replay ratio "
        f"{loader.num}/{loader.den} exact | {block_size} seq = "
        f"{block_size * args.seq_len:,} tokens per optimizer step")

    # ---- model ----------------------------------------------------------
    torch.cuda.set_per_process_memory_fraction(args.mem_frac, 0)
    cap = args.mem_frac * torch.cuda.get_device_properties(0).total_memory
    log(f"device {torch.cuda.get_device_name(0)} | memory cap {gb(cap)} GB")

    t0 = time.time()
    model = AutoModelForCausalLM.from_pretrained(
        REPO, revision=REVISION, dtype=torch.bfloat16, device_map=None,
        attn_implementation=args.attn).cuda()
    log(f"loaded {type(model).__name__} in {time.time()-t0:.1f}s")
    n_all = sum(p.numel() for p in model.parameters())
    n_train = sum(p.numel() for p in model.parameters() if p.requires_grad)
    if n_train != n_all:
        die(EXIT_ERROR, f"only {n_train}/{n_all} params require grad -- this "
                        "script is for FULL-WEIGHT training, not adapters.")
    log(f"params {n_all/1e9:.4f} B, all trainable, bf16 = {gb(n_all*2)} GB")

    # ---- --init-weights: fresh run, warm start ---------------------------
    # Loaded BEFORE the optimiser is built, because MasterAdamW clones the
    # bf16 params into its fp32 masters at construction time. The fp32 values
    # are then re-applied to the masters after the build (see below) so no
    # precision is lost through the bf16 round trip.
    init_sd = None
    if args.init_weights:
        ip = os.path.expanduser(args.init_weights)
        if not os.path.exists(ip):
            die(EXIT_ERROR, f"--init-weights {ip} does not exist")
        if args.resume and args.resume != "none":
            die(EXIT_ERROR, "--init-weights is a FRESH start; pass --resume none "
                            "and a fresh --ckpt-dir so it cannot silently race a "
                            "resumable checkpoint.")
        t1 = time.time()
        init_sd = load_ckpt_file(ip, weights_only=True)
        pnames = {n for n, _ in model.named_parameters()}
        extra = [k for k in init_sd if k not in pnames]
        if extra:
            die(EXIT_ERROR, f"--init-weights has {len(extra)} keys that are not "
                            f"model parameters, e.g. {extra[:5]}")
        got = model.load_state_dict(init_sd, strict=False)
        # A missing key that is itself a named parameter is a real hole. One
        # that is not (a tied lm_head, a buffer) is filled already by
        # from_pretrained or shares storage with a key we did load.
        holes = [k for k in got.missing_keys if k in pnames]
        if holes or got.unexpected_keys:
            die(EXIT_ERROR, f"--init-weights key mismatch: "
                            f"unexpected={list(got.unexpected_keys)[:5]} "
                            f"missing-parameters={holes[:5]}")
        skipped = [k for k in got.missing_keys if k not in pnames]
        log(f"--init-weights: loaded {len(init_sd)}/{len(pnames)} parameter "
            f"tensors from {ip} in {time.time()-t1:.1f}s"
            + (f" | {len(skipped)} tied/buffer keys not in the file: "
               f"{skipped[:4]}" if skipped else ""))

    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.config.use_cache = False
    if hasattr(model.config, "text_config"):
        model.config.text_config.use_cache = False
    model.train()

    Opt = MasterAdamW if args.precision == "master-fp32" else PlainAdamW
    optim = Opt(model.named_parameters(), args.lr, (args.beta1, args.beta2),
                args.eps, args.weight_decay, bool(args.optim_foreach))
    log(f"optimizer {Opt.__name__}: {optim.n_decay} decayed tensors, "
        f"{optim.n_no_decay} undecayed | mem after build {gb(torch.cuda.memory_allocated())} GB")

    if init_sd is not None and args.precision == "master-fp32":
        # The masters were cloned from bf16 params a moment ago, so they carry
        # bf16 rounding. Re-apply the fp32 file to them so the warm start is
        # bit-exact with the checkpoint it came from -- the whole point of
        # master-fp32 is that sub-bf16 detail matters.
        mnames = [n for n, _ in model.named_parameters()]
        if len(mnames) != len(optim.pairs):
            die(EXIT_ERROR, f"--init-weights: {len(mnames)} named params vs "
                            f"{len(optim.pairs)} optimiser pairs")
        with torch.no_grad():
            for name, (p_, m_) in zip(mnames, optim.pairs):
                s_ = init_sd[name]
                if tuple(s_.shape) != tuple(m_.shape):
                    die(EXIT_ERROR, f"--init-weights shape mismatch on {name}: "
                                    f"{tuple(s_.shape)} vs {tuple(m_.shape)}")
                m_.data.copy_(s_)
                p_.data.copy_(m_.data)
        log(f"--init-weights: refilled {len(mnames)} fp32 master tensors "
            "bit-exactly; bf16 params re-cast from them")
    init_sd = None
    gc.collect()

    warm, total, floor = max(1, args.warmup), max(1, args.max_steps), args.min_lr_ratio

    def lr_lambda(s):
        if s < warm:
            return (s + 1) / warm
        prog = min(1.0, (s - warm) / max(1, total - warm))
        return floor + (1.0 - floor) * 0.5 * (1.0 + math.cos(math.pi * prog))

    sched = torch.optim.lr_scheduler.LambdaLR(optim.opt, lr_lambda)

    # ---- resume ---------------------------------------------------------
    start_step, tokens_seen = 0, 0
    if args.resume and args.resume != "none":
        path = None
        if args.resume == "auto":
            done = ckpt_dirs(args.ckpt_dir, verbose=True)
            path = done[-1][1] if done else None
            if path is None:
                log("--resume auto: no complete checkpoint, starting from the base model")
        else:
            path = os.path.expanduser(args.resume)
            miss = ckpt_missing(path)
            if miss:
                die(EXIT_ERROR, f"{path} is not a usable checkpoint: missing {miss}")
        if path:
            st = load_checkpoint(path, model, optim, sched, loader, args)
            start_step = int(st["step"])
            tokens_seen = int(st.get("tokens_seen", 0))
            # The stream is a pure function of (seed, block index), so the
            # cursors the checkpoint stored must equal the ones seek() derives.
            # If they disagree, the run would silently see different data than
            # it did before the restart.
            want_dom, want_rep = loader.dom_cursor, loader.rep_cursor
            loader.seek(start_step)
            if (loader.dom_cursor, loader.rep_cursor) != (want_dom, want_rep):
                die(EXIT_ERROR,
                    "dataloader cursors in the checkpoint "
                    f"(dom={want_dom}, rep={want_rep}) disagree with the ones "
                    f"derived from step {start_step} (dom={loader.dom_cursor}, "
                    f"rep={loader.rep_cursor}). Resuming would change the data "
                    "order. Did --replay, --micro-batch or --grad-accum change?")
    loader.seek(start_step)
    loader.check_exact()

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    def build_status(status, step, loss, gnorm, tps, extra=None):
        s = {
            "status": status,
            "step": step,
            "max_steps": args.max_steps,
            "tokens_seen": tokens_seen,
            "loss": None if loss is None else round(float(loss), 5),
            "grad_norm": None if gnorm is None else round(float(gnorm), 4),
            "lr": round(float(sched.get_last_lr()[0]), 10),
            "tokens_per_sec": None if tps is None else round(float(tps), 1),
            "peak_gb": gb(torch.cuda.max_memory_allocated()),
            "reserved_gb": gb(torch.cuda.max_memory_reserved()),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "unix": round(time.time(), 1),
            "pid": os.getpid(),
            "replay_seen": loader.rep_cursor,
            "replay_frac": (round(loader.rep_cursor / loader.seq_index, 5)
                            if loader.seq_index else 0.0),
        }
        if extra:
            s.update(extra)
        return s

    def write_status(*a, **k):
        atomic_write_json(args.status_path, build_status(*a, **k))

    write_status("starting", start_step, None, None, None)

    # ---- the loop -------------------------------------------------------
    log(f"training steps {start_step} -> {args.max_steps}")
    torch.cuda.reset_peak_memory_stats()
    run_t0 = time.time()
    last_loss = None
    step = start_step
    dry_log = []
    last_saved_step = start_step   # CODER-07: the resume point is already on disk

    def save_guarded(done_, why, gnorm_=None, tps_=None):
        """CODER-11: a save that fails must not look like a crash with no cause,
        and must not be retried by a restart that cannot fix a full disk."""
        nonlocal last_saved_step
        try:
            save_checkpoint(args.ckpt_dir, done_, model, optim, sched, loader,
                            args, {"tokens_seen": tokens_seen, "loss": last_loss},
                            status_base=build_status("checkpointing", done_,
                                                     last_loss, gnorm_, tps_))
        except (OSError, RuntimeError) as e:
            write_status("crash_save_failed", done_, last_loss, None, None,
                         {"error": str(e)[:300]})
            die(EXIT_SAVE,
                f"CHECKPOINT SAVE FAILED at step {done_} ({why}): {str(e)[:400]}\n"
                "Exit code 6. A restart cannot make disk space or repair IO -- "
                "check df and the ckpt dir before starting this again.")
        last_saved_step = done_

    try:
        for step in range(start_step, args.max_steps):
            st0 = time.time()
            batch = loader.block(step)
            optim.zero_grad()
            model.zero_grad(set_to_none=True)
            loss_sum = 0.0
            real_tokens = 0

            for mb in range(args.grad_accum):
                sl = batch[mb * args.micro_batch:(mb + 1) * args.micro_batch]
                ids = torch.from_numpy(np.stack([s[0] for s in sl])).cuda(non_blocking=True)
                lab = torch.from_numpy(np.stack([s[1] for s in sl])).cuda(non_blocking=True)
                out = model(input_ids=ids, labels=lab)
                loss = out.loss
                if not torch.isfinite(loss):
                    write_status("crash_nonfinite_loss", step, float(loss), None, None)
                    die(EXIT_NONFINITE,
                        f"NON-FINITE LOSS at step {step}, micro-batch {mb}: "
                        f"{float(loss)}. Not skipping it -- something is wrong "
                        "with the data or the optimiser state. Watchdog: do not "
                        "restart blindly, exit code 3 means investigate.")
                loss_sum += float(loss.detach())
                real_tokens += int((lab != -100).sum())
                (loss / args.grad_accum).backward()
                del out, loss, ids, lab

            missing = optim.sync_grads()
            gnorm = grad_global_norm_and_clip_(optim.master_params(), args.clip)
            if not math.isfinite(gnorm):
                write_status("crash_nonfinite_grad", step, loss_sum / args.grad_accum,
                             gnorm, None)
                die(EXIT_NONFINITE,
                    f"NON-FINITE GRADIENT NORM at step {step}: {gnorm}. Exit "
                    "code 3: investigate, do not restart blindly.")
            optim.step()
            optim.copy_back()
            sched.step()

            tokens_seen += real_tokens
            dt = time.time() - st0
            tps = real_tokens / max(dt, 1e-6)
            last_loss = loss_sum / args.grad_accum
            done = step + 1
            loader.check_exact()

            if step == start_step:
                log(f"first step: {missing} of {len(optim.master_params())} "
                    f"parameter tensors received no gradient | peak "
                    f"{gb(torch.cuda.max_memory_allocated())} GB")

            if done % args.log_every == 0 or args.dry_run:
                eta = (args.max_steps - done) * dt / 3600.0
                log(f"step {done}/{args.max_steps} loss {last_loss:.4f} "
                    f"gnorm {gnorm:.3f} lr {sched.get_last_lr()[0]:.3e} "
                    f"{tps:.0f} tok/s peak {gb(torch.cuda.max_memory_allocated())} GB "
                    f"tokens {tokens_seen:,} eta {eta:.1f} h")
            write_status("running", done, last_loss, gnorm, tps,
                         {"wall_s": round(time.time() - run_t0, 1),
                          "step_s": round(dt, 3),
                          "eta_h": round((args.max_steps - done) * dt / 3600.0, 2)})
            if args.dry_run:
                dry_log.append({"step": done, "loss": round(last_loss, 5),
                                "grad_norm": round(gnorm, 4),
                                "lr": sched.get_last_lr()[0],
                                "tokens_seen": tokens_seen,
                                "tokens_per_sec": round(tps, 1),
                                "step_s": round(dt, 2),
                                "replay_seen": loader.rep_cursor,
                                "dom_cursor": loader.dom_cursor,
                                "peak_gb": gb(torch.cuda.max_memory_allocated())})

            if should_save_periodic(done, args.save_every, last_saved_step):
                save_guarded(done, "save-every", gnorm, tps)
            if args.save_hf_every > 0 and done % args.save_hf_every == 0:
                # CODER-04: THE ONLY WAY THE TRAINING EVER RETURNS ANYTHING.
                # With save-hf-every 0 the masters live only inside a 50 GB
                # optim.pt, so nothing on this box or any other could load, serve
                # or SCORE the trained model -- the held-out set that the 4-guard
                # contract exists to protect has not been scored since the base
                # model, before training began. An export is what eval_ckpt.py
                # reads; without it "is the coder better than base?" has no answer.
                root = os.path.join(args.out, "export")
                d = os.path.join(root, f"step_{done:08d}")
                os.makedirs(d, exist_ok=True)
                model.save_pretrained(d, safe_serialization=True)
                tok.save_pretrained(d)
                log(f"HF export -> {d}")
                gone = prune_export_dirs(root, args.keep_ckpt)
                if gone:
                    log(f"pruned old HF export(s): {gone}")

            if STOP["flag"]:
                if should_save_on_stop(done, last_saved_step):
                    save_guarded(done, "SIGTERM", gnorm, tps)
                else:
                    log(f"stop signal on a step already checkpointed "
                        f"({done}) -- not writing 47 GB twice")
                write_status("stopped", done, last_loss, gnorm, tps)
                log("stopped on signal, checkpoint written, exit 0")
                return

    except torch.cuda.OutOfMemoryError as e:
        write_status("crash_oom", step, last_loss, None, None,
                     {"error": str(e)[:300]})
        die(EXIT_OOM, f"CUDA OOM at step {step}: {str(e)[:400]}\n"
                      "Lower --micro-batch or --seq-len, or use "
                      "--precision pure-bf16, or wait for the other job on this "
                      "GPU to finish.")

    done = args.max_steps
    if args.save_every > 0 and done != last_saved_step:
        save_guarded(done, "final")
    write_status("finished", done, last_loss, None, None)

    if args.dry_run:
        summary = {
            "DRY_RUN": True,
            "model": REPO, "revision": REVISION,
            "precision": args.precision,
            "seq_len": args.seq_len,
            "micro_batch": args.micro_batch, "grad_accum": args.grad_accum,
            "tokens_per_step": block_size * args.seq_len,
            "clip": args.clip,
            "replay_requested": args.replay,
            "replay_exact": f"{loader.num}/{loader.den}",
            "replay_seen_of_total": f"{loader.rep_cursor}/{loader.seq_index}",
            "heldout_paths_enforced": len(heldout_paths),
            "domain": {k: dom_meta[k] for k in
                       ("n_docs", "n_tokens", "dropped_heldout_path",
                        "dropped_heldout_content", "leak_check")},
            "replay_corpus": ({k: rep_meta[k] for k in
                               ("n_docs", "n_tokens", "dropped_heldout_path",
                                "dropped_heldout_content", "leak_check")}
                              if rep_meta else None),
            "steps": dry_log,
            "PEAK_GB": gb(torch.cuda.max_memory_allocated()),
            "PEAK_RESERVED_GB": gb(torch.cuda.max_memory_reserved()),
            "wall_s": round(time.time() - run_t0, 1),
        }
        p = os.path.join(args.out, "dryrun_result.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        print("DRY_RUN_SUMMARY_BEGIN", flush=True)
        print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
        print("DRY_RUN_SUMMARY_END", flush=True)
        log(f"wrote {p}")
    log("TRAIN_DONE")


if __name__ == "__main__":
    main()
