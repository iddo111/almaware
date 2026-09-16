# -*- coding: utf-8 -*-
"""dj_bridge.py -- main entry point. Wires:

    utterance (Hebrew text) -> grammar.parse() -> ParsedCommand
                             -> midi_out.Sender.send_command() -> Mixcraft

Two input modes:
  --mode console  (default) opens listener_console.ListenerConsole -- the
                   focused-window approach KESHEV's typed output reaches.
  --mode stdin     reads lines from stdin, one utterance per line. Useful
                   for testing the whole pipeline (grammar -> MIDI) without
                   a GUI, KESHEV, or a microphone anywhere near it.

Every utterance and its outcome (matched command, ignored, or error) is
logged to state/dj_bridge.log AND to stderr, so a live DJ session leaves a
readable trail (Iddo's "test the real output" law -- if it silently ignored
"דרופ" nobody should have to guess why).

Run with PYTHONIOENCODING=utf-8 (Hebrew text throughout).
"""
import argparse
import io
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grammar
import midi_out

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(HERE, "..", "state", "dj_bridge.log")


def _log(line: str):
    ts = datetime.now().isoformat(timespec="seconds")
    full = f"[{ts}] {line}"
    print(full, file=sys.stderr)
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with io.open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(full + "\n")
    except OSError:
        pass  # a full disk must not crash the DJ bridge mid-set


def make_handler(sender: "midi_out.Sender | None", dry_run: bool, on_result=None):
    def handle(utterance: str):
        parsed = grammar.parse(utterance)
        if parsed is None:
            _log(f"IGNORED  utterance={utterance!r} (no grammar match)")
            if on_result:
                on_result(f"(not a command) {utterance}")
            return
        _log(f"MATCHED  utterance={utterance!r} -> {parsed.command} "
             f"param={parsed.param} trigger={parsed.matched_text!r}")
        try:
            if sender is not None:
                cid = sender.send_command(parsed.command, parsed.param)
                _log(f"SENT     command={parsed.command} id={cid} param={parsed.param}")
            if on_result:
                on_result(f"-> {parsed.command} (param={parsed.param})")
        except Exception as e:
            _log(f"SEND-FAIL command={parsed.command} error={e!r}")
            if on_result:
                on_result(f"SEND FAILED: {e}")
    return handle


def run_stdin(sender, dry_run):
    # Defensive: don't rely on PYTHONIOENCODING having propagated through
    # whatever launched this (measured 2026-09-04: `VAR=x cmd1 | cmd2` in
    # bash only sets VAR for cmd1, so a naive pipe silently mojibake'd
    # Hebrew here during testing -- reconfigure explicitly instead of
    # trusting the environment).
    try:
        sys.stdin.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    handle = make_handler(sender, dry_run)
    _log("dj_bridge stdin mode ready -- type a Hebrew utterance per line, Ctrl+C to stop")
    for line in sys.stdin:
        line = line.rstrip("\n")
        if not line.strip():
            continue
        handle(line)


def run_console(sender, dry_run):
    import listener_console

    console_ref = {}

    def on_result(text: str):
        console_ref["console"].append_result(text)

    handle = make_handler(sender, dry_run, on_result=on_result)
    console = listener_console.ListenerConsole(on_utterance=handle)
    console_ref["console"] = console

    _log("dj_bridge console mode ready -- keep the DJ-ALMA window focused")
    console.run()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=["console", "stdin"], default="console")
    ap.add_argument("--port", default="ALMA-DJ-Control",
                     help="MIDI output port name (must match dj_alma_control.js's bound input)")
    ap.add_argument("--dry-run", action="store_true",
                     help="parse and log commands but do not open/send to a MIDI port "
                          "(use this until loopMIDI + Mixcraft are set up)")
    args = ap.parse_args()

    sender = None
    if not args.dry_run:
        try:
            sender = midi_out.Sender(args.port, dry_run=False)
            _log(f"opened MIDI port {args.port!r}")
        except midi_out.PortNotFound as e:
            _log(f"MIDI port not available, falling back to --dry-run behavior: {e}")
            sender = midi_out.Sender(args.port, dry_run=True)
    else:
        sender = midi_out.Sender(args.port, dry_run=True)

    try:
        if args.mode == "stdin":
            run_stdin(sender, args.dry_run)
        else:
            run_console(sender, args.dry_run)
    finally:
        sender.close()


if __name__ == "__main__":
    main()
