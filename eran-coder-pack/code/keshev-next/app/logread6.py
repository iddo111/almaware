"""logread6 -- read trial.log the way the engine actually writes it, today.

The old window's segment regex (gui.py:235-237) has been matching NOTHING since
main.py:399 started printing `lp=` between gate= and decode=. Measured on the
live 7.0 MB trial.log on 2026-09-04: of the 4,792 recent `decode=ok` lines,
ZERO matched -- so "הוקלדו" read 0 forever and no green row could ever appear.
A second 2,742 lines were lost because main.py truncates with ascii(text)[:80],
which cuts the closing quote off any long sentence. And because the text is
ascii()-escaped, gui.py's Hebrew test (`'֐' <= c <= '׿'`) was always
False, so the RTL alignment could never fire either.

This module fixes all three, and is importable on its own so the fix can be
tested against the real log instead of believed.
"""

import codecs
import re

# 2026-09-11 -- app/logstamp.py now prefixes every engine line with `HH:MM:SS `
# so "when did the last word arrive" is finally a measurable question. Every
# pattern below is anchored with ^, so the prefix is stripped BEFORE they run.
# A line without a stamp (an old trial.log, a test fixture) is returned
# untouched -- this is tolerance, not a new required format.
TS_RE = re.compile(r"^(\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?)\s")


def strip_ts(line):
    """('06:53:42', '[segment] ...') -- or ('', line) when there is no stamp."""
    m = TS_RE.match(line)
    return (m.group(1), line[m.end():]) if m else ("", line)


def unstamp(line):
    """Just the line, stamp removed. The one-liner every old reader needs."""
    return strip_ts(line)[1]


# gate= can be `0.123/PASS`, `0.123/BLOCK` or a bare `-` (no owner gate).
# lp= is present on the success line and absent on empty/fail lines.
# text= is a Python ascii() repr, possibly truncated mid-escape, or a bare `-`.
SEGMENT_RE = re.compile(
    r"^\[segment\]\s+bytes=(\d+)\s+secs=([\d.]+)\s+peak_rms=(\d+)"
    r"\s+gate=(?:([\d.]+)/(PASS|BLOCK)|-)"
    r"(?:\s+lp=(-?[\d.]+))?"
    r"\s+decode=(\S+)\s+route=(\S+)\s+text=(.*)$"
)

# The SKIP family: these are segments the engine threw away BEFORE the decoder.
# They are not failures of the decoder and must never be counted as one.
SKIP_RE = re.compile(
    r"^\[segment\]\s+bytes=(\d+)\s+secs=([\d.]+)\s+peak_rms=(\d+)\s+"
    r"(?:vad=([\d.]+)|mod=([\d.]+)|floor=(\d+))\s+SKIP(?:\s+(\S+))?"
)

MIC_RE = re.compile(
    r"\[mic\]\s+device='([^']+)'.*?native=(\d+)Hz\s+resample=(\d+)/(\d+)"
    r"\s+->\s+(\d+)Hz\s+block=(\d+)ms")
DROPS_RE = re.compile(r"^\[mic\] status_events=(\d+) dropped_blocks=(\d+)")
DEAF_RE = re.compile(r"^\[mic\] DEAF: (.*)$")
HEARTBEAT_RE = re.compile(r"^\[mic\] heartbeat: (\d+) blocks, peak RMS (\d+)")
WAITING_RE = re.compile(r"^\[mic\] waiting for the decoder: (\S+) \((\d+)s\)")
READY_RE = re.compile(r"^\[mic\] decoder READY")
NO_MIC_RE = re.compile(r"^\[mic\] NO ALLOWED USB MIC")
FALLBACK_RE = re.compile(r"^\[decoder\] answered by fallback (\S+)")
TYPER_BLOCKED_RE = re.compile(r"\[typer\] BLOCKED admin-window proc=(\S+)")
# 2026-09-06 -- main.py now prints this BEFORE the [segment] line of a sentence the
# typer refused to type (elevated / Run-as-administrator target). Same shape as
# [textguard], paired by byte count, so the ledger says נחסם instead of הוקלד.
TYPER_REFUSED_RE = re.compile(r"^\[typer\] refused segment \((\d+) bytes\): (.*)$")

