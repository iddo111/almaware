r"""
soundcard_pan.py -- OPT-IN system-wide L<->R pan via Windows Core Audio.

*** READ THIS BEFORE ENABLING ANYTHING HERE ***

This module modulates the DEFAULT RENDER ENDPOINT's per-channel volumes
(IAudioEndpointVolume::SetChannelVolumeLevelScalar). That is a SYSTEM MIXER
SETTING on the user's actual output device: every app on the machine -- his
music, his browser, everything -- gets swung, and the change outlives the
process if it is killed.

It is therefore NOT the default output for the EMDR sweep and must never be
made one again. EMDR's own stereo tone (BilateralEngine in emdr_widget.py)
pans EMDR's own samples and leaves every mixer setting alone; that is the
default and the recommended path. This module exists only for the user who
explicitly asks for his whole desktop to swing, and it only runs when the
opt-in box in Settings is ticked.

What changed on 2026-09-01
--------------------------
1. EQUAL-POWER LAW, not a duck. Was: near channel pinned at 1.0, far channel
   dipped to 0.15. That pumped total loudness by 2.91 dB every sweep and gave
   only 4.81 dB of L-R cue at half travel. Now:
       theta  = (pan + 1) * pi / 4
       gain_L = cos(theta),  gain_R = sin(theta)
   cos^2 + sin^2 == 1, so total power is constant. 7.66 dB of cue at half
   travel, and the centre sits 3 dB down, as a real pan law does.
2. NEVER RAISES HIS VOLUME. Applied gain is ``saved * gain``, clamped to
   [0, saved]. The old ``max(_MIN_SCALAR, ...)`` clamp meant that with his
   master below 0.15 the widget WROTE 0.15 -- turning his music UP -- and the
   pan silently died (both channels pinned to the same floor).
3. CRASH RECOVERY. The pre-sweep channel volumes are written to disk BEFORE
   the first modulation. The old code kept them in a module global restored
   only by stop_pan() and an atexit hook -- and atexit does NOT run on a
   qFatal abort or a Task Manager kill, so a channel could stay stuck at 15%
   with the original value recorded nowhere. recover_residue() puts them back
   on the next launch.
4. Writes are deadbanded (default ~0.2% of full scale) instead of 120 blind
   COM writes/second, each of which fires IAudioEndpointVolumeCallback to
   every listener on the machine and makes the Windows volume OSD flap.
5. Gains are one-pole smoothed. Honest limit: this path can only be updated
   at the worker rate, so it can never be as smooth as EMDR's own stream,
   which ramps per sample.

Public API:
    start_pan(get_pan_fn, rate_hz=60) -> bool
    stop_pan() -> None
    recover_residue() -> bool
    set_residue_path(path) -> None
    set_log_fn(fn) -> None
    last_error() -> str | None
    is_active() -> bool
"""

from __future__ import annotations

import atexit
import json
import logging
import math
import os
import threading
import time
from typing import Callable, Optional

_log = logging.getLogger("soundcard_pan")
_log.addHandler(logging.NullHandler())

#: optional sink into the host app's log file (set by emdr_widget)
_log_fn: Optional[Callable[[str], None]] = None

#: where the pre-sweep channel volumes are parked so a kill is recoverable
_residue_path: Optional[str] = None

#: smallest change worth a COM write (fraction of full scale)
_DEADBAND = 0.002

#: gain smoothing time constant, seconds
_SMOOTH_TAU = 0.020

_state_lock = threading.Lock()
_thread: Optional[threading.Thread] = None
_stop_evt: Optional[threading.Event] = None
_endpoint = None  # IAudioEndpointVolume pointer
_saved_channels: Optional[list] = None
_nchannels: int = 0
_active: bool = False
_last_error: Optional[str] = None


def set_log_fn(fn) -> None:
    """Route this module's messages into the host app's log FILE.

    Necessary because the app ships as a windowed build where sys.stderr is
    None, so the stdlib logging fallback handler goes nowhere.
    """
    global _log_fn
    _log_fn = fn


def set_residue_path(path: str) -> None:
    global _residue_path
    _residue_path = path


def _say(msg: str) -> None:
    try:
        _log.info(msg)
    except Exception:
        pass
    if _log_fn is not None:
        try:
            _log_fn(f"soundcard_pan: {msg}")
        except Exception:
            pass


