"""main.py — the assembly. One process, one mutex, edges that heal.

Laws inherited (INSIGHTS §1.2, §1.9; ADDENDUM #5):
- ONE instance: a kernel mutex (Global\\KESHEV_FABLE_MIC) taken before
  anything else; second starts exit 0 silently — the logon task + a human
  double-click must never fight.
- ONE-MIC LAW: refuses to run while KESHEV A's mutex exists. This app goes
  live only after it beats A's baseline and Iddo retires A by hand.
- Boot-storm decoupling: capture opens within seconds; the first decode may
  wait for the server — the spool absorbs the gap.
- No audio OUTPUT call site exists anywhere in this repo.

Run:  python -m app.main            (exits 3 while KESHEV A holds the mic)
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import pathlib
import sys
import threading
import time

from . import lawbook
from .capture import Capture, RivalAliveError
from .corpus import Corpus
from .lane import Lane
from .ear import Ear
from .journal import Journal
from .presence import Presence
from .router import Router
from .segmenter import Segmenter
from .spool import Spool
from .stt import OwnerShadow, SttClient
from .supervisor import Supervisor
from .typer import FocusInfo, Typer
from .window import StatusWindow

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / "state"
OUR_MUTEX = "Global\\KESHEV_FABLE_MIC"
A_MUTEXES = ("Global\\ALMAWARE_KESHEV_SINGLE",)    # A's real name (mutexguard.py)
# Decode on the PC GPU by Iddo's order 2026-08-20 01:00 ("תעביר את הפענוח לפיסי
# ושנה את החוקים בהתאם") — measured 01:07: PC RTX 3070 Ti p50 176 ms round-trip
# vs eran1 170 ms, text 14/14 identical (same models, same LoRA). eran1 stays
# up as rollback: KESHEV_STT_URL=http://<lan-ip>:8737
BASE_URL = os.environ.get("KESHEV_STT_URL", "http://127.0.0.1:8737")
TOKEN = pathlib.Path(r"D:\CLAUDE\mic-rebuild\state\stt-token")
# The always-train loop reads THIS directory: corpus-push.ps1 (scheduled task
# KESHEV-Corpus-Push, 03:00) tars it to eran4, keshev-lora.timer trains on it
# at 03:30. It lives in mic-rebuild because the push and the trainer already
# watch it — the dir starved from the 08-18 cutover until fable fed it too.
# KESHEV_CORPUS=0 turns capture off.
CORPUS_ROOT = pathlib.Path(r"D:\CLAUDE\mic-rebuild\state\corpus")

ERROR_ALREADY_EXISTS = 183
SYNCHRONIZE = 0x00100000


# ------------------------------------------------------------------ win32 --
def take_our_mutex() -> bool:
    """True = we are the one instance. False = another us exists (exit 0)."""
    ctypes.windll.kernel32.CreateMutexW(None, True, OUR_MUTEX)
    return ctypes.windll.kernel32.GetLastError() != ERROR_ALREADY_EXISTS


def rival_alive() -> bool | None:
    """Read-only probe of A's mutex. True=alive, False=free, None=unknown."""
    try:
        for name in A_MUTEXES:
            h = ctypes.windll.kernel32.OpenMutexW(SYNCHRONIZE, False, name)
            if h:
                ctypes.windll.kernel32.CloseHandle(h)
                return True
        return False
    except Exception:  # noqa: BLE001 — cannot prove → fail closed upstream
        return None


def usb_mic_names() -> list[str]:
    """Capture device names via the injected audio backend (sounddevice),
    imported HERE and only here — capture.py stays grep-clean."""
    try:
        import sounddevice as sd  # type: ignore[import-untyped]
        return [d["name"] for d in sd.query_devices()
                if d.get("max_input_channels", 0) > 0]
    except Exception:  # noqa: BLE001
        return []


def current_focus() -> FocusInfo | None:
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    exe = _exe_of_pid(pid.value) or "?"
    return FocusInfo(hwnd=int(hwnd), pid=int(pid.value), exe=exe)


def _exe_of_pid(pid: int) -> str | None:
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    h = ctypes.windll.kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None
    try:
        buf = ctypes.create_unicode_buffer(4096)
        size = wt.DWORD(len(buf))
        if ctypes.windll.kernel32.QueryFullProcessImageNameW(
                h, 0, buf, ctypes.byref(size)):
            return pathlib.Path(buf.value).name
        return None
    finally:
        ctypes.windll.kernel32.CloseHandle(h)


