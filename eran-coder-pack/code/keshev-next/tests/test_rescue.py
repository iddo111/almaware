"""Tests for tools/rescue.py -- the 3 a.m. self-rescue button.

🪟 BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY.

Every path is exercised against a SANDBOX state directory, never the live one:
a test that can pause Iddo's microphone is a weapon, not a test.

Nothing here opens an audio device. `capture_devices()` is not called at all --
it shells out to Get-PnpDevice, which is slow and machine-dependent; its
contract (full names, never sounddevice) is enforced by reading the source.

    pytest tests/test_rescue.py -q
"""

import importlib.util
import os
import sys
import tempfile

import pytest

RESCUE_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "tools", "rescue.py")


@pytest.fixture()
def r(tmp_path):
    """rescue.py with every writable path pointed at a throwaway directory."""
    spec = importlib.util.spec_from_file_location("rescue_under_test", RESCUE_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    state = tmp_path / "state"
    state.mkdir()
    mod.STATE = str(state)
    mod.PAUSE_FILE = str(state / "PAUSED")
    mod.MIC_PID_FILE = str(state / "mic.pid")
    mod.HEARTBEAT = str(state / "gui.heartbeat")
    mod.MIC_CHOICE = str(state / "mic-choice.json")
    mod.TRIAL_LOG = str(tmp_path / "trial.log")
    mod.GUI_CRASH = str(state / "gui-crash.log")
    return mod


def test_pause_is_moved_aside_never_deleted(r):
    """The night of 2026-09-03 is in this file. When the tool lifts a pause it
    must leave the evidence behind -- deleting it destroys the only record of
    who paused him and when."""
    with open(r.PAUSE_FILE, "w") as fh:
        fh.write("2026-09-03T22:55:13\n")
    r.do_repair("1")
    assert not os.path.exists(r.PAUSE_FILE)
    left = [f for f in os.listdir(r.STATE) if f.startswith("PAUSED.removed-")]
    assert len(left) == 1, "the pause file must be preserved, not deleted"
    with open(os.path.join(r.STATE, left[0])) as fh:
        assert "22:55:13" in fh.read(), "the original timestamp must survive"


def test_repairs_are_idempotent_and_never_raise(r):
    """He will press the same number twice at 3 a.m. Nothing may explode."""
    r.do_repair("1")                       # nothing to unpause
    with open(r.MIC_PID_FILE, "w") as fh:
        fh.write("999999")
    r.do_repair("5")
    assert not os.path.exists(r.MIC_PID_FILE)
    r.do_repair("5")                       # already gone
    r.do_repair("")                        # garbage input
    r.do_repair("nonsense")


def test_unreachable_decoder_is_an_honest_third_answer(r):
    """UNREACHABLE must never be reported as LOADING or READY -- guessing here
    is what makes a dead mic look alive."""
    state, _ = r.health("http://127.0.0.1:1", timeout=1.0)
    assert state == "UNREACHABLE"


def test_missing_files_do_not_crash_the_diagnosis(r):
    counts, lines = r.summarise_log()
    assert lines == []
    assert counts["typed"] == 0
    assert r.tail_lines(r.TRIAL_LOG) == []


def test_log_summary_is_scoped_to_the_current_session(r):
    """Last night's 2,825 [paused] lines must not colour this morning's verdict."""
    with open(r.TRIAL_LOG, "w", encoding="utf-8") as fh:
        fh.write("[paused] segment dropped (16384 bytes)\n" * 50)
        fh.write("=== gui start mic 2026-09-04T06:32:51 ===\n")
        for _ in range(3):
            fh.write("[segment] bytes=1 secs=1 peak_rms=1 gate=0.5/PASS "
                     "lp=-0.3 decode=ok route=he text='x'\n")
        fh.write("[mic] heartbeat: 900 blocks, peak RMS 4000, floor 600\n")
    counts, _ = r.summarise_log()
    assert counts["typed"] == 3
    assert counts["paused"] == 0, "history from before the restart leaked in"


def test_deaf_and_waiting_are_counted(r):
    with open(r.TRIAL_LOG, "w", encoding="utf-8") as fh:
        fh.write("=== gui start mic 2026-09-04T06:32:51 ===\n")
        fh.write("[mic] waiting for the decoder: UNREACHABLE (15s)\n")
        fh.write("[mic] DEAF: no audio blocks arrived in 60s (1 min running).\n")
    counts, _ = r.summarise_log()
    assert counts["waiting"] == 1 and counts["deaf"] == 1


def test_ago_never_raises(r):
    for value in (None, 0, 5, 300, 27000, 10 ** 7):
        assert isinstance(r.ago(value), str)


def test_effective_url_reads_both_sources(r):
    """The 2026-09-04 trap: RUN-KESHEV.cmd's inline `set` and a user-level setx
    can disagree, and nothing on screen said which one wins. Both must be read."""
    in_cmd, user_level = r.effective_stt_url()
    assert isinstance(in_cmd, str) and isinstance(user_level, str)
    assert "8737" in in_cmd or "8738" in in_cmd or in_cmd == "", in_cmd


def test_it_can_never_open_a_microphone(r):
    """The rule that matters more than every other test in this file.

    The rescue tool is the one thing Iddo runs when the mic is already broken.
    If it can open an audio device it can seize the BRIO, or worse flip the
    WH-1000XM4 into HFP and wreck his sound.

    Checked on the parsed AST, not on the text: the file DISCUSSES sounddevice
    at length in its comments (deliberately -- the reasoning is the point), so a
    substring scan would fail on its own prose. What must be true is that it
    never IMPORTS one, and never imports from app/, whose breakage is the whole
    reason this tool exists."""
    import ast

    with open(RESCUE_PY, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())

    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    banned_audio = {"sounddevice", "pyaudio", "soundfile", "wave", "winsound",
                    "audioop", "pyaudiowpatch", "speech_recognition"}
    assert not (imported & banned_audio), \
        f"rescue.py must never touch audio: imports {imported & banned_audio}"

    banned_app = {"main", "decoder", "ear", "vad", "segmenter", "typer",
                  "ownergate", "textguard", "gui", "app", "engine_probe"}
    assert not (imported & banned_app), \
        f"rescue.py must not depend on app/: imports {imported & banned_app}"

    allowed_third_party = {"pytest"}
    stdlib = set(getattr(sys, "stdlib_module_names", ()))
    if stdlib:
        outside = imported - stdlib - allowed_third_party
        assert not outside, f"rescue.py must be stdlib-only, found {outside}"


def test_it_only_ever_launches_the_official_runners(r):
    """Repair 2 and 3 must start the mic exactly the way the Desktop icon does.
    A rescue tool that invents its own launch line is a second, untested mic."""
    with open(RESCUE_PY, encoding="utf-8") as fh:
        src = fh.read()
    assert r"D:\CLAUDE\keshev-next\RUN-KESHEV.cmd".lower() in \
        os.path.join(r.KESHEV_NEXT, "RUN-KESHEV.cmd").lower()
    assert "RUN-KESHEV.cmd" in src and "RUN-STT-PC.cmd" in src
    assert "gui.py" not in src, "must not start the window by any private path"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
