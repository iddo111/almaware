"""End-to-end proof for app/gui6.py, WITHOUT going near the microphone.

The window is launched in its dry --selftest-hold mode against a SYNTHETIC
trial.log that this test appends to while the window is running -- so the live
tail, the parser, the counters, the textguard pairing and every label are all
exercised the way the real log exercises them. No engine is started, no audio
device is opened, state/gui.heartbeat and state/mic.pid are never written.

Run:  python -X utf8 tests\\test_gui6_render.py
"""

import io
import json
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Q = "'"
BS = "\\"

HEADER = [
    "[mic] device='Microphone (Logitech BRIO)' [Windows DirectSound] (index 19 at "
    "pick time, re-resolved at open, fenced) native=44100Hz resample=160/441 -> "
    "16000Hz block=64ms",
    "[mic] decoder READY",
]

# appended AFTER the window is up, so they are LIVE lines, not history
LIVE = [
    "[mic] status_events=2 dropped_blocks=41",
    "[segment] bytes=16384 secs=0.51 peak_rms=255 floor=600 SKIP too-quiet",
    "[segment] bytes=108544 secs=3.39 peak_rms=972 vad=0.05 SKIP",
    # a real typed sentence (main.py writes ascii(text)[:80])
    "[segment] bytes=161792 secs=5.06 peak_rms=8061 gate=0.584/PASS lp=-0.60 "
    "decode=ok route=he text=" + Q + BS + "u05e9" + BS + "u05dc" + BS + "u05d5" + BS + "u05dd"
    + BS + "u0020" + BS + "u05e2" + BS + "u05d9" + BS + "u05d3" + BS + "u05d5" + Q,
    # decoded, routed, and then thrown away by textguard: NOT typed
    "[textguard] dropped segment (99999 bytes): blocklist:תודה",
    "[segment] bytes=99999 secs=3.00 peak_rms=5000 gate=0.600/PASS lp=-0.50 "
    "decode=ok route=he text=" + Q + BS + "u05ea" + BS + "u05d5" + BS + "u05d3" + BS + "u05d4." + Q,
    "[segment] bytes=57344 secs=1.79 peak_rms=2611 gate=0.671/PASS decode=empty route=- text=-",
    "[segment] bytes=57344 secs=1.79 peak_rms=2611 gate=0.671/PASS decode=fail route=- text=-",
    "[segment] bytes=100 secs=0.50 peak_rms=900 gate=0.100/BLOCK decode=- route=- text=-",
    "[confidence] dropped (143360 bytes, lp=-1.56)",
    "[segment] DROPPED: the decode worker is more than 32 segments behind",
    # the silent downgrade this window must make impossible
    "[decoder] answered by fallback http://<lan-ip>:8737/v1/transcribe",
    "[typer] BLOCKED admin-window proc=cmd.exe integrity=HIGH",
]

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


def _stat(path):
    """(exists, size, mtime) -- enough to prove we did not write it."""
    try:
        st = os.stat(path)
        return (True, st.st_size, round(st.st_mtime, 3))
    except OSError:
        return (False, 0, 0.0)


