# -*- coding: utf-8 -*-
"""midi_data.py -- corpus loader for the lean-MIDI Darwish model.

WHAT THIS FILE OWNS
-------------------
Turning ~/darwish-ai/tokens-midi/*.json (191 files, one JSON per set) into
fixed-length int64 windows for training, with a train/heldout split that is
frozen BY TRACK in code-midi/split.json and never leaks.

It touches nothing else. Reads tokens-midi read-only, writes only its own
cache under code-midi/cache/.

THE THREE DECISIONS THAT MATTER, AND WHY
========================================

1. SPLIT BY TRACK, NEVER BY WINDOW.
   split.json (built by make_split.py) is the source of truth: 156 train
   tracks / 17 heldout tracks / 18 excluded non-Darwish files. A psytrance
   track repeats its own 16-bar phrase dozens of times, so two windows cut
   from one track on opposite sides of a split would leak almost perfectly
   and the heldout number would measure memorisation of that track's loops
   instead of generalisation. This file only ever reads whole tracks out of
   the lists in split.json, so the split cannot be violated by accident.

   Splitting by NAME is not enough, and this corpus proved it: two sets were
   uploaded to YouTube twice under different titles, so one copy of each landed
   in train and the other in heldout with byte-identical tokens. This loader
   hashes every track's token stream, claims heldout first, and drops the
   colliding train copy. 2 tracks / 8,395 tokens (0.31% of train) removed. See
   build_cache() for the names. Without this the heldout number would have been
   quietly wrong and nothing in the loss curve would have shown it.

2. SHORT TRACKS ARE **PACKED**, NOT PADDED AND NOT SKIPPED.
   seq_len is 8192 and 122 of the 173 clean tracks are SHORTER than that --
   every single (non-set) track in the corpus is short. So:

     * SKIPPING them would throw away 100% of the singles, i.e. exactly the
       tracks the "hold a whole track in context" argument is about. Refused.

     * PADDING them is worse than it looks. The contract with midi_model.py is
       `loss_fn(model, tokens) -> (loss, parts)` -- there is NO mask argument,
       so padded positions would be scored. A 4,654-token single inside an
       8,193-token window is 43% padding, and "PAD follows PAD" is free to
       predict, so the reported CE would be dragged toward zero by an amount
       that depends on which tracks happened to be sampled. That is a silent
       wrong answer, which is the one thing this loader must not produce.

     * So: PACKING. A window is filled by taking a random start inside one
       track and, if that track ends before the window is full, continuing
       with another whole track drawn from the SAME split, from its BOS(106).
       Every scored position is a real token of real music. No mask is needed,
       no PAD id is invented, VOCAB stays 108, and midi_model.py needs to know
       nothing about any of this.

   What packing costs, stated plainly: a packed window contains a track change
   in the middle, so tempo and key change mid-window with no signal other than
   the EOS(107)/BOS(106) pair at the seam. Two mitigations, one of them real
   luck: (a) this is standard document-packing, the same thing every GPT-style
   LM does, and the model can see the seam; (b) the corpus is 82.6% live DJ
   SETS, which are literally concatenations of tracks with key/tempo changes at
   the mix points -- so a seam is in-distribution for this particular music in
   a way it would not be for, say, sonatas. Measured below: with the default
   token-proportional sampling only ~17% of windows contain a seam at all,
   because the long sets that carry most of the token mass are longer than the
   window and produce clean single-track windows.

   Filler tracks are re-drawn at random every call, so no fixed pair of tracks
   is ever memorised as "A is followed by B".

3. SAMPLING IS TOKEN-PROPORTIONAL BY DEFAULT.
   The corpus is sharply bimodal: 130 singles (median 4,654 tok) and 61 long
   sets (median 43,313 tok, max 111,787). Uniform-over-tracks would show the
   shortest single 44x more often per token than the longest set and overfit it
   hard. Token-proportional (weight proportional to track length) gives every
   token in the corpus equal exposure, which is what "train on the corpus"
   means. `sampling="track"` is available for comparison and is not the default.

CONTRACT THIS FILE EXPORTS (midi_train.py and midi_model.py both use it)
-----------------------------------------------------------------------
    VOCAB           = 108      ids 0..107, no PAD, nothing added
    TOKENS_PER_BAR  = 17       16 grid tokens + the BAR token 104
    TOKENS_PER_PHRASE = 273    16 bars * 17 + the PHRASE token 105
    SEQ_LEN         = 8192     ~13.4 min of music, ~482 bars, ~30 phrases

    TOKENS_PER_BAR is STRUCTURAL, not a tempo guess. midi_lean.py emits a BAR
    token after every 16 grid steps, so consecutive BAR tokens are 17 apart
    (18 where a PHRASE also lands). Measured over all 191 files: 186,544 gaps
    of 17 and 12,340 of 18, mean 17.0625. Use 17 for the JEPA gist span; the
    "4*60/bpm seconds * 9.96 tok/s = 16.7" arithmetic lands on the same number
    from the other direction, but 17 is the exact one.

Batches are int64 tensors of shape [B, seq_len + 1]: midi_model.loss_fn splits
them into input tokens[..., :-1] and targets tokens[..., 1:], exactly as
code/model.py already does for the big audio model.

numpy + torch(CPU only, tensors are built on the host and moved by the caller).
"""
from __future__ import annotations

