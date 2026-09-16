"""Proof for app/logread6.py -- the reader the KESHEV 6 window trusts.

Why this file exists: the old window's regex silently stopped matching when
main.py started printing `lp=`, and nobody noticed for a day because the window
had no way to say "I understood 0 of the last 4,792 lines". These tests run
against BOTH synthetic lines and the real trial.log, and the real-log test
FAILS if the parser's coverage ever drops -- so the next format change is loud.

Run:  python -X utf8 tests\test_logread6.py
"""

import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
import logread6 as L  # noqa: E402

TRIAL_LOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "trial.log")

FAILURES = []


def check(label, got, want):
    if got == want:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}\n       got  {got!r}\n       want {want!r}")
        FAILURES.append(label)


def check_true(label, cond, detail=""):
    if cond:
        print(f"  ok   {label} {detail}")
    else:
        print(f"  FAIL {label} {detail}")
        FAILURES.append(label)


print("unrepr -- main.py writes ascii(text)[:80], so quotes and escapes get cut")
Q, D, BS = "'", '"', "\\"
check("full hebrew repr", L.unrepr(Q + BS + "u05e9" + BS + "u05dc" + BS + "u05d5" + BS + "u05dd" + Q), "שלום")
check("closing quote lost to [:80]", L.unrepr(Q + BS + "u05e9" + BS + "u05dc"), "של")
check("escape chopped in half", L.unrepr(Q + BS + "u05e9" + BS + "u05d"), "ש")
check("bare backslash at the cut", L.unrepr(Q + BS + "u05e9" + BS), "ש")
check("double-quoted repr (text had an apostrophe)", L.unrepr(D + "it" + Q + "s" + D), "it's")
check("escaped backslash then close", L.unrepr(Q + "a" + BS + BS + Q), "a" + BS)
check("no text", L.unrepr("-"), "")
check("empty field", L.unrepr(""), "")
check("None", L.unrepr(None), "")
check_true("hebrew is detected AFTER unescaping (gui.py tested the escapes)",
           L.has_hebrew(L.unrepr(Q + BS + "u05e9" + BS + "u05dc" + BS + "u05d5" + BS + "u05dd" + Q)))
check_true("the escaped form itself has no hebrew -- the old RTL test could never fire",
           not L.has_hebrew(BS + "u05e9" + BS + "u05dc"))

print("\nparse_segment -- the live line shapes")
ok_line = ("[segment] bytes=161792 secs=5.06 peak_rms=8061 gate=0.584/PASS lp=-0.60 "
           "decode=ok route=he text=" + Q + BS + "u05e9" + BS + "u05dc" + BS + "u05d5" + BS + "u05dd" + Q)
d = L.parse_segment(ok_line, {})
check("typed verdict", d["verdict"], "typed")
check("typed text", d["text"], "שלום")
check("typed lp", d["lp"], -0.60)

empty_line = ("[segment] bytes=57344 secs=1.79 peak_rms=2611 gate=0.671/PASS "
              "decode=empty route=- text=-")
check("empty verdict (no lp= on this shape)", L.parse_segment(empty_line, {})["verdict"], "empty")

fail_line = ("[segment] bytes=57344 secs=1.79 peak_rms=2611 gate=0.671/PASS "
             "decode=fail route=- text=-")
check("fail stays apart from empty", L.parse_segment(fail_line, {})["verdict"], "fail")

block_line = ("[segment] bytes=100 secs=0.5 peak_rms=900 gate=0.100/BLOCK "
              "decode=- route=- text=-")
check("owner-gate block", L.parse_segment(block_line, {})["verdict"], "blocked")

nogate_line = ("[segment] bytes=100 secs=0.5 peak_rms=900 gate=- lp=-0.3 "
               "decode=ok route=he text=" + Q + "hi" + Q)
check("bare gate=- (no owner gate)", L.parse_segment(nogate_line, {})["verdict"], "typed")

for line, want, why in [
    ("[segment] bytes=16384 secs=0.51 peak_rms=255 floor=600 SKIP too-quiet", "too-quiet", "floor"),
    ("[segment] bytes=108544 secs=3.39 peak_rms=972 vad=0.05 SKIP", "vad", "vad"),
    ("[segment] bytes=1 secs=0.1 peak_rms=9 mod=0.20 SKIP steady-noise", "steady-noise", "mod"),
]:
    s = L.parse_segment(line, {})
    check(f"skip/{why} verdict", s["verdict"], "skip")
    check(f"skip/{why} reason", s["reason"], want)

