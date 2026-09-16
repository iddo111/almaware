# -*- coding: utf-8 -*-
"""voice_to_live.py -- drives DJ_ALMIDO (Ableton) from the SAME Hebrew voice
grammar the Mixcraft bridge uses (bridge/grammar.py, unmodified) and the SAME
"be the focused window" input path KESHEV's typed output already reaches
(bridge/listener_console.py, unmodified, imported by path). This file opens
NO audio device and touches NO KESHEV state file -- see
bridge/listener_console.py's own docstring for why that approach exists and
what it actually measures about KESHEV's only output path (typer.type_string
+ SendInput into whatever window has OS focus).

    utterance (Hebrew text, typed by KESHEV or Iddo) -> grammar.parse()
        -> ParsedCommand -> send.Sender.send_command() -> DJ_ALMIDO (Ableton)

This is bridge/dj_bridge.py's own pipeline (utterance -> grammar -> command)
with ONE difference at the very end: instead of midi_out.Sender putting a
MIDI note on a virtual port for Mixcraft's controller script to read, this
sends one JSON line straight into DJ_ALMIDO's TCP socket server -- Ableton's
Remote Script can read JSON directly, so it never needed the
MIDI-note-as-command-id encoding Mixcraft's sandboxed JS API forced on
bridge/protocol.py in the first place. Only the COMMAND NAMES and PARAM
ENCODINGS from protocol.py are reused, unchanged (grammar.py already produces
them; DJ_ALMIDO/dispatch.py decodes the exact same formulas on the Ableton
side -- see protocol_bridge.py there).

Two modes, matching dj_bridge.py:
  --mode console  (default) opens bridge/listener_console.ListenerConsole.
  --mode stdin     reads one Hebrew utterance per line from stdin -- for
                   testing the whole pipeline without a GUI, KESHEV, or a
                   microphone anywhere near it.

Run with PYTHONIOENCODING=utf-8 (Hebrew text throughout, same reason
dj_bridge.py documents -- `VAR=x cmd1 | cmd2` in bash only sets VAR for
cmd1, so a naive pipe can mojibake Hebrew).
"""
import argparse
import io
import os
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BRIDGE_DIR = os.path.join(os.path.dirname(HERE), "bridge")  # D:\CLAUDE\dj-alma\bridge
for _p in (HERE, BRIDGE_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import grammar  # bridge/grammar.py, unmodified
import send     # ./send.py

LOG_PATH = os.path.join(os.path.dirname(HERE), "state", "voice_to_live.log")


def _log(line: str):
    ts = datetime.now().isoformat(timespec="seconds")
    full = f"[{ts}] {line}"
    print(full, file=sys.stderr)
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with io.open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(full + "\n")
    except OSError:
        pass  # a full disk must not crash a live DJ session


def make_handler(sender, on_result=None):
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
            reply = sender.send_command(parsed.command, param=parsed.param,
                                        **parsed.fields)
            if reply.get("ok"):
                _log(f"SENT     command={parsed.command} param={parsed.param} -> {reply.get('result')}")
            else:
                _log(f"REJECTED command={parsed.command} param={parsed.param} error={reply.get('error')}")
            if on_result:
                on_result(f"-> {parsed.command} (param={parsed.param})")
        except send.NotConnected as e:
            _log(f"SEND-FAIL command={parsed.command} error={e!r}")
            if on_result:
                on_result(f"SEND FAILED: {e}")
    return handle


def run_stdin(sender):
    # Defensive, same measured reason as dj_bridge.py's run_stdin: don't
    # trust PYTHONIOENCODING to have propagated through whatever launched
    # this -- reconfigure explicitly.
    try:
        sys.stdin.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    handle = make_handler(sender)
    _log("voice_to_live stdin mode ready -- type a Hebrew utterance per line, Ctrl+C to stop")
    for line in sys.stdin:
        line = line.rstrip("\n")
        if not line.strip():
            continue
        handle(line)


def run_console(sender):
    import listener_console  # bridge/listener_console.py, unmodified

    console_ref = {}

    def on_result(text: str):
        console_ref["console"].append_result(text)

    handle = make_handler(sender, on_result=on_result)
    console = listener_console.ListenerConsole(on_utterance=handle, title="DJ-ALMA -> Ableton console")
    console_ref["console"] = console

    _log("voice_to_live console mode ready -- keep the DJ-ALMA window focused")
    console.run()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=["console", "stdin"], default="console")
    ap.add_argument("--host", default=send.HOST)
    ap.add_argument("--port", type=int, default=send.PORT)
    ap.add_argument("--dry-run", action="store_true",
                     help="parse and log commands but do not connect to DJ_ALMIDO "
                          "(use this until Ableton is running with DJ_ALMIDO enabled)")
    args = ap.parse_args()

    if args.dry_run:
        sender = send.Sender(args.host, args.port, dry_run=True)
    else:
        try:
            sender = send.Sender(args.host, args.port, dry_run=False)
            _log(f"connected to DJ_ALMIDO at {args.host}:{args.port}")
        except send.NotConnected as e:
            _log(f"could not connect, falling back to --dry-run behavior: {e}")
            sender = send.Sender(args.host, args.port, dry_run=True)

    try:
        if args.mode == "stdin":
            run_stdin(sender)
        else:
            run_console(sender)
    finally:
        sender.close()


if __name__ == "__main__":
    main()
