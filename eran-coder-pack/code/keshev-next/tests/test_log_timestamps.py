# -*- coding: utf-8 -*-
r"""2026-09-11 -- trial.log finally has a clock, and every reader still works.

Until tonight trial.log carried NO timestamps. The delivery watchdog says so in
its own docstring: "the window is taken by POSITION, not by clock ... it CANNOT
answer 'at 14:03 exactly'". So "when did the last word reach his chat" -- the
only question that matters when the mic goes quiet at 3 a.m. -- was unanswerable,
and every night-scare of the last month was diagnosed by counting lines backwards.

app/logstamp.py now stamps every line the engine writes. The risk of that change
is the whole point of this file: EVERY pattern in logread6 is ^-anchored, so a
prefix would have silently blinded the window, the watchdog and the probe -- the
exact shape of the 2026-09-04 bug where "הוקלדו" read 0 forever because a regex
had stopped matching and nothing noticed.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import logread6  # noqa: E402
import logstamp  # noqa: E402

TYPED = ("[segment] bytes=120832 secs=3.78 peak_rms=5275 gate=- lp=-0.13 "
         "decode=ok route=he text='\\u05e9\\u05dc\\u05d5\\u05dd'")
SKIP = "[segment] bytes=16384 secs=0.51 peak_rms=112 floor=600 SKIP too-quiet"


def test_a_stamped_line_parses_exactly_like_an_unstamped_one():
    plain = logread6.parse_segment(TYPED)
    stamped = logread6.parse_segment("07:24:25 " + TYPED)
    assert plain["verdict"] == stamped["verdict"] == "typed"
    assert plain["text"] == stamped["text"] == "שלום"
    assert plain["bytes"] == stamped["bytes"] == 120832


def test_the_stamp_is_kept_not_just_discarded():
    """The clock is the POINT. Throwing it away would be half a fix."""
    assert logread6.parse_segment("07:24:25 " + TYPED)["at"] == "07:24:25"
    assert logread6.parse_segment(TYPED)["at"] == ""


def test_skip_lines_too():
    assert logread6.parse_segment("23:59:59 " + SKIP)["verdict"] == "skip"
    assert logread6.parse_segment(SKIP)["verdict"] == "skip"


def test_every_anchored_pattern_survives_the_prefix():
    """The ones that would have gone blind: the window keys its whole state off
    these, and a silent non-match is how 4,792 lines went unread on 09-04."""
    cases = [
        (logread6.HEARTBEAT_RE, "[mic] heartbeat: 936 blocks, peak RMS 333"),
        (logread6.DEAF_RE, "[mic] DEAF: no blocks for 120 s"),
        (logread6.NO_MIC_RE, "[mic] NO ALLOWED USB MIC on this machine"),
        (logread6.READY_RE, "[mic] decoder READY"),
        (logread6.DROPS_RE, "[mic] status_events=2 dropped_blocks=17"),
        (logread6.FALLBACK_RE, "[decoder] answered by fallback http://eran1:8737/v1/transcribe"),
        (logread6.TEXTGUARD_RE, "[textguard] dropped segment (1024 bytes): repeat"),
        (logread6.TYPER_REFUSED_RE, "[typer] refused segment (1024 bytes): elevated proc=x"),
        (logread6.CONFIDENCE_RE, "[confidence] dropped (1024 bytes, lp=-0.55) text='x'"),
        (logread6.BACKLOG_RE, "[segment] DROPPED: the decode worker is more than 32 behind"),
        (logread6.WAITING_RE, "[mic] waiting for the decoder: LOADING (12s)"),
    ]
    for rx, line in cases:
        assert rx.match(logread6.unstamp("07:24:25 " + line)), \
            "pattern went blind on a stamped line: %r" % line
        assert rx.match(line), "pattern broke on an UNstamped line: %r" % line


def test_the_writer_stamps_line_starts_only():
    """print() writes the text and the newline separately; a naive wrapper puts a
    second stamp in the middle of the sentence."""
    import io
    buf = io.StringIO()
    s = logstamp.TimestampedStream(buf)
    s.write("[segment] bytes=1 ")
    s.write("secs=0.1 peak_rms=700 gate=- lp=-0.2 decode=ok route=he text='x'")
    s.write("\n")
    out = buf.getvalue().splitlines()
    assert len(out) == 1
    at, body = logread6.strip_ts(out[0])
    assert at and body.startswith("[segment] bytes=1 secs=0.1")
    assert logread6.parse_segment(out[0])["verdict"] == "typed"


def test_it_can_be_turned_off():
    import sys as _sys
    real = _sys.stderr
    try:
        os.environ["KESHEV_LOG_TIMESTAMPS"] = "0"
        assert logstamp.install("stderr") is False
        assert _sys.stderr is real
    finally:
        os.environ.pop("KESHEV_LOG_TIMESTAMPS", None)
        _sys.stderr = real