def send_text_win32(text: str) -> bool:
    """SendInput unicode burst. The return value is honest about the CALL;
    round-trip verification (pulse) is the only proof of DELIVERY."""
    INPUT_KEYBOARD, KEYEVENTF_UNICODE, KEYEVENTF_KEYUP = 1, 0x0004, 0x0002

    # x64 layout law (found live 07:53 - TYPE_VERIFY_FAIL on every burst):
    # dwExtraInfo is ULONG_PTR (c_size_t) and the union must include
    # MOUSEINPUT, else sizeof(INPUT)=32 instead of 40 and SendInput
    # rejects the whole array with sent=0.
    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                    ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD),
                    ("dwFlags", wt.DWORD), ("time", wt.DWORD),
                    ("dwExtraInfo", ctypes.c_size_t)]

    class INPUT(ctypes.Structure):
        class _U(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]
        _anonymous_ = ("u",)
        _fields_ = [("type", wt.DWORD), ("u", _U)]

    events = []
    for ch in text:
        for flags in (KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP):
            inp = INPUT(type=INPUT_KEYBOARD)
            inp.ki = KEYBDINPUT(0, ord(ch), flags, 0, 0)
            events.append(inp)
    arr = (INPUT * len(events))(*events)
    sent = ctypes.windll.user32.SendInput(len(events), arr, ctypes.sizeof(INPUT))
    return sent == len(events)


def send_enter_win32() -> bool:
    VK_RETURN, KEYEVENTF_KEYUP = 0x0D, 0x0002
    ok1 = ctypes.windll.user32.keybd_event(VK_RETURN, 0, 0, 0)
    ok2 = ctypes.windll.user32.keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0)
    return True if (ok1 is None and ok2 is None) else bool(ok1 and ok2)


# ----------------------------------------------------------------- wiring --
def build(journal: Journal):
    """Wire the pipeline. Pure construction — nothing opens, nothing runs."""
    spool = Spool(STATE / "spool", journal)
    stt = SttClient(BASE_URL, TOKEN)
    presence = Presence()
    def _send_text(t: str) -> bool:
        ok = send_text_win32(t)
        if ok and WINDOW: WINDOW.typed(t)
        return ok
    typer = Typer(journal=journal, presence_verdict=presence.verdict,
                  focus_fn=current_focus, send_text=_send_text,
                  send_enter=send_enter_win32,
                  avoid_exes=("KeePass.exe", "1Password.exe"))
    # engine in the manifest is a court record of WHO decoded: "pc" for the
    # local GPU (Iddo's 08-20 order), "dgx" when KESHEV_STT_URL points at eran1.
    engine = "pc" if ("127.0.0.1" in BASE_URL or "localhost" in BASE_URL) else "dgx"
    corpus = Corpus(CORPUS_ROOT, journal=journal, engine=engine,
                    enabled=os.environ.get("KESHEV_CORPUS", "1") != "0")
    router = Router(journal=journal, spool=spool, stt=stt, typer=typer,
                    read_wav=lambda rid: _read_pcm(spool, rid),
                    focus_fn=current_focus,
                    recovered_path=STATE / "recovered.txt",
                    owner_shadow=OwnerShadow(),
                    owner_floor=float(os.environ.get("KESHEV_OWNER_FLOOR", "0.60")),
                    corpus=corpus)
    supervisor = Supervisor(journal,
                            mic_present_fn=lambda: bool(
                                lawbook.choose_device(usb_mic_names())))
    capture = Capture(journal, rival_alive_fn=rival_alive,
                      open_stream_fn=_open_stream, close_stream_fn=_close_stream)
    return spool, stt, presence, typer, router, supervisor, capture


def _read_pcm(spool: Spool, rec_id: str) -> bytes | None:
    p = spool.root / f"{rec_id}.wav"
    try:
        import wave
        with wave.open(str(p)) as w:
            return w.readframes(w.getnframes())
    except (FileNotFoundError, EOFError, OSError):
        return None


_EAR: Ear | None = None          # wired in main() before capture starts
WINDOW: StatusWindow | None = None   # the inquiry's sentence: a visible surface