# 2026-09-04 -- measured on the live log, and the old window got this WRONG.
# main.py prints [textguard] dropped BEFORE the [segment] line of the same
# segment, and that segment still says `decode=ok route=he`. gui.py called that
# "typed" and counted it. It was decoded, routed, and then thrown away: nothing
# reached his chat. Pair the two lines by their byte count and say so.
TEXTGUARD_RE = re.compile(r"^\[textguard\] dropped segment \((\d+) bytes\): (.*)$")
# same shape: [confidence] dropped is a silent bin -- no [segment] line follows.
CONFIDENCE_RE = re.compile(r"^\[confidence\] dropped \((\d+) bytes, lp=(-?[\d.]+)\)")
# the decode worker fell 32 segments behind and the engine started shedding.
BACKLOG_RE = re.compile(r"^\[segment\] DROPPED: the decode worker is more than (\d+)")

# a trailing escape the [:80] truncation cut in half
_TRUNC_ESCAPE_RE = re.compile(r"(?:\\U[0-9a-fA-F]{0,7}|\\u[0-9a-fA-F]{0,3}|"
                              r"\\x[0-9a-fA-F]?|\\N\{[^}]*|\\)$")


def unrepr(field):
    """Turn main.py's `ascii(text)[:80]` field back into the real string.

    Handles both quote styles, a closing quote lost to truncation, and an
    escape sequence chopped in half. Returns '' when there is no text.
    """
    if field is None:
        return ""
    field = field.strip()
    if not field or field == "-":
        return ""
    quote = field[0]
    if quote not in ("'", '"'):
        body = field
    else:
        body = field[1:]
        if body and body[-1] == quote:
            # a real closing quote, unless an odd run of backslashes escaped it
            stem = body[:-1]
            backslashes = len(stem) - len(stem.rstrip("\\"))
            if backslashes % 2 == 0:
                body = stem
    body = _TRUNC_ESCAPE_RE.sub("", body)
    try:
        return codecs.decode(body, "unicode_escape")
    except Exception:
        # last resort: decode the \uXXXX escapes we can see and keep the rest
        def _one(m):
            try:
                return chr(int(m.group(1), 16))
            except Exception:
                return ""
        return re.sub(r"\\u([0-9a-fA-F]{4})", _one, body)


def has_hebrew(text):
    return any("֐" <= c <= "׿" for c in text)


def parse_segment(line, pending_guard=None):
    """One [segment] line -> dict, or None when the line is not one.

    verdict: 'typed' | 'guarded' | 'blocked' | 'empty' | 'fail' | 'skip'

    'empty' and 'fail' are kept APART on purpose (main.py:374-378): empty means
    the server answered 200 and the honesty guard dropped it; fail means the
    transport broke. Conflating them cost two night-scares.

    pending_guard: {bytes: reason} collected from the [textguard] lines that
    precede a segment. A byte-count hit turns 'typed' into 'guarded' -- decoded,
    routed, and then NOT typed. Only 'typed' means text reached his chat.

    A leading `HH:MM:SS ` stamp (2026-09-11, app/logstamp.py) is removed first
    and returned as `at`; lines without one still parse exactly as before.
    """
    at, line = strip_ts(line)
    m = SKIP_RE.match(line)
    if m:
        bytes_, secs, rms, vad, mod, floor, why = m.groups()
        return {"verdict": "skip", "at": at,
                "bytes": int(bytes_), "peak_rms": int(rms),
                "secs": float(secs), "gate": None, "lp": None, "text": "",
                "reason": (why or ("too-quiet" if floor else ("vad" if vad else "steady-noise"))),
                "vad": float(vad) if vad else None,
                "mod": float(mod) if mod else None,
                "floor": int(floor) if floor else None}
    m = SEGMENT_RE.match(line)
    if not m:
        return None
    bytes_, secs, rms, gate, gate_status, lp, decode, route, text_field = m.groups()
    nbytes = int(bytes_)
    text = unrepr(text_field)
    reason = ""
    if gate_status == "BLOCK":
        verdict = "blocked"
    elif decode == "ok" and route != "-":
        verdict = "typed"
        if pending_guard is not None:
            reason = pending_guard.pop(nbytes, "")
            if reason:
                verdict = "guarded"
    elif decode == "fail":
        verdict = "fail"
    else:
        verdict = "empty"
    return {"verdict": verdict, "at": at, "bytes": nbytes, "peak_rms": int(rms),
            "secs": float(secs), "gate": float(gate) if gate else None,
            "lp": float(lp) if lp else None, "text": text, "reason": reason,
            "vad": None, "mod": None, "floor": None}
