"""mac.py - macOS InputBackend (osascript/AppleScript System Events + best-effort cliclick).
External tools (optional): cliclick (brew install cliclick) for robustness.
Permission: System Settings > Privacy & Security > Accessibility (add python / .app).
Handle: pid (int) or "app:NAME" / title string (opaque to callers).

macOS has its own compositor / permission model — full window control requires Accessibility.
Enum is best-effort (may be limited or require extra grants).

rez.ai
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from typing import Any

from .base import InputBackend

logger = logging.getLogger("voiceinput.backends.mac")


def _have(tool: str) -> bool:
    return shutil.which(tool) is not None


def _run(cmd: list[str], inp: bytes | None = None, timeout: float = 8.0):
    """Run helper. Never raises — logs and returns None so dictation loop survives."""
    try:
        return subprocess.run(cmd, input=inp, capture_output=True,
                              timeout=timeout, check=False)
    except FileNotFoundError:
        logger.warning("helper not found: %s", cmd[0])
        return None
    except Exception as e:  # noqa: BLE001
        logger.debug("helper failed %s: %s", cmd, e)
        return None


def _osascript(script: str) -> subprocess.CompletedProcess | None:
    return _run(["osascript", "-e", script])


class MacBackend(InputBackend):
    name = "mac"

    def __init__(self):
        self._has_cliclick = _have("cliclick")
        self._has_pbcopy = _have("pbcopy") and _have("pbpaste")
        logger.info("mac backend: cliclick=%s pbcopy=%s", self._has_cliclick, self._has_pbcopy)
        if not self._has_pbcopy:
            logger.warning("pbcopy/pbpaste not found — will try pyperclip. For full fidelity: brew install coreutils or ensure base system tools.")

    # ── low-level primitives (System Events) ─────────────────────────────────
    def _keystroke(self, text: str) -> bool:
        """Send unicode text via System Events keystroke. Chunk for safety."""
        if not text:
            return True
        for i in range(0, len(text), 80):
            chunk = text[i:i+80]
            # Quote safely — osascript -e expects the string literal
            r = _osascript(f'tell application "System Events" to keystroke {chunk!r}')
            if r is None or r.returncode != 0:
                return False
            time.sleep(0.015)
        return True

    def _key_combo(self, keys: str) -> None:
        """e.g. keys='"z" using command down' or '"v" using command down'."""
        _osascript(f'tell application "System Events" to keystroke {keys}')

    def _press_enter(self) -> None:
        # return key code 36 is more reliable than "return" in some contexts
        _osascript('tell application "System Events" to key code 36')

    # ── typing / paste (paste preferred for Hebrew bursts, like Win) ─────────
    def type_text(self, text: str, enter: bool = False) -> None:
        if not text:
            if enter:
                self._press_enter()
            return
        if not self._keystroke(text):
            logger.warning("type_text: osascript may have been blocked (check Accessibility permission)")
        if enter:
            time.sleep(0.03)
            self._press_enter()

    def paste_text(self, text: str, enter: bool = False) -> None:
        prev = None
        try:
            if self._has_pbcopy:
                p = _run(["pbpaste", "--no-newline"])
                if p is not None and p.returncode == 0:
                    prev = p.stdout.decode("utf-8", "replace")
            else:
                import pyperclip
                prev = pyperclip.paste()
        except Exception:  # noqa: BLE001
            pass

        data = text.encode("utf-8", "replace")
        if self._has_pbcopy:
            _run(["pbcopy"], inp=data)
        else:
            try:
                import pyperclip
                pyperclip.copy(text)
            except Exception:  # noqa: BLE001
                logger.warning("paste_text: no working clipboard — falling back to type")
                self.type_text(text, enter=enter)
                return

        time.sleep(0.06)
        self._key_combo('"v" using command down')
        time.sleep(0.08)
        if enter:
            self._press_enter()
        time.sleep(0.12)
        # restore previous clipboard contents
        if prev is not None:
            if self._has_pbcopy:
                _run(["pbcopy"], inp=prev.encode("utf-8", "replace"))
            else:
                try:
                    import pyperclip
                    pyperclip.copy(prev)
                except Exception:  # noqa: BLE001
                    pass

    def set_clipboard(self, text: str) -> None:
        if self._has_pbcopy:
            _run(["pbcopy"], inp=text.encode("utf-8", "replace"))
        else:
            try:
                import pyperclip
                pyperclip.copy(text)
            except Exception:  # noqa: BLE001
                pass

    # ── window discovery / focus (Accessibility strongly recommended) ────────
    def get_foreground_window(self) -> Any | None:
        """Return pid (int) of frontmost process, or synthetic token."""
        r = _osascript('tell application "System Events" to get unix id of first process whose frontmost is true')
        if r is not None and r.returncode == 0:
            try:
                val = r.stdout.decode("utf-8", "replace").strip()
                if val:
                    return int(val)
            except Exception:  # noqa: BLE001
                pass
        return "frontmost"

    def focus_window(self, handle: Any) -> bool:
        if handle in (None, "frontmost", "active"):
            return True
        if isinstance(handle, int):
            _osascript(f'tell application "System Events" to set frontmost of (first process whose unix id is {handle}) to true')
            return True
        # treat as app name / bundle hint
        _osascript(f'tell application {str(handle)!r} to activate')
        return True

    def enum_windows(self) -> list[tuple[Any, str, str]]:
        """Best-effort list. Full rich window list on macOS usually requires Accessibility + may still be limited by the OS."""
        r = _osascript('tell application "System Events" to get {name, unix id} of every process whose background only is false')
        if r is None or r.returncode != 0:
            fg = self.get_foreground_window()
            return [(fg, "", "")] if fg else []
        out: list[tuple[Any, str, str]] = []
        try:
            raw = r.stdout.decode("utf-8", "replace").strip()
            # Very defensive parse of AppleScript list output — real production can use pyobjc/appscript for richer data.
            items = [x.strip().strip('"\'') for x in raw.replace("{", "").replace("}", "").split(",") if x.strip()]
            for i in range(0, len(items) - 1, 2):
                name = items[i]
                pid_s = items[i + 1]
                try:
                    pid = int(pid_s)
                except Exception:
                    pid = pid_s
                out.append((pid, name, (name or "").lower()))
        except Exception as e:  # noqa: BLE001
            logger.debug("enum_windows parse partial: %s", e)
        if not out:
            fg = self.get_foreground_window()
            if fg:
                out.append((fg, "", ""))
        return out

    def send_undo(self, handle: Any) -> None:
        self.focus_window(handle)
        time.sleep(0.05)
        self._key_combo('"z" using command down')

    # ── audio duck (global best-effort only; per-app is app-specific and complex) ─
    # NOTE: cfg ships with ducking_enabled=false / duck_pct=100 so this is rarely active.
    def duck(self) -> list[str]:
        try:
            _osascript('set volume output volume 25')
            return ["system:global->25% (mac)"]
        except Exception as e:  # noqa: BLE001
            logger.debug("duck failed: %s", e)
            return []

    def restore(self) -> None:
        try:
            _osascript('set volume output volume 100')
        except Exception as e:  # noqa: BLE001
            logger.debug("restore failed: %s", e)

    # ── misc ─────────────────────────────────────────────────────────────────
    def beep(self) -> None:
        _run(["osascript", "-e", "beep"])

    def open_path(self, path: str) -> None:
        _run(["open", path])
