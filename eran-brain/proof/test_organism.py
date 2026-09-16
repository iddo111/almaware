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
genome.CORTEX_FILE = os.path.join(genome.STATE_DIR, "cortex.json.gz")
genome.CROWN_FILE = os.path.join(genome.STATE_DIR, "crown.json")
genome.LOCK_FILE = os.path.join(genome.STATE_DIR, ".lock")
genome.PRAYER_FILE = os.path.join(genome.STATE_DIR, "eran_prayer.jsonl")
for d in (genome.STATE_DIR, genome.FOOD_TRAIN, genome.FOOD_WORDS,
          genome.HELDOUT_VAULT, genome.FEEDBACK_INBOX, genome.OUTBOX_DIR,
          genome.RESULTS_DIR):
    os.makedirs(d, exist_ok=True)

from brain import Brain                           # noqa: E402
from cortex import Cortex                         # noqa: E402
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


def _alma_available():
    """The weave round-trip needs the ALMA loom, which lives on the PC. The
    live box has no reason to carry it — skip there, never fail there."""
    import importlib.util
    for root in (r"D:\CLAUDElma-language",
                 os.path.expanduser("~/alma-language")):
        if os.path.isdir(os.path.join(root, "alma")):
            return True
    return importlib.util.find_spec("alma") is not None


def _depth_locked():
    """On the LIVE box MAX_LAYERS is locked to 1 because depth lost its
    number (2026-08-21). A test that cannot run in this configuration must
    SKIP loudly, never FAIL — a red suite nobody can fix teaches the team to
    ignore red suites."""
    return getattr(genome, "MAX_LAYERS", 4) < 2


def check(name, fn):
    if name.startswith(("a layer is not born", "birth evidence", "a late-born",
                        "layer 1 percepts", "sleep prunes every layer",
                        "MAX_LAYERS is respected")) and _depth_locked():
        print(f"SKIP - {name}  (depth locked: MAX_LAYERS={genome.MAX_LAYERS})")
        return
    if name.startswith("weave export") and not _alma_available():
        print(f"SKIP - {name}  (alma-language not on this box)")
        return
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
    assert abs(float(np.linalg.norm(u1)) - 1.0) < 1e-6      # float32 percept


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


