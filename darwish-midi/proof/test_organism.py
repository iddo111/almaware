"""test_organism.py — fast offline tests for Chai the Songbird. No corpus,
no eran4, no network. Every organ is exercised with small synthetic data.

Run: python proof/test_organism.py   (must print PASS lines and exit 0)

Covers exactly what the build asked for:
  * brain eat/persist roundtrip determinism
  * MIDI bytes: valid MThd/MTrk header from midi_out on a tiny song
  * WAV RMS nonzero from synth
  * parent payout math on a synthetic 👎 (motif attraction drops)
  * tap_server's jsonl schema matches parent.py's own reader
  * archive-guard refuses ~/darwish-ai paths
plus one bonus: the single-writer lock (real fcntl on Linux, documented
no-op on Windows — same test, both worlds, per the crash-proofing law).
"""
import json
import os
import shutil
import struct
import sys
import tempfile
import traceback

for _stream in (sys.stdout, sys.stderr):           # Hebrew/emoji-safe console
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(ROOT, "body"))
sys.path.insert(0, ROOT)

import genome                                     # noqa: E402
from brain import Brain                           # noqa: E402
from chemistry import Chemistry                   # noqa: E402
import midi_out                                    # noqa: E402
import synth                                        # noqa: E402
import parent as parent_mod                         # noqa: E402
import tap_server                                    # noqa: E402
from darwish_life import (assert_not_archive, acquire_lock,   # noqa: E402
                          SecondWriterError)

TMP = tempfile.mkdtemp(prefix="chai-test-")
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


