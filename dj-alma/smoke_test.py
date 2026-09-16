# -*- coding: utf-8 -*-
"""smoke_test.py -- the REAL acceptance check for this project, per D:\\CLAUDE's
own law: "test the real output, not a proxy". Run with:

    "C:\\Program Files\\Python312\\python.exe" smoke_test.py

What this DOES verify, for real, every run:
  1. bridge/protocol.py and bridge/grammar.py import cleanly.
  2. The Hebrew grammar actually parses a table of realistic utterances into
     the commands they should produce (a real pass/fail, not "looks right").
  3. bridge/protocol.py's COMMANDS table and controller/ALMA/dj_alma_control.js's
     CMD_* constants agree on every id -- catches hand-sync drift mechanically.
  4. mido + python-rtmidi import and mido.get_output_names() runs for real.
  5. listener_console.py's Tkinter widget actually receives a typed Enter-
     terminated line and calls back (a real Tk event, not a mock).

What this CANNOT verify on this machine, and says so instead of faking it:
  - Whether Mixcraft actually receives and acts on a sent MIDI command --
    Mixcraft is not installed here (see the status report). If a MIDI port
    named --port exists, this sends ONE real PLAY command to it and tells
    you to check Mixcraft's script Log window by eye -- that half is a
    human verification step, not something this script can confirm alone.
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "bridge"))

FAILURES = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}" + (f" -- {detail}" if detail else ""))
    if not condition:
        FAILURES.append(name)
    return condition


def section(title):
    print("\n=== " + title + " ===")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="ALMA-DJ-Control",
                     help="if this MIDI port exists, also send one real PLAY command to it")
    ap.add_argument("--send-real", action="store_true",
                     help="actually send if --port is found (otherwise only reports whether it would)")
    args = ap.parse_args()

    section("1. imports")
    try:
        import protocol
        import grammar
        check("protocol.py imports", True)
        check("grammar.py imports", True)
    except Exception as e:
        check("bridge module imports", False, repr(e))
        print("\nCannot continue without the bridge modules importing. Stopping.")
        sys.exit(1)

    section("2. Hebrew grammar -> command table")
    # (utterance, expected_command_name_or_None)
    cases = [
        ("קצב 142", "SET_TEMPO"),
        ("תוריד את הבס", "BASS_VOL"),
        ("תעלה ליד", "LEAD_VOL"),
        ("דרופ", "SECTION_DROP"),
        ("תן דרופ עכשיו", "SECTION_DROP"),
        ("עוד 8 בר", "EXTEND_SECTION"),
        ("עוד 16 בארים", "EXTEND_SECTION"),
        ("עצור הכל", "STOP_ALL_CLIPS"),
        ("עצור", "STOP"),
        ("נגן", "PLAY"),
        ("השתק תופים", "DRUMS_MUTE_TOGGLE"),
        ("בילד אפ", "SECTION_BUILD"),
        ("ברייקדאון", "SECTION_BREAK"),
        ("אינטרו", "SECTION_INTRO"),
        ("אאוטרו", "SECTION_OUTRO"),
        ("מהר יותר", "TEMPO_NUDGE_UP"),
        ("לאט יותר", "TEMPO_NUDGE_DOWN"),
        ("הקלטה", "RECORD_TOGGLE"),
        ("מה השעה", None),   # must NOT match anything
        ("שלום עידו", None),  # must NOT match anything
    ]
    for utterance, expected in cases:
        parsed = grammar.parse(utterance)
        got = parsed.command if parsed else None
        check(f"grammar({utterance!r}) -> {expected}", got == expected, f"got {got}")

    section("3. protocol.py <-> dj_alma_control.js command-table drift check")
    js_path = os.path.join(HERE, "controller", "ALMA", "dj_alma_control.js")
    try:
        with open(js_path, "r", encoding="utf-8") as f:
            js_src = f.read()
        js_ids = {}
        for m in re.finditer(r"var\s+CMD_(\w+)\s*=\s*(\d+)\s*;", js_src):
            js_ids[m.group(1)] = int(m.group(2))
        py_ids = {name: cid for cid, (name, _) in protocol.COMMANDS.items()}

        missing_in_js = sorted(set(py_ids) - set(js_ids))
        missing_in_py = sorted(set(js_ids) - set(py_ids))
        mismatched = sorted(n for n in (set(py_ids) & set(js_ids)) if py_ids[n] != js_ids[n])

        check("every protocol.py command exists in dj_alma_control.js",
              not missing_in_js, f"missing: {missing_in_js}")
        check("every dj_alma_control.js CMD_* exists in protocol.py",
              not missing_in_py, f"missing: {missing_in_py}")
        check("matching command ids agree between the two files",
              not mismatched, f"mismatched: {mismatched}")

        # cross-check the OnMIDI if/else chain actually handles every command
        # (a command could exist as a CMD_ constant but never be dispatched)
        undispatched = [n for n in js_ids if f"cmd == CMD_{n}" not in js_src]
        check("every CMD_* constant is dispatched in OnMIDI()",
              not undispatched, f"undispatched: {undispatched}")
    except Exception as e:
        check("protocol/js drift check ran", False, repr(e))

    section("4. MIDI library + port discovery (real, not mocked)")
    try:
        import midi_out
        ports = midi_out.list_output_ports()
        check("mido + python-rtmidi import and list ports", True, f"ports={ports}")
        target_present = any(p == args.port or p.startswith(args.port) for p in ports)
        if target_present:
            print(f"[INFO] port {args.port!r} IS present.")
            if args.send_real:
                with midi_out.Sender(args.port, dry_run=False) as sender:
                    sender.send_command("PLAY", 0)
                print("[INFO] sent a real PLAY command. Check Mixcraft's script Log "
                      "window BY EYE for 'PLAY' -- this script cannot see Mixcraft's "
                      "own log, that confirmation is a human step.")
            else:
                print("[INFO] rerun with --send-real to actually send a test PLAY command.")
        else:
            print(f"[INFO] port {args.port!r} NOT present (found: {ports}). "
                  f"This is EXPECTED until loopMIDI (or equivalent) is installed and a "
                  f"port is created -- see README.md. Not a failure of this code.")
    except Exception as e:
        check("MIDI port discovery", False, repr(e))

    section("5. dry-run send path (works with zero MIDI hardware/ports)")
    try:
        import midi_out
        with midi_out.Sender(args.port, dry_run=True) as sender:
            cid = sender.send_command("SET_TEMPO", protocol_bpm_param(protocol))
        check("dry-run Sender.send_command()", cid == protocol.command_id_by_name("SET_TEMPO"))
    except Exception as e:
        check("dry-run send path", False, repr(e))

    section("6. listener_console.py Tkinter selftest (real Tk event, not mocked)")
    try:
        import subprocess
        py = sys.executable
        result = subprocess.run(
            [py, os.path.join(HERE, "bridge", "listener_console.py"), "--selftest"],
            capture_output=True, text=True, timeout=30, encoding="utf-8",
        )
        ok = result.returncode == 0 and "selftest OK" in result.stdout
        check("listener_console.py --selftest", ok,
              (result.stdout + result.stderr)[-400:] if not ok else "")
    except Exception as e:
        check("listener_console selftest subprocess", False, repr(e))

    section("summary")
    if FAILURES:
        print(f"\n{len(FAILURES)} FAILED: {FAILURES}")
        sys.exit(1)
    else:
        print("\nAll checks that CAN run on this machine passed. "
              "Mixcraft itself was never exercised -- see section 4 and README.md.")


def protocol_bpm_param(protocol_mod):
    return protocol_mod.bpm_to_param(142.0)


if __name__ == "__main__":
    main()
