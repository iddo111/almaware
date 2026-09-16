r"""logstamp -- put a clock on every line the engine writes to trial.log.

🪟 BROKEN WINDOWS LAW: test the REAL output, not a proxy.

WHY
---
trial.log carried no timestamps at all. "When did the last word actually reach
his chat?" was therefore UNANSWERABLE -- the delivery watchdog says so itself in
`read_window()`: "the window is taken by POSITION, not by clock ... it CANNOT
answer 'at 14:03 exactly'". Every night-scare of the last month ("the mic died
at some point", "310 minutes silent") was diagnosed by counting lines backwards.
That ends here: one prefix, `HH:MM:SS `, on every line, written by the engine
itself at the moment it prints.

HOW, AND WHY NOT MORE
---------------------
Only sys.stderr is wrapped. Everything main.py logs goes to stderr (gui6 spawns
it with stdout=trial.log, stderr=STDOUT, so both land in the same file), while
STDOUT carries exactly one machine-read payload -- the `--list-devices` JSON the
window's chooser parses. Stamping that JSON would break the mic chooser, so
stdout is left alone. One wrapper, one channel, no format changed.

Readers stay tolerant, not rewritten: `logread6.strip_ts()` removes the prefix
before any of the existing `^\[segment\]` regexes run, and gui6 / the delivery
watchdog / mic_probe all go through it. A log line with no stamp (an old file,
a test fixture) parses exactly as it always did.

Off switch: KESHEV_LOG_TIMESTAMPS=0.
"""
from __future__ import annotations

import os
import sys
import threading
import time

TS_FORMAT = "%H:%M:%S"


class TimestampedStream:
    """A text stream that prefixes HH:MM:SS to the start of every line.

    Partial writes are handled (print() emits the text and the newline as two
    separate write() calls), and the whole thing is under one lock because the
    engine logs from the audio callback thread, the decode worker and the main
    thread at once -- an interleaved prefix would corrupt the line it stamps.
    """

    def __init__(self, stream):
        self._s = stream
        self._lock = threading.Lock()
        self._at_line_start = True

    # -- the only two methods that do anything ---------------------------
    def write(self, data):
        if not data:
            return 0
        try:
            with self._lock:
                out = []
                for part in data.splitlines(keepends=True):
                    if self._at_line_start:
                        out.append(time.strftime(TS_FORMAT))
                        out.append(" ")
                    out.append(part)
                    self._at_line_start = part.endswith("\n") or part.endswith("\r")
                self._s.write("".join(out))
        except Exception:
            # A logger must never be the thing that kills the microphone.
            try:
                self._s.write(data)
            except Exception:
                return 0
        return len(data)

    def flush(self):
        try:
            self._s.flush()
        except Exception:
            pass

    # -- everything else is the wrapped stream ---------------------------
    def __getattr__(self, name):
        return getattr(self._s, name)

    @property
    def raw_stream(self):
        return self._s


def install(stream_name="stderr"):
    """Wrap sys.<stream_name> once. Returns True when it was installed now."""
    if os.environ.get("KESHEV_LOG_TIMESTAMPS", "1").strip() not in ("1", "true", "yes", "on"):
        return False
    cur = getattr(sys, stream_name, None)
    if cur is None or isinstance(cur, TimestampedStream):
        return False
    setattr(sys, stream_name, TimestampedStream(cur))
    return True


if __name__ == "__main__":
    # python app/logstamp.py --selftest : proves the prefix on the real shapes
    # main.py prints, including a print() split into text + newline.
    import io as _io
    buf = _io.StringIO()
    s = TimestampedStream(buf)
    print("[mic] heartbeat: 936 blocks, peak RMS 333", file=s)
    s.write("[segment] bytes=1 secs=0.1 ")
    s.write("peak_rms=700 gate=- lp=-0.20 decode=ok route=he text='x'\n")
    s.write("a\nb\n")
    lines = buf.getvalue().splitlines()
    import re as _re
    ok = len(lines) == 4 and all(_re.match(r"^\d{2}:\d{2}:\d{2} \S", ln) for ln in lines)
    ok = ok and lines[1].endswith("decode=ok route=he text='x'")
    ok = ok and lines[1].count(":") >= 2 and "peak_rms=700" in lines[1]
    # the partial write must NOT get a second stamp in the middle of the line
    ok = ok and lines[1].count("bytes=1") == 1 and len(lines[1].split("[segment]")) == 2
    for ln in lines:
        print(repr(ln))
    print("LOGSTAMP OK" if ok else "LOGSTAMP FAIL")
    sys.exit(0 if ok else 1)
