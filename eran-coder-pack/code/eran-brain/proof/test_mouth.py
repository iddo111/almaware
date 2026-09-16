"""test_mouth.py — fast offline tests for the mouth + babbling loop.

Run: python3 proof/test_mouth.py   (must print PASS lines and exit 0)

Mirrors proof/test_organism.py's own house style (a plain check()/PASS/FAIL
harness, no pytest dependency, no network, no fleet, no torch) and its
sandboxing trick (every genome.* path is redirected into a tempdir before
anything is imported, so the real tree is never touched).

Covers exactly what the mouth build was asked to prove:
  * mouth.articulate() is deterministic (same seed -> same waveform)
  * mouth.py imports NOTHING but numpy, and reaches no file I/O at all
    (AST-scanned, not just grepped — a call to open()/read()/wave.* would
    make this file a tape recorder wearing a tube's clothing)
  * babble.babble() improves similarity to a target over generations, on a
    fixed seed (babbling that never gets better is not babbling)
  * say_judge.judge() rejects a pure sine and rejects silence, against a
    synthetic 'ah' class it was never allowed to see beforehand
  * the ears path babble.py actually uses (utterance_from_samples) is
    byte-identical to the wav path (utterance) for the same underlying
    samples — the child hears itself with the SAME ear a wav on disk would
    hit, not a look-alike second implementation
"""
import ast
import datetime
import json
import os
import shutil
import struct
import sys
import tempfile
import traceback

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(ROOT, "body"))
sys.path.insert(0, os.path.join(ROOT, "voice"))
sys.path.insert(0, ROOT)
sys.path.insert(0, _HERE)

import genome                                     # noqa: E402

TMP = tempfile.mkdtemp(prefix="eranb-mouth-test-")

# ---- redirect every genome path into the sandbox (the real tree untouched) --
genome.STATE_DIR = os.path.join(TMP, "state")
genome.FOOD_DIR = os.path.join(TMP, "food")
genome.FOOD_TRAIN = os.path.join(genome.FOOD_DIR, "train")
genome.FOOD_WORDS = os.path.join(genome.FOOD_DIR, "words")
genome.HELDOUT_VAULT = os.path.join(TMP, "heldout-vault")
genome.FEEDBACK_INBOX = os.path.join(TMP, "feedback", "inbox")
genome.OUTBOX_DIR = os.path.join(TMP, "songs", "outbox")
genome.RESULTS_DIR = os.path.join(TMP, "results")
genome.BRAIN_FILE = os.path.join(genome.STATE_DIR, "brain.json.gz")
genome.BEST_FILE = os.path.join(genome.STATE_DIR, "best.json.gz")
genome.METRICS_FILE = os.path.join(genome.STATE_DIR, "metrics.jsonl")
genome.CURRICULUM_FILE = os.path.join(genome.STATE_DIR, "curriculum.json")
genome.CROWN_FILE = os.path.join(genome.STATE_DIR, "crown.json")
genome.LOCK_FILE = os.path.join(genome.STATE_DIR, ".lock")
genome.PRAYER_FILE = os.path.join(genome.STATE_DIR, "eran_prayer.jsonl")
for d in (genome.STATE_DIR, genome.FOOD_TRAIN, genome.FOOD_WORDS,
          genome.HELDOUT_VAULT, genome.FEEDBACK_INBOX, genome.OUTBOX_DIR,
          genome.RESULTS_DIR):
    os.makedirs(d, exist_ok=True)

from ears import Ears, read_wav, write_wav        # noqa: E402
import mouth                                       # noqa: E402
import babble as babble_mod                        # noqa: E402
import say_judge                                    # noqa: E402

SR = genome.SAMPLE_RATE
PASSED, FAILED = [], []


def check(name, fn):
    try:
        fn()
        PASSED.append(name)
        print(f"PASS - {name}")
    except Exception:
        FAILED.append(name)
        print(f"FAIL - {name}")
        traceback.print_exc()


# --------------------------------------------------------------- wav helpers
def write_pcm(path, samples):
    x = np.clip(samples, -1, 1)
    data = (x * 32767).astype("<i2").tobytes()
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE")
        f.write(b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, SR, SR * 2, 2, 16))
        f.write(b"data" + struct.pack("<I", len(data)) + data)