import hashlib
import json
import os

import numpy as np
import torch

HOME = os.path.expanduser("~/darwish-ai")
TOKDIR = os.path.join(HOME, "tokens-midi")
SPLIT_PATH = os.path.join(HOME, "code-midi", "split.json")
CACHE_DIR = os.path.join(HOME, "code-midi", "cache")

# --- the lean-MIDI vocabulary, from midi_lean.py. Do not extend it. ---
VOCAB = 108
TOK_BAR, TOK_PHRASE, TOK_BOS, TOK_EOS = 104, 105, 106, 107

TOKENS_PER_BAR = 17            # 16 grid steps + BAR(104)
TOKENS_PER_PHRASE = 16 * TOKENS_PER_BAR + 1   # 273, + PHRASE(105)
SEQ_LEN = 8192

CACHE_VERSION = 3


# ------------------------------------------------------------------ cache

def _fingerprint(split_path, tokdir):
    """Cache key: the split file plus the size/mtime of every token file."""
    h = hashlib.sha256()
    h.update(f"midi_data v{CACHE_VERSION}".encode())
    with open(split_path, "rb") as fh:
        h.update(fh.read())
    for name in sorted(os.listdir(tokdir)):
        if not name.endswith(".json"):
            continue
        st = os.stat(os.path.join(tokdir, name))
        h.update(name.encode("utf-8"))
        h.update(f"{st.st_size}:{int(st.st_mtime)}".encode())
    return h.hexdigest()[:16]


