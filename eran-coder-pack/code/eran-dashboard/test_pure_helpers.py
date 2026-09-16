"""Pure-function regression tests for the eran-dashboard widgets.

These cover only side-effect-free helpers: no network, no GUI, no reading of
credentials. They lock in the small but load-bearing pieces of logic that drive
the fleet health dots and the Claude/Grok usage widgets.

Run:  python -m pytest test_pure_helpers.py -q
"""
from __future__ import annotations

import master_widget as mw
import claude_usage_client as cuc
import grok_usage_client as guc
from web import master_dashboard as web_dashboard


# ---------------------------------------------------------------------------
# master_widget temperature -> color thresholds (drives the FLEET dots)
# ---------------------------------------------------------------------------
def test_temp_color_thresholds():
    assert mw._temp_color(0) == mw.OK
    assert mw._temp_color(49.9) == mw.OK
    assert mw._temp_color(50) == mw.WARN     # boundary: 50 is no longer "cool"
    assert mw._temp_color(71.9) == mw.WARN
    assert mw._temp_color(72) == mw.HOT       # boundary: 72 is hot
    assert mw._temp_color(90) == mw.HOT


def test_temp_color_non_numeric_is_subdued():
    assert mw._temp_color("not-a-number") == mw.SUB
    assert mw._temp_color(None) == mw.SUB


def test_node_dot_color():
    assert mw._node_dot_color(None) == mw.OFF
    assert mw._node_dot_color({}) == mw.OFF
    assert mw._node_dot_color({"online": False, "temp": 30}) == mw.OFF
    assert mw._node_dot_color({"online": True, "temp": 30}) == mw.OK
    assert mw._node_dot_color({"online": True, "temp": 60}) == mw.WARN
    assert mw._node_dot_color({"online": True, "temp": 80}) == mw.HOT


# ---------------------------------------------------------------------------
# claude_usage_client._parse_window (drives the Claude usage widget)
# ---------------------------------------------------------------------------
def test_parse_window_empty():
    assert cuc._parse_window(None) == {}
    assert cuc._parse_window({}) == {}


def test_parse_window_utilization_and_remaining():
    out = cuc._parse_window({"utilization": 12.34})
    assert out["utilization"] == 12.3
    assert out["percent_remaining"] == 87.7
    # No reset timestamp -> graceful defaults, never raises.
    assert out["days_to_reset"] == 0
    assert out["reset_label"] == "?"


def test_parse_window_bad_reset_is_graceful():
    out = cuc._parse_window({"utilization": 5, "resets_at": "garbage"})
    assert out["utilization"] == 5.0
    # Falls back to a truncated string rather than raising.
    assert out["reset_label"] == "garbage"[:16]


# ---------------------------------------------------------------------------
# grok_usage_client small pure helpers (_val, _parse_iso)
# ---------------------------------------------------------------------------
def test_val_coercion():
    assert guc._val(None) == 0.0
    assert guc._val(3) == 3.0
    assert guc._val(2.5) == 2.5
    assert guc._val({"val": 7}) == 7.0
    assert guc._val({"nope": 1}) == 0.0
    assert guc._val("string") == 0.0


def test_parse_iso():
    assert guc._parse_iso(None) is None
    assert guc._parse_iso("") is None
    assert guc._parse_iso("not-a-date") is None
    dt = guc._parse_iso("2026-07-05T10:00:00Z")
    assert dt is not None
    assert dt.year == 2026 and dt.month == 7 and dt.day == 5


# ---------------------------------------------------------------------------
# web dashboard trainer-log parsing (drives live Yigael training status)
# ---------------------------------------------------------------------------
def test_parse_training_round_format_after_older_done_marker():
    log = """TRAIN_DONE
RESUME from ckpt/last.pt at global step 6030 (opt=yes)
step   6205 (+175/2000) loss 3.3962 ppl 29.9 121s 1.4it/s
"""
    out = web_dashboard._parse_training(log)
    assert out == {"step": 6205, "total": 8030, "loss": 3.3962,
                   "ppl": 29.9, "done": False}


def test_parse_training_marks_done_only_after_latest_step():
    log = "step 4000 / 4000 loss 3.562 ppl 35.2\nTRAIN_DONE\n"
    out = web_dashboard._parse_training(log)
    assert out["step"] == 4000
    assert out["total"] == 4000
    assert out["done"] is True