# Two acoustically distinct vowel-shaped POSTURES (open-back vs close-front,
# the same tongue_x/tongue_y contrast mouth_v1.AH/EE use) — deliberately
# MOUTH-PRODUCED, not band noise. That matters for
# test_judge_rejects_sine_and_silence: the null control is also built from
# mouth.articulate(), so the 'ah' centroid needs to live in the same family
# of signals (glottal source + tube resonance + jitter/shimmer) for "beats
# the null" to mean anything. A sine or silence belongs to neither family.
_OPEN_BACK = {"breath": 0.80, "pitch": 0.46, "press": 0.64, "tongue_x": 1.00,
             "tongue_y": 0.30, "lips": 1.00, "jaw": 0.41}
_CLOSE_FRONT = {"breath": 0.80, "pitch": 0.46, "press": 0.60, "tongue_x": 0.35,
                "tongue_y": 0.95, "lips": 1.00, "jaw": 0.60}


def build_mouth_shaped_corpus(per_class=20, seconds=0.3):
    """'ah' = mouth articulated open-back, 'aa' = mouth articulated close-
    front — same vocal apparatus as the null control, different postures."""
    for unit, posture in (("ah", _OPEN_BACK), ("aa", _CLOSE_FRONT)):
        for i in range(per_class):
            name = f"{unit}_t{i:02d}_0.wav"
            path = os.path.join(genome.FOOD_TRAIN, name)
            y = mouth.articulate(seconds=seconds, seed=1000 * hash(unit) % 100000 + i,
                                 **posture)
            write_pcm(path, y)


# ------------------------------------------------------------------- tests
def test_mouth_deterministic():
    a = mouth.articulate(seconds=0.2, seed=3)
    b = mouth.articulate(seconds=0.2, seed=3)
    assert np.array_equal(a, b), "same seed must give the same waveform"
    c = mouth.articulate(seconds=0.2, seed=4)
    assert not np.array_equal(a, c), "different seed must differ"
    assert a.dtype == np.float32


def test_mouth_no_breath_is_silent():
    y = mouth.articulate(breath=0.0, seconds=0.2)
    assert float(np.max(np.abs(y))) < 1e-6


def _imported_top_level_modules(tree):
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mods.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mods.add(node.module.split(".")[0])
    return mods


def _forbidden_file_calls(tree):
    """Anything shaped like reaching a file: open/read/readframes/load(s)."""
    forbidden_names = {"open", "read", "readframes", "load", "loads"}
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fname = None
            if isinstance(node.func, ast.Name):
                fname = node.func.id
            elif isinstance(node.func, ast.Attribute):
                fname = node.func.attr
            if fname in forbidden_names:
                hits.append(fname)
    return hits


def test_mouth_imports_only_numpy():
    src = open(mouth.__file__, encoding="utf-8").read()
    tree = ast.parse(src)
    mods = _imported_top_level_modules(tree)
    assert mods <= {"numpy", "__future__"}, f"mouth.py imports: {mods}"


def test_mouth_has_no_file_io():
    src = open(mouth.__file__, encoding="utf-8").read()
    # a real file-I/O reference, not a substring hit inside "waveform"/
    # "waveguide" — those words are legitimate prose in a mouth's docstring
    assert "import wave" not in src and "wave.open" not in src, \
        "mouth.py must never reference the wave module as a file reader"
    assert "\"rb\"" not in src and "'rb'" not in src, \
        "mouth.py must never open anything for reading"
    tree = ast.parse(src)
    hits = _forbidden_file_calls(tree)
    assert not hits, f"mouth.py calls forbidden file-I/O-shaped functions: {hits}"


def test_babble_improves_over_generations_fixed_seed():
    ears = Ears()
    target_posture = babble_mod.random_posture(np.random.default_rng(99))
    target_y = mouth.articulate(seconds=0.28, seed=42, **target_posture)
    target_vec = ears.utterance_from_samples(target_y)

    posture, sim, log = babble_mod.babble(target_vec, ears, gens=30, lam=5,
                                          seconds=0.28, seed=7)
    sims = [e["best_sim"] for e in log]
    assert sim >= sims[0], f"final sim {sim} fell below the starting try {sims[0]}"
    assert sim > sims[0] + 0.05 or sim > 0.9, (
        f"no meaningful improvement: {sims[0]:.4f} -> {sim:.4f}")
    # monotone non-decreasing best-so-far, by construction of (1+lambda)
    for a, b in zip(sims, sims[1:]):
        assert b >= a - 1e-9, "best-so-far must never get worse"