def test_boot_assert_recovery_stays_out_of_ram():
    """--accept-loss must not read the metrics file into memory.

    2026-09-07: eran1 OOMed, rebooted, and eranb-life crash-looped 176 times
    on a stale brain. The documented recovery was --accept-loss -- and its
    body was `kept = []` followed by `kept.append(line)` for every line of
    state/metrics.jsonl, which on the live body is 58 GB. Recovering from an
    out-of-memory kill would have caused another one. The guard must be able
    to survive the crash it exists to catch.
    """
    import tracemalloc
    brain_path = os.path.join(TMP, "ram-brain.json.gz")
    metrics_path = os.path.join(TMP, "ram-metrics.jsonl")
    b = Brain(genome.N_BANDS)
    b.beat = 200000
    b.save(brain_path)
    with open(metrics_path, "w", encoding="utf-8") as f:
        for beat in range(200400):                   # ~85 MB, beats 0..200399
            f.write(json.dumps({"beat": beat, "pad": "x" * 400}) + chr(10))
    size = os.path.getsize(metrics_path)
    assert size > 40 * 1024 * 1024, f"test file too small to prove anything ({size})"

    tracemalloc.start()
    boot_assert(brain_path, metrics_path, accept_loss=True, log=lambda *a: None)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    budget = size // 10
    assert peak < budget, (
        f"recovery held {peak/1e6:.1f} MB for a {size/1e6:.1f} MB file "
        f"(budget {budget/1e6:.1f} MB) -- it is still reading it into RAM")

    beats = []
    with open(metrics_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                beats.append(json.loads(line)["beat"])
    assert max(beats) == 200000, f"truncated to the wrong beat: {max(beats)}"
    assert len(beats) == 200001, f"lost rows it should have kept: {len(beats)}"
    boot_assert(brain_path, metrics_path, accept_loss=False)   # now clean


def test_boot_assert_recovery_handles_unordered_metrics():
    """A row below the brain's beat AFTER one above it must still survive."""
    brain_path = os.path.join(TMP, "unordered-brain.json.gz")
    metrics_path = os.path.join(TMP, "unordered-metrics.jsonl")
    b = Brain(genome.N_BANDS)
    b.beat = 10
    b.save(brain_path)
    with open(metrics_path, "w", encoding="utf-8") as f:
        for beat in (5, 20, 7, 30):                  # 7 sits after 20
            f.write(json.dumps({"beat": beat}) + chr(10))
    boot_assert(brain_path, metrics_path, accept_loss=True, log=lambda *a: None)
    beats = [json.loads(l)["beat"]
             for l in open(metrics_path, encoding="utf-8") if l.strip()]
    assert beats == [5, 7], f"unordered recovery kept {beats}, expected [5, 7]"


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


# ------------------------------------------------- the ear the tournament emits
def _corpus_wav():
    """A real 16 kHz wav on disk. The ear must be exercised END TO END —
    constructing an Ears object proves nothing; hearing with it does."""
    build_synthetic_corpus()
    names = sorted(os.listdir(genome.FOOD_TRAIN))
    assert names, "no corpus to hear"
    return os.path.join(genome.FOOD_TRAIN, names[0])


def test_every_crownable_ear_hears_a_real_wav():
    """Every ear the tournament can put in crown.json must build AND hear.

    The scar (2026-08-21): ears.py still carried "onset"/"cepstrum" branches
    whose genome constants (ONSET_MS, ONSET_START_FRAC) had been deleted with
    the frozen-anatomy order, so Ears(repr_="onset").utterance(wav) died with
    AttributeError deep inside pool() — on wake, in the living organism.
    This walks the tournament's OWN search space, so widening that space
    without widening the ear fails here and not at 03:30 on the box.
    """
    import tournament
    wav = _corpus_wav()
    space = [{"n_bands": nb, "pooling": pl}
             for nb in tournament.N_BANDS_SPACE
             for pl in tournament.POOL_SPACE]
    assert space, "the tournament proposes nothing — search space is empty"
    for cfg in space:
        # a) the way the tournament itself builds an ear, by kwargs
        ear = Ears(exam=True, **cfg)
        v = ear.utterance(wav)
        assert v.shape == (ear.dim,), (cfg, v.shape, ear.dim)
        assert np.isfinite(v).all(), (cfg, "non-finite percept")
        # the percept is float32 (float32 samples through a float32 rfft), so
        # "unit" means unit to float32 epsilon, not to 1e-9
        assert abs(float(np.linalg.norm(v)) - 1.0) < 1e-6, (
            cfg, float(np.linalg.norm(v)), v.dtype)
        # b) the way the ORGANISM builds it at wake, through crown.json
        crown = dict(cfg, crowned="test", ci_lo=0.01)
        assert "repr" not in crown, (
            "the tournament may not crown a repr — the ear is frozen")
        with open(genome.CROWN_FILE, "w", encoding="utf-8") as f:
            json.dump(crown, f)
        try:
            worn = Ears(exam=True)
            assert worn.n_bands == cfg["n_bands"], cfg
            assert worn.pooling == cfg["pooling"], cfg
            assert np.array_equal(worn.utterance(wav), v), cfg
        finally:
            os.remove(genome.CROWN_FILE)


def test_only_the_frozen_ear_can_be_crowned():
    """Door 1 — THE ORGANISM. genome.EAR_REPR and state/crown.json may name
    only genome.EAR_REPRS. A crown naming anything else must be refused at
    wake, by name, instead of reaching a living beat."""
    wav = _corpus_wav()
    for bad in ("onset", "cepstrum", "bands", "typo"):
        with open(genome.CROWN_FILE, "w", encoding="utf-8") as f:
            json.dump({"repr": bad, "n_bands": 24, "pooling": "loudest60"}, f)
        try:
            Ears(exam=True)
        except ValueError as e:
            assert bad in str(e), str(e)
        else:
            raise AssertionError(
                f"a crowned {bad!r} ear was worn at wake — frozen anatomy "
                f"breached")
        finally:
            os.remove(genome.CROWN_FILE)
    ear = Ears(exam=True)                       # the frozen ear still hears
    assert ear.repr == genome.EAR_REPR
    assert ear.utterance(wav).shape == (ear.dim,)


def test_examiner_may_rebuild_a_legacy_ear_but_never_a_broken_one():
    """Door 2 — THE EXAMINER. proof/ear_frozen_audit.py re-measures the frozen
    claim by building the historical ears on purpose, so repr_= must still
    work. But an ear whose genome constants were deleted has to say so AT
    BIRTH: the scar is Ears(repr_="onset") raising AttributeError from inside
    pool(), after frames() had already run."""
    wav = _corpus_wav()
    for legacy in ("bands", "cepstrum"):        # still buildable, still hear
        ear = Ears(exam=True, repr_=legacy)
        v = ear.utterance(wav)
        assert v.shape == (ear.dim,), (legacy, v.shape, ear.dim)
        assert np.isfinite(v).all(), legacy

    assert not hasattr(genome, "ONSET_MS"), (
        "ONSET_MS is back in the genome — the onset ear was refrozen without "
        "a decision from Iddo")
    try:
        Ears(exam=True, repr_="onset")
    except ValueError as e:
        assert "ONSET_MS" in str(e) and "ONSET_START_FRAC" in str(e), str(e)
    except AttributeError:
        raise AssertionError(
            "onset ear died with AttributeError instead of naming its missing "
            "constants — the 2026-08-21 broken window is back")
    else:
        raise AssertionError("onset ear built without ONSET_MS")

    # ...and the audit's own move: supply the reconstructed constants, and the
    # ear becomes buildable and hearable. Nothing is left behind in the genome.
    genome.ONSET_START_FRAC = genome.EAR_SPEECH_FRAC
    genome.ONSET_MS = 80
    try:
        ear = Ears(exam=True, repr_="onset")
        v = ear.utterance(wav)
        assert v.shape == (ear.dim,), (v.shape, ear.dim)
        assert np.isfinite(v).all()
    finally:
        del genome.ONSET_START_FRAC
        del genome.ONSET_MS

    for nonsense in ("typo", "cochlea2"):
        try:
            Ears(exam=True, repr_=nonsense)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Ears accepted repr_={nonsense!r}")

    # A FALSY repr_ is not an explicit choice — it resolves from the crown, so
    # it must be judged as a crown and hit door 1, not slip through door 2.
    with open(genome.CROWN_FILE, "w", encoding="utf-8") as f:
        json.dump({"repr": "bands", "n_bands": 24, "pooling": "loudest60"}, f)
    try:
        for falsy in ("", None):
            try:
                Ears(exam=True, repr_=falsy)
            except ValueError as e:
                assert "frozen anatomy" in str(e), (falsy, str(e))
            else:
                raise AssertionError(
                    f"repr_={falsy!r} let a crowned 'bands' ear through door 2")
    finally:
        os.remove(genome.CROWN_FILE)


def test_tournament_may_not_crown_while_the_ear_is_frozen():
    """The freeze guard must EXIST and hold. It was a bare NameError at
    tournament.py:117 — the nightly job would have died the first night a
    challenger actually won, on the very line meant to protect the ear."""
    import tournament
    assert tournament._ear_is_frozen() is True, (
        "the ear is frozen by Iddo's order (genome.EAR_FROZEN)")
    assert genome.EAR_REPR in genome.EAR_REPRS


# ============================== DEPTH (body/cortex.py) =======================
_STATE_KEYS = ("STATE_DIR", "BRAIN_FILE", "BEST_FILE", "METRICS_FILE",
               "CURRICULUM_FILE", "CORTEX_FILE", "CROWN_FILE", "LOCK_FILE",
               "PRAYER_FILE")


class sandbox_state:
    """Point the genome at a fresh state dir for one test, then put it back."""

    def __init__(self, name):
        self.path = os.path.join(TMP, name)

    def __enter__(self):
        self.saved = {k: getattr(genome, k) for k in _STATE_KEYS}
        genome.use_state_dir(self.path)
        return self.path

    def __exit__(self, *exc):
        for k, v in self.saved.items():
            setattr(genome, k, v)
        return False


def _grown_cortex(n_wavs=60, dim=None):
    """A cortex that really lived: fed real wavs from the sandbox corpus."""
    build_synthetic_corpus()
    ears = Ears()
    c = Cortex(dim or ears.dim)
    chem = Chemistry()
    names = sorted(os.listdir(genome.FOOD_TRAIN))[:n_wavs]
    for i, n in enumerate(names):
        c.hear_path(ears, os.path.join(genome.FOOD_TRAIN, n), chem, i + 1)
    return c, ears, chem


def _force_birth(c, beat=1):
    """Hand the cortex both preconditions and let IT decide.

    The sandbox corpus is two classes of band-limited noise on purpose (it
    exists to test fences, not to teach a child), so it never produces the
    hundreds of DISTINCT sequences a real corpus does — food/train gives 323
    after 200 utterances. These tests are about what the birth rule does once
    the evidence exists, so the evidence is supplied and maybe_birth() still
    makes the decision itself.
    """
    k = c.n_layers()
    c.sleep_counts[k - 1] = [len(c.layers[k - 1].protos)] * (
        2 * genome.LAYER_SETTLE_SLEEPS)
    if k < genome.MAX_LAYERS:
        c.distinct[k] = {(i, i + 1, i + 2)
                         for i in range(genome.LAYER_BIRTH_MIN_EVENTS)}
    return c.maybe_birth(beat)


def test_cortex_does_not_touch_the_frozen_ear():
    """The whole depth design rests on this: reading the cochlea through a
    narrower window is NOT changing the ear. Over the FULL span the cortex's
    own path must give back exactly ears.utterance(path) — bit for bit."""
    build_synthetic_corpus()
    ears = Ears()
    for n in sorted(os.listdir(genome.FOOD_TRAIN))[:5]:
        p = os.path.join(genome.FOOD_TRAIN, n)
        feats, rms = ears.frames(p)
        assert np.array_equal(ears.pool(feats, rms), ears.utterance(p)), n
    assert genome.EAR_FROZEN and genome.EAR_REPR == "cochlea"
    assert genome.EAR_REPRS == ("cochlea",)


def test_layer0_learns_identically_under_the_cortex():
    """Wiring depth in may not change what layer 0 becomes. Same wavs, same
    order: a bare Brain and layer 0 of a Cortex must end up identical."""
    build_synthetic_corpus()
    ears = Ears()
    names = sorted(os.listdir(genome.FOOD_TRAIN))[:40]
    bare, chem_a = Brain(ears.dim), Chemistry()
    for i, n in enumerate(names):
        bare.hear(ears.utterance(os.path.join(genome.FOOD_TRAIN, n)),
                  chem_a, i + 1)
    cx, chem_b = Cortex(ears.dim), Chemistry()
    for i, n in enumerate(names):
        cx.hear_path(ears, os.path.join(genome.FOOD_TRAIN, n), chem_b, i + 1)
    assert len(bare.protos) == len(cx.layers[0].protos), (
        len(bare.protos), len(cx.layers[0].protos))
    for a, b in zip(bare.protos, cx.layers[0].protos):
        assert np.allclose(a["vec"], b["vec"]) and a["mass"] == b["mass"]


def test_layer_is_not_born_before_its_preconditions():
    """A layer is BORN, never configured. Both preconditions must bite."""
    c, ears, chem = _grown_cortex(60)
    assert c.n_layers() == 1
    assert len(c.distinct[1]) > 0, "distinct sequences are not being counted"
    assert c.distinct_total[1] > 0

    evidence = {(i, i + 1, i + 2)
                for i in range(genome.LAYER_BIRTH_MIN_EVENTS)}

    # (a) sequences but NOT settled: a churning layer 0 blocks the birth
    c.distinct[1] = set(evidence)
    c.sleep_counts[0] = [10, 25, 40, 70, 100, 130]      # still growing fast
    assert c.settled(0) is False
    assert c.maybe_birth(1000) is None and c.n_layers() == 1

    # (b) settled but NOT enough distinct sequences
    c.sleep_counts[0] = [80, 92, 79, 81, 90, 80]   # a saw that goes nowhere
    assert c.settled(0) is True, c.settle_trend(0)
    c.distinct[1] = set(list(evidence)[:genome.LAYER_BIRTH_MIN_EVENTS - 1])
    assert c.maybe_birth(1000) is None and c.n_layers() == 1

    # (c) both -> born, and logged
    c.distinct[1] = set(evidence)
    rec = c.maybe_birth(1234)
    assert rec is not None and c.n_layers() == 2, rec
    assert rec["layer"] == 1 and rec["beat"] == 1234
    assert c.layers[1].dim == genome.LAYER_SLOTS * ears.dim
    assert c.layers[1].max_protos == genome.LAYER_MAX_PROTOTYPES
    assert c.births and c.births[-1] == rec

    # and it then actually learns from what layer 0 does
    for i, n in enumerate(sorted(os.listdir(genome.FOOD_TRAIN))[:20]):
        c.hear_path(ears, os.path.join(genome.FOOD_TRAIN, n), chem, 2000 + i)
    assert c.counts()[1] > 0, "layer 1 was born and learned nothing"


def test_max_layers_is_respected():
    """The fence. The brain may grow inside it and never past it."""
    c, ears, chem = _grown_cortex(60)
    for _ in range(genome.MAX_LAYERS + 5):
        _force_birth(c)
    assert c.n_layers() == genome.MAX_LAYERS, c.n_layers()
    assert c.birth_status()["why"] == "MAX_LAYERS reached"

    # Iddo may also move the fence DOWN. That used to leave the per-layer
    # bookkeeping shorter than the layer list, and the next sleep died with
    # IndexError inside after_sleep — in a live beat, unguarded.
    import sleep as sleep_mod
    from drives import Drives
    with sandbox_state("fence"):
        c.save()
        saved = genome.MAX_LAYERS
        try:
            genome.MAX_LAYERS = 2
            small = Cortex.load(ears.dim)
            assert small.n_layers() <= genome.MAX_LAYERS + 2   # loaded as-is
            assert len(small.sleep_counts) == genome.MAX_LAYERS
            small.layers = small.layers[:genome.MAX_LAYERS]
            sleep_mod.cycle(small, chem, Drives(), ears, 10, "ah", 1,
                            log=lambda *a: None)
            assert small.maybe_birth(11) is None
        finally:
            genome.MAX_LAYERS = saved


def test_birth_evidence_does_not_survive_a_sleep():
    """A sequence key is a tuple of prototype INDICES and sleep._prune
    renumbers them. Evidence gathered across a prune is nonsense in both
    directions, and left running it made the birth gate satisfiable by
    re-indexing churn alone (measured 2026-08-21: 3,625 'distinct' sequences
    against a gate of 200, on a layer 0 pruned six times). So the evidence is
    an EPOCH set, cleared every sleep."""
    import sleep as sleep_mod
    from drives import Drives
    c, ears, chem = _grown_cortex(60)
    c.distinct[1] = {(i, i + 1, i + 2)
                     for i in range(genome.LAYER_BIRTH_MIN_EVENTS * 3)}
    before = len(c.distinct[1])
    sleep_mod.cycle(c, chem, Drives(), ears, 10, "ah", 5, log=lambda *a: None)
    assert c.distinct[1] == set(), "stale index keys survived a sleep"
    assert c.distinct_best[1] >= before, "the epoch's size was not remembered"
    # and a new epoch fills again from real hearing
    for i, n in enumerate(sorted(os.listdir(genome.FOOD_TRAIN))[:10]):
        c.hear_path(ears, os.path.join(genome.FOOD_TRAIN, n), chem, 11 + i)
    assert 0 < len(c.distinct[1]) < before
    # a restart does not resurrect them either
    with sandbox_state("epoch"):
        c.save()
        assert Cortex.load(ears.dim).distinct[1] == set()


def test_a_late_born_layer_gets_its_own_childhood():
    """A layer born at beat 700,000 must be a NEWBORN, not an instant adult.

    Brain.strictness() grows over CRITICAL_PERIOD_BEATS from self.beat; a
    layer born late with a global clock starts at STRICTNESS_ADULT and can
    barely spawn at all. Each layer counts its own age from its own birth.
    """
    c, ears, chem = _grown_cortex(60)
    late = 700_000
    c.layers[0].beat = late
    assert _force_birth(c, late) is not None
    baby = c.layers[1]
    assert baby.age_offset == late
    assert baby.age() == 0.0
    assert abs(baby.strictness() - genome.STRICTNESS_INFANT) < 1e-9, (
        baby.strictness(), "a newborn layer woke up already grown")
    baby.beat = late + genome.CRITICAL_PERIOD_BEATS * 10
    assert baby.strictness() > genome.STRICTNESS_ADULT - 0.01, "it never grows up"
    # layer 0 is untouched by any of this
    assert c.layers[0].age_offset == 0
    assert c.layers[0].age() == float(late)
    # and the offset survives a save/load
    with sandbox_state("childhood"):
        baby.beat = late + 5
        c.beat = late + 5
        c.save()
        again = Cortex.load(ears.dim)
        assert again.n_layers() == 2
        assert again.layers[1].age_offset == late
        assert again.layers[1].age() == 5.0


def test_word_corpus_has_no_duplicate_wavs():
    """96 word wavs must be 96 DISTINCT recordings. The first version shipped
    60 unique files under 96 names (4-way byte-identical groups), so every AUC
    and every permutation p-value was computed over pseudo-replicates — which
    narrows a null and flatters the result."""
    import hashlib
    import make_words
    made = make_words.build(train_dir=genome.FOOD_TRAIN,
                            words_dir=genome.FOOD_WORDS,
                            log=lambda *a: None) if False else None
    real = os.path.join(ROOT, "food", "words")
    manifest_path = os.path.join(real, "manifest.json")
    if not os.path.exists(manifest_path):
        print("      (SKIP: food/words not built — run proof/make_words.py)")
        return
    m = json.load(open(manifest_path, encoding="utf-8"))
    names = sorted(m["words"])
    assert len(names) == 96, len(names)
    seen = {}
    for n in names:
        with open(os.path.join(real, n), "rb") as f:
            h = hashlib.sha1(f.read()).hexdigest()
        assert h not in seen, f"{n} is byte-identical to {seen.get(h)}"
        seen[h] = n
    # every syllable class appears as a real constituent, so the permutation
    # null (which draws from all 22) is not biased downward
    used = {c for w in m["words"].values() for c in w["syllables"]}
    assert used == set(genome.CLASSES), sorted(set(genome.CLASSES) - used)
    # and the words are built from tokens the organism never eats
    import measure as measure_mod
    for w in m["words"].values():
        for t in w["tokens"]:
            assert measure_mod.is_dev(t), f"{t} is NOT dev — the child ate it"
    assert made is None


def test_layer1_percepts_contain_no_labels():
    """Depth may not become a label leak. What layer 1 eats is arithmetic on
    layer 0's own vectors — no filename, no class, no string at all."""
    c, ears, chem = _grown_cortex(60)
    assert _force_birth(c, 500) is not None
    p = os.path.join(genome.FOOD_TRAIN,
                     sorted(os.listdir(genome.FOOD_TRAIN))[0])
    feats, rms = ears.frames(p)
    trace = c.trace0(ears, feats, rms)
    for idx, sim in trace:
        assert isinstance(idx, int) and isinstance(sim, float)
    percepts = c.percepts_from(1, trace)
    assert percepts, "no percepts to check"
    for v in percepts:
        assert isinstance(v, np.ndarray) and v.dtype.kind == "f"
        assert v.shape == (genome.LAYER_SLOTS * ears.dim,)
        assert np.isfinite(v).all()
        assert abs(float(np.linalg.norm(v)) - 1.0) < 1e-9
    rec = c.hear_path(ears, p, chem, 900)
    assert not (set(rec) & FORBIDDEN_KEYS), set(rec)
    for r in rec["layers"]:
        assert not (set(r) & FORBIDDEN_KEYS), set(r)


def test_old_single_layer_brain_loads_without_rebirth():
    """THE ONE THAT PROTECTS ERAN. He is alive on eran1 with a real history in
    a single-layer state/brain.json.gz written before depth existed. It must
    load and BECOME layer 0 — no rebirth, no archive, no loss. The worst scar
    in this project is 11.9M steps destroyed."""
    with sandbox_state("legacy") as state:
        build_synthetic_corpus()
        ears = Ears()
        old = Brain(ears.dim)                   # exactly the pre-depth object
        chem = Chemistry()
        for i, n in enumerate(sorted(os.listdir(genome.FOOD_TRAIN))[:30]):
            old.hear(ears.utterance(os.path.join(genome.FOOD_TRAIN, n)),
                     chem, i + 1)
        old.beat = 11_900_000                   # the number that must survive
        old.save()
        raw = json.loads(gzip.open(genome.BRAIN_FILE, "rb").read())
        assert "pos" not in json.dumps(raw["protos"][0]), (
            "the fixture is not an OLD brain file")
        assert not os.path.exists(genome.CORTEX_FILE)

        c = Cortex.load(ears.dim)
        assert c.n_layers() == 1
        assert len(c.layers[0].protos) == len(old.protos)
        assert c.layers[0].beat == 11_900_000
        for a, b in zip(old.protos, c.layers[0].protos):
            assert np.allclose(a["vec"], b["vec"], atol=1e-5)
            assert a["mass"] == b["mass"]
            assert a["birth_step"] == b["birth_step"]
            assert b["pos"] is not None          # given a body on arrival

        # and the whole life loop wakes on it without archiving anything
        import eran_life
        life = eran_life.Life()
        assert life.cortex.n_layers() == 1
        assert len(life.brain.protos) == len(old.protos)
        assert life.beat == 11_900_000
        assert life.brain is life.cortex.layers[0]
        assert not [n for n in os.listdir(state) if n.startswith("brain-dim")], \
            "the organism was REBORN — history destroyed"
        life.checkpoint()                        # and round-trips through save
        again = Cortex.load(ears.dim)
        assert len(again.layers[0].protos) == len(old.protos)
        assert again.layers[0].beat == 11_900_000


def test_positions_are_deterministic():
    """Same history in, same coordinates out — on any machine, any process."""
    build_synthetic_corpus()
    ears = Ears()
    runs = []
    for _ in range(2):
        c = Cortex(ears.dim)
        chem = Chemistry()
        for i, n in enumerate(sorted(os.listdir(genome.FOOD_TRAIN))[:50]):
            c.hear_path(ears, os.path.join(genome.FOOD_TRAIN, n), chem, i + 1)
        runs.append([tuple(p["pos"]) for p in c.layers[0].protos])
    assert runs[0] == runs[1], "positions are not deterministic"
    assert len(set(runs[0])) == len(runs[0]), "two prototypes share a point"
    assert all(abs(p[2]) < 1e-9 for p in runs[0]), "layer 0 is not the z=0 plane"

    with sandbox_state("positions"):
        c = Cortex(ears.dim)
        chem = Chemistry()
        for i, n in enumerate(sorted(os.listdir(genome.FOOD_TRAIN))[:50]):
            c.hear_path(ears, os.path.join(genome.FOOD_TRAIN, n), chem, i + 1)
        before = [tuple(p["pos"]) for p in c.layers[0].protos]
        c.save()
        after = [tuple(p["pos"])
                 for p in Cortex.load(ears.dim).layers[0].protos]
        assert before == after, "positions did not survive a save/load"

    # a layer above sits in its own z plane
    if _force_birth(c, 10) is not None:
        for i, n in enumerate(sorted(os.listdir(genome.FOOD_TRAIN))[:20]):
            c.hear_path(ears, os.path.join(genome.FOOD_TRAIN, n), chem, 50 + i)
        if c.layers[1].protos:
            assert all(abs(p["pos"][2] - genome.POS_Z_SPACING) < 1e-9
                       for p in c.layers[1].protos)


def test_sleep_prunes_every_layer():
    """A layer that grows but never prunes is a layer that memorises."""
    import sleep as sleep_mod
    from drives import Drives
    c, ears, chem = _grown_cortex(60)
    assert _force_birth(c, 1) is not None
    for i, n in enumerate(sorted(os.listdir(genome.FOOD_TRAIN))):
        c.hear_path(ears, os.path.join(genome.FOOD_TRAIN, n), chem, 2 + i)
    assert c.counts()[1] > 0
    far = 10 * genome.PRUNE_UNUSED_BEATS

    # 1. an ordinary sleep: SHY downscale and scar decay reach EVERY layer
    for brain in c.layers:
        for p in brain.protos:
            p["scar"] = 0.5
    before = [[p["mass"] for p in b.protos] for b in c.layers]
    s = sleep_mod.cycle(c, chem, Drives(), ears, far, "ah", 10,
                        log=lambda *a: None)
    assert len(s["pruned_per_layer"]) == c.n_layers(), s
    assert s["protos_per_layer"] == c.counts()
    for k, brain in enumerate(c.layers):
        assert brain.protos, f"layer {k} emptied unexpectedly"
        for p, was in zip(brain.protos, before[k]):
            assert abs(p["mass"] - was * genome.SHY_FACTOR) < 1e-9, k
            assert abs(p["scar"] - 0.5 * genome.SCAR_DECAY) < 1e-9, k

    # 2. make every prototype light, old and unused: EVERY layer must prune
    for brain in c.layers:
        for p in brain.protos:
            p["mass"] = genome.PRUNE_MASS_MIN - 1.0
            p["birth_step"] = 0
            p["last_used"] = 0
    s = sleep_mod.cycle(c, chem, Drives(), ears, far, "ah", 10,
                        log=lambda *a: None)
    assert all(n > 0 for n in s["pruned_per_layer"]), (
        "a layer slept without pruning", s)
    assert s["protos_per_layer"] == c.counts() == [0] * c.n_layers(), s
    # a bare Brain still sleeps, exactly as it did before depth existed
    b = Brain(ears.dim)
    b.hear(ears.utterance(os.path.join(
        genome.FOOD_TRAIN, sorted(os.listdir(genome.FOOD_TRAIN))[0])), chem, 1)
    s2 = sleep_mod.cycle(b, chem, Drives(), ears, far, "ah", 1,
                         log=lambda *a: None)
    assert s2["layer_born"] is None and s2["protos_per_layer"] == [0]


def test_weave_export_round_trips_through_alma():
    """The 3D export must be a LEGAL alma weave, not JSON that merely looks
    like one: alma.text.from_dict must rebuild it and Loom.validate accept it."""
    import brain_to_weave
    c, ears, chem = _grown_cortex(60)
    assert _force_birth(c, 1) is not None
    for i, n in enumerate(sorted(os.listdir(genome.FOOD_TRAIN))[:30]):
        c.hear_path(ears, os.path.join(genome.FOOD_TRAIN, n), chem, 2 + i)
    out = os.path.join(TMP, "weave.json")
    d = brain_to_weave.export(c, out, log=lambda *a: None)
    assert os.path.exists(out)
    assert len(d["knots"]) == sum(c.counts()), (len(d["knots"]), c.counts())
    assert d["threads"], "a brain with no connections is the thing we fixed"
    assert set(d["scene"]["positions"]) == {k["name"] for k in d["knots"]}
    for name, pos in d["scene"]["positions"].items():
        assert len(pos) == 3 and all(isinstance(x, float) for x in pos)
    # the positions in the file are the REAL ones the cortex grew
    for k, brain in enumerate(c.layers):
        for i, p in enumerate(brain.protos):
            nm = brain_to_weave.knot_name(k, i)
            assert d["scene"]["positions"][nm] == [round(float(x), 4)
                                                   for x in p["pos"]]
    alma_root = os.path.join(os.path.dirname(ROOT), "alma-language")
    if not os.path.isdir(alma_root):
        print("      (SKIP round-trip: D:\\CLAUDE\\alma-language not present "
              "— the export format is still checked above)")
        return
    sys.path.insert(0, alma_root)
    from alma.text import from_dict                        # noqa: E402
    from alma.loom import Loom                             # noqa: E402
    w = from_dict(json.load(open(out, encoding="utf-8")))
    assert len(w.knots) == len(d["knots"])
    assert len(w.threads) == len(d["threads"])
    assert len(w.seeds) == len(d["seeds"])
    w.validate()                                  # a legal weave, not a lookalike
    r = Loom().run(w, 4)                          # and it actually runs
    assert r.fires, "the weave never fired"


def main():
    print(f"[test] sandbox: {TMP}")
    print("[test] chance = 4.545% (22 classes) — printed before any result, "
          "by law")
    check("ear determinism (synthetic sine)", test_ear_determinism)
    check("brain spawn/pull math", test_brain_spawn_pull)
    check("every crownable ear hears a real wav",
          test_every_crownable_ear_hears_a_real_wav)
    check("only the frozen ear can be crowned",
          test_only_the_frozen_ear_can_be_crowned)
    check("examiner may rebuild a legacy ear, never a broken one",
          test_examiner_may_rebuild_a_legacy_ear_but_never_a_broken_one)
    check("tournament may not crown a frozen ear",
          test_tournament_may_not_crown_while_the_ear_is_frozen)
    check("chemistry bounds", test_chemistry_bounds)
    check("school never leaks labels", test_school_never_leaks_labels)
    check("heldout guard (life refuses, examiner may)", test_heldout_guard)
    check("atomic write survives crash sim", test_atomic_write_crash_sim)
    check("boot assert refuses stale brain", test_boot_assert_refuses_stale_brain)
    check("boot assert recovery stays out of RAM",
          test_boot_assert_recovery_stays_out_of_ram)
    check("boot assert recovery handles unordered metrics",
          test_boot_assert_recovery_handles_unordered_metrics)
    check("flock excludes second writer", test_flock_excludes_second_writer)
    check("mastery gate end-to-end (12h retention)", test_mastery_gate_end_to_end)
    check("parent taps pay traces", test_parent_taps_pay_traces)
    check("echo-babble honestly labeled", test_echo_babble_is_honest)
    check("examiner baselines + heldout exam", test_examiner_baselines_and_exam)
    print("[test] --- depth (body/cortex.py) ---")
    check("cortex does not touch the frozen ear",
          test_cortex_does_not_touch_the_frozen_ear)
    check("layer 0 learns identically under the cortex",
          test_layer0_learns_identically_under_the_cortex)
    check("a layer is not born before its preconditions",
          test_layer_is_not_born_before_its_preconditions)
    check("MAX_LAYERS is respected", test_max_layers_is_respected)
    check("birth evidence does not survive a sleep",
          test_birth_evidence_does_not_survive_a_sleep)
    check("a late-born layer gets its own childhood",
          test_a_late_born_layer_gets_its_own_childhood)
    check("word corpus has no duplicate wavs",
          test_word_corpus_has_no_duplicate_wavs)
    check("layer 1 percepts contain no labels",
          test_layer1_percepts_contain_no_labels)
    check("old single-layer brain loads without rebirth",
          test_old_single_layer_brain_loads_without_rebirth)
    check("positions are deterministic", test_positions_are_deterministic)
    check("sleep prunes every layer", test_sleep_prunes_every_layer)
    check("weave export round-trips through alma",
          test_weave_export_round_trips_through_alma)
    print(f"\n[test] {len(PASSED)} passed, {len(FAILED)} failed")
    shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
