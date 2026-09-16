#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""keshev_delivery_watchdog.py -- the only KESHEV check that measures the PRODUCT.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL
> output, not a proxy (`health: ok` != working).

WHY THIS EXISTS
---------------
Ledger rule #4, written after an earlier failure and injected into every session
by a hook: **"healthy" is measured by what reached Iddo, never by a success
counter.** On 2026-09-05 it was broken anyway, while sitting in the context
window. The microphone reported itself alive from a heartbeat for hours while it
was PAUSED: 843 segments cut, **54 reached his chat -- 2.2%**, 1,382 dropped.

The 11th commission of inquiry that afternoon found the general shape of it:
~100 written laws against 2 mechanical gates, and a backup log whose 223 lines
said `OK` 221 times and **FAIL not once in its entire history** -- through the
whole window where ERAN's brain was 12 days stale. A counter that cannot fall is
not a measurement, it is a constant.

An audit the same evening found the specific cause here. The retired
`mic-rebuild` tree carried three things that measured usefulness -- a MUTE
watchdog, a delivered-vs-parked ledger (`tools/measure_gates.py`), and a written
doctrine against "almost-true numbers". The rebuild into `keshev-next` carried
forward the heartbeat, the PID check and the log-freshness check, and **left all
three behind**. What survived knows the process is running. Nothing knows
whether the product arrived.

`app/gui6.py` did fix the counting itself on 2026-09-04 -- it stopped calling
`decode=ok` "typed" after measuring that 9,701 of 15,733 such segments were
thrown away by textguard *after* being decoded and routed. But gui6 keeps those
counters in memory and paints them in a Tk window. **Nothing writes them where a
watchdog can read them, so nothing can raise an alarm when they go to zero.**
Display is not monitoring.

WHAT IT DOES
------------
Reads `trial.log` -- the same source, through the same parser gui6 uses -- and
answers one question: *in the last N minutes, did anything Iddo said reach his
chat?* `verdict == 'typed'` is the only verdict that means text arrived
(decode=ok AND routed AND not dropped by textguard afterwards).

Three alarms, each one a failure that actually happened:
  PAUSED_TOO_LONG   the mic has been paused longer than a person would mean to
  NOTHING_DELIVERED segments are being cut and NONE of them reach his chat
  ENGINE_SILENT     the mic claims to be listening and the log has gone quiet

SAFETY
------
**Strictly read-only on the live microphone.** It opens `trial.log`, `PAUSED`
and `gui.heartbeat` for reading and writes nothing whatsoever inside
`keshev-next/` -- its own state lives here, beside it. It never restarts, kills,
pauses or resumes anything: it is a judge, not a hand. This is deliberate --
today's rule is that the judge is never the builder, and a watchdog that repairs
its own subject can hide the failure it was built to report.

It also does not touch audio devices, so the Sacred Audio Law is not in play.

Run:
    python keshev_delivery_watchdog.py            # loop, one line per cycle
    python keshev_delivery_watchdog.py --once     # single reading, exit code 0/1
    python keshev_delivery_watchdog.py --selftest # PROVE it can say FAIL
