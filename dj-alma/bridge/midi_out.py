# -*- coding: utf-8 -*-
"""midi_out.py -- sends ALMA DJ commands out over a real MIDI port using
mido (+ the python-rtmidi backend). Talks the wire format defined in
protocol.py: one NOTE_ON immediately followed by NOTE_OFF, on
protocol.CHANNEL, per command.

MEASURED on this machine 2026-09-04: mido 1.3.3 was already installed;
python-rtmidi 1.5.8 was installed for this project (pip install
python-rtmidi, a normal library install, not a Windows software install).
mido.get_output_names() returned only ['Microsoft GS Wavetable Synth 0'] --
there is NO virtual MIDI port on this machine yet. Nothing in this file can
be smoke-tested end-to-end against a real Mixcraft until Iddo installs
loopMIDI (or an equivalent virtual MIDI driver) and creates a port -- see
README.md. This module is written to fail LOUDLY and honestly when that
port is missing, never to pretend a send worked.
"""
import sys
import time

import protocol

try:
    import mido
except ImportError:  # pragma: no cover -- documented, not expected on this box
    mido = None


class PortNotFound(RuntimeError):
    pass


def list_output_ports() -> list:
    if mido is None:
        raise RuntimeError("mido is not installed -- pip install mido python-rtmidi")
    return mido.get_output_names()


def open_port(port_name: str):
    """Open a MIDI output port by exact name. Raises PortNotFound (not a
    generic exception) if it isn't there, with the list of what IS there,
    so the caller can print something a human can act on."""
    if mido is None:
        raise RuntimeError("mido is not installed -- pip install mido python-rtmidi")
    available = mido.get_output_names()
    matches = [p for p in available if p == port_name or p.startswith(port_name)]
    if not matches:
        raise PortNotFound(
            f"MIDI output port {port_name!r} not found. "
            f"Available ports: {available or '(none)'}. "
            f"See README.md -- install loopMIDI and create a port named {port_name!r}."
        )
    return mido.open_output(matches[0])


class Sender:
    """Thin stateful wrapper: open once, send many commands, close on exit."""

    def __init__(self, port_name: str, dry_run: bool = False):
        self.port_name = port_name
        self.dry_run = dry_run
        self._port = None
        if not dry_run:
            self._port = open_port(port_name)

    def send_command(self, command_name: str, param: int = 0) -> int:
        """command_name must be one of protocol.COMMANDS's names. Returns the
        command id sent, for logging. Raises KeyError on an unknown name --
        never silently drops a typo'd command."""
        cid = protocol.command_id_by_name(command_name)
        param = max(0, min(127, int(param)))
        note_on = mido.Message("note_on", channel=protocol.CHANNEL, note=cid,
                                velocity=param) if mido else None
        note_off = mido.Message("note_off", channel=protocol.CHANNEL, note=cid,
                                 velocity=0) if mido else None
        if self.dry_run or self._port is None:
            print(f"[midi_out DRY-RUN] would send {command_name} (id={cid}) "
                  f"param={param} on channel {protocol.CHANNEL + 1}", file=sys.stderr)
            return cid
        self._port.send(note_on)
        time.sleep(0.005)  # a real key press has non-zero duration; some hosts
        self._port.send(note_off)  # debounce NOTE_ON immediately followed by NOTE_OFF at 0ms
        return cid

    def close(self):
        if self._port is not None:
            self._port.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def main():
    """CLI smoke helper: python midi_out.py [--dry-run] [--port NAME] COMMAND [PARAM]
    e.g.  python midi_out.py --dry-run PLAY
          python midi_out.py --dry-run SET_TEMPO 64"""
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("command")
    ap.add_argument("param", nargs="?", type=int, default=0)
    ap.add_argument("--port", default="ALMA-DJ-Control")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--list-ports", action="store_true")
    args = ap.parse_args()

    if args.list_ports:
        print(list_output_ports())
        return

    with Sender(args.port, dry_run=args.dry_run) as sender:
        cid = sender.send_command(args.command, args.param)
        print(f"sent {args.command} id={cid} param={args.param}")


if __name__ == "__main__":
    main()