print("\ntextguard pairing -- decoded, routed, and then NOT typed")
# main.py prints [textguard] dropped BEFORE the [segment] line of the SAME segment,
# and that segment still reads decode=ok route=he. gui.py counted it as typed.
pend = {}
m = L.TEXTGUARD_RE.match("[textguard] dropped segment (161792 bytes): blocklist:תודה")
check_true("textguard line parses", m is not None)
pend[int(m.group(1))] = m.group(2)
g = L.parse_segment(ok_line, pend)
check("same-byte segment becomes 'guarded', not 'typed'", g["verdict"], "guarded")
check("and it carries the reason", g["reason"], "blocklist:תודה")
check("the pending entry is consumed", pend, {})
check("a different segment is still typed", L.parse_segment(ok_line, pend)["verdict"], "typed")

print("\ntyper refusal pairing (2026-09-06) -- decoded, routed, refused by the typer (admin window)")
refused = ("[typer] refused segment (161792 bytes): elevated proc=windowsterminal.exe integrity=HIGH"
           " | החלון הפעיל רץ כמנהל | The focused window runs as Administrator")
m = L.TYPER_REFUSED_RE.match(refused)
check_true("typer refused line parses", m is not None)
check("byte count is the pairing key", int(m.group(1)), 161792)
pend = {int(m.group(1)): "admin-window: " + m.group(2).split(" | ")[0]}
g = L.parse_segment(ok_line, pend)
check("same-byte segment becomes 'guarded', not 'typed'", g["verdict"], "guarded")
check("and names the admin window", g["reason"],
      "admin-window: elevated proc=windowsterminal.exe integrity=HIGH")
check_true("the 09-03 BLOCKED banner line still matches (unchanged format)",
           L.TYPER_BLOCKED_RE.match("[typer] BLOCKED admin-window proc=windowsterminal.exe integrity=HIGH: x") is not None)

print("\nother honest-state lines")
check_true("confidence drop", L.CONFIDENCE_RE.match("[confidence] dropped (161792 bytes, lp=-1.90)") is not None)
check_true("backlog shed", L.BACKLOG_RE.match("[segment] DROPPED: the decode worker is more than 32 segments behind") is not None)
check_true("fallback answered", L.FALLBACK_RE.match("[decoder] answered by fallback http://<lan-ip>:8737/v1/transcribe") is not None)
check_true("waiting for decoder", L.WAITING_RE.match("[mic] waiting for the decoder: UNREACHABLE (15s)") is not None)
check_true("decoder ready", L.READY_RE.match("[mic] decoder READY - listening") is not None)
check_true("DEAF", L.DEAF_RE.match("[mic] DEAF: no audio blocks arrived in 60s (1 min running).") is not None)
check_true("mic device", L.MIC_RE.search(
    "[mic] device='Microphone (Logitech BRIO)' [Windows DirectSound] (index 19 at pick time, "
    "re-resolved at open, fenced) native=44100Hz resample=160/441 -> 16000Hz block=64ms") is not None)
check_true("drops", L.DROPS_RE.match("[mic] status_events=3 dropped_blocks=256") is not None)

print("\nagainst the REAL trial.log (regression fence)")
if not os.path.exists(TRIAL_LOG):
    print("  skip -- no trial.log here")
else:
    total = parsed = 0
    pend = {}
    verdicts = {}
    with io.open(TRIAL_LOG, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            m = L.TEXTGUARD_RE.match(line)
            if m:
                pend[int(m.group(1))] = m.group(2)
                continue
            if not line.startswith("[segment] bytes="):
                continue
            total += 1
            d = L.parse_segment(line, pend)
            if d:
                parsed += 1
                verdicts[d["verdict"]] = verdicts.get(d["verdict"], 0) + 1
    cover = parsed / total if total else 0.0
    print(f"  {parsed}/{total} lines understood ({cover:.4%})")
    print(f"  verdicts: {verdicts}")
    check_true("coverage of real [segment] bytes= lines is 100%", cover >= 0.9999, f"({cover:.4%})")
    check_true("real typed lines exist (the old regex found 0 of the recent ones)",
               verdicts.get("typed", 0) > 0, f"typed={verdicts.get('typed', 0)}")
    check_true("guarded lines exist and are NOT counted as typed",
               verdicts.get("guarded", 0) > 0, f"guarded={verdicts.get('guarded', 0)}")

print()
if FAILURES:
    print(f"FAILED {len(FAILURES)}: {FAILURES}")
    sys.exit(1)
print("all logread6 checks passed")