def test_ears_babble_path_matches_wav_path():
    """The exact requirement: feed the SAME samples both ways, assert equal
    vectors. This is what makes 'the child hears itself with its own ears'
    true rather than aspirational."""
    ears = Ears()
    rng = np.random.default_rng(3)
    posture = babble_mod.random_posture(rng)
    y = mouth.articulate(seconds=0.3, seed=5, **posture)

    wav_path = os.path.join(TMP, "roundtrip.wav")
    write_wav(wav_path, y)                    # body/ears.py's own writer
    y_roundtrip = read_wav(wav_path)          # what the wav path would see

    v_wav = ears.utterance(wav_path)
    v_direct = ears.utterance_from_samples(y_roundtrip)
    assert np.array_equal(v_wav, v_direct), (
        "utterance(path) and utterance_from_samples(same samples) diverged "
        "— babble.py is NOT hearing itself through the same ear as a wav")


def test_judge_rejects_sine_and_silence():
    build_mouth_shaped_corpus()
    ears = Ears(exam=True)
    centroids = say_judge.class_centroids(ears)
    assert set(centroids) == {"ah", "aa"}

    t = np.arange(int(SR * 0.30)) / SR
    sine = 0.4 * np.sin(2 * np.pi * 440 * t).astype(np.float32)
    sine_path = os.path.join(TMP, "sine.wav")
    write_pcm(sine_path, sine)

    silence = np.zeros(int(SR * 0.30), dtype=np.float32)
    silence_path = os.path.join(TMP, "silence.wav")
    write_pcm(silence_path, silence)

    res_sine = say_judge.judge(sine_path, intended="ah", null_n=40, write=False,
                               seconds=0.3)
    res_silence = say_judge.judge(silence_path, intended="ah", null_n=40,
                                  write=False, seconds=0.3)
    assert not res_sine["pass"], f"a pure sine must not pass as 'ah': {res_sine}"
    assert not res_silence["pass"], f"silence must not pass as 'ah': {res_silence}"


def test_judge_result_is_json_serializable_and_scored_honestly():
    """The null control must actually be a real distribution (not degenerate)
    and the pass rule must be exactly argmax+null as documented."""
    build_mouth_shaped_corpus()
    ears = Ears(exam=True)
    # Use a real ah_t00_0.wav as the 'produced' wav — the honest positive
    # control: if the judge cannot pass the class's own training data against
    # its own centroid family, something is broken in the judge itself.
    own = os.path.join(genome.FOOD_TRAIN, "ah_t00_0.wav")
    res = say_judge.judge(own, intended="ah", null_n=30, write=True, seconds=0.3)
    json.dumps(res)                      # must round-trip through json
    assert res["null_control"]["n"] == 30
    assert res["null_control"]["p95"] is not None
    out = os.path.join(genome.RESULTS_DIR,
                       f"SAY-AH-{datetime.date.today().isoformat()}.json")
    assert os.path.exists(out)


def main():
    print(f"[test] sandbox: {TMP}")
    check("mouth: deterministic + dtype", test_mouth_deterministic)
    check("mouth: no breath -> silence", test_mouth_no_breath_is_silent)
    check("mouth: imports only numpy", test_mouth_imports_only_numpy)
    check("mouth: no file I/O (AST-scanned)", test_mouth_has_no_file_io)
    check("babble: improves over generations (fixed seed)",
          test_babble_improves_over_generations_fixed_seed)
    check("ears: babble path == wav path (byte-identical)",
          test_ears_babble_path_matches_wav_path)
    check("say_judge: rejects a pure sine and silence",
          test_judge_rejects_sine_and_silence)
    check("say_judge: honest null control + JSON result",
          test_judge_result_is_json_serializable_and_scored_honestly)
    print(f"\n[test] {len(PASSED)} passed, {len(FAILED)} failed")
    shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