# --------------------------------------------------------------- endpoint
def _get_device_and_endpoint():
    """Return (device, endpoint_volume, channel_count) or (None, None, 0)."""
    global _last_error
    try:
        import comtypes
        from ctypes import POINTER, cast
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    except Exception as e:
        _last_error = f"import failed: {e}"
        return None, None, 0

    try:
        try:
            comtypes.CoInitialize()
        except Exception:
            pass
        device = AudioUtilities.GetSpeakers()
        # Newer pycaw exposes EndpointVolume directly; older requires Activate.
        endpoint = getattr(device, "EndpointVolume", None)
        if endpoint is None:
            interface = device._dev.Activate(
                IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            endpoint = cast(interface, POINTER(IAudioEndpointVolume))
        nch = int(endpoint.GetChannelCount())
        return device, endpoint, nch
    except Exception as e:
        _last_error = f"endpoint activate failed: {e}"
        return None, None, 0


def _get_endpoint():
    _, endpoint, nch = _get_device_and_endpoint()
    return endpoint, nch


def _device_id(device) -> Optional[str]:
    """Best-effort stable id for the endpoint, so crash recovery can refuse to
    restore saved volumes onto a DIFFERENT device the user has since chosen."""
    for getter in (lambda d: d.GetId(),
                   lambda d: d.id,
                   lambda d: d._dev.GetId()):
        try:
            val = getter(device)
            if val:
                return str(val)
        except Exception:
            continue
    return None


def _snapshot_channels(endpoint, nch: int) -> Optional[list]:
    global _last_error
    try:
        return [float(endpoint.GetChannelVolumeLevelScalar(i)) for i in range(nch)]
    except Exception as e:
        _last_error = f"snapshot failed: {e}"
        return None


def _restore_channels(endpoint, saved: list) -> bool:
    if endpoint is None or not saved:
        return False
    ok = True
    for i, v in enumerate(saved):
        try:
            endpoint.SetChannelVolumeLevelScalar(i, float(v), None)
        except Exception as e:
            ok = False
            _say(f"restore of channel {i} failed: {e}")
    return ok


# --------------------------------------------------------------- residue
def _write_residue(device_id: Optional[str], nch: int, saved: list) -> None:
    """Park the pre-sweep volumes on disk BEFORE touching anything."""
    if not _residue_path:
        return
    try:
        payload = {
            "device_id": device_id,
            "nch": int(nch),
            "saved": [float(v) for v in saved],
            "written": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "note": "pre-sweep channel volumes; restore these if EMDR was killed",
        }
        tmp = _residue_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, _residue_path)
    except Exception as e:
        _say(f"could not write residue file: {e}")


def _clear_residue() -> None:
    if not _residue_path:
        return
    try:
        if os.path.exists(_residue_path):
            os.remove(_residue_path)
    except Exception as e:
        _say(f"could not clear residue file: {e}")


def recover_residue() -> bool:
    """Undo a kill that happened mid-sweep. Returns True if volumes were put back.

    Only ever runs when the residue file exists -- i.e. only when a previous
    run of THIS app was interrupted while it held the endpoint. It restores
    the exact values it recorded, and refuses if the default output device is
    no longer the one those values came from.
    """
    if not _residue_path or not os.path.exists(_residue_path):
        return False
    try:
        with open(_residue_path, encoding="utf-8") as f:
            data = json.load(f)
        saved = [float(v) for v in data.get("saved", [])]
        want_id = data.get("device_id")
        want_nch = int(data.get("nch", 0))
    except Exception as e:
        _say(f"residue file unreadable ({e}); removing it")
        _clear_residue()
        return False

    if not saved:
        _clear_residue()
        return False

    device, endpoint, nch = _get_device_and_endpoint()
    if endpoint is None:
        _say("residue found but the endpoint could not be opened; leaving the "
             "file in place to retry next launch")
        return False

    have_id = _device_id(device)
    if want_id and have_id and want_id != have_id:
        _say("residue found, but the default output device has changed since. "
             "NOT restoring onto a different device. Left in place. If your "
             "left/right balance is off, reset it in Windows Sound > "
             "Properties > Levels > Balance.")
        return False
    if want_nch and nch and want_nch != nch:
        _say(f"residue found but channel count differs ({want_nch} vs {nch}); "
             "not restoring")
        return False

    ok = _restore_channels(endpoint, saved[:nch] if nch else saved)
    if ok:
        _say(f"RECOVERED: a previous run was killed mid-sweep; restored "
             f"channel volumes {saved} on the output device")
        _clear_residue()
    else:
        _say("residue restore failed; leaving the file for the next launch")
    return ok


# --------------------------------------------------------------- pan law
def equal_power_gains(pan: float) -> tuple:
    """gain_L, gain_R for pan in [-1, +1]. cos^2 + sin^2 == 1: constant power.

    Pure function, no COM, no device -- so it can be tested numerically.
    """
    pan = max(-1.0, min(1.0, float(pan)))
    theta = (pan + 1.0) * math.pi / 4.0
    return math.cos(theta), math.sin(theta)


