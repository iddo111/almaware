r"""mic_accept -- the only test that answers the real question: DID THE WORDS ARRIVE?

🪟 BROKEN WINDOWS LAW: test the REAL output, not a proxy. `health: ok` != working.

THE MEASUREMENT
---------------
A known Hebrew WAV goes in. The REAL decoder decodes it (whatever door
state\decoder.json currently names). The REAL typer types it. A decoy window
THIS TEST opened and focused receives the keystrokes and writes its own contents
to a file. The assertion is on that file: the text in the window must be
byte-identical to the text the decoder produced.

Nothing here is a proxy:
  * not `/health: READY` -- on 2026-09-10 the decoder answered READY for 310
    minutes while its own canary came back empty.
  * not `decode=ok` -- that line is printed even when the typer refused
    (the ledger counted refused sentences as delivered until 09-06).
  * not `SendInput returned success` -- UIPI returns success and eats the keys.

SAFETY
------
* THE MICROPHONE IS NEVER OPENED. A WAV goes in; no audio device is touched.
* The target is a DECOY the test owns (tools\accept_decoy.py), never his chat.
  A gate is never tested on the living system.
* It REFUSES to run while state\PAUSED exists. A pause means "do not type into
  my windows", and this test types.
* It restores the window that had the focus when it started.

Run:
    python tools\mic_accept.py                       # the bundled WAV
    python tools\mic_accept.py --wav <path>          # any 16 kHz mono WAV
    python tools\mic_accept.py --quiet               # one PASS/FAIL line
Exit code 0 = the words arrived. 1 = they did not. 2 = the test could not run.
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wintypes
import glob
import io
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STATE = os.path.join(ROOT, "state")
PAUSED = os.path.join(STATE, "PAUSED")
ASSETS = os.path.join(ROOT, "tests", "assets")
DECOY = os.path.join(HERE, "accept_decoy.py")
GOLDEN = os.path.join(ASSETS, "golden.json")
PYTHON = r"C:\Program Files\Python312\python.exe"
PYTHONW = r"C:\Program Files\Python312\pythonw.exe"
_NOWIN = 0x08000000 if os.name == "nt" else 0

WAIT_FOR_WINDOW_S = 12.0
WAIT_FOR_TEXT_S = 15.0

_u32 = ctypes.windll.user32 if os.name == "nt" else None
if _u32 is not None:
    _u32.GetForegroundWindow.argtypes = []
    _u32.GetForegroundWindow.restype = wintypes.HWND
    _u32.SetForegroundWindow.argtypes = [wintypes.HWND]
    _u32.SetForegroundWindow.restype = wintypes.BOOL
    _u32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _u32.GetWindowTextW.restype = ctypes.c_int


def _foreground_title():
    if _u32 is None:
        return ""
    hwnd = _u32.GetForegroundWindow()
    if not hwnd:
        return ""
    buf = ctypes.create_unicode_buffer(256)
    _u32.GetWindowTextW(hwnd, buf, 256)
    return buf.value


def default_wav():
    cands = sorted(glob.glob(os.path.join(ASSETS, "*.wav")))
    return cands[0] if cands else ""


def load_golden():
    try:
        with io.open(GOLDEN, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def run(wav, quiet=False, force=False, bless=False):
    def say(msg):
        if not quiet:
            print(msg, flush=True)

    if not wav or not os.path.exists(wav):
        print("ACCEPT CANNOT RUN: no test WAV. Pass --wav <16 kHz mono wav>. "
              "(Nothing was recorded and no microphone was opened.)")
        return 2
    if os.path.exists(PAUSED) and not force:
        print("ACCEPT SKIPPED: state\\PAUSED exists. A pause means 'do not type "
              "into my windows', and this test types. Not overridden.")
        return 2
    if not os.path.exists(DECOY):
        print("ACCEPT CANNOT RUN: the decoy window %s is missing." % DECOY)
        return 2

    content = os.path.join(STATE, "accept_decoy_content.txt")
    try:
        os.remove(content)
    except OSError:
        pass

    prev_hwnd = _u32.GetForegroundWindow() if _u32 is not None else None
    t_all = time.monotonic()
    decoy = subprocess.Popen([PYTHONW, DECOY, content], cwd=ROOT, creationflags=_NOWIN)
    try:
        # 1. wait for OUR window to actually have the focus. If it never does,
        #    the test has not failed -- it could not run, and saying so is the
        #    whole point of having three exit codes.
        t0 = time.monotonic()
        focused = False
        while time.monotonic() - t0 < WAIT_FOR_WINDOW_S:
            if _foreground_title() == "KESHEV-ACCEPT-DECOY":
                focused = True
                break
            time.sleep(0.2)
        t_focus = time.monotonic() - t0
        if not focused:
            print("ACCEPT CANNOT RUN: the decoy window never took the focus in "
                  "%.1fs (foreground is %r). Nothing was typed."
                  % (WAIT_FOR_WINDOW_S, _foreground_title()[:40]))
            return 2
        say("decoy window focused in %.1fs" % t_focus)

        # 2. the REAL path: decode the WAV and TYPE the result.
        t1 = time.monotonic()
        p = subprocess.run([PYTHON, "-X", "utf8", os.path.join(ROOT, "app", "main.py"),
                            "--decode-file", wav, "--type", "--no-debug-dump"],
                           cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=120, creationflags=_NOWIN,
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        t_decode = time.monotonic() - t1
        payload = {}
        for line in reversed((p.stdout or "").splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    payload = json.loads(line)
                    break
                except ValueError:
                    continue
        if not payload:
            print("ACCEPT FAIL: the decode+type path printed nothing usable.\n"
                  "stdout: %s\nstderr: %s" % ((p.stdout or "")[-400:], (p.stderr or "")[-400:]))
            return 1
        decoded = payload.get("decoded", "")
        say("decoded in %.2fs via %s: %r"
            % (t_decode, (payload.get("door") or "?").split("//")[-1].split("/")[0], decoded))
        if not decoded:
            print("ACCEPT FAIL: the decoder returned NOTHING for a WAV that is "
                  "known to contain speech. door=%s lp=%s peak_rms=%s"
                  % (payload.get("door"), payload.get("lp"), payload.get("peak_rms")))
            return 1

        # 3. the assertion: the words are IN THE WINDOW.
        t2 = time.monotonic()
        landed = ""
        while time.monotonic() - t2 < WAIT_FOR_TEXT_S:
            try:
                with io.open(content, encoding="utf-8") as fh:
                    landed = fh.read()
            except OSError:
                landed = ""
            if landed.strip() == decoded.strip():
                break
            time.sleep(0.25)
        t_type = time.monotonic() - t2
    finally:
        try:
            decoy.terminate()
        except Exception:
            pass
        if _u32 is not None and prev_hwnd:
            try:
                _u32.SetForegroundWindow(prev_hwnd)
            except Exception:
                pass

    total = time.monotonic() - t_all
    arrived = landed.strip() == decoded.strip() and bool(decoded.strip())

    # The golden text is a WATCH, not the gate. Delivery is the gate; the golden
    # says whether the DECODER drifted. They are different failures and must not
    # be conflated (a beam search on a GB10 is not the same search as on Ampere:
    # 170/209 byte-identical when this was measured on 09-05).
    golden = load_golden().get(os.path.basename(wav), {})
    expect = golden.get("text", "")
    drift = ""
    if bless:
        g = load_golden()
        g[os.path.basename(wav)] = {"text": decoded, "blessed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                    "door": payload.get("door", "")}
        os.makedirs(ASSETS, exist_ok=True)
        with io.open(GOLDEN, "w", encoding="utf-8") as fh:
            json.dump(g, fh, ensure_ascii=False, indent=2)
        say("golden blessed: %r" % decoded)
    elif expect and expect.strip() != decoded.strip():
        drift = " DECODER-DRIFT expected=%r" % expect

    line = ("ACCEPT %s  decode=%.2fs type=%.2fs total=%.2fs door=%s text=%r%s"
            % ("PASS" if arrived else "FAIL", t_decode, t_type, total,
               (payload.get("door") or "?").split("//")[-1].split("/")[0],
               decoded[:60], drift))
    print(line, flush=True)
    if not arrived:
        print("   the decoder produced text and the window did NOT receive it. "
              "In the window: %r" % landed[:80])
    return 0 if arrived else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--wav", default=None, help="16 kHz mono 16-bit WAV of real speech")
    ap.add_argument("--quiet", action="store_true", help="only the PASS/FAIL line")
    ap.add_argument("--force", action="store_true",
                    help="run even while PAUSED (it will type into the decoy)")
    ap.add_argument("--bless", action="store_true",
                    help="record what the decoder says today as the golden text")
    a = ap.parse_args(argv)
    return run(a.wav or default_wav(), quiet=a.quiet, force=a.force, bless=a.bless)


if __name__ == "__main__":
    sys.exit(main())
