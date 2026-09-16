"""linux.py - Linux InputBackend (X11 + best-effort Wayland).

External helper tools (all optional; the backend degrades gracefully with a
clear log line and never crashes if one is missing):

  typing/keys : xdotool        (X11)            preferred when DISPLAY set
                ydotool         (X11 + Wayland)  fallback; needs `ydotoold`
                                                 daemon running + uinput perms
  clipboard   : xclip / xsel    (X11)
                wl-copy/wl-paste (Wayland; from wl-clipboard)
  windows     : wmctrl          (list + activate, X11)
                xdotool         (getactivewindow / windowactivate, X11)
  ducking     : pactl           (PulseAudio / PipeWire sink-input volume)

Install hints (Debian/Ubuntu):
  sudo apt install xdotool ydotool wmctrl xclip wl-clipboard pulseaudio-utils

DISPLAY SERVER NOTES
  X11      : full support - enum_windows / focus / undo all work via wmctrl +
             xdotool.
  Wayland  : window enumeration & arbitrary focus are RESTRICTED by the
             compositor for security. We degrade to "type into whatever is
             focused": enum_windows() returns the active window if we can read
             it (else []), focus_window() is best-effort/no-op, and typing uses
             ydotool (the only injector that works under Wayland). The mic still
             dictates into the focused app - it just can't route between windows.

Handle type: an X11 window-id string like "0x03a00007" (from wmctrl/xdotool).
Under Wayland the handle may be a synthetic "active" token; treat it opaquely.

NOTE: the shipped config has ducking disabled (duck_pct=100 /
ducking_enabled=false), so duck()/restore() being a no-op (when pactl is
absent) is perfectly acceptable for v1.

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

logger = logging.getLogger("voiceinput.backends.linux")


def _have(tool: str) -> bool:
    return shutil.which(tool) is not None


def _run(cmd: list[str], inp: bytes | None = None, timeout: float = 5.0):
    """Run a helper command. Returns CompletedProcess or None on failure.
    Never raises - logs and returns None so the dictation loop survives."""
    try:
        return subprocess.run(cmd, input=inp, capture_output=True,
                              timeout=timeout, check=False)
    except FileNotFoundError:
        logger.warning("helper not found: %s", cmd[0])
        return None
    except Exception as e:  # noqa: BLE001
        logger.debug("helper failed %s: %s", cmd, e)
        return None


class LinuxBackend(InputBackend):
    name = "linux"

    def __init__(self):
        self._wayland = bool(os.environ.get("WAYLAND_DISPLAY")) or \
            (os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland")
        self._has_xdotool = _have("xdotool")
        self._has_ydotool = _have("ydotool")
        self._has_wmctrl = _have("wmctrl")
        self._has_xclip = _have("xclip")
        self._has_xsel = _have("xsel")
        self._has_wlcopy = _have("wl-copy")
        self._has_wlpaste = _have("wl-paste")
        self._has_pactl = _have("pactl")
        # pactl ducking state: sink-input-id -> original volume percent
        self._ducked: dict[str, int] = {}

        sess = "wayland" if self._wayland else "x11"
        logger.info("linux backend: session=%s xdotool=%s ydotool=%s wmctrl=%s "
                    "clip=%s pactl=%s", sess, self._has_xdotool,
                    self._has_ydotool, self._has_wmctrl,
                    "wl-copy" if self._has_wlcopy else
                    ("xclip" if self._has_xclip else
                     ("xsel" if self._has_xsel else "none")),
                    self._has_pactl)
        if self._wayland and not self._has_ydotool:
            logger.warning("Wayland session but ydotool missing - typing will "
                           "not work. Install ydotool + run ydotoold.")
        if not self._has_xdotool and not self._has_ydotool:
            logger.warning("neither xdotool nor ydotool present - typing/keys "
                           "disabled (mic will transcribe but not type).")

    # ── low-level key/type primitives ─────────────────────────────────────────
    def _type_via_tool(self, text: str) -> bool:
        # Prefer xdotool on X11 (fast, reliable unicode); else ydotool.
        if self._has_xdotool and not self._wayland:
            r = _run(["xdotool", "type", "--clearmodifiers", "--", text])
            if r is not None and r.returncode == 0:
                return True
        if self._has_ydotool:
            r = _run(["ydotool", "type", "--", text])
            if r is not None and r.returncode == 0:
                return True
        # last resort: xdotool even under Wayland (works if XWayland app focused)
        if self._has_xdotool:
            r = _run(["xdotool", "type", "--clearmodifiers", "--", text])
            if r is not None and r.returncode == 0:
                return True
        logger.warning("type_text: no working injector (xdotool/ydotool)")
        return False

    def _press_enter(self) -> None:
        if self._has_xdotool and not self._wayland:
            if _run(["xdotool", "key", "Return"]):
                return
        if self._has_ydotool:
            # ydotool keycode 28 = Enter (KEY_ENTER); :1 press, :0 release
            _run(["ydotool", "key", "28:1", "28:0"])
            return
        if self._has_xdotool:
            _run(["xdotool", "key", "Return"])

    def _key_combo(self, *, xdo: str, ydo: list[str]) -> None:
        """Send a key combo. xdo = xdotool key spec (e.g. 'ctrl+v'); ydo =
        ydotool key event list."""
        if self._has_xdotool and not self._wayland:
            if _run(["xdotool", "key", "--clearmodifiers", xdo]):
                return
        if self._has_ydotool:
            _run(["ydotool", "key", *ydo])
            return
        if self._has_xdotool:
            _run(["xdotool", "key", "--clearmodifiers", xdo])

    # ── typing ────────────────────────────────────────────────────────────────
    def type_text(self, text: str, enter: bool = False) -> None:
        if not text:
            if enter:
                self._press_enter()
            return
        self._type_via_tool(text)
        if enter:
            time.sleep(0.03)
            self._press_enter()

    def paste_text(self, text: str, enter: bool = False) -> None:
        prev = self._read_clipboard()
        if not self._write_clipboard(text):
            # clipboard unavailable -> fall back to typing the text directly
            logger.info("paste_text: no clipboard tool, typing instead")
            self.type_text(text, enter=enter)
            return
        time.sleep(0.06)
        # ctrl+v (28 not needed; v=47). ydotool: ctrl=29, v=47.
        self._key_combo(xdo="ctrl+v", ydo=["29:1", "47:1", "47:0", "29:0"])
        time.sleep(0.08)
        if enter:
            self._press_enter()
        time.sleep(0.12)
        if prev is not None:
            self._write_clipboard(prev)

    # ── clipboard ─────────────────────────────────────────────────────────────
    def _write_clipboard(self, text: str) -> bool:
        data = text.encode("utf-8", "replace")
        if self._wayland and self._has_wlcopy:
            return _run(["wl-copy"], inp=data) is not None
        if self._has_xclip:
            return _run(["xclip", "-selection", "clipboard"], inp=data) is not None
        if self._has_xsel:
            return _run(["xsel", "--clipboard", "--input"], inp=data) is not None
        if self._has_wlcopy:  # wl-copy can work under XWayland too
            return _run(["wl-copy"], inp=data) is not None
        # pyperclip as a final fallback (needs xclip/xsel/wl-clipboard anyway,
        # but try in case it found something we didn't)
        try:
            import pyperclip
            pyperclip.copy(text)
            return True
        except Exception:  # noqa: BLE001
            return False

    def _read_clipboard(self) -> str | None:
        if self._wayland and self._has_wlpaste:
            r = _run(["wl-paste", "--no-newline"])
        elif self._has_xclip:
            r = _run(["xclip", "-selection", "clipboard", "-o"])
        elif self._has_xsel:
            r = _run(["xsel", "--clipboard", "--output"])
        elif self._has_wlpaste:
            r = _run(["wl-paste", "--no-newline"])
        else:
            try:
                import pyperclip
                return pyperclip.paste()
            except Exception:  # noqa: BLE001
                return None
        if r is not None and r.returncode == 0:
            return r.stdout.decode("utf-8", "replace")
        return None

    def set_clipboard(self, text: str) -> None:
        self._write_clipboard(text)

    # ── window discovery / focus ──────────────────────────────────────────────
    def get_foreground_window(self) -> Any | None:
        if self._has_xdotool:
            r = _run(["xdotool", "getactivewindow"])
            if r is not None and r.returncode == 0:
                wid = r.stdout.decode().strip()
                if wid:
                    return wid
        if self._wayland:
            logger.debug("Wayland: get_foreground_window unsupported -> 'active'")
            return "active"  # synthetic opaque token
        return None

    def _proc_for_pid(self, pid: str) -> str:
        try:
            with open(f"/proc/{int(pid)}/comm", "r", encoding="utf-8") as f:
                return f.read().strip().lower()
        except Exception:  # noqa: BLE001
            return ""

    def enum_windows(self) -> list[tuple[Any, str, str]]:
        # X11: wmctrl -lp gives  "<id> <desktop> <pid> <host> <title>"
        if self._has_wmctrl and not self._wayland:
            r = _run(["wmctrl", "-lp"])
            if r is not None and r.returncode == 0:
                out: list[tuple[Any, str, str]] = []
                for line in r.stdout.decode("utf-8", "replace").splitlines():
                    parts = line.split(None, 4)
                    if len(parts) < 5:
                        continue
                    wid, _desk, pid, _host, title = parts
                    out.append((wid, title, self._proc_for_pid(pid)))
                return out
            logger.debug("wmctrl -lp returned nothing")
        # Wayland (or no wmctrl): degrade to just the active window, if any.
        fg = self.get_foreground_window()
        if fg and fg != "active":
            title, proc = "", ""
            if self._has_xdotool:
                r = _run(["xdotool", "getactivewindow", "getwindowname"])
                if r is not None and r.returncode == 0:
                    title = r.stdout.decode("utf-8", "replace").strip()
                rp = _run(["xdotool", "getactivewindow", "getwindowpid"])
                if rp is not None and rp.returncode == 0:
                    proc = self._proc_for_pid(rp.stdout.decode().strip())
            return [(fg, title, proc)]
        if self._wayland:
            logger.info("Wayland: enum_windows restricted by compositor - "
                        "returning [] (type into focused window only).")
        return []

    def focus_window(self, handle: Any) -> bool:
        if handle in (None, "active"):
            # nothing to raise; the focused window is already the target
            return True
        # X11: wmctrl -ia raises + activates by window id
        if self._has_wmctrl and not self._wayland:
            r = _run(["wmctrl", "-ia", str(handle)])
            if r is not None and r.returncode == 0:
                time.sleep(0.05)
                return True
        if self._has_xdotool:
            r = _run(["xdotool", "windowactivate", "--sync", str(handle)])
            if r is not None and r.returncode == 0:
                return True
        if self._wayland:
            logger.debug("Wayland: focus_window unsupported; assuming focused")
            return True
        logger.warning("focus_window failed for handle=%s", handle)
        return False

    def send_undo(self, handle: Any) -> None:
        self.focus_window(handle)
        time.sleep(0.05)
        # ctrl+z ; ydotool ctrl=29, z=44
        self._key_combo(xdo="ctrl+z", ydo=["29:1", "44:1", "44:0", "29:0"])

    # ── audio ducking (PulseAudio / PipeWire via pactl) ───────────────────────
    _EXCLUDE = {"python", "python3", "ffplay", "ffmpeg"}

    def duck(self) -> list[str]:
        if not self._has_pactl:
            return []  # acceptable no-op (ducking disabled in shipped config)
        r = _run(["pactl", "list", "sink-inputs"])
        if r is None or r.returncode != 0:
            return []
        ducked: list[str] = []
        cur_id = None
        cur_vol_pct = None
        cur_app = ""
        target_pct = 20  # lower others to ~20%
        for raw in r.stdout.decode("utf-8", "replace").splitlines():
            line = raw.strip()
            if line.startswith("Sink Input #"):
                cur_id = line.split("#", 1)[1].strip()
                cur_vol_pct, cur_app = None, ""
            elif line.startswith("Volume:") and "%" in line:
                try:
                    seg = line.split("/")[1].strip()  # ".. / 100% / .."
                    cur_vol_pct = int(seg.replace("%", ""))
                except Exception:  # noqa: BLE001
                    cur_vol_pct = None
            elif "application.name" in line or "application.process.binary" in line:
                cur_app = line.split("=", 1)[-1].strip().strip('"').lower() or cur_app
            elif line == "" and cur_id is not None:
                self._maybe_duck(cur_id, cur_vol_pct, cur_app, target_pct, ducked)
                cur_id = None
        if cur_id is not None:
            self._maybe_duck(cur_id, cur_vol_pct, cur_app, target_pct, ducked)
        if ducked:
            logger.info("ducked: %s", ", ".join(ducked))
        return ducked

    def _maybe_duck(self, sid, vol_pct, app, target_pct, ducked):
        if any(x in app for x in self._EXCLUDE):
            return
        if vol_pct is None or vol_pct <= target_pct + 1:
            return
        if _run(["pactl", "set-sink-input-volume", sid, f"{target_pct}%"]) is not None:
            self._ducked[sid] = vol_pct
            ducked.append(f"{app or sid}({vol_pct}%->{target_pct}%)")

    def restore(self) -> None:
        if not self._has_pactl or not self._ducked:
            self._ducked.clear()
            return
        for sid, pct in list(self._ducked.items()):
            _run(["pactl", "set-sink-input-volume", sid, f"{pct}%"])
        logger.info("restored %d sink-input(s)", len(self._ducked))
        self._ducked.clear()

    # ── misc ──────────────────────────────────────────────────────────────────
    def open_path(self, path: str) -> None:
        if _have("xdg-open"):
            _run(["xdg-open", path])
        else:
            super().open_path(path)