def _apply_pan(endpoint, nch: int, saved: list, gain_l: float, gain_r: float,
               last: list) -> bool:
    """Write L/R channel volumes. Other channels untouched.

    The applied value is ``saved * gain`` clamped into [0, saved]: it can only
    ever be QUIETER than what the user had set, never louder.
    """
    global _last_error
    base_l = saved[0] if nch > 0 else 1.0
    base_r = saved[1] if nch > 1 else 1.0
    v_l = max(0.0, min(base_l, base_l * gain_l))
    v_r = max(0.0, min(base_r, base_r * gain_r))

    try:
        if nch > 0 and abs(v_l - last[0]) >= _DEADBAND:
            endpoint.SetChannelVolumeLevelScalar(0, v_l, None)
            last[0] = v_l
        if nch > 1 and abs(v_r - last[1]) >= _DEADBAND:
            endpoint.SetChannelVolumeLevelScalar(1, v_r, None)
            last[1] = v_r
        return True
    except Exception as e:
        _last_error = f"SetChannelVolumeLevelScalar failed: {e}"
        return False


def _worker(get_pan_fn: Callable[[], float], rate_hz: float) -> None:
    global _active
    try:
        import comtypes
        try:
            comtypes.CoInitialize()
        except Exception:
            pass
    except Exception:
        pass

    dt = 1.0 / max(10.0, float(rate_hz))
    alpha = math.exp(-dt / _SMOOTH_TAU)
    # start centred so the first write is not a jump
    g_l, g_r = equal_power_gains(0.0)
    last = [-1.0, -1.0]

    while _stop_evt is not None and not _stop_evt.is_set():
        try:
            pan = float(get_pan_fn())
        except Exception:
            pan = 0.0
        t_l, t_r = equal_power_gains(pan)
        g_l = t_l + (g_l - t_l) * alpha
        g_r = t_r + (g_r - t_r) * alpha
        if _endpoint is not None and _saved_channels is not None:
            if not _apply_pan(_endpoint, _nchannels, _saved_channels,
                              g_l, g_r, last):
                # driver failed mid-run: restore and abort
                _restore_channels(_endpoint, _saved_channels)
                _clear_residue()
                _active = False
                _say(f"mid-run failure, channels restored: {_last_error}")
                return
        time.sleep(dt)


def start_pan(get_pan_fn: Callable[[], float], rate_hz: float = 60.0) -> bool:
    """Start system-wide pan modulation. Returns True if active.

    CALLER CONTRACT: only reach this after the user has explicitly opted in.
    """
    global _thread, _stop_evt, _endpoint, _saved_channels, _nchannels
    global _active, _last_error
    with _state_lock:
        if _active:
            return True
        device, _endpoint, _nchannels = _get_device_and_endpoint()
        if _endpoint is None or _nchannels < 2:
            _last_error = _last_error or f"nch={_nchannels} (need >=2 stereo channels)"
            _say(f"cannot start: {_last_error}")
            _endpoint = None
            return False
        _saved_channels = _snapshot_channels(_endpoint, _nchannels)
        if _saved_channels is None:
            _endpoint = None
            return False
        # park the originals on disk BEFORE the first modulation
        _write_residue(_device_id(device), _nchannels, _saved_channels)
        _stop_evt = threading.Event()
        _thread = threading.Thread(
            target=_worker, args=(get_pan_fn, rate_hz),
            name="soundcard_pan", daemon=True)
        _active = True
        _thread.start()
        _say(f"started, equal-power, nch={_nchannels}, saved={_saved_channels}")
        return True


def stop_pan() -> None:
    """Stop pan and restore pre-sweep channel volumes. Idempotent."""
    global _thread, _stop_evt, _endpoint, _saved_channels, _nchannels, _active
    with _state_lock:
        if not _active and _endpoint is None:
            return
        if _stop_evt is not None:
            _stop_evt.set()
        t = _thread
    if t is not None:
        try:
            t.join(timeout=1.0)
        except Exception:
            pass
    with _state_lock:
        if _endpoint is not None and _saved_channels is not None:
            if _restore_channels(_endpoint, _saved_channels):
                _say(f"restored channels {_saved_channels}")
                _clear_residue()
            else:
                _say("restore INCOMPLETE -- residue file kept for next launch")
        else:
            _clear_residue()
        _thread = None
        _stop_evt = None
        _endpoint = None
        _saved_channels = None
        _nchannels = 0
        _active = False


def last_error() -> Optional[str]:
    return _last_error


def is_active() -> bool:
    return _active


@atexit.register
def _cleanup_on_exit() -> None:
    # Best effort only. atexit does NOT run on a qFatal abort or a hard kill --
    # that is precisely why the residue file exists.
    try:
        stop_pan()
    except Exception:
        pass


if __name__ == "__main__":
    # Deliberately NOT a live sweep. Running this file only prints the pan law
    # so it can be checked without opening or modulating any audio device.
    logging.basicConfig(level=logging.INFO)
    _say("pan law table (pan, gain_L, gain_R, total power):")
    for p in (-1.0, -0.5, 0.0, 0.5, 1.0):
        gl, gr = equal_power_gains(p)
        _say(f"  pan={p:+.2f}  L={gl:.5f}  R={gr:.5f}  "
             f"L^2+R^2={gl * gl + gr * gr:.6f}")