def _build_split(files, tokdir, seen=None):
    """Read the listed token JSONs into one int64 stream + track boundaries.

    `seen` is a set of already-claimed content hashes. Any track whose token
    stream is byte-identical to one already claimed is DROPPED and reported --
    see the DEDUPLICATION note in build_cache().
    """
    chunks, meta, bounds, dropped = [], [], [0], []
    if seen is None:
        seen = set()
    for name in files:
        path = os.path.join(tokdir, name)
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        t = np.asarray(d["tokens"], dtype=np.int64)

        # A silent wrong answer here poisons everything downstream, so shout.
        if t.size < 64:
            raise ValueError(f"{name}: only {t.size} tokens")
        if t.min() < 0 or t.max() >= VOCAB:
            raise ValueError(f"{name}: token out of range [0,{VOCAB}): "
                             f"min={t.min()} max={t.max()}")
        if t[0] != TOK_BOS or t[-1] != TOK_EOS:
            raise ValueError(f"{name}: expected BOS..EOS, got {t[0]}..{t[-1]}")
        mid = t[1:-1]
        if np.any((mid == TOK_BOS) | (mid == TOK_EOS)):
            raise ValueError(f"{name}: BOS/EOS appears mid-stream")
        if t.size != d["n_tokens"]:
            raise ValueError(f"{name}: header n_tokens={d['n_tokens']} "
                             f"but {t.size} tokens present")

        sha1 = hashlib.sha1(t.tobytes()).hexdigest()[:16]
        if sha1 in seen:
            dropped.append({"file": name, "sha1": sha1, "n_tokens": int(t.size)})
            continue
        seen.add(sha1)

        chunks.append(t)
        bounds.append(bounds[-1] + t.size)
        meta.append({"file": name, "n_tokens": int(t.size), "bpm": d["bpm"],
                     "key": d["key"], "key_pc": d["key_pc"],
                     "seconds": d["seconds"], "sha1": sha1})
    if not chunks:
        raise ValueError("split has no usable tracks")
    return (np.concatenate(chunks).astype(np.int64),
            np.asarray(bounds, dtype=np.int64), meta, dropped)


def build_cache(split_path=SPLIT_PATH, tokdir=TOKDIR, cache_dir=CACHE_DIR,
                verbose=True):
    """Materialise train/heldout int64 arrays on disk. Idempotent.

    DEDUPLICATION -- a real leak found in this corpus, not a hypothetical.
    ---------------------------------------------------------------------
    The corpus was harvested from YouTube by name, and two sets were uploaded
    TWICE under different titles, so their token streams are byte-identical:

        "2022 - DARWISH & NO SPOON > Trance From Scratch ..."  ==
        "2022 - Darwish & No Spoon - Trance from Scratch"        (4,766 tok)

        "2025 - Darwish - Feels Like Home"                     ==
        "2025 - Feels Like Home - Darwish"                       (3,629 tok)

    make_split.py splits by FILE NAME, so in both pairs one copy landed in
    train and the other in heldout. That is a perfect leak: the heldout loss on
    those two tracks would have measured nothing but memorisation, and there is
    no way to see it from the loss curve. 189 of the 191 token streams are
    unique; only these two pairs collide.

    The rule here: heldout is claimed FIRST, then train, and any train track
    whose content is already claimed is dropped. The measuring instrument stays
    whole and the training set loses 2 tracks / 8,395 tokens (0.31% of train).
    The same rule also removes any within-split duplicate, so this stays correct
    if the corpus grows. Every drop is recorded in the manifest and printed.
    split.json is left untouched -- it remains the source of truth for WHICH
    track goes where; this is a content filter on top of it.
    """
    os.makedirs(cache_dir, exist_ok=True)
    fp = _fingerprint(split_path, tokdir)
    manifest_path = os.path.join(cache_dir, f"{fp}.manifest.json")
    if os.path.exists(manifest_path):
        return fp, json.load(open(manifest_path, encoding="utf-8"))

    with open(split_path, encoding="utf-8") as fh:
        split = json.load(fh)

    train_files, held_files = split["train"], split["heldout"]
    overlap = set(train_files) & set(held_files)
    if overlap:
        raise ValueError(f"split.json leaks {len(overlap)} tracks: {sorted(overlap)[:3]}")

    manifest = {"fingerprint": fp, "seq_len_agnostic": True,
                "split_rule": split.get("rule", ""), "splits": {},
                "dropped_as_duplicate": []}
    seen = set()
    # HELDOUT FIRST: it claims its content, so a colliding train track is the
    # one that gets dropped. Never shrink the measuring instrument.
    for name, files in (("heldout", held_files), ("train", train_files)):
        arr, bounds, meta, dropped = _build_split(files, tokdir, seen)
        np.save(os.path.join(cache_dir, f"{fp}.{name}.tokens.npy"), arr)
        np.save(os.path.join(cache_dir, f"{fp}.{name}.bounds.npy"), bounds)
        manifest["splits"][name] = {"n_tracks": len(meta), "n_listed": len(files),
                                    "n_tokens": int(arr.size), "tracks": meta}
        for d in dropped:
            d["split"] = name
        manifest["dropped_as_duplicate"] += dropped
        if verbose:
            print(f"cache: {name:8s} {len(meta):>4} tracks  {arr.size:>10,} tokens"
                  + (f"   ({len(dropped)} dropped as duplicate content)"
                     if dropped else ""))

    # Belt and braces: prove the leak is gone rather than assuming the loop did it.
    tr_sha = {m["sha1"] for m in manifest["splits"]["train"]["tracks"]}
    he_sha = {m["sha1"] for m in manifest["splits"]["heldout"]["tracks"]}
    if tr_sha & he_sha:
        raise ValueError(f"content still shared across split: {tr_sha & he_sha}")
    manifest["content_overlap_after_dedup"] = 0
    if verbose and manifest["dropped_as_duplicate"]:
        for d in manifest["dropped_as_duplicate"]:
            print(f"       dropped from {d['split']}: {d['file'][:70]} "
                  f"({d['n_tokens']:,} tok, identical content already claimed)")

    tmp = manifest_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, manifest_path)
    return fp, manifest