def main():
    # Snapshot the LIVE mic's files first. The dry window must leave every one
    # of them byte-for-byte and second-for-second as it found them, whether or
    # not Iddo's KESHEV happens to be running while this test does.
    live_before = {name: _stat(os.path.join(ROOT, "state", name))
                   for name in ("gui.heartbeat", "mic.pid", "PAUSED",
                                "mic-choice.json")}

    work = tempfile.mkdtemp(prefix="keshev6-render-")
    synth = os.path.join(work, "synthetic-trial.log")
    with io.open(synth, "w", encoding="utf-8") as fh:
        fh.write("\n".join(HEADER) + "\n")

    # Stand up a FAKE engine so the decoder panel is exercised too: dry mode
    # reads mic.pid from the scratch dir, so pointing it at THIS process makes
    # the window read this process's environment out of its PEB -- exactly the
    # code path it uses on the real engine. Nothing in state/ is touched.
    os.environ["KESHEV_STT_URL"] = "http://127.0.0.1:8738/v1/transcribe"
    os.environ["KESHEV_STT_FALLBACK_URL"] = "http://<lan-ip>:8737/v1/transcribe"
    with io.open(os.path.join(work, "mic.pid"), "w") as fh:
        fh.write(str(os.getpid()))

    proc = subprocess.Popen(
        [sys.executable, "-X", "utf8", os.path.join(ROOT, "app", "gui6.py"),
         f"--selftest-dir={work}", "--selftest-hold=8", "--mode=full", synth],
        cwd=ROOT, env=dict(os.environ, PYTHONIOENCODING="utf-8"))

    # wait for the window, then feed it LIVE lines (after catching_up has cleared)
    hwnd_file = os.path.join(work, "hold.hwnd")
    win_pid = 0
    for _ in range(80):
        if os.path.exists(hwnd_file):
            try:
                win_pid = int(open(hwnd_file).read().split()[0])
            except Exception:
                pass
            break
        time.sleep(0.1)
    time.sleep(1.6)
    with io.open(synth, "a", encoding="utf-8") as fh:
        for line in LIVE:
            fh.write(line + "\n")
            fh.flush()
            time.sleep(0.12)
    proc.wait(timeout=40)

    report_path = os.path.join(work, "hold-report.json")
    if not os.path.exists(report_path):
        print("FAIL: the window wrote no report -- it did not come up")
        return 1
    r = json.load(io.open(report_path, encoding="utf-8"))
    print(json.dumps(r["state"], ensure_ascii=False))
    print(json.dumps(r["counters"], ensure_ascii=False))
    print()

    print("the window survived its own event loop")
    check("no UI errors", r["counters"]["ui_errors"], 0)

    print("\ncounters -- what really happened, not what looked like it happened")
    c = r["counters"]
    check("typed (reached his chat)", c["typed"], 1)
    check("guarded (decoded, then binned by textguard)", c["guarded"], 1)
    check("empty (server answered 200 with nothing)", c["empty"], 1)
    check("fail (transport broke) is NOT merged into empty", c["fail"], 1)
    check("blocked by the owner gate", c["blocked"], 1)
    check("skipped before the decoder", c["skip"], 2)
    check("confidence drops", c["confidence"], 1)
    check("backlog sheds", c["backlog"], 1)

    print("\nHebrew comes through as Hebrew, not as backslash escapes")
    check("last typed text", r["last_typed_text"], "שלום עידו")
    check_true("no escapes leaked into the UI", BS + "u05" not in r["totals"] + str(r["rows"]))

    print("\nthe fallback cannot be silent")
    check("fallback counted", r["fallback_n"], 1)
    check("fallback url", r["fallback_url"], "http://<lan-ip>:8737/v1/transcribe")
    check_true("the amber fallback banner is on screen", r["fb_banner_shown"])
    check_true("and the badge itself says גיבוי", "גיבוי" in r["state"]["text"],
               r["state"]["text"])

    print("\nthe decoder is read back from the ENGINE, never echoed from config")
    et = r["engine_truth"]
    check_true("the engine's environment was read out of its PEB", et["env_read_ok"])
    check("and it is the URL the engine really has",
          et["stt_url"], "http://127.0.0.1:8738/v1/transcribe")
    check_true("the panel names it", "KESHEV 6 (8738)" in r["dec_line1"], r["dec_line1"])
    check_true("with MEASURED health, not a hardcoded ok",
               r["health"] is not None and r["health"]["state"] == "READY",
               str(r["health"] and r["health"]["state"]))
    check_true("the real model is named", "whisper-large-v3-turbo" in r["dec_line2"],
               r["dec_line2"])
    check_true("the canary age is shown", "קנרי" in r["dec_line2"])
    check_true("the badge carries the decoder tag", r["pill_dec"] == "6", r["pill_dec"])
    check_true("the configured fallback is named too",
               "eran1 8737" in r["dec_line2"], r["dec_line2"])

    print("\nthe admin-window block is surfaced")
    check_true("admin banner is on screen", r["admin_banner_shown"])

    print("\nengine lines are read")
    check_true("mic device parsed", (r["mic"] or {}).get("device") == "Microphone (Logitech BRIO)",
               str(r["mic"]))
    check("audio drops shown", r["drops"], 41)
    check_true("drops label warns above 10", "המחשב עמוס" in r["drops_label"], r["drops_label"])

    print("\nthe rows show verdicts, and 'guarded' is not called 'typed'")
    rows = r["rows"]
    check_true("a הוקלד row exists", "הוקלד" in rows)
    check_true("a נחסם row exists", "נחסם" in rows)
    check_true("the typed sentence is in a row", "שלום עידו" in rows, )
    check_true("the guarded reason is shown", any("blocklist" in x for x in rows))

    print("\nnothing of the LIVE mic's was touched")
    # Asserted against a snapshot taken before the window ran, so this holds
    # whether or not a real KESHEV is running at the time. gui.heartbeat is the
    # exception: a LIVE window rewrites it every 8 s, so the thing to prove
    # there is that our pid is not the one in it.
    for name in ("mic.pid", "PAUSED", "mic-choice.json"):
        after = _stat(os.path.join(ROOT, "state", name))
        check(f"state/{name} untouched", after, live_before[name])
    hb_path = os.path.join(ROOT, "state", "gui.heartbeat")
    if not live_before["gui.heartbeat"][0]:
        check_true("state/gui.heartbeat was not created", not os.path.exists(hb_path))
    else:
        try:
            beat = open(hb_path).read().strip()
        except OSError:
            beat = ""
        check_true("state/gui.heartbeat still belongs to the LIVE window, not to us",
                   beat != str(win_pid) and beat != "",
                   f"(it holds pid {beat}, the dry window was {win_pid})")
    check_true("the window's own files stayed in the scratch dir",
               os.path.exists(os.path.join(work, "gui6.pid"))
               or not os.path.exists(os.path.join(ROOT, "state", "gui6.pid")))

    viewer_scenario()

    print()
    if FAILURES:
        print(f"FAILED {len(FAILURES)}: {FAILURES}")
        return 1
    print("all gui6 render checks passed")
    print("workdir:", work)
    return 0


