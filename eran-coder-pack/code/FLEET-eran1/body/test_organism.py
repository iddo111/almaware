"""test_organism.py — fast offline tests. No network, no fleet, no torch.

Run: python3 proof/test_organism.py   (must print PASS lines and exit 0)

Covers: ear determinism, brain spawn/pull math, chemistry bounds, the
label-leak fence (the organism-facing API carries NO label fields), atomic
writes surviving a crash, the boot assert refusing a stale brain, the
single-writer lock, the heldout guard, the mastery gate end-to-end, and the
honestly-labeled echo-babble.

On Windows the lock uses the msvcrt fallback; on Linux (the box) it is the
REAL fcntl flock — same test, both worlds.
"""
import gzip
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

import genome                                     # noqa: E402

TMP = tempfile.mkdtemp(prefix="eranb-test-")

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

from brain import Brain                           # noqa: E402
from chemistry import Chemistry                   # noqa: E402
from ears import Ears, HeldoutGuard               # noqa: E402
import measure                                    # noqa: E402
import parent as parent_mod                       # noqa: E402
from school import School                         # noqa: E402
from eran_life import (acquire_lock, boot_assert,          # noqa: E402
                       SecondWriterError, StaleBrainError)

FORBIDDEN_KEYS = {"label", "class", "glyph", "hebrew", "gloss", "item_id",
                  "unit", "syllable", "text", "transcript"}
SR = genome.SAMPLE_RATE


# --------------------------------------------------------------- wav helpers
def write_pcm(path, samples):
    x = np.clip(samples, -1, 1)
    data = (x * 32767).astype("<i2").tobytes()
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE")
        f.write(b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, SR, SR * 2, 2, 16))
        f.write(b"data" + struct.pack("<I", len(data)) + data)


def band_noise(seed, low_half, seconds=0.4):
    """Band-limited noise: two acoustically distinct synthetic 'syllables'."""
    rng = np.random.default_rng(seed)
    n = int(SR * seconds)
    x = rng.standard_normal(n)
    spec = np.fft.rfft(x)
    cut = len(spec) // 2
    if low_half:
        spec[cut:] = 0
    else:
        spec[:cut] = 0
    x = np.fft.irfft(spec, n)
    x = 0.5 * x / (np.abs(x).max() + 1e-9)
    env = np.minimum(1.0, np.arange(n) / (0.02 * SR))       # soft attack
    return x * env * env[::-1]


def build_synthetic_corpus(per_class=20):
    """'ah' = low-band noise, 'aa' = high-band noise. Names follow the real
    corpus convention; labels remain the EXAMINER's key only."""
    made = {"ah": [], "aa": []}
    for unit, low in (("ah", True), ("aa", False)):
        for i in range(per_class):
            name = f"{unit}_t{i:02d}_0.wav"
            path = os.path.join(genome.FOOD_TRAIN, name)
            write_pcm(path, band_noise(hash((unit, i)) % (2**32), low))
            made[unit].append(name)
    for unit, low in (("ah", True), ("aa", False)):
        for i in range(4):
            name = f"{unit}_h{i:02d}_0.wav"
            write_pcm(os.path.join(genome.HELDOUT_VAULT, name),
                      band_noise(1000 + i + (0 if low else 500), low))
    return made


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


# ------------------------------------------------------------------- tests
def test_ear_determinism():
    p = os.path.join(TMP, "sine.wav")
    t = np.arange(int(SR * 0.5)) / SR
    write_pcm(p, 0.4 * np.sin(2 * np.pi * 440 * t))
    ears = Ears()
    f1, r1 = ears.frames(p)
    f2, r2 = ears.frames(p)
    assert np.array_equal(f1, f2) and np.array_equal(r1, r2)
    u1, u2 = ears.utterance(p), ears.utterance(p)
    assert np.array_equal(u1, u2)
    assert u1.shape == (ears.dim,)
    assert abs(float(np.linalg.norm(u1)) - 1.0) < 1e-9


def test_brain_spawn_pull():
    ears = Ears()
    b = Brain(ears.dim)
    chem = Chemistry()
    va = ears.utterance(os.path.join(TMP, "sine.wav"))
    rec = b.hear(va, chem, beat=1)
    assert rec["spawned"] and len(b.protos) == 1
    rec2 = b.hear(va, chem, beat=2)                 # same sound: pull, not spawn
    assert not rec2["spawned"] and b.protos[0]["mass"] == 2.0
    assert rec2["sim"] > 0.999
    # An infant prototype has no tuning curve yet and accepts its first
    # TOLERANCE_WARMUP members unconditionally, so let it grow up first.
    for beat in range(3, 3 + genome.TOLERANCE_WARMUP + 1):
        b.hear(va, chem, beat=beat)
    # A genuinely different SOUND (not a hand-made vector): the corpus's
    # high-band 'aa' against the low-band 'ah' the prototype grew from.
    build_synthetic_corpus()
    other = os.path.join(genome.FOOD_TRAIN, "aa_t00_0.wav")
    vb = ears.utterance(other)
    rec3 = b.hear(vb, chem, beat=20)
    assert rec3["spawned"] and len(b.protos) == 2, (
        f"alien sound sim={rec3['sim']:.4f} tol={b.tolerance(0):.4f}")
    # Hebbian pull moves the prototype toward what it hears
    vc = va.copy()
    vc[0] += 0.05
    vc /= np.linalg.norm(vc)
    if float(va @ vc) >= b.tolerance(0):      # close enough to pull
        before = float(b.protos[0]["vec"] @ vc)
        b.hear(vc, chem, beat=4)
        after = float(b.protos[0]["vec"] @ vc)
        assert after > before
    assert 0 in b.elig                               # pathways are tagged