# ------------------------------------------------------------------ corpus

class MidiCorpus:
    """Windows of lean-MIDI tokens, split by track, packed never padded."""

    def __init__(self, seq_len=SEQ_LEN, sampling="token", seed=1337,
                 split_path=SPLIT_PATH, tokdir=TOKDIR, cache_dir=CACHE_DIR,
                 verbose=True):
        if sampling not in ("token", "track"):
            raise ValueError("sampling must be 'token' or 'track'")
        self.seq_len = int(seq_len)
        self.need = self.seq_len + 1          # +1 target shift
        self.sampling = sampling
        self.rng = np.random.default_rng(seed)

        fp, manifest = build_cache(split_path, tokdir, cache_dir, verbose)
        self.fingerprint, self.manifest = fp, manifest
        self.data = {}
        for name in ("train", "heldout"):
            arr = np.load(os.path.join(cache_dir, f"{fp}.{name}.tokens.npy"),
                          mmap_mode="r")
            bounds = np.load(os.path.join(cache_dir, f"{fp}.{name}.bounds.npy"))
            lens = np.diff(bounds)
            if sampling == "token":
                w = lens.astype(np.float64)
            else:
                w = np.ones(len(lens), dtype=np.float64)
            self.data[name] = {"arr": arr, "bounds": bounds, "lens": lens,
                               "w": w / w.sum(),
                               "meta": manifest["splits"][name]["tracks"]}

        self.train_files = [m["file"] for m in self.data["train"]["meta"]]
        self.heldout_files = [m["file"] for m in self.data["heldout"]["meta"]]
        assert not (set(self.train_files) & set(self.heldout_files))
        self._held_starts = None

    # ------------------------------------------------------------ sampling

    def _window(self, name):
        """One packed window of `need` int64 tokens. Returns (window, n_tracks)."""
        d = self.data[name]
        arr, bounds, w = d["arr"], d["bounds"], d["w"]
        out = np.empty(self.need, dtype=np.int64)
        filled, used, first = 0, 0, True
        while filled < self.need:
            i = int(self.rng.choice(len(w), p=w))
            lo, hi = int(bounds[i]), int(bounds[i + 1])
            length = hi - lo
            if first and length >= self.need:
                # Long enough on its own: a clean single-track window.
                s = lo + int(self.rng.integers(0, length - self.need + 1))
                out[:] = arr[s:s + self.need]
                filled, used = self.need, 1
            else:
                # Short track (or filler): take it whole, from its BOS.
                take = min(length, self.need - filled)
                out[filled:filled + take] = arr[lo:lo + take]
                filled += take
                used += 1
            first = False
        return out, used

    def train_batch(self, b, device=None):
        """[b, seq_len+1] int64."""
        w = np.stack([self._window("train")[0] for _ in range(b)])
        t = torch.from_numpy(w)
        return t.to(device) if device else t

    # ------------------------------------------------------------ heldout

    def heldout_starts(self, max_windows=32):
        """Deterministic eval windows. No RNG anywhere in this path.

        Non-overlapping stride of seq_len over the heldout stream, so every
        heldout target token is scored exactly once. 247,572 heldout tokens at
        seq_len 8192 gives 30 windows, i.e. the whole heldout set fits under
        the default cap and the number is a true full-heldout loss.
        """
        if self._held_starts is not None and self._held_cap == max_windows:
            return self._held_starts
        n_tok = int(self.data["heldout"]["arr"].shape[0])
        n = (n_tok - 1) // self.seq_len
        if n < 1:
            raise ValueError("heldout stream shorter than one window")
        starts = np.arange(n, dtype=np.int64) * self.seq_len
        if n > max_windows:
            idx = np.unique(np.linspace(0, n - 1, max_windows).round().astype(int))
            starts = starts[idx]
        self._held_starts, self._held_cap = starts, max_windows
        return starts

    def heldout_batches(self, b=2, max_windows=32, device=None):
        """Yield deterministic [<=b, seq_len+1] int64 batches."""
        arr = self.data["heldout"]["arr"]
        starts = self.heldout_starts(max_windows)
        for i in range(0, len(starts), b):
            chunk = starts[i:i + b]
            w = np.stack([np.asarray(arr[s:s + self.need], dtype=np.int64)
                          for s in chunk])
            t = torch.from_numpy(w)
            yield t.to(device) if device else t

    # ------------------------------------------------------------ reporting

    def stats(self):
        s = {"seq_len": self.seq_len, "sampling": self.sampling,
             "vocab": VOCAB, "tokens_per_bar": TOKENS_PER_BAR,
             "fingerprint": self.fingerprint}
        for name in ("train", "heldout"):
            d = self.data[name]
            lens = d["lens"]
            s[name] = {"tracks": int(len(lens)), "tokens": int(lens.sum()),
                       "min": int(lens.min()), "median": float(np.median(lens)),
                       "max": int(lens.max()),
                       "shorter_than_window": int((lens < self.need).sum())}
        s["heldout_eval_windows"] = int(len(self.heldout_starts()))
        s["bars_per_window"] = round(self.seq_len / TOKENS_PER_BAR, 1)
        return s


