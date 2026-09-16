# -*- coding: utf-8 -*-
"""KESHEV-6 must be a DROP-IN for :8737, or the one-line switch is a lie.

This test reads mic-rebuild's own protocol.py and asserts that every wire
constant KESHEV-6 copied still matches the original. Copying was deliberate
(keshev-6 must keep answering if mic-rebuild moves); an UNNOTICED copy that has
drifted is the thing that would hurt.

Run:  python -m pytest tests/ -q     (or: python tests/test_contract_parity.py)
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import keshev6_server as k6  # noqa: E402

MIC_REBUILD = Path(r"D:/CLAUDE/mic-rebuild")


def _load_protocol():
    spec = importlib.util.spec_from_file_location(
        "_orig_protocol", MIC_REBUILD / "common" / "protocol.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_wire_constants_match():
    p = _load_protocol()
    assert k6.PATH_TRANSCRIBE == p.PATH_TRANSCRIBE
    assert k6.PATH_HEALTH == p.PATH_HEALTH
    assert k6.PATH_METRICS == p.PATH_METRICS
    assert k6.SAMPLE_RATE == p.SAMPLE_RATE
    assert k6.MAX_BODY_BYTES == p.MAX_BODY_BYTES
    assert k6.HDR_REQUEST_ID == p.HDR_REQUEST_ID
    assert k6.HDR_LANG_HINT == p.HDR_LANG_HINT
    assert k6.LANG_HINTS == p.LANG_HINTS
    assert k6.INFLIGHT_CAP == p.INFLIGHT_CAP
    # the ONE deliberate difference, asserted so it stays deliberate
    assert k6.PORT == 8738 and p.PORT == 8737


def test_response_carries_every_field_the_client_reads():
    """keshev-next/app/decoder.py reads exactly these three off the JSON.
    Losing one of them is a silent mic, not an error."""
    src = (Path(r"D:/CLAUDE/keshev-next/app/decoder.py")).read_text(encoding="utf-8")
    for field in ("text", "lang", "avg_logprob"):
        assert f'data.get("{field}"' in src, f"client no longer reads {field}?"


def test_status_line_refuses_transcripts():
    k6.status_line(evt="REQ", code=200)          # fine
    for banned in ("text", "transcript", "title"):
        try:
            k6.status_line(**{banned: "sod"})
        except TypeError:
            continue
        raise AssertionError(f"status_line accepted {banned}")


def test_no_audio_path_on_disk():
    """Privacy is STRUCTURAL: assert the server source has no way to write
    request audio to a file (same gate mic-rebuild applies to its own).

    2026-09-06, K6-03: this test caught its own author. The canary fix added
    `wave.open(canary_clip, "rb")` -- a fixed reference clip read for a health
    check, never his speech -- and the old rule banned the STRING `wave.open`
    outright, so it failed. The rule is now sharper AND wider, not looser:

      * wave may be opened, but only in "rb". A "wb" anywhere near it fails.
      * NO binary write mode at all may appear in this server -- "wb", "ab",
        "w+b", "x+b". The old rule said nothing about plain open(..., "wb"),
        which is the more obvious way audio would actually escape.

    What is NOT negotiable and is unchanged: request audio lives in RAM, and
    there is no path from a decode to a file."""
    src = (ROOT / "keshev6_server.py").read_text(encoding="utf-8")
    for bad in ("sf.write", "soundfile", "tofile("):
        assert bad not in src, f"{bad} in the server: audio could reach disk"
    for line in src.splitlines():
        if "wave.open" in line:
            assert '"rb"' in line or "'rb'" in line, (
                f"wave.open without an explicit read mode: {line.strip()!r}")
    for mode in ('"wb"', "'wb'", '"ab"', "'ab'", '"w+b"', "'w+b'", '"xb"', "'xb'"):
        assert mode not in src, (
            f"a binary write mode {mode} appears in the server: audio could "
            f"reach disk")


def test_speech_ratio_separates_silence_from_speech():
    import numpy as np
    rng = np.random.default_rng(0)
    silence = np.zeros(16000, dtype=np.float32)
    steady = (0.05 * np.sin(2 * np.pi * 120 * np.arange(16000) / 16000)).astype(np.float32)
    # a crude "speech": loud bursts separated by quiet, i.e. an envelope that moves
    speech = (rng.normal(0, 0.002, 32000)).astype(np.float32)
    for start in range(0, 32000, 8000):
        speech[start:start + 4000] += rng.normal(0, 0.08, 4000).astype(np.float32)
    assert k6.speech_ratio(silence) == 0.0
    assert k6.speech_ratio(steady) < 0.2, "a steady tone must not look like a voice"
    assert k6.speech_ratio(speech) > 0.3, "bursty audio must look like a voice"


def test_join_buffer_only_joins_short_and_adjacent():
    import numpy as np
    jb = k6.JoinBuffer()
    long_a = np.zeros(16000 * 2, dtype=np.float32)      # 2 s
    short_b = np.zeros(int(16000 * 0.5), dtype=np.float32)  # 0.5 s
    out, joined = jb.offer("c", long_a)
    assert not joined and out.size == long_a.size, "first segment can never join"
    out, joined = jb.offer("c", short_b)
    assert joined and out.size == long_a.size + short_b.size
    out, joined = jb.offer("c", long_a)
    assert not joined, "a long segment is never joined onto the previous one"


def test_single_instance_lock_actually_locks():
    """THE FIRST VERSION OF THIS LOCK DID NOT LOCK, and only this test found it.

    It did `open(path, "w")` and assumed Windows would refuse a second writer.
    CPython opens with FILE_SHARE_WRITE, so a second process acquired the same
    "lock" and reported success. A lock that always succeeds is worse than none:
    it is a guarantee someone will rely on. Never delete this test.
    """
    import subprocess
    lock = ROOT / "state" / "test_lock.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    held = k6._single_instance_lock(lock)
    try:
        code = (f"import sys; sys.path.insert(0, r'{ROOT}');"
                "from keshev6_server import _single_instance_lock;"
                "from pathlib import Path;"
                f"_single_instance_lock(Path(r'{lock}')); print('ACQUIRED')")
        r = subprocess.run([sys.executable, "-c", code], capture_output=True,
                           text=True, timeout=120)
        assert "ACQUIRED" not in r.stdout, "a second process took the lock"
        assert "refusing to start" in (r.stdout + r.stderr)
    finally:
        held.close()
        lock.unlink(missing_ok=True)
        lock.with_suffix(".pid").unlink(missing_ok=True)


def test_repair_never_touches_ordinary_hebrew():
    import lexicon
    for sentence in ("שלום מה שלומך", "אני הולך לישון", "תעלה לי שוב מוזיקה",
                     "כן", "לא", "בסדר גמור אחי"):
        out, changes = lexicon.repair(sentence)
        assert out == sentence and not changes, f"repair corrupted {sentence!r} -> {out!r}"


def test_lexicon_matches_the_deployed_copy():
    """K6-04 (2026-09-06): the DATA file drifted while the server file did not.

    keshev6_server.py was byte-identical between this tree and eran1, so nothing
    looked wrong -- but the 04:30 lexicon edit (Assassin's Creed, Meshtastic,
    Kropotkin, added because Iddo demonstrated at 02:41 that the mic could not
    hear the first of them) lived only on eran1. A redeploy from this tree would
    have reverted his fix, silently.

    So: the prompt-and-repair-map FINGERPRINT of this tree must equal the one
    recorded from the deployed copy. Drift now breaks the tests instead of
    breaking his dictation. `python tools/lexicon_parity.py --fetch` says which
    way it drifted; eran1 is the source of truth.
    """
    import importlib.util
    here = pathlib.Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "lexicon_parity_tool", here / "tools" / "lexicon_parity.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    assert tool.RECORD.exists(), (
        "LEXICON-DEPLOYED.json is missing -- run tools/lexicon_parity.py "
        "--fetch --record")
    rec = json.loads(tool.RECORD.read_text(encoding="utf-8"))
    mine = tool.local_fingerprint()
    assert mine == rec["fingerprint"], (
        "lexicon.py has drifted from the deployed copy: local %s, deployed %s "
        "(recorded %s). eran1 is the source of truth -- run "
        "tools/lexicon_parity.py --fetch before you overwrite anything."
        % (mine, rec["fingerprint"], rec.get("recorded")))


def test_prompt_still_carries_the_names_he_demonstrated():
    """The 02:41 failure, kept from being quietly undone by a redeploy."""
    import lexicon
    for name in ("Assassin's Creed", "Meshtastic", "Kropotkin"):
        assert name in lexicon.PROMPT_HE, (
            "%r fell out of PROMPT_HE -- Iddo demonstrated the mic missing it "
            "on 2026-09-06 02:41" % name)


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as e:
                fails += 1
                print("FAIL", name, type(e).__name__, e)
    print("---", "all passed" if not fails else f"{fails} FAILED")
    raise SystemExit(1 if fails else 0)
