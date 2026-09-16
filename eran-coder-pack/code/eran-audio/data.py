"""
data.py — ERAN v2's heard world.

THE PHILOSOPHY (Iddo, 2026-06-18):
    "אם הוא שומע מה שאני שומע, ערן, זה לא זיהום סביבתי.
     זה מה שאני רוצה, שיגדל כמו תינוק."
    "If Eran hears what I hear — that is NOT environmental contamination.
     That is what I WANT: that he grows like a baby."

So this loader feeds Eran EVERYTHING in his sound collection — his own voice AND
the world around it (other people, music, TV, the room, phone calls). A baby does
not get a gated, cleaned audio feed; it hears its whole world and slowly makes
sense of it. We do NOT speaker-gate, we do NOT denoise, we do NOT drop "noisy"
clips. Every real recorded moment of sound is welcome.

(The ONLY thing refused is non-heard, synthetic/text data — Eran learns from
SOUND that was actually heard, never from a book corpus. Same spirit as v1.)

Pipeline:
    samples/*.wav  --(EnCodec cochlea, on CPU)-->  flat audio-token stream
The stream is cached to tokens_cache.npy so training is instant; new recordings
are folded in incrementally on rescan (the 24/7 collection keeps growing => Eran
keeps hearing more of his life).
"""

import os
import json
import glob
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_NPY = os.path.join(HERE, "tokens_cache.npy")
MANIFEST = os.path.join(HERE, "tokens_manifest.json")

# refuse anything that is not actually-heard sound (no book/synthetic corpora)
_FORBIDDEN = ("eran-corpus", "eran_all_corpus", "books", "wiki", "ben-yehuda", "synthetic_tts")


def _list_wavs(cfg):
    """All heard sound, in a STABLE order: the mic's voice/ambient collection first,
    then any curated 'heard music' (classical, Jewish songs Iddo plays him). Music is
    part of the baby's world too — appended AFTER the voice so the incremental cache
    stays valid as the voice collection grows."""
    dirs = [cfg["samples_dir"]] + list(cfg.get("extra_audio_dirs", []))
    out = []
    for d in dirs:
        for p in sorted(glob.glob(os.path.join(d, "*.wav"))):
            low = p.lower().replace("\\", "/")
            if any(tok in low for tok in _FORBIDDEN):
                continue  # HARD GUARD: never the books — only real heard sound
            out.append(p)
    return out


def _load_manifest():
    if os.path.exists(MANIFEST):
        try:
            with open(MANIFEST, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def _save_manifest(files, n_tokens):
    try:
        with open(MANIFEST, "w", encoding="utf-8") as f:
            json.dump({"files": files, "n_tokens": int(n_tokens),
                       "n_files": len(files)}, f, ensure_ascii=False)
    except Exception:
        pass


def build_token_stream(cfg, cochlea=None, verbose=True, max_new=None):
    """Return a 1-D np.int64 array of ALL heard audio tokens.

    Uses tokens_cache.npy when the wav set is unchanged. Otherwise encodes the
    new wavs (EnCodec, CPU) and appends — incremental, so a growing collection
    never re-encodes everything. Pass a shared `cochlea` to avoid reloading it.
    """
    files = _list_wavs(cfg)
    manifest = _load_manifest()

    # fast path: nothing changed -> just load the cache
    if manifest and manifest.get("files") == files and os.path.exists(CACHE_NPY):
        toks = np.load(CACHE_NPY)
        if verbose:
            print(f"[data] cache hit: {len(files)} wavs -> {toks.size:,} audio tokens "
                  f"({toks.size/cfg['codec']['frame_rate']/cfg['codec']['n_codebooks']:.0f}s of heard sound)")
        return toks.astype(np.int64)

    # need to (re)encode -> load the cochlea on CPU (mic always wins the GPU)
    if cochlea is None:
        from cochlea import Cochlea
        cochlea = Cochlea(device="cpu", cfg=cfg)

    import soundfile as sf
    from cochlea import resample_to_codec

    # incremental: keep tokens for files already in the manifest, encode the rest
    prev_files = manifest.get("files", []) if manifest else []
    have_cache = os.path.exists(CACHE_NPY) and prev_files and prev_files == files[:len(prev_files)]
    if have_cache:
        chunks = [np.load(CACHE_NPY).astype(np.int64)]
        todo = files[len(prev_files):]
        if verbose:
            print(f"[data] incremental: {len(prev_files)} cached, encoding {len(todo)} new wavs")
    else:
        chunks = []
        todo = files
        if verbose:
            print(f"[data] full encode: {len(todo)} wavs (one-time, on CPU)")

    if max_new is not None:
        todo = todo[:max_new]

    sr_codec = cfg["codec"]["sample_rate"]

    def _persist(n_done):
        """Write the cache + a manifest covering exactly the files encoded so far.
        Called periodically so progress is visible + crash-safe (not all-or-nothing)."""
        stream = np.concatenate(chunks) if chunks else np.zeros((0,), dtype=np.int64)
        covered = prev_files + todo[:n_done]
        try:
            tmp = CACHE_NPY + ".tmp.npy"
            np.save(tmp, stream.astype(np.int64))
            os.replace(tmp, CACHE_NPY)
            _save_manifest(covered, stream.size)
        except Exception as e:
            if verbose:
                print(f"[data] cache save failed: {e}")
        return stream

    done = 0
    for p in todo:
        try:
            wav, sr = sf.read(p, dtype="float32")
            if wav.ndim > 1:
                wav = wav.mean(axis=1)
            w = resample_to_codec(wav, sr, sr_codec)
            ids = cochlea.encode(w).numpy().astype(np.int64)
            if ids.size:
                chunks.append(ids)
            done += 1
            if done % 200 == 0:
                _persist(done)               # incremental checkpoint of the cache
                if verbose:
                    print(f"[data]   encoded {done}/{len(todo)} (cache flushed) ...", flush=True)
        except Exception as e:
            if verbose:
                print(f"[data]   skip {os.path.basename(p)}: {e}")

    stream = _persist(len(todo))
    if verbose:
        print(f"[data] heard-world stream: {stream.size:,} audio tokens from "
              f"{len(prev_files)+len(todo)} wavs")
    return stream


if __name__ == "__main__":
    import sys
    sys.path.insert(0, HERE)
    from train import load_config  # reuse loader
    cfg = load_config()
    n = None
    if len(sys.argv) > 1:
        n = int(sys.argv[1])
    s = build_token_stream(cfg, verbose=True, max_new=n)
    print("stream dtype", s.dtype, "len", s.size,
          "min", int(s.min()) if s.size else 0, "max", int(s.max()) if s.size else 0)