# ------------------------------------------------------------------ selftest

def _selftest():
    import collections
    import time

    print("=" * 74)
    print("midi_data.py selftest -- real data, real batches, no GPU touched")
    print("=" * 74)

    t0 = time.time()
    c = MidiCorpus(verbose=True)
    print(f"first open (cache build if cold): {time.time() - t0:.2f}s")
    t0 = time.time()
    c2 = MidiCorpus(verbose=False)
    print(f"warm open:                        {time.time() - t0:.2f}s")

    st = c.stats()
    print("\n-- corpus --")
    for k in ("seq_len", "sampling", "vocab", "tokens_per_bar",
              "bars_per_window", "heldout_eval_windows", "fingerprint"):
        print(f"  {k:22s} {st[k]}")
    for name in ("train", "heldout"):
        d = st[name]
        print(f"  {name:8s} tracks={d['tracks']:>4}  tokens={d['tokens']:>10,}  "
              f"len min/med/max={d['min']}/{d['median']:.0f}/{d['max']}  "
              f"shorter_than_window={d['shorter_than_window']}")

    print("\n-- split integrity --")
    tr, he = set(c.train_files), set(c.heldout_files)
    tr_sha = {m["sha1"] for m in c.data["train"]["meta"]}
    he_sha = {m["sha1"] for m in c.data["heldout"]["meta"]}
    print(f"  train tracks used      {len(tr)}")
    print(f"  heldout tracks used    {len(he)}")
    print(f"  filename intersection  {len(tr & he)}  <-- must be 0")
    print(f"  CONTENT intersection   {len(tr_sha & he_sha)}  <-- must be 0")
    dropped = c.manifest.get("dropped_as_duplicate", [])
    print(f"  dropped as duplicate   {len(dropped)}")
    for d in dropped:
        print(f"      [{d['split']}] {d['file'][:66]}  ({d['n_tokens']:,} tok)")
    assert not (tr & he) and not (tr_sha & he_sha)

    print("\n-- batches --")
    for b in (1, 2, 4):
        t0 = time.time()
        x = c.train_batch(b)
        dt = time.time() - t0
        print(f"  train_batch({b}) -> shape={tuple(x.shape)} dtype={x.dtype} "
              f"device={x.device} min={int(x.min())} max={int(x.max())} "
              f"{dt * 1000:.0f} ms")
        assert x.shape == (b, c.seq_len + 1) and x.dtype == torch.int64
        assert 0 <= int(x.min()) and int(x.max()) < VOCAB

    hb = list(c.heldout_batches(b=2))
    print(f"  heldout_batches(2) -> {len(hb)} batches, shapes "
          f"{sorted({tuple(t.shape) for t in hb})}, "
          f"{sum(t.shape[0] for t in hb)} windows total")
    hb2 = list(c2.heldout_batches(b=2))
    same = all(torch.equal(a, b_) for a, b_ in zip(hb, hb2))
    print(f"  heldout deterministic across two independent loaders: {same}")
    assert same

    print("\n-- what packing actually produces (400 windows) --")
    seams, per_track = [], collections.Counter()
    bos_counts = []
    for _ in range(400):
        w, used = c._window("train")
        seams.append(used)
        bos_counts.append(int((w == TOK_BOS).sum()))
    n = len(seams)
    print(f"  single-track windows      {sum(1 for s in seams if s == 1) / n:6.1%}")
    print(f"  windows with >=1 seam     {sum(1 for s in seams if s > 1) / n:6.1%}")
    print(f"  mean tracks per window    {np.mean(seams):.2f}  max {max(seams)}")
    print(f"  mean BOS tokens/window    {np.mean(bos_counts):.2f} "
          f"(a whole track start inside the window)")

    print("\n-- token-proportional exposure is really token-proportional --")
    lens = c.data["train"]["lens"]
    order = np.argsort(lens)
    shortest, longest = int(order[0]), int(order[-1])
    draws = c.rng.choice(len(lens), size=20000, p=c.data["train"]["w"])
    cnt = collections.Counter(draws.tolist())
    for label, i in (("shortest track", shortest), ("longest track", longest)):
        exp = lens[i] / lens.sum()
        got = cnt.get(i, 0) / 20000
        print(f"  {label:15s} len={lens[i]:>7,}  expected={exp:7.4%}  "
              f"drawn={got:7.4%}")

    print("\n-- a real window, decoded structurally --")
    w, used = c._window("train")
    bar_pos = np.flatnonzero(w == TOK_BAR)
    gaps = np.diff(bar_pos)
    print(f"  window covers {len(bar_pos)} BAR tokens, {int((w == TOK_PHRASE).sum())} PHRASE")
    if len(gaps):
        u, ct = np.unique(gaps, return_counts=True)
        print(f"  BAR-to-BAR gaps: {dict(zip(u.tolist(), ct.tolist()))} "
              f"(17 = 16 grid + BAR; 18 where a PHRASE lands)")
        print(f"  mean gap {gaps.mean():.4f}  -> TOKENS_PER_BAR={TOKENS_PER_BAR} confirmed")
    print(f"  first 24 tokens: {w[:24].tolist()}")
    print("\nOK -- data loader is real.")


if __name__ == "__main__":
    _selftest()