def _tiny_song_tokens():
    """~2 bars of plausible tokens: kick+bass on the downbeat, rests between,
    a BAR marker every 16 steps, BOS/EOS bookends — small but real."""
    toks = [genome.TOK_BOS]
    for bar in range(2):
        for step in range(genome.STEPS_PER_BAR):
            if step % 4 == 0:
                drums, bass = 0b001, (step // 4) % 12 + 1     # kick + a bass degree
            else:
                drums, bass = 0, 0
            toks.append(drums * genome.DRUM_BASE + bass)
        toks.append(genome.TOK_BAR)
    toks.append(genome.TOK_EOS)
    return toks


def _bigger_song_tokens(bars=32):
    """Enough bars that the resulting .mid clears the >1KB real acceptance bar."""
    toks = [genome.TOK_BOS]
    for bar in range(bars):
        for step in range(genome.STEPS_PER_BAR):
            drums = 0b001 if step % 4 == 0 else (0b100 if step % 2 == 0 else 0)
            bass = (step % 12) + 1 if step % 2 == 0 else 0
            toks.append(drums * genome.DRUM_BASE + bass)
        toks.append(genome.TOK_BAR)
        if (bar + 1) % genome.BARS_PER_PHRASE == 0:
            toks.append(genome.TOK_PHRASE)
    toks.append(genome.TOK_EOS)
    return toks


def _feed(brain, chem, tokens, learn=True):
    """Digest a raw token list end to end, tracking bar-phase like ears.py does."""
    phase = 0
    bits = []
    for tok in tokens:
        bits.append(brain.digest(tok, phase, chem, learn=learn))
        if tok == genome.TOK_BAR:
            phase = 0
        elif tok not in genome.STRUCTURAL:
            phase = (phase + 1) % genome.STEPS_PER_BAR
    return bits


# --------------------------------------------------------------------- tests
def test_brain_persist_roundtrip_deterministic():
    tokens = _tiny_song_tokens() * 3
    b1, chem1 = Brain(), Chemistry()
    _feed(b1, chem1, tokens)

    # a second, independently-fed brain on the identical input: bit-identical
    b2, chem2 = Brain(), Chemistry()
    _feed(b2, chem2, tokens)
    assert b1.w == b2.w, "two brains fed identical tokens diverged — not deterministic"
    assert b1.n == b2.n
    assert b1.uni == b2.uni

    # save/load roundtrip must reproduce the exact same state
    path = os.path.join(TMP, "brain.json.gz")
    b1.save(path)
    b3 = Brain.load(path)
    assert b3.w == b1.w and b3.n == b1.n and b3.uni == b1.uni and b3.mass == b1.mass


def test_midi_bytes_valid():
    tokens = _bigger_song_tokens(32)
    path = os.path.join(TMP, "song.mid")
    midi_out.write(path, tokens)
    with open(path, "rb") as f:
        data = f.read()
    assert data[:4] == b"MThd"
    hdr_len, fmt, ntrks, division = struct.unpack(">IHHH", data[4:14])
    assert hdr_len == 6 and ntrks == 1 and division == 480
    assert data[14:18] == b"MTrk"
    track_len = struct.unpack(">I", data[18:22])[0]
    assert 22 + track_len == len(data), "MTrk length field doesn't match the file"
    assert len(data) > 1000, f"32-bar song should clear 1KB, got {len(data)} bytes"


def test_wav_rms_nonzero():
    tokens = _bigger_song_tokens(8)
    path = os.path.join(TMP, "song.wav")
    dur = synth.render(path, tokens)
    assert dur > 0
    with open(path, "rb") as f:
        data = f.read()
    assert data[:4] == b"RIFF" and data[8:12] == b"WAVE"
    i = 12
    pcm = None
    while i + 8 <= len(data):
        cid = data[i:i + 4]
        csize = struct.unpack("<I", data[i + 4:i + 8])[0]
        if cid == b"data":
            pcm = data[i + 8:i + 8 + csize]
            break
        i += 8 + csize + (csize % 2)
    assert pcm, "no data chunk found"
    n = len(pcm) // 2
    total = sum(struct.unpack_from("<h", pcm, k)[0] ** 2 for k in range(0, n * 2, 2))
    rms = (total / n) ** 0.5
    assert rms > 0.0, "synth produced silence"


def test_parent_payout_motif_drop():
    """A repeated motif earns a strong synapse; one synthetic 👎 through the
    real trace-payout path (brain.pay_trace, ACh=parent, eta=parent) must
    drop that motif's re-emission probability — pain actively depresses the
    traced pathway, it doesn't merely withhold reward."""
    brain, chem = Brain(), Chemistry()
    ctx = [10, 20, 30]
    target = 40
    for _ in range(40):                              # establish a confident synapse
        for t in ctx:
            brain.digest(t, 0, chem, learn=True)
        brain.digest(target, 0, chem, learn=True)

    brain.history = ctx[:]
    p_before = brain.p_of(target, 0)                  # measure BEFORE any tap

    # "sing" the motif once: this IS the trace a real song would save — the
    # cells active right after ctx get tagged with the token that followed.
    brain.history = ctx[:]
    brain.elig = {}
    brain.tag_only(target, 0)
    trace = brain.snapshot_trace()
    assert trace, "singing the motif produced no eligibility trace"

    chem.mode(genome.ACH_PARENT)
    paid, missing = brain.pay_trace(trace, -1.0 * genome.V_TAP, genome.ETA_PARENT, chem)
    assert paid > 0, "the tap paid nothing — trace/weights mismatch"

    brain.history = ctx[:]
    p_after = brain.p_of(target, 0)

    assert p_after < p_before, f"motif attraction did not drop: {p_before} -> {p_after}"
    rel_drop = (p_before - p_after) / p_before
    # This toy 3-cell trace is diluted by reliability-mixed backoff (the real
    # ~50% bar is measure.py's job on a full sung trace); here we only need
    # proof the direction and magnitude are a real effect, not float noise.
    assert rel_drop > 0.02, f"drop too small to be a real effect: {rel_drop:.1%}"
    print(f"    (motif p: {p_before:.4f} -> {p_after:.4f}, drop {rel_drop:.1%})")


def test_tap_schema_matches_parent():
    """tap_server.write_tap() must produce EXACTLY what parent.pay_taps() reads."""
    inbox = os.path.join(TMP, "tapschema", "inbox")
    outbox = os.path.join(TMP, "tapschema", "outbox")
    os.makedirs(inbox, exist_ok=True)
    os.makedirs(outbox, exist_ok=True)

    brain, chem = Brain(), Chemistry()
    ctx, target = [1, 2, 3], 4
    for _ in range(10):
        for t in ctx:
            brain.digest(t, 0, chem, learn=True)
        brain.digest(target, 0, chem, learn=True)
    brain.history = ctx[:]
    brain.elig = {}
    brain.tag_only(target, 0)
    trace = brain.snapshot_trace()

    song_id = "chai-testsong-0001"
    with open(os.path.join(outbox, song_id + ".trace.json"), "w", encoding="utf-8") as f:
        json.dump({"song_id": song_id, "trace": trace}, f)

    tap_path = tap_server.write_tap(song_id, -1.0, inbox_dir=inbox)
    assert os.path.exists(tap_path)
    with open(tap_path, "r", encoding="utf-8") as f:
        rec = json.loads(f.readline())
    assert rec["song_id"] == song_id
    assert rec["tap"] == -1.0
    assert "ts" in rec

    paid_total = parent_mod.pay_taps(brain, chem, inbox, outbox, log=lambda *a: None)
    assert paid_total > 0, "parent.py could not read what tap_server.py wrote"
    # DW-11 (2026-09-06): this used to assert the `.paid` RENAME. That rename was
    # the defect — tap_server appends to the same daily path from another
    # process, so a tap written between the read and the rename was renamed away
    # unpaid, and a second payout the same day renamed a fresh file onto the
    # existing .paid and destroyed the earlier record. Payment is by cursor now;
    # what must hold is the contract, not the mechanism: paid exactly once, and
    # the record still on disk.
    assert os.path.exists(tap_path), "the tap record was moved or destroyed"
    with open(tap_path, "r", encoding="utf-8") as f:
        assert json.loads(f.readline())["song_id"] == song_id, "record damaged"
    assert parent_mod.pay_taps(brain, chem, inbox, outbox, log=lambda *a: None) == 0, (
        "an already-paid tap got paid twice")


def test_archive_guard():
    bad = os.path.join(os.path.expanduser("~"), "darwish-ai", "food", "x.json")
    good = os.path.join(TMP, "food", "x.json")

    for guard in (assert_not_archive, tap_server._archive_guard):
        try:
            guard(bad)
            raise AssertionError(f"{guard} let an ~/darwish-ai path through")
        except RuntimeError:
            pass
        guard(good)                                   # must NOT raise


def test_lock_excludes_second_writer():
    lock_path = os.path.join(TMP, "lock", ".lock")
    h1 = acquire_lock(lock_path)
    try:
        import fcntl                                  # noqa: F401
        has_fcntl = True
    except ImportError:
        has_fcntl = False

    if has_fcntl:
        try:
            acquire_lock(lock_path)
            raise AssertionError("two writers held the lock on a real fcntl platform")
        except SecondWriterError:
            pass
        import fcntl
        fcntl.flock(h1.fileno(), fcntl.LOCK_UN)
    else:
        h2 = acquire_lock(lock_path)          # Windows: documented no-op, both succeed
        h2.close()
        print("    (no fcntl on this OS — lock is a documented no-op, as designed)")
    h1.close()


def main():
    print(f"[test] sandbox: {TMP}")
    check("brain digest/persist roundtrip is deterministic",
          test_brain_persist_roundtrip_deterministic)
    check("midi_out produces valid MThd/MTrk bytes", test_midi_bytes_valid)
    check("synth produces nonzero-RMS WAV", test_wav_rms_nonzero)
    check("parent payout drops a synthetic 👎'd motif", test_parent_payout_motif_drop)
    check("tap_server jsonl schema matches parent.py's reader",
          test_tap_schema_matches_parent)
    check("archive-guard refuses ~/darwish-ai paths", test_archive_guard)
    check("lock excludes a second writer (fcntl) / no-op (Windows)",
          test_lock_excludes_second_writer)
    print(f"\n[test] {len(PASSED)} passed, {len(FAILED)} failed")
    shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
