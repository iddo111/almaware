"""make_words.py — build food/words: 96 word wavs over 12 word classes.

WHY THIS FILE EXISTS, said plainly. The depth brief names "the 96 word wavs in
food/words (12 word classes)". THERE IS NO food/words ON THE PC MIRROR — the
directory does not exist and no revision of this repo contains one; only the
genome's FOOD_WORDS path points at it. The live organism runs on eran1 and this
session may not ssh, so the corpus could not be fetched. It is BUILT here
instead, and the fact that it was built (not recorded) is written into the
manifest and into every result computed from it. Reporting a decomposition
number without saying which words it came from would be the exact dishonesty
this project exists to refuse.

HOW IT IS BUILT, and why that is the honest construction available:

  * Each word is a CONCATENATION of real syllable recordings from food/train,
    with a short crossfade at each seam, so its constituent syllables are known
    EXACTLY. Ground truth here is not a transcription anyone had to trust — it
    is the recipe.
  * The syllable tokens used are the DEV split only (measure.is_dev), which
    school.py excludes from every menu it ever serves. So the words are made of
    recordings the organism has NEVER eaten, of classes it HAS heard. That is
    the fair question: can a brain that knows syllables find them inside a word
    it has never heard?
  * Nothing from proof/heldout-vault is touched.
  * Deterministic: same corpus in, byte-identical wavs out.

WHAT IT IS NOT. These are concatenated syllables, not naturally spoken words:
no coarticulation, no cross-syllable prosody, seams at exactly known places. A
real word is harder. That makes this an EASIER test than the real thing — so a
failure here is a real failure, and a success here is not yet a success at
speech. Labelled that way in the manifest, and in the results.

    python3 proof/make_words.py            # writes food/words/*.wav + manifest
"""
import hashlib
import json
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(ROOT, "body"))
sys.path.insert(0, _HERE)

import genome                                     # noqa: E402
import ears as ears_mod                           # noqa: E402
import measure                                    # noqa: E402

# 12 word classes over the 22-syllable inventory. Eight of two syllables, four
# of three, so word length is not itself the answer. All 22 syllables are used,
# which matters for the permutation null: it draws fake constituent sets from
# all 22, so a class that can never be a real constituent would bias the null
# downward and flatter the result.
WORDS = {
    "saba":    ("sa", "ba"),
    "mala":    ("ma", "la"),
    "daga":    ("da", "ga"),
    "kara":    ("ka", "ra"),
    "naha":    ("na", "ha"),
    "tava":    ("ta", "va"),
    "yaza":    ("ya", "za"),
    "shana":   ("sha", "na"),
    "gamala":  ("ga", "ma", "la"),
    "khatapa": ("kha", "ta", "pa"),
    "tsaqara": ("tsa", "qa", "ra"),
    "thabaah": ("tha", "ah", "aa"),
}
TOKENS_PER_WORD = 8                 # 12 x 8 = 96
CROSSFADE_MS = 20                   # a seam, not a click
GAP_MS = 0                          # syllables abut; no silence to count


def _dev_tokens_by_class(train_dir):
    """{class: [paths]} over the DEV split only — never eaten in life."""
    out = {}
    for p in measure.wavs_in(train_dir):
        if not measure.is_dev(p):
            continue
        out.setdefault(measure.label_of(p), []).append(p)
    return {c: sorted(v) for c, v in out.items()}


def _join(chunks, sr, crossfade_ms=CROSSFADE_MS, gap_ms=GAP_MS):
    fade = int(round(sr * crossfade_ms / 1000.0))
    gap = int(round(sr * gap_ms / 1000.0))
    out = np.asarray(chunks[0], dtype=np.float64).copy()
    for nxt in chunks[1:]:
        nxt = np.asarray(nxt, dtype=np.float64)
        if gap:
            out = np.concatenate([out, np.zeros(gap)])
        f = min(fade, len(out), len(nxt))
        if f <= 0:
            out = np.concatenate([out, nxt])
            continue
        ramp = np.linspace(0.0, 1.0, f)
        head, tail = out[:-f], out[-f:]
        out = np.concatenate([head, tail * (1.0 - ramp) + nxt[:f] * ramp,
                              nxt[f:]])
    m = float(np.max(np.abs(out))) or 1.0
    return (out * (0.7 / m))


