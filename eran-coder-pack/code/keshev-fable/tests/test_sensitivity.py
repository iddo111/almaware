"""The tunable ear: manual slider and AUTO both move the live gate; the segmenter
reads the gate through the sensitivity object, so a change needs no restart."""
from app.sensitivity import Sensitivity, GATE_MIN, GATE_MAX
from app.segmenter import Segmenter


def test_manual_set_clamps_and_disables_auto():
    s = Sensitivity(0.008)
    s.auto = True
    s.set(999)                       # a hand on the slider
    assert s.gate == GATE_MAX        # clamped
    assert s.auto is False           # AUTO turned off
    s.set(-1)
    assert s.gate == GATE_MIN


def test_auto_tracks_the_room_floor():
    s = Sensitivity(0.030)
    for _ in range(80):
        s.observe(0.004)             # quiet room
    s.observe(0.05)                  # one speech blip does not dominate
    rec = s.recommend()
    assert 0.004 <= rec <= 0.012     # just above the floor, not the blip


def test_segmenter_reads_gate_live():
    s = Sensitivity(0.05)            # start deaf
    seg = Segmenter(sensitivity=s)
    assert seg.gate == 0.05
    s.set(0.002)                     # make it sensitive WITHOUT rebuilding
    assert seg.gate == 0.002         # the segmenter sees it immediately


def test_no_sensitivity_uses_fixed_gate():
    seg = Segmenter(gate=0.008)
    assert seg.gate == 0.008         # unchanged behaviour when not wired
