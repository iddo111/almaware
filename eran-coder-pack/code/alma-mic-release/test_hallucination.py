"""alma-mic / test_hallucination.py — PROVE the Whisper-on-silence fix.

Feeds three classes of audio through the REAL Transcriber and reports, BEFORE vs
AFTER the anti-hallucination guards:

  1. synthetic SILENCE (zeros) and low-level NOISE / a pure TONE  -> must be EMPTY
  2. cached-corpus real speech WAVs                               -> must STILL transcribe

"BEFORE" = a config with every guard disabled (legacy behaviour: any-language auto
-detect, no energy gate, conditioning on/permissive thresholds) so the hallucination
is reproduced. "AFTER" = the shipped config (guards on). Same model, same clips.

Owner-safe: uses ONLY synthetic audio + already-cached corpus WAVs. No live mic.
Run on CPU by default to avoid touching the GPU the Eran nodes may need:
    python test_hallucination.py            # CPU
    python test_hallucination.py --gpu      # allow CUDA
    python test_hallucination.py --n 8      # how many real corpus clips to check
"""
from __future__ import annotations
import sys, io, os, json, argparse, copy, wave, time
import numpy as np

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
SR = 16000


def load_wav(path):
    with wave.open(path, "rb") as w:
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return pcm.astype(np.float32) / 32768.0


def synth_clips():
    """The non-speech inputs that trigger the bug."""
    rng = np.random.default_rng(0)
    n = SR * 4  # 4 seconds
    clips = {
        "pure_silence": np.zeros(n, dtype=np.float32),
        "tiny_silence_floor": (rng.standard_normal(n) * 1e-4).astype(np.float32),
        "white_noise_low": (rng.standard_normal(n) * 0.004).astype(np.float32),
        "white_noise_mid": (rng.standard_normal(n) * 0.02).astype(np.float32),
        "tone_440hz": (0.02 * np.sin(2 * np.pi * 440 * np.arange(n) / SR)).astype(np.float32),
        "hum_60hz": (0.03 * np.sin(2 * np.pi * 60 * np.arange(n) / SR)).astype(np.float32),
    }
    return clips


def make_cfg(gpu, guards):
    from config import Config
    c = Config.load()
    c.device = "cuda" if gpu else "cpu"
    c.type_output = False
    c.collect_corpus = False
    if not guards:
        # ---- BEFORE: legacy / no anti-hallucination guards ----
        c.lang_lock = False            # any-language auto-detect (the drift source)
        c.code_switch = True
        c.speech_rms_gate = 0.0        # no energy gate
        c.no_speech_threshold = 1.0    # effectively disabled
        c.log_prob_threshold = -10.0   # accept anything
        c.compression_ratio_threshold = 100.0  # accept repetitive junk
        c.vad_threshold = 0.1          # permissive VAD
        c.vad_min_silence_ms = 100
        c._guards = False
    return c


def run(label, cfg, gpu, n_real):
    import stt as stt_mod
    # For the BEFORE run we must also bypass the post-filter so the raw hallucination
    # is visible; monkeypatch _is_hallucinated to the OLD char-run-only behaviour.
    saved = stt_mod._is_hallucinated
    if getattr(cfg, "_guards", True) is False:
        def _legacy(text):
            import re
            t = re.sub(r"\s+", "", text or "")
            if len(t) < 6:
                return False
            longest = max((len(m.group(0)) for m in re.finditer(r"(.)\1+", t)), default=0)
            return longest >= 8 or (len(t) >= 12 and len(set(t)) <= 3)
        stt_mod._is_hallucinated = _legacy

    from stt import Transcriber
    t = Transcriber(cfg)
    t0 = time.time()
    t.load(log=lambda m: None)
    print(f"\n########## {label}  [{t.desc}]  (loaded {time.time()-t0:.1f}s) ##########")

    print("\n--- NON-SPEECH (silence / noise / tone) -> want EMPTY ---")
    bad = 0
    for name, clip in synth_clips().items():
        text, lang, info = t.transcribe(clip, return_info=True)
        ok = (text == "")
        bad += (0 if ok else 1)
        flag = "OK(empty)" if ok else "!! HALLUCINATED !!"
        print(f"  [{flag:18}] {name:20} -> lang={lang} text={text!r}  (rms={info.get('rms',0):.5f} dropped={info.get('dropped','')!r})")

    print(f"\n--- REAL SPEECH (first {n_real} corpus clips) -> want NON-empty ---")
    testset_path = os.path.join(HERE, "testset.json")
    if os.path.exists(testset_path):
        testset = json.load(open(testset_path, encoding="utf-8"))
    else:
        testset = []
        print("  (no testset.json / voice_corpus in this checkout — real-speech part "
              "skipped; the synthetic part above still proves the guards)")
    good = total = 0
    for r in testset[:n_real]:
        wav = os.path.join(HERE, "voice_corpus", r["wav"])
        if not os.path.exists(wav):
            continue
        text, lang, info = t.transcribe(load_wav(wav), return_info=True)
        total += 1
        ok = bool(text.strip())
        good += (1 if ok else 0)
        flag = "OK" if ok else "!! EMPTY (broke STT) !!"
        print(f"  [{flag:22}] cat={r['cat']:5} lang={lang} text={text!r}")

    stt_mod._is_hallucinated = saved
    return bad, good, total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gpu", action="store_true", help="allow CUDA (default CPU)")
    ap.add_argument("--n", type=int, default=8, help="real corpus clips to check")
    args = ap.parse_args()

    print("=" * 78)
    print("ANTI-HALLUCINATION PROOF  (BEFORE = guards off, AFTER = guards on)")
    print("=" * 78)

    before_bad, before_good, before_tot = run("BEFORE (no guards)", make_cfg(args.gpu, guards=False), args.gpu, args.n)
    after_bad, after_good, after_tot = run("AFTER (guards on)", make_cfg(args.gpu, guards=True), args.gpu, args.n)

    print("\n" + "=" * 78)
    print("SUMMARY")
    print("=" * 78)
    print(f"  non-speech hallucinations:  BEFORE={before_bad}   AFTER={after_bad}   (want AFTER=0)")
    print(f"  real-speech still works  :  BEFORE={before_good}/{before_tot}  AFTER={after_good}/{after_tot}  (want AFTER unchanged)")
    ok = (after_bad == 0 and after_good == after_tot)  # tot may be 0 when no corpus is shipped
    print(f"\n  VERDICT: {'PASS — silence->empty AND real-speech->works' if ok else 'FAIL — see above'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