def _decimate_48k_to_16k(block48: bytes) -> bytes:
    """48 kHz int16 mono -> 16 kHz: mean of every 3 samples (light AA)."""
    import array
    a = array.array("h")
    a.frombytes(block48[: len(block48) - (len(block48) % 6)])
    out = array.array("h", bytes(0))
    n = len(a) // 3
    for i in range(n):
        j = 3 * i
        out.append((a[j] + a[j + 1] + a[j + 2]) // 3)
    return out.tobytes()


def _open_stream(device_name: str):
    """The device → ear wiring. The callback runs on the audio thread and
    must never raise; Ear.feed_block absorbs everything."""
    import sounddevice as sd  # type: ignore[import-untyped]

    def _cb(indata, frames, time_info, status) -> None:
        if _EAR is not None:
            try:
                _EAR.feed_block(_decimate_48k_to_16k(bytes(indata)))
            except Exception:  # noqa: BLE001 — the audio thread must live
                pass

    # Windows lists the same mic once per host API (MME/DirectSound/WASAPI/
    # WDM-KS) — an ambiguous name raises. Resolve to the WASAPI INDEX;
    # fall back to the first input-capable entry with that name.
    devices = sd.query_devices()
    candidates = [i for i, d in enumerate(devices)
                  if d["name"] == device_name
                  and d.get("max_input_channels", 0) > 0]
    wasapi = [i for i in candidates
              if "WASAPI" in sd.query_hostapis(devices[i]["hostapi"])["name"]]
    index = (wasapi or candidates)[0]

    # WASAPI refuses 16000 (PaErrorCode -9997, found live 07:46); the BRIO's
    # native rate is 48000. Open native, decimate 3:1 with a 3-tap average
    # (a light anti-alias) down to the decoder's 16 kHz.
    stream = sd.RawInputStream(device=index, samplerate=48000,
                               channels=1, dtype="int16",
                               blocksize=4800,          # 100 ms at 48 kHz
                               callback=_cb)
    stream.start()
    return stream


def _close_stream(stream) -> None:
    stream.stop()
    stream.close()


# ------------------------------------------------------------------- main --
def main() -> int:
    if not take_our_mutex():
        return 0                                  # the other us wins, silently

    journal = Journal(STATE / "events.jsonl")
    session_id = __import__("uuid").uuid4().hex[:8]
    journal.event("SESSION_BEGIN", app="keshev-fable", sid=session_id)

    spool, stt, presence, typer, router, supervisor, capture = build(journal)
    spool.sweep()                                  # crash recovery first

    # ---- the ear: device blocks → segments → spool → router, immediately
    global _EAR

    # ---- the lane: ONE thread decodes; the audio thread only hands over ids.
    # (Until 2026-08-20 process_one ran INSIDE the 100 ms audio callback —
    # every decode was a hole in the next utterance — and the beat thread
    # drained the same spool concurrently: two lanes.)
    def _on_outcome(rec_id: str, state: str) -> None:
        if state.startswith("typed"):
            supervisor.note_typed()
            if WINDOW: WINDOW.set_state("listen", "מאזין")
        elif state == "gated":
            supervisor.note_gated()
            if WINDOW: WINDOW.gated(); WINDOW.set_state("quiet", "רעש נחסם")
        elif state == "parked":
            supervisor.note_parked()
            if WINDOW: WINDOW.set_state("fault", "שרת לא זמין — נשמר")
        elif state == "error":
            if WINDOW: WINDOW.set_state("fault", "שגיאה — ראה יומן")
        if state != "parked":
            supervisor.note_decode()

    def _on_lane_error(rec_id: str, err: str) -> None:
        try:
            journal.event("ALARM", kind="lane_exception", id=rec_id, err=err)
        except Exception:  # noqa: BLE001
            pass

    lane = Lane(router, on_outcome=_on_outcome, on_error=_on_lane_error)
    lane.start()

    def _on_segment(rec_id: str, seg) -> None:
        # audio thread: journal the fact, count it, hand it over. Nothing here
        # may wait on the network — a sentence still does not wait for the next
        # beat (the lane picks it up at once), it just no longer blocks the ear.
        journal.event("SEG", id=rec_id, ms=seg.dur_ms, forced=seg.forced)
        supervisor.note_seg()
        if WINDOW: WINDOW.seg(); WINDOW.set_state("decode", "מפענח…")
        lane.submit(rec_id)

    from .gates import GATE_RMS
    from .sensitivity import Sensitivity
    _SENS = Sensitivity(gate=float(os.environ.get("KESHEV_GATE", GATE_RMS)))
    _EAR = Ear(spool, session_id, on_segment=_on_segment,
               segmenter=Segmenter(sensitivity=_SENS),
               on_level=lambda rms: WINDOW.level(rms) if WINDOW else None)

    try:
        device = lawbook.choose_device(usb_mic_names())
        started = capture.start(device)
    except RivalAliveError:
        journal.event("SESSION_END", why="one_mic_law_rival_alive")
        print("KESHEV A holds the mic — ONE-MIC LAW. Exiting.")
        return 3

    stop = threading.Event()

    def beat() -> None:
        # The heartbeat thread is the health verdict (watchdog-v2 law). It
        # died once (2026-08-19 22:20:48) on an exception out of drain();
        # nothing journalled, no heartbeat for 4 h, nobody knew. Each step is
        # fenced: a bad beat is an ALARM line, never a dead thread. The drain
        # itself runs ON THE LANE — the beat only requests it, so a decode and
        # a drain can never race the same record.
        while not stop.wait(60):
            try:
                supervisor.heartbeat()
            except Exception as e:  # noqa: BLE001 — the beat must live
                try:
                    journal.event("ALARM", kind="heartbeat_exception",
                                  err=f"{type(e).__name__}: {e}"[:300])
                except Exception:  # noqa: BLE001
                    pass
            lane.request_drain()

    threading.Thread(target=beat, daemon=True, name="beat").start()
    journal.event("STATE", state="READY", capturing=bool(started))

    global WINDOW
    paused = {"v": False}

    def _pause(p: bool) -> None:
        paused["v"] = p
        journal.event("STATE", state="PAUSED" if p else "RESUMED", by="window")
    WINDOW = StatusWindow(on_pause=_pause, sensitivity=_SENS)
    # the ear honors the pause button
    real_feed = _EAR.feed_block
    def _feed(block: bytes) -> None:
        if not paused["v"]:
            real_feed(block)
    _EAR.feed_block = _feed  # type: ignore[method-assign]
    WINDOW.set_state("listen" if started else "idle",
                     "מאזין" if started else "אין מיקרופון USB")
    try:
        WINDOW.run()                      # blocks on the main thread
    finally:
        stop.set()
        capture.stop()
        lane.stop()
        journal.event("SESSION_END", why="window_closed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