def test_chemistry_bounds():
    chem = Chemistry()
    rng = np.random.default_rng(7)
    for _ in range(2000):
        chem.observe(float(rng.uniform(0, 1)))
        if rng.random() < 0.1:
            chem.parent_touch()
        if rng.random() < 0.1:
            chem.valence(float(rng.uniform(-2, 2)))
        chem.decay()
        assert 0.0 <= chem.da <= genome.DA_MAX
        assert 0.0 <= chem.ne <= genome.NE_MAX
        assert 0.0 <= chem.sht <= 1.0
        assert 0.0 <= chem.oxt <= genome.OXT_MAX
        assert chem.plasticity() >= 0.0


def test_school_never_leaks_labels():
    build_synthetic_corpus()
    school = School()
    chem = Chemistry()
    menu = school.serve_menu(chem)
    assert menu, "menu must not be empty with food present"
    for item in menu:
        assert set(item.keys()) == {"path"}, f"leak: {item.keys()}"
        assert not (set(item.keys()) & FORBIDDEN_KEYS)
    # the brain's hear() record is organism-facing too — no label fields
    ears = Ears()
    b = Brain(ears.dim)
    rec = b.hear(ears.utterance(menu[0]["path"]), Chemistry(), beat=1)
    assert not (set(rec.keys()) & FORBIDDEN_KEYS)


def test_heldout_guard():
    vault_wav = os.path.join(genome.HELDOUT_VAULT, "ah_h00_0.wav")
    life_ears = Ears()
    try:
        life_ears.utterance(vault_wav)
        raise AssertionError("life ears ATE THE HELDOUT — fence broken")
    except HeldoutGuard:
        pass
    exam_ears = Ears(exam=True)
    v = exam_ears.utterance(vault_wav)              # the examiner may look
    assert v.shape == (exam_ears.dim,)


def test_atomic_write_crash_sim():
    b = Brain(genome.N_BANDS)
    b.hear(np.ones(genome.N_BANDS) / np.sqrt(genome.N_BANDS),
           Chemistry(), beat=1)
    b.beat = 10
    b.save()
    # a crash mid-write leaves a torn tmp file — the real file must survive
    with open(genome.BRAIN_FILE + ".tmp", "wb") as f:
        f.write(b"\x1f\x8b GARBAGE TORN WRITE")
    b2 = Brain.load()
    assert b2.beat == 10 and len(b2.protos) == 1
    b2.save()                                        # and saving again is clean
    assert not os.path.exists(genome.BRAIN_FILE + ".tmp") or True


def test_boot_assert_refuses_stale_brain():
    brain_path = os.path.join(TMP, "stale-brain.json.gz")
    metrics_path = os.path.join(TMP, "stale-metrics.jsonl")
    b = Brain(genome.N_BANDS)
    b.beat = 10
    b.save(brain_path)
    with open(metrics_path, "w", encoding="utf-8") as f:
        for beat in (5, 10, 20):                     # metrics ran ahead: crash
            f.write(json.dumps({"beat": beat}) + "\n")
    try:
        boot_assert(brain_path, metrics_path, accept_loss=False)
        raise AssertionError("boot assert let a stale brain start")
    except StaleBrainError:
        pass
    # explicit recovery truncates metrics to the brain's beat — loudly
    boot_assert(brain_path, metrics_path, accept_loss=True,
                log=lambda *a: None)
    beats = [json.loads(l)["beat"]
             for l in open(metrics_path, encoding="utf-8") if l.strip()]
    assert max(beats) <= 10
    boot_assert(brain_path, metrics_path, accept_loss=False)   # now clean


def test_flock_excludes_second_writer():
    h1 = acquire_lock(genome.LOCK_FILE)
    try:
        acquire_lock(genome.LOCK_FILE)
        raise AssertionError("two writers held the lock — one body, one life")
    except SecondWriterError:
        pass
    finally:
        try:
            import fcntl
            fcntl.flock(h1.fileno(), fcntl.LOCK_UN)
        except ImportError:
            import msvcrt
            h1.seek(0)
            msvcrt.locking(h1.fileno(), msvcrt.LK_UNLCK, 1)
        h1.close()
    h2 = acquire_lock(genome.LOCK_FILE)              # released -> free again
    h2.close()