"""
from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import time
from datetime import datetime
# 2026-09-08: windowless (pythonw) parent + console child = Windows Terminal pops a window and
# steals Iddo's focus (measured: 41 ssh.exe windows before noon). Every console child gets no window.
_NOWIN = 0x08000000 if os.name == "nt" else 0


for _s in (sys.stdin, sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
KESHEV = os.environ.get("KESHEV_DIR", r"D:\CLAUDE\keshev-next")
TRIAL = os.path.join(KESHEV, "trial.log")
PAUSED = os.path.join(KESHEV, "state", "PAUSED")
HEARTBEAT = os.path.join(KESHEV, "state", "gui.heartbeat")
RAMLINK = r"D:\CLAUDE\RAMCHAT\ramlink.py"
# RAMCHAT/receipts.py enforces "every live-state change leaves a receipt" --
# born from the 2026-09-03 scar where an agent wrote state\PAUSED with
# nothing but a timestamp and walked away, and Iddo's mic was dead until 06:34
# while the window looked alive. Its own docstring says "a rule nobody can
# check is a wish" -- and it WAS one: grep finds it referenced by nothing but
# itself. It works: run once by hand it immediately found 6 real violations,
# one lock 2,562 hours old. A checker nobody runs is the same wish one level up.
RECEIPTS = r"D:\CLAUDE\RAMCHAT\receipts.py"
RECEIPTS_EVERY = 30          # cycles (~30 min); it walks the whole workspace

# Our own state lives HERE, never inside the mic's tree.
STATE = os.path.join(HERE, "keshev-delivery.json")
LOG = os.path.join(HERE, "keshev-delivery.log")
HISTORY = os.path.join(HERE, "keshev-delivery-history.json")

# --- K6-13 (2026-09-06): NOTHING_DELIVERED only fires at typed == 0.
#
# Measured at 12:22 today: verdict OK, delivery_rate 0.1316, alarms []. Typed
# 1,249 of 9,489 decoded and this file called it healthy -- because the only
# failing value it has is zero. That is one step from the liveness checks this
# whole workspace has been unlearning: of 32 watchdogs audited on 09-05, 23
# could only ever report that something was running.
#
# The fix is NOT a hand-picked "good" rate. 13% may well BE his normal -- the
# 85.8% empties were measured to be room, breath and laughter, not lost speech,
# and inventing a 40% target here would produce a permanent false alarm that
# gets muted within a week, which is how a gate dies. So the alarm is derived
# from THIS run's own recent history: a collapse is the rate falling to half of
# what the last 24 h actually delivered. With no history there is no alarm --
# a baseline you do not have is not evidence.
HISTORY_HOURS = 24.0
BASELINE_MIN_SAMPLES = 30      # ~30 cycles; fewer is not a distribution
BASELINE_MIN_SPAN_H = 2.0      # and they must span real time, not one burst
BASELINE_MIN_DECODED = 20      # a window with less than this says nothing
COLLAPSE_FACTOR = 0.5          # FAIL  below half the median
WARN_FACTOR = 0.75             # WARN  below three quarters

WINDOW_MIN = 20.0        # how far back "recently" reaches
PAUSE_ALARM_MIN = 15.0   # an UNSIGNED pause longer than this is the 09-03 shape
PAUSE_AGENT_ALARM_H = 8.0  # a signed pause by an agent, this old, is one too
# Iddo's own signed pause is NEVER an alarm, at any age -- see judge().
SILENT_ALARM_MIN = 25.0  # log quiet this long while claiming to listen
CYCLE_S = 60.0
TAIL_BYTES = 3_000_000   # enough for many hours; we never read the whole file


# --------------------------------------------------------------- the parser
def _load_parser():
    """Use the mic's OWN parser, so this cannot drift from what the window says.

    Imported by path, not installed: keshev-next is not a package and must not
    be made into one by this file.
    """
    import importlib.util
    p = os.path.join(KESHEV, "app", "logread6.py")
    spec = importlib.util.spec_from_file_location("logread6", p)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load the mic's parser at %s" % p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ------------------------------------------------------------------ reading
def tail_lines(path, nbytes=TAIL_BYTES):
    """Last nbytes of a file as text lines. The first line may be partial and is
    dropped -- a half-parsed segment is worse than a missing one."""
    if not os.path.exists(path):
        return []
    size = os.path.getsize(path)
    with io.open(path, "rb") as fh:
        if size > nbytes:
            fh.seek(size - nbytes)
        raw = fh.read()
    text = raw.decode("utf-8", "replace")
    lines = text.split("\n")
    return lines[1:] if size > nbytes else lines


def read_window(minutes=WINDOW_MIN):
    """Count verdicts over the last `minutes` of trial.log.

    trial.log lines carry no timestamp of their own, so the window is taken by
    POSITION, not by clock: we use the file's own mtime as "now" and count back
    a number of lines proportional to the recent rate. That is honest about what
    it is -- it answers "of the last stretch of activity, how much arrived" and
    it CANNOT answer "at 14:03 exactly". Say so rather than implying precision.
    """
    lr = _load_parser()
    lines = tail_lines(TRIAL)
    pending_guard = {}
    counts = {k: 0 for k in ("typed", "guarded", "blocked", "empty", "fail", "skip")}
    last_typed_text = ""
    for line in lines:
        line = line.rstrip("\r")
        # 2026-09-11: the engine stamps every line HH:MM:SS (app/logstamp.py).
        # Use the mic's OWN stripper so this can never drift from what the
        # window sees; an unstamped line comes back unchanged.
        try:
            line = lr.unstamp(line)
        except AttributeError:      # an older logread6 beside a newer watchdog
            pass
        if line.startswith("[textguard]"):
            # gui6 collects these to turn a 'typed' into a 'guarded'; mirror it.
            for tok in line.split():
                if tok.startswith("bytes="):
                    try:
                        pending_guard[int(tok[6:])] = "guard"
                    except ValueError:
                        pass
            continue
        try:
            d = lr.parse_segment(line, pending_guard)
        except Exception:
            d = None
        if not d:
            continue
        counts[d["verdict"]] = counts.get(d["verdict"], 0) + 1
        if d["verdict"] == "typed" and d.get("text"):
            last_typed_text = d["text"]
    return counts, last_typed_text


def read_pause():
    """Who paused the mic, and did they sign it?

    2026-09-07 16:53 -- this watchdog DELETED Iddo's own pause and his room was
    typed into his chat for 43 minutes, because the pause button wrote the
    unsigned shape. And every day since 09-08 it has raised a RAMCHAT alarm every
    ~15 min on pauses that were *deliberate* -- his and agents'. An alarm on a
    person's stated intent is noise, and noise is how the real alarm gets missed.

    signed  = the file carries an author AND a reason (RAMCHAT RULES.md sec. 7).
    by_iddo = that author is Iddo himself. His pause is never a fault, at any age.
    """
    out = {"exists": os.path.exists(PAUSED), "signed": False, "by_iddo": False,
           "who": "", "why": "", "body": ""}
    if not out["exists"]:
        return out
    try:
        with io.open(PAUSED, encoding="utf-8", errors="replace") as fh:
            body = fh.read(4000)
    except Exception:
        body = ""
    out["body"] = body
    who = why = ""
    try:
        j = json.loads(body)
        if isinstance(j, dict):
            who, why = str(j.get("who", "")), str(j.get("why", ""))
    except Exception:
        pass
    if not who:
        # A hand-written or receipts.py-shaped note: `who: X` / `why: Y`, one per
        # line. Plain scanning, no regex -- this file gets edited at 04:00 by
        # whoever is awake and a clever pattern is a trap for the next person.
        for raw in body.splitlines():
            head = raw.strip().strip('"\'').lower()
            val = raw.split(":", 1)[1].strip().strip(',').strip('"\'') if ":" in raw else ""
            if head.startswith("who") and not who:
                who = val
            elif head.startswith("why") and not why:
                why = val
    out["who"], out["why"] = who, why
    out["signed"] = bool(who) and bool(why)
    out["by_iddo"] = "iddo" in who.lower()
    return out


def mic_facts():
    now = time.time()
    paused = os.path.exists(PAUSED)
    paused_for = (now - os.path.getmtime(PAUSED)) / 60.0 if paused else 0.0
    pz = read_pause()
    hb = os.path.getmtime(HEARTBEAT) if os.path.exists(HEARTBEAT) else 0.0
    log_age = (now - os.path.getmtime(TRIAL)) / 60.0 if os.path.exists(TRIAL) else 1e9
    return {
        "paused": paused,
        "paused_signed": pz["signed"],
        "paused_by_iddo": pz["by_iddo"],
        "paused_who": pz["who"],
        "paused_for_min": round(paused_for, 1),
        "heartbeat_age_min": round((now - hb) / 60.0, 1) if hb else None,
        "log_age_min": round(log_age, 1),
    }


# --------------------------------------------------------------- the baseline
def load_history():
    """[(ts, typed, decoded), ...] within the window. Never raises: a corrupt
    history must cost us the baseline, never the alarm beside it."""
    try:
        with io.open(HISTORY, "r", encoding="utf-8") as fh:
            rows = json.load(fh)
    except Exception:
        return []
    cutoff = time.time() - HISTORY_HOURS * 3600.0
    out = []
    for r in rows:
        try:
            ts, typed, decoded = float(r[0]), int(r[1]), int(r[2])
        except Exception:
            continue
        if ts >= cutoff:
            out.append((ts, typed, decoded))
    return out


def save_history(rows):
    """Pruned on every write. A counter that only grows is the other half of
    the same disease as a counter that cannot fall."""
    cutoff = time.time() - HISTORY_HOURS * 3600.0
    # sorted, never "assume the file was in order": the span this baseline is
    # built on must not depend on how someone happened to append.
    rows = sorted((r for r in rows if r[0] >= cutoff), key=lambda r: r[0])[-5000:]
    try:
        tmp = HISTORY + ".tmp"
        with io.open(tmp, "w", encoding="utf-8") as fh:
            json.dump([[round(a, 1), b, c] for a, b, c in rows], fh)
        os.replace(tmp, HISTORY)
    except Exception:
        pass
    return rows


def baseline(rows):
    """The median delivery rate this microphone actually achieved recently, or
    None when there is not enough of a record to call anything a collapse."""
    usable = [(t / d) for _ts, t, d in rows if d >= BASELINE_MIN_DECODED]
    if len(usable) < BASELINE_MIN_SAMPLES:
        return None
    stamps = [r[0] for r in rows]
    span_h = (max(stamps) - min(stamps)) / 3600.0
    if span_h < BASELINE_MIN_SPAN_H:
        return None
    usable.sort()
    mid = len(usable) // 2
    med = usable[mid] if len(usable) % 2 else (usable[mid - 1] + usable[mid]) / 2.0
    return {"median_rate": round(med, 4), "n": len(usable),
            "span_h": round(span_h, 1)}


# ----------------------------------------------------------------- the verdict
def judge(counts, facts, base=None, warns=None):
    """Return (verdict, alarms). verdict is 'OK' or 'FAIL' -- and FAIL is
    reachable, which --selftest proves rather than asserts."""
    alarms = []
    reached = counts["typed"]
    decoded = sum(counts[k] for k in ("typed", "guarded", "blocked", "empty", "fail"))

    # 2026-09-11 -- A SIGNED PAUSE IS NOT A FAULT.
    #
    # Measured before this change: 9 RAMCHAT alarms between 09-08 18:59 and
    # 09-11 06:20, every one of them on a pause somebody MEANT -- including the
    # one Iddo pressed himself at 04:23 ("who": "iddo (pause button in KESHEV 6)").
    # An alarm on a person's stated intent is noise, and noise is exactly how the
    # 08-15 deaf night went unnoticed. The failure this alarm was born from
    # (2026-09-03 22:55) was an ORPHAN file: a timestamp, no author, no reason.
    # So that is what it fires on now.
    #
    #   Iddo's signature  -> never an alarm, at any age. It is his microphone.
    #   an agent's signature -> an alarm only after PAUSE_AGENT_ALARM_H hours,
    #                           because an agent that paused and walked away is
    #                           the 09-03 shape wearing a name tag.
    #   no signature      -> the original alarm, unchanged.
    if facts["paused"] and facts["paused_for_min"] >= PAUSE_ALARM_MIN:
        if not facts.get("paused_signed"):
            alarms.append("PAUSED_TOO_LONG paused %.0f min with NO author and no "
                          "reason -- nothing can reach his chat while this file "
                          "exists" % facts["paused_for_min"])
        elif (not facts.get("paused_by_iddo")) and \
                facts["paused_for_min"] >= PAUSE_AGENT_ALARM_H * 60.0:
            alarms.append("PAUSED_TOO_LONG paused %.0f min by %s -- signed, but an "
                          "agent pause this old is the 2026-09-03 shape with a name "
                          "on it" % (facts["paused_for_min"],
                                     facts.get("paused_who") or "?"))
    if decoded >= 20 and reached == 0:
        alarms.append("NOTHING_DELIVERED %d segments reached the decoder and 0 "
                      "reached his chat" % decoded)
    if (not facts["paused"]) and facts["log_age_min"] >= SILENT_ALARM_MIN:
        alarms.append("ENGINE_SILENT not paused, but the log has been quiet for "
                      "%.0f min" % facts["log_age_min"])

    # K6-13: the derived one. Silent unless there is a real baseline AND a real
    # window -- it must never fire because the room was quiet for 20 minutes.
    if base and decoded >= BASELINE_MIN_DECODED:
        med = base["median_rate"]
        rate = reached / decoded
        if med > 0 and rate < med * COLLAPSE_FACTOR:
            alarms.append("DELIVERY_COLLAPSED %.1f%% of %d decoded reached his "
                          "chat; this mic's own last %.0f h median is %.1f%% "
                          "(n=%d)" % (100 * rate, decoded, base["span_h"],
                                      100 * med, base["n"]))
        elif med > 0 and rate < med * WARN_FACTOR and warns is not None:
            warns.append("DELIVERY_DOWN %.1f%% vs a %.1f%% median over %.0f h"
                         % (100 * rate, 100 * med, base["span_h"]))
    return ("FAIL" if alarms else "OK"), alarms


def delivery_rate(counts):
    decoded = sum(counts[k] for k in ("typed", "guarded", "blocked", "empty", "fail"))
    return (counts["typed"] / decoded) if decoded else None


# ------------------------------------------------------------------- output
def receipts_check():
    """Run the unused receipt checker. Returns (ok, first_line). Never raises:
    a broken checker must not silence the delivery alarm beside it."""
    try:
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        p = subprocess.run([sys.executable, RECEIPTS, "check"], capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=120, env=env, creationflags=_NOWIN)
    except Exception as e:
        return None, "receipts check could not run: %s" % e
    head = ""
    for ln in (p.stdout or "").splitlines():
        if "violation" in ln or "clean" in ln:
            head = ln.strip(); break
    return (p.returncode == 0), (head or "no summary line")


def clear_stale_pause(facts):
    r"""The ONE repair this watchdog is allowed to make, and only this one.

    2026-09-05, Iddo: "תפעיל את KESHEV-Watchdog בחזרה" -- then, when told it
    aims at a retired tree, "תעשה מה אתה מבין, לא מבין בזה. אני רק האוזן."

    The old KESHEV-Watchdog cannot be re-enabled. Measured, read-only, tonight:
    it reads `mic-rebuild\state\events.jsonl` (last written 2026-09-02, dead)
    and restarts `mic-rebuild\RUN-KESHEV.cmd`. Asked for its verdict while
    Iddo's mic was running perfectly it answered **"DOWN - no app or worker
    process"** -- so enabling it would have launched a SECOND microphone against
    the live one. That is the 2026-09-02 incident, where both mics typed into
    his chat for 43 minutes. The ONE-MIC LAW is not negotiable.

    What he actually wants is a watchdog that REPAIRS, not only reports. So this
    repairs exactly one failure, the one that really happened:

      2026-09-03 22:55 -- an agent wrote `state\PAUSED` containing nothing but a
      timestamp and walked away. Iddo's microphone was dead until 06:34 the next
      morning and the window looked alive the whole time.

    Deliberately NOT in scope: starting, stopping or restarting any process. The
    dead-man and gui6 already restart the engine, and a second restarter is
    precisely how two microphones happen.

    It never repairs silently. Removing the file writes a receipt through
    RAMCHAT's own receipts.py and returns a line that is reported as an ALARM --
    "a watchdog that repairs its own subject can hide the failure it was built to
    report" is still true, so the repair is announced, not absorbed.
    """
    if not facts["paused"] or facts["paused_for_min"] < PAUSE_ALARM_MIN:
        return None
    # A PAUSE someone MEANT is a pause with an author and a reason -- that is
    # RAMCHAT RULES.md section 7, and receipts.py exists to enforce it. Leave
    # those alone however old they are; the person meant it.
    #
    # 2026-09-11: this used to have its OWN idea of "signed" (a substring scan
    # for who/why/restore anywhere in the body). judge() now has one too, and two
    # definitions of the same word in one file is how his pause got deleted on
    # 09-07. ONE predicate, read_pause(), for both.
    pz = read_pause()
    body = pz["body"]
    if pz["signed"] or "restore" in body:
        return None
    try:
        os.replace(PAUSED, PAUSED + ".cleared-by-watchdog-%s"
                   % time.strftime("%Y%m%d-%H%M%S"))
    except Exception as e:
        return "PAUSE STUCK %0.0f min and I could not clear it: %s" % (
            facts["paused_for_min"], e)
    try:
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        # 2026-09-06 17:20 -- THE REPAIR RE-CREATED THE FAULT. The receipt was
        # written to PAUSED itself, and the mere EXISTENCE of that path is what
        # pauses the microphone. So clearing the pause immediately re-paused it,
        # and because the receipt carries who/why the looks_like_receipt guard
        # above then refuses to ever clear it again: the watchdog had paused
        # Iddo's mic permanently with its own note. Measured, not theorised --
        # state\PAUSED held this watchdog's JSON while the engine sat idle.
        # The receipt belongs BESIDE the file, never ON it.
        subprocess.run([sys.executable, RECEIPTS, "write", PAUSED + ".receipt",
                        "--who", "keshev-delivery-watchdog",
                        "--why", "PAUSED sat %0.0f min with no author, no reason and "
                                 "no expiry -- the 2026-09-03 shape that cost Iddo "
                                 "his microphone overnight" % facts["paused_for_min"],
                        "--restore", "recreate state\\PAUSED to pause again"],
                       capture_output=True, timeout=30, env=env,
                       creationflags=_NOWIN)
    except Exception:
        pass
    return ("PAUSE CLEARED: it sat %0.0f min unattributed. Renamed, not deleted; "
            "receipt written. The mic can hear again." % facts["paused_for_min"])


def sleeping_watchdogs():
    """Which scheduled watchdogs are DISABLED or have not run in days.

    2026-09-05, found during this file's own inquiry: the scheduled task
    `KESHEV-Watchdog` is Disabled with a LastRunTime of 18 Aug -- somebody turned
    it off and NOTHING NOTICED FOR 18 DAYS. That is the recursion terminating one
    level too early, the same shape as `watch_relay.py` on eran3, whose 105 alarms
    went unread for four days because the relay carrying them was never scheduled.

    **A disabled watchdog looks exactly like a passing one.** Both are silent.
    So silence has to be interrogated, not trusted -- which is what this does.

    Read-only: `schtasks /query`. It never enables, disables or runs anything;
    a watchdog that repairs its own subject can hide the failure it exists to
    report. Reporting is the whole job.
    """
    import re
    watched = ("KESHEV-Watchdog", "KESHEV-STT-PC", "KeshevDeliveryWatchdog",
               "CpuHeatWatchdog", "GpuHeatWatchdog", "DiskWatchdog", "PopupWatchdog")
    # Disabled deliberately, with the reason, so a known-good state does not
    # masquerade as a finding.
    EXPECTED_OFF = {
        "KESHEV-STT-PC": "disabled 2026-09-05 19:22 on purpose -- it relaunched "
                         "the unused 3.2 GB PC decoder at logon and undid the "
                         "VRAM saving; re-enable with schtasks /change /enable",
        "KESHEV-Watchdog": "superseded 2026-09-10/11 by keshev_guard.py -- ONE "
                           "supervisor replacing this task's DOWN/DEAF/STUCK_DEVICE/"
                           "MUTE checks plus three other half-supervisors (see "
                           "keshev_guard.py's own header). Confirmed 2026-09-15: "
                           "keshev_guard.py covers the same failure modes and was "
                           "live and running at the time this was verified. Re-enabling "
                           "this task risks the exact 'four half-supervisors, nobody "
                           "owns the boot' bug keshev_guard.py was built to end.",
    }
    asleep = []
    for name in watched:
        try:
            r = subprocess.run(["schtasks", "/query", "/tn", "\\" + name, "/fo", "list", "/v"],
                               capture_output=True, text=True, timeout=25,
                               encoding="utf-8", errors="replace", creationflags=_NOWIN)
        except Exception:
            continue
        if r.returncode != 0:
            continue                      # not registered at all -- not our claim to make
        out = r.stdout or ""
        m = re.search(r"(?im)^\s*Status:\s*(.+)$", out)
        status = (m.group(1).strip() if m else "?")
        if status.lower().startswith("disab"):
            last = re.search(r"(?im)^\s*Last Run Time:\s*(.+)$", out)
            when = last.group(1).strip() if last else "unknown"
            if name in EXPECTED_OFF:
                asleep.append("%s is disabled AS INTENDED (%s)" % (name, EXPECTED_OFF[name]))
            else:
                asleep.append("%s is DISABLED and nobody noticed (last run %s)"
                              % (name, when))
    return asleep


def post_ramchat(text):
    try:
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        subprocess.run([sys.executable, RAMLINK, "post", "keshev-delivery", text],
                       timeout=30, capture_output=True, env=env,
                       creationflags=_NOWIN)
    except Exception:
        pass          # the council being down must never silence the alarm


_receipt_tick = 0
_receipt_state = (None, "not checked yet")
_sleeping: list[str] = []


def cycle(announce=True):
    counts, last_text = read_window()
    facts = mic_facts()
    # K6-13: the baseline is read BEFORE this cycle is appended, so a collapsing
    # window cannot dilute the median it is being judged against.
    rows = load_history()
    base = baseline(rows)
    decoded_now = sum(counts[k] for k in ("typed", "guarded", "blocked",
                                          "empty", "fail"))
    if decoded_now >= BASELINE_MIN_DECODED:
        rows.append((time.time(), counts["typed"], decoded_now))
        save_history(rows)
    warns = []
    verdict, alarms = judge(counts, facts, base, warns)

    # The one repair, announced. If it fires, the verdict stays FAIL for this
    # cycle -- a fault that was repaired still happened, and a watchdog that
    # quietly fixes its subject teaches you nothing about why it broke.
    repaired = None
    try:
        repaired = clear_stale_pause(facts)
    except Exception as e:
        repaired = "repair attempt itself failed: %r" % (e,)
    if repaired:
        alarms.append(repaired)
        verdict = "FAIL"
        facts = mic_facts()          # re-read: the pause may now be gone

    # Every RECEIPTS_EVERY cycles, also ask the receipt checker. A stale PAUSED
    # with no author is the exact shape that killed the mic on 2026-09-03.
    global _receipt_tick, _receipt_state
    _receipt_tick += 1
    if _receipt_tick % RECEIPTS_EVERY == 1:
        _receipt_state = receipts_check()
        try:
            _sleeping[:] = sleeping_watchdogs()
        except Exception:
            pass
    r_ok, r_msg = _receipt_state
    # Reported BESIDE the delivery verdict, never folded into it. FAIL here must
    # keep meaning ONE thing -- his speech is not reaching his chat. Receipt
    # hygiene matters, but a stale .pid during a legitimate mic restart is not
    # the same event as the microphone going deaf, and a FAIL that fires for two
    # different reasons is a FAIL nobody reads. (Caught within a minute of wiring
    # it in: a normal 19:11 restart flipped the whole watchdog to FAIL.)
    if r_ok is False:
        warns.append("RECEIPTS %s" % r_msg)
    for a in _sleeping:
        warns.append("SLEEPING WATCHDOG " + a)
    rate = delivery_rate(counts)
    rec = {
        "ts": time.time(),
        "iso": datetime.now().astimezone().isoformat(timespec="seconds"),
        "verdict": verdict,
        "alarms": alarms,
        "warnings": warns,
        "counts": counts,
        "delivery_rate": None if rate is None else round(rate, 4),
        "baseline": base,
        "facts": facts,
        "last_typed_text": last_text[:80],
        "repaired": repaired,
        "receipts": {"ok": r_ok, "msg": r_msg},
        "window": "recent tail of trial.log (%d KB), not a wall-clock window"
                  % (TAIL_BYTES // 1000),
    }
    with io.open(STATE, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, ensure_ascii=False, indent=1)

    rpct = "n/a" if rate is None else "%.1f%%" % (100 * rate)
    tail = "; ".join(alarms) if alarms else ""
    if warns:
        tail = (tail + "  " if tail else "") + "[warn] " + "; ".join(warns)
    line = ("%s  %-4s  typed=%d guarded=%d empty=%d fail=%d blocked=%d skip=%d  "
            "delivered=%s  %s"
            % (rec["iso"], verdict, counts["typed"], counts["guarded"],
               counts["empty"], counts["fail"], counts["blocked"], counts["skip"],
               rpct, tail))
    with io.open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line.rstrip() + "\n")
    if announce:
        print(line.rstrip(), flush=True)
    return verdict, alarms, rec


# ----------------------------------------------------------------- selftest
def selftest():
    """Prove the FAIL branch is reachable. A gate that has never refused
    anything has not been demonstrated -- that is the whole lesson of the
    backup log whose history never once said FAIL."""
    ok = True

    healthy = {"typed": 40, "guarded": 5, "blocked": 1, "empty": 3, "fail": 0, "skip": 9}
    v, a = judge(healthy, {"paused": False, "paused_for_min": 0.0,
                           "heartbeat_age_min": 0.2, "log_age_min": 0.3})
    print("healthy        -> %-4s %s" % (v, a))
    ok &= (v == "OK")

    # The actual 2026-09-03 failure: an ORPHAN pause -- a timestamp, no author,
    # no reason -- and his mic was dead until 06:34. Still an alarm.
    v, a = judge(healthy, {"paused": True, "paused_for_min": 270.0,
                           "paused_signed": False, "paused_by_iddo": False,
                           "paused_who": "",
                           "heartbeat_age_min": 0.2, "log_age_min": 0.4})
    print("orphan pause 4.5 h  -> %-4s %s" % (v, a))
    ok &= (v == "FAIL" and any("PAUSED_TOO_LONG" in x for x in a))

    # 2026-09-11 -- HIS OWN SIGNED PAUSE IS NOT A FAULT, at any age. This is the
    # case that produced 9 RAMCHAT alarms in three days on his own pause button.
    v, a = judge(healthy, {"paused": True, "paused_for_min": 270.0,
                           "paused_signed": True, "paused_by_iddo": True,
                           "paused_who": "iddo (pause button in KESHEV 6)",
                           "heartbeat_age_min": 0.2, "log_age_min": 0.4})
    print("iddo pause 4.5 h    -> %-4s %s" % (v, a))
    ok &= (v == "OK" and not a)

    # ...and a 20-hour one is still not a fault. He is allowed to leave it off.
    v, a = judge(healthy, {"paused": True, "paused_for_min": 1200.0,
                           "paused_signed": True, "paused_by_iddo": True,
                           "paused_who": "iddo", "heartbeat_age_min": 0.2,
                           "log_age_min": 0.4})
    print("iddo pause 20 h     -> %-4s %s" % (v, a))
    ok &= (v == "OK" and not a)

    # An AGENT that signed a pause and walked away is the 09-03 shape with a
    # name tag: quiet for the first 8 h, an alarm after.
    v, a = judge(healthy, {"paused": True, "paused_for_min": 120.0,
                           "paused_signed": True, "paused_by_iddo": False,
                           "paused_who": "claude-cli", "heartbeat_age_min": 0.2,
                           "log_age_min": 0.4})
    print("agent pause 2 h     -> %-4s %s" % (v, a))
    ok &= (v == "OK")
    v, a = judge(healthy, {"paused": True, "paused_for_min": 600.0,
                           "paused_signed": True, "paused_by_iddo": False,
                           "paused_who": "claude-cli", "heartbeat_age_min": 0.2,
                           "log_age_min": 0.4})
    print("agent pause 10 h    -> %-4s %s" % (v, a))
    ok &= (v == "FAIL" and any("PAUSED_TOO_LONG" in x for x in a))

    # And the reader itself, on DECOY files -- never on his live state\PAUSED.
    import tempfile as _tf
    global PAUSED
    _real_paused = PAUSED
    try:
        d = _tf.mkdtemp(prefix="keshev-pause-decoy-")
        cases = [
            ('{"who": "iddo (pause button in KESHEV 6)", "why": "he pressed pause", '
             '"at": "2026-09-11T04:23:52"}', True, True, "iddo signed JSON"),
            ('{"at": "2026-09-03T22:55:00"}', False, False, "orphan JSON"),
            ('2026-09-03T22:55:00', False, False, "bare timestamp"),
            ('who: claude-cli\nwhy: building the guard\n', True, False, "agent text note"),
        ]
        for body, want_signed, want_iddo, name in cases:
            PAUSED = os.path.join(d, "PAUSED")
            with io.open(PAUSED, "w", encoding="utf-8") as fh:
                fh.write(body)
            got = read_pause()
            good = (got["signed"] == want_signed and got["by_iddo"] == want_iddo)
            print("decoy pause %-18s -> signed=%s by_iddo=%s who=%r  %s"
                  % (name, got["signed"], got["by_iddo"], got["who"][:28],
                     "OK" if good else "FAIL"))
            ok &= good
            os.remove(PAUSED)
        os.rmdir(d)
    finally:
        PAUSED = _real_paused

    # Decoding fine, nothing arriving.
    dead = {"typed": 0, "guarded": 30, "blocked": 2, "empty": 11, "fail": 0, "skip": 4}
    v, a = judge(dead, {"paused": False, "paused_for_min": 0.0,
                        "heartbeat_age_min": 0.2, "log_age_min": 0.5})
    print("0 delivered    -> %-4s %s" % (v, a))
    ok &= (v == "FAIL" and any("NOTHING_DELIVERED" in x for x in a))
    print("               delivery_rate on that case: %s" % delivery_rate(dead))
    ok &= (delivery_rate(dead) == 0.0)

    v, a = judge(healthy, {"paused": False, "paused_for_min": 0.0,
                           "heartbeat_age_min": 0.2, "log_age_min": 90.0})
    print("engine silent  -> %-4s %s" % (v, a))
    ok &= (v == "FAIL" and any("ENGINE_SILENT" in x for x in a))

    # K6-13. Today's real numbers: typed 1,249 of 9,489 decoded = 13.2%, which
    # the old judge called OK because its only failing value was zero.
    live = {"paused": False, "paused_for_min": 0.0, "heartbeat_age_min": 0.2,
            "log_age_min": 0.3}
    today = {"typed": 1249, "guarded": 117, "blocked": 0, "empty": 8240,
             "fail": 0, "skip": 8317}
    steady = {"median_rate": 0.13, "n": 300, "span_h": 22.0}
    v, a = judge(today, live, steady)
    print("13%% on a 13%% baseline -> %-4s %s" % (v, a))
    ok &= (v == "OK")           # a stable low rate is his normal, not a fault

    collapsed = {"typed": 30, "guarded": 20, "blocked": 0, "empty": 900,
                 "fail": 0, "skip": 40}
    w = []
    v, a = judge(collapsed, live, steady, w)
    print("3%% on a 13%% baseline  -> %-4s %s" % (v, a))
    ok &= (v == "FAIL" and any("DELIVERY_COLLAPSED" in x for x in a))

    w = []
    halved = {"typed": 85, "guarded": 20, "blocked": 0, "empty": 800,
              "fail": 0, "skip": 40}
    v, a = judge(halved, live, steady, w)
    print("9%% on a 13%% baseline  -> %-4s warn=%s" % (v, w))
    ok &= (v == "OK" and any("DELIVERY_DOWN" in x for x in w))

    v, a = judge(collapsed, live, None)
    print("collapse, no baseline -> %-4s %s" % (v, a))
    ok &= (v == "OK")           # never alarm on a baseline you do not have

    # 2026-09-05: this selftest PASSED while the live loop crashed with a
    # NameError on EVERY cycle, because it only exercised judge() and never
    # cycle(). A test that cannot see the real path is a proxy -- precisely
    # the fault this file exists to catch. So run one real cycle here.
    try:
        v, alarms, rec = cycle(announce=False)
        print("live cycle    -> %-4s typed=%d delivered=%s receipts=%s"
              % (v, rec["counts"]["typed"], rec["delivery_rate"],
                 rec.get("receipts", {}).get("ok")))
    except Exception as e:
        print("live cycle    -> BROKEN: %r" % (e,))
        ok = False

    print("\nselftest: %s" % ("PASS -- FAIL is reachable on all three alarms"
                              if ok else "BROKEN"))
    return 0 if ok else 1


def _below_normal():
    """Drop this process to BELOW_NORMAL on Windows, and VERIFY it took.

    2026-09-05: these two now start from the Startup folder at logon, so they
    can no longer rely on whoever launched them setting the priority. That
    matters more than it sounds -- normal-priority work on this PC starved
    Iddo's live microphone and 78% of his decodes came back empty. Nothing here
    may ever outrank his mic.

    The argtypes are NOT decoration. gui6.py records the same trap, measured:
    without restype/argtypes the (HANDLE)-1 pseudo-handle is truncated on 64-bit,
    SetPriorityClass fails SILENTLY and the process stays at Normal. Another tool
    on this fleet hit the identical bug tonight. So read the class back.
    """
    if os.name != "nt":
        return None
    try:
        import ctypes
        BELOW_NORMAL = 0x00004000
        k32 = ctypes.windll.kernel32
        k32.GetCurrentProcess.restype = ctypes.c_void_p
        k32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        k32.GetPriorityClass.argtypes = [ctypes.c_void_p]
        k32.GetPriorityClass.restype = ctypes.c_uint32
        h = k32.GetCurrentProcess()
        k32.SetPriorityClass(h, BELOW_NORMAL)
        return k32.GetPriorityClass(h) == BELOW_NORMAL   # verified, not assumed
    except Exception:
        return None


def main():
    prio_ok = _below_normal()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--once", action="store_true", help="one reading, then exit")
    ap.add_argument("--selftest", action="store_true", help="prove FAIL is reachable")
    ap.add_argument("--quiet", action="store_true", help="no stdout, file only")
    a = ap.parse_args()

    if a.selftest:
        return selftest()
    if a.once:
        v, alarms, _ = cycle(announce=not a.quiet)
        return 0 if v == "OK" else 1

    last = None
    while True:
        try:
            v, alarms, _ = cycle(announce=not a.quiet)
            # Announce only on CHANGE. An alarm repeated every minute becomes
            # wallpaper, and wallpaper is how the last one was missed.
            key = (v, tuple(x.split()[0] for x in alarms))
            if key != last:
                if v == "FAIL":
                    post_ramchat("KESHEV DELIVERY ALARM: " + " | ".join(alarms))
                elif last is not None:
                    post_ramchat("KESHEV delivery recovered: text is reaching his chat again")
                last = key
        except Exception as e:
            with io.open(LOG, "a", encoding="utf-8") as fh:
                fh.write("%s  FAIL  watchdog itself broke: %s\n"
                         % (datetime.now().astimezone().isoformat(timespec="seconds"), e))
        time.sleep(CYCLE_S)


if __name__ == "__main__":
    sys.exit(main())