def viewer_scenario():
    """VIEWER MODE -- the guard that stops KESHEV 6 becoming a second mic.

    If another window already owns the engine (KESHEV 5's gui.py, say), this
    window must not beat the heartbeat, must not start an engine, and must not
    kill one on close. Two windows over one heartbeat, with both supervisors
    racing to restart the engine, is how you end up with a live mic and no
    visible owner -- and two engines typing at once is the 2026-09-02 scar.

    Dry mode reads mic.pid and gui.heartbeat from the scratch dir, so a fake
    owner can be staged here without going near the live ones.
    """
    print("\nVIEWER MODE: another window already owns the mic")
    work = tempfile.mkdtemp(prefix="keshev6-viewer-")
    synth = os.path.join(work, "synthetic-trial.log")
    with io.open(synth, "w", encoding="utf-8") as fh:
        fh.write("\n".join(HEADER) + "\n")
    # this test process plays BOTH the rival window and its engine
    for name in ("gui.heartbeat", "mic.pid"):
        with io.open(os.path.join(work, name), "w") as fh:
            fh.write(str(os.getpid()))
    hb_before = _stat(os.path.join(work, "gui.heartbeat"))

    proc = subprocess.Popen(
        [sys.executable, "-X", "utf8", os.path.join(ROOT, "app", "gui6.py"),
         f"--selftest-dir={work}", "--selftest-hold=5", "--mode=full", synth],
        cwd=ROOT, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    proc.wait(timeout=40)

    path = os.path.join(work, "hold-report.json")
    if not os.path.exists(path):
        FAILURES.append("viewer window did not come up")
        print("  FAIL the window did not come up")
        return
    r = json.load(io.open(path, encoding="utf-8"))
    check("it declares itself a viewer", r["state"]["key"], "viewer")
    check("and says so in Hebrew", r["state"]["text"], "צופה בלבד")
    check_true("naming the window to close", "קשב 5" in r["state"]["detail"],
               r["state"]["detail"])
    check("it did not touch the owner's heartbeat",
          _stat(os.path.join(work, "gui.heartbeat")), hb_before)
    check_true("it started no engine",
               io.open(os.path.join(work, "mic.pid")).read().strip() == str(os.getpid()))
    check("no UI errors in viewer mode", r["counters"]["ui_errors"], 0)


if __name__ == "__main__":
    sys.exit(main())