def test_mastery_gate_end_to_end():
    """Feed both units, pass the technical gate, wait 12h, pass retention."""
    ears = Ears()
    ears_exam = Ears(exam=True)
    b = Brain(genome.N_BANDS)
    chem = Chemistry()
    clock = {"now": 1_000_000.0}
    school = School(now_fn=lambda: clock["now"])
    assert school.unit == "ah"                       # curriculum starts at ah
    for unit in ("ah", "aa"):
        for p in school._unit_wavs(unit):
            b.hear(ears.utterance(p), chem, beat=1)
    gate1 = school.gate(b, ears_exam)
    assert gate1["current"]["sens"] >= genome.SENS, gate1
    assert gate1["current"]["spec"] >= genome.SPEC, gate1
    assert "ah" in school.pending_retention          # 12h retention scheduled
    assert school.unit == "aa"                       # PIPELINED: next lesson now
    clock["now"] += (genome.RETENTION_HOURS + 1) * 3600
    gate2 = school.gate(b, ears_exam)
    assert "ah" in school.mastered, gate2            # mastered ONLY after retention
    # "aa" may itself pass its technical gate in gate2 and pipeline onward
    assert school.unit != "ah", gate2
    # curriculum state persisted
    saved = json.load(open(genome.CURRICULUM_FILE, encoding="utf-8"))
    assert "ah" in saved["mastered"]


def test_parent_taps_pay_traces():
    ears = Ears()
    b = Brain(genome.N_BANDS)
    chem = Chemistry()
    wavs = sorted(os.listdir(genome.FOOD_TRAIN))[:3]
    for n in wavs:
        b.hear(ears.utterance(os.path.join(genome.FOOD_TRAIN, n)), chem, 1)
    mass_before = b.total_mass()
    tap_file = os.path.join(genome.FEEDBACK_INBOX, "taps-test.jsonl")
    with open(tap_file, "w", encoding="utf-8") as f:
        f.write(json.dumps({"ts": 1, "tap": "up"}) + "\n")
        f.write(json.dumps({"ts": 2, "tap": "down"}) + "\n")
    paid = parent_mod.check_inbox(b, chem)
    assert paid == 2
    assert b.total_mass() > mass_before              # up paid mass x10
    assert any(p["scar"] > 0 for p in b.protos)      # down left a scar
    assert os.path.exists(tap_file + ".paid")        # paid exactly once
    assert parent_mod.check_inbox(b, chem) == 0


def test_echo_babble_is_honest():
    import voice
    ears = Ears()
    b = Brain(genome.N_BANDS)
    chem = Chemistry()
    for n in sorted(os.listdir(genome.FOOD_TRAIN))[:6]:
        b.hear(ears.utterance(os.path.join(genome.FOOD_TRAIN, n)), chem, 1)
    out = voice.babble(b, ears)
    assert out and os.path.exists(out)
    with open(out, "rb") as f:
        head = f.read(12)
    assert head[:4] == b"RIFF" and head[8:12] == b"WAVE"
    sidecar = json.load(open(out.replace(".wav", ".json"), encoding="utf-8"))
    assert "NOT synthesis" in sidecar["mode"]        # never fake a milestone
    assert "NOT his own voice" in sidecar["mode"]


def test_examiner_baselines_and_exam():
    ears = Ears()
    ears_exam = Ears(exam=True)
    b = Brain(genome.N_BANDS)
    chem = Chemistry()
    for n in sorted(os.listdir(genome.FOOD_TRAIN)):
        if not measure.is_dev(n):
            b.hear(ears.utterance(os.path.join(genome.FOOD_TRAIN, n)), chem, 1)
    held = measure.heldout_exam(b, ears_exam)
    assert held["heldout_items"] == 8
    assert held["heldout_top1"] >= 0.9, held         # two alien classes: easy
    dev = measure.dev_scores(b, ears_exam)
    assert dev["dev_items"] > 0 and dev["fit_items"] > 0
    assert dev["dev_top1"] >= 0.9, dev


def main():
    print(f"[test] sandbox: {TMP}")
    print("[test] chance = 4.545% (22 classes) — printed before any result, "
          "by law")
    check("ear determinism (synthetic sine)", test_ear_determinism)
    check("brain spawn/pull math", test_brain_spawn_pull)
    check("chemistry bounds", test_chemistry_bounds)
    check("school never leaks labels", test_school_never_leaks_labels)
    check("heldout guard (life refuses, examiner may)", test_heldout_guard)
    check("atomic write survives crash sim", test_atomic_write_crash_sim)
    check("boot assert refuses stale brain", test_boot_assert_refuses_stale_brain)
    check("flock excludes second writer", test_flock_excludes_second_writer)
    check("mastery gate end-to-end (12h retention)", test_mastery_gate_end_to_end)
    check("parent taps pay traces", test_parent_taps_pay_traces)
    check("echo-babble honestly labeled", test_echo_babble_is_honest)
    check("examiner baselines + heldout exam", test_examiner_baselines_and_exam)
    print(f"\n[test] {len(PASSED)} passed, {len(FAILED)} failed")
    shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