def build(train_dir=None, words_dir=None, log=print):
    train_dir = train_dir or genome.FOOD_TRAIN
    words_dir = words_dir or genome.FOOD_WORDS
    by_class = _dev_tokens_by_class(train_dir)
    missing = sorted({c for parts in WORDS.values() for c in parts}
                     - set(by_class))
    if missing:
        raise SystemExit(f"no dev tokens for syllable classes: {missing}")
    os.makedirs(words_dir, exist_ok=True)
    manifest = {
        "built_by": "proof/make_words.py",
        "honest_note": (
            "SYNTHETIC WORDS. food/words did not exist on the PC mirror, so "
            "these were BUILT by concatenating real DEV-split syllable "
            "recordings from food/train (tokens school.py never serves) with "
            "a 20 ms crossfade. Constituents are exact by construction. They "
            "are NOT naturally spoken words: no coarticulation, no "
            "cross-syllable prosody. This is an EASIER test than real speech."),
        "sample_rate": genome.SAMPLE_RATE,
        "crossfade_ms": CROSSFADE_MS,
        "words": {},
    }
    made, seen = 0, {}
    for word, parts in sorted(WORDS.items()):
        pools = [by_class[c] for c in parts]
        combos = 1
        for pool in pools:
            combos *= len(pool)
        if combos < TOKENS_PER_WORD:
            raise SystemExit(
                f"{word}: only {combos} distinct token combinations available "
                f"from the dev pools {[len(p) for p in pools]}, and "
                f"{TOKENS_PER_WORD} tokens are wanted. Pick a word whose "
                f"syllables have more dev recordings, or lower "
                f"TOKENS_PER_WORD — do NOT ship duplicates.")
        for t in range(TOKENS_PER_WORD):
            # A MIXED-RADIX counter over the pools, so every take is a
            # DIFFERENT combination of source recordings. The old rule,
            # pool[(t*len(parts)+j) % len(pool)], cycled: it produced 96 files
            # of which only 60 were unique, several in 4-way byte-identical
            # groups. Every AUC and every permutation p-value was then computed
            # over pseudo-replicates, which narrows a null distribution and
            # flatters the result. Found in review, 2026-08-21.
            chunks, used, rest = [], [], t
            for pool in pools:
                pick = pool[rest % len(pool)]
                rest //= len(pool)
                chunks.append(ears_mod.read_wav(pick))
                used.append(os.path.basename(pick))
            name = f"{word}_w{t:02d}_0.wav"
            out = os.path.join(words_dir, name)
            ears_mod.write_wav(out, _join(chunks, genome.SAMPLE_RATE))
            key = tuple(used)
            if key in seen:
                raise SystemExit(f"{name} duplicates {seen[key]}: {used}")
            seen[key] = name
            manifest["words"][name] = {"word": word, "take": t,
                                       "syllables": list(parts),
                                       "tokens": used}
            made += 1
    path = os.path.join(words_dir, "manifest.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)
    digests = {}
    for name in manifest["words"]:
        with open(os.path.join(words_dir, name), "rb") as f:
            digests.setdefault(hashlib.sha1(f.read()).hexdigest(), []).append(name)
    dupes = {h: v for h, v in digests.items() if len(v) > 1}
    if dupes:
        raise SystemExit(f"byte-identical word wavs shipped: {dupes}")
    manifest["unique_wavs"] = len(digests)
    manifest["source_recordings"] = sorted(
        {t for w in manifest["words"].values() for t in w["tokens"]})
    manifest["honest_note"] += (
        f" The {made} wavs are all distinct, but they are built from only "
        f"{len(manifest['source_recordings'])} distinct syllable recordings "
        f"(the dev pool is 1-6 tokens per class), so the effective sample is "
        f"smaller than the file count.")
    tmp2 = path + ".tmp"
    with open(tmp2, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1, ensure_ascii=False)
    os.replace(tmp2, path)
    log(f"[words] built {made} wavs ({len(digests)} unique) over "
        f"{len(WORDS)} word classes in {words_dir}, from "
        f"{len(manifest['source_recordings'])} DEV-split syllable recordings")
    return manifest


def load_manifest(words_dir=None):
    words_dir = words_dir or genome.FOOD_WORDS
    path = os.path.join(words_dir, "manifest.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    build()
