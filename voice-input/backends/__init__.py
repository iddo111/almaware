"""backends/ - cross-platform input backend package for the Hebrew mic.

get_backend() returns a singleton InputBackend implementation for the current
OS. The runtime app imports ONLY this:

    from backends import get_backend
    be = get_backend()
    be.paste_text("שלום", enter=True)

Selection is by sys.platform:
    win32          -> WindowsBackend  (pure delegation to typer.py + router.py
                                       + ducking.py - byte-for-byte identical
                                       Windows behavior)
    darwin         -> MacBackend      (osascript / AppleScript System Events)
    everything else-> LinuxBackend    (xdotool/ydotool + wmctrl + pactl)

Override for testing with env VOICEINPUT_BACKEND in {win, linux, mac}.

rez.ai
"""
from __future__ import annotations

import logging
import os
import sys

from .base import InputBackend

logger = logging.getLogger("voiceinput.backends")

_BACKEND: InputBackend | None = None

_OVERRIDE_MAP = {"win": "win32", "windows": "win32",
                 "mac": "darwin", "macos": "darwin", "osx": "darwin",
                 "linux": "linux"}


def _platform_key() -> str:
    override = (os.environ.get("VOICEINPUT_BACKEND") or "").strip().lower()
    if override:
        key = _OVERRIDE_MAP.get(override)
        if key:
            logger.info("backend override via VOICEINPUT_BACKEND=%s -> %s",
                        override, key)
            return key
        logger.warning("unknown VOICEINPUT_BACKEND=%r (use win|linux|mac); "
                       "ignoring", override)
    return sys.platform


def get_backend() -> InputBackend:
    """Return the singleton InputBackend for this OS (created on first call)."""
    global _BACKEND
    if _BACKEND is not None:
        return _BACKEND

    p = _platform_key()
    if p == "win32":
        from .win import WindowsBackend as B
    elif p == "darwin":
        from .mac import MacBackend as B
    else:  # linux, *bsd, anything else
        from .linux import LinuxBackend as B

    _BACKEND = B()
    logger.info("input backend: %s (platform=%s)", _BACKEND.name, sys.platform)
    return _BACKEND


__all__ = ["InputBackend", "get_backend"]
