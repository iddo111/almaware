"""KESHEV UIPI selftest — the RECEIVING console (spawned by client/selftest.py
with CREATE_NEW_CONSOLE, so it gets its OWN console window — the selftest
never types into a terminal it did not create).

Criterion 8's terminal clause: console hosts (Windows Terminal / conhost)
DISCARD KEYEVENTF_UNICODE entirely (scar 31) — the paste path is the only
reliable door. This child proves the paste path end-to-end: the parent types
through the real typer (clipboard + Ctrl+V + a separate Enter burst), this
process reads ONE line from its console and writes what it ACTUALLY received
to the got-file. Round-trip or it did not happen (scar 19).

argv: got_file ready_file
  ready_file JSON: {"hwnd": .., "pid": .., "title": ..} — hwnd is
  GetConsoleWindow(); under a Windows-Terminal default host that handle is a
  hidden pseudo-console, so the parent falls back to finding the visible
  window whose title contains the nonce (discovery only — the focus guard
  never trusts titles for identity).
"""
from __future__ import annotations

import ctypes
import json
import os
import sys

HARD_TIMEOUT_S = 60


def main() -> int:
    got_file = sys.argv[1]
    ready_file = sys.argv[2]
    nonce = f"UIPI-CONSOLE-{os.getpid()}"

    k32 = ctypes.windll.kernel32
    k32.SetConsoleTitleW(nonce)
    hwnd = int(k32.GetConsoleWindow() or 0)
    with open(ready_file, "w", encoding="utf-8") as f:
        f.write(json.dumps({"hwnd": hwnd, "pid": os.getpid(), "title": nonce}))

    # One line from OUR OWN console. input() blocks until the typer's
    # separate Enter burst arrives (scar 36 exercised for real).
    try:
        line = input()
    except EOFError:
        line = ""
    with open(got_file, "w", encoding="utf-8") as f:
        f.write(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
