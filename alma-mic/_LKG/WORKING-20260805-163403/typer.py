"""alma-mic / typer.py — type recognized text into an approved chat window.

ALMAWARE-pure: our own Windows SendInput via ctypes. No external automation library.
Unicode path (KEYEVENTF_UNICODE) so Hebrew types correctly into any app.
We never steal focus (No Screen Hijack).  Typing fails closed unless the foreground
window has an explicit ChatGPT, Claude, or Codex title.  The same foreground HWND is
checked again immediately before each SendInput burst so a focus race cannot redirect
dictation into a terminal or another application.
"""
from __future__ import annotations
import ctypes
import re
import time
import unicodedata
from ctypes import wintypes
from typing import NamedTuple

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_RETURN = 0x0D

ULONG_PTR = ctypes.c_size_t  # pointer-sized, for dwExtraInfo


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = (("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR))


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = (("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR))


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = (("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD))


class _IUNION(ctypes.Union):
    _fields_ = (("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT), ("hi", _HARDWAREINPUT))


class _INPUT(ctypes.Structure):
    _fields_ = (("type", wintypes.DWORD), ("u", _IUNION))


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT
user32.GetForegroundWindow.argtypes = ()
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = (
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
)
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
kernel32.CloseHandle.restype = wintypes.BOOL


class FocusGuardError(RuntimeError):
    """Typing was refused because the foreground target was not an approved chat."""


class FocusChangedError(FocusGuardError):
    """Typing was refused because foreground focus changed during the guard check."""


class _Target(NamedTuple):
    hwnd: int
    title: str
    pid: int
    image_path: str


_TITLE_PRODUCT = {
    "chatgpt": "openai",
    "chatgpt (beta)": "openai",
    "codex": "openai",
    "codex (beta)": "openai",
    "claude": "claude",
    "claude (beta)": "claude",
}
_DENIED_TITLE_MARKERS = (
    "terminal",
    "powershell",
    "command prompt",
    "cmd.exe",
    "address bar",
    "omnibox",
    "url bar",
    # A top-level browser HWND/title does not reveal whether focus is in chat
    # content or the browser address bar.  Deny browser-hosted chat entirely;
    # native ChatGPT/Claude/Codex windows remain eligible.
    "google chrome",
    "microsoft edge",
    "mozilla firefox",
    "brave browser",
    "opera browser",
)
_TITLE_SEPARATOR = re.compile(r"\s*(?:\||-|\N{EN DASH}|\N{EM DASH}|:)\s*")
_MAX_TITLE_CHARS = 32768
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_OPENAI_APP_PATH = re.compile(
    r"^[a-z]:\\program files\\windowsapps\\openai\."
    r"(?:codex(?:beta)?|chatgpt)_[^\\]+__2p2nqsd0c76g0\\app\\"
    r"(?:chatgpt(?: \(beta\))?|codex(?: \(beta\))?)\.exe$",
    re.IGNORECASE,
)
_CLAUDE_APP_PATH = re.compile(
    r"^[a-z]:\\program files\\windowsapps\\claude_[^\\]+__pzs8sxrjxfjjc\\"
    r"app\\claude\.exe$",
    re.IGNORECASE,
)


def _clean_title(title: str) -> str:
    # Windows can wrap RTL/LTR titles in invisible formatting controls.  Removing
    # those controls makes exact product-name segments deterministic.
    return "".join(ch for ch in (title or "") if unicodedata.category(ch) != "Cf").strip()


def _title_product(title: str) -> str | None:
    """Return the single app family explicitly named by a safe title."""
    cleaned = _clean_title(title)
    if not cleaned:
        return None
    folded = cleaned.casefold()
    if any(marker in folded for marker in _DENIED_TITLE_MARKERS):
        return None
    products = {
        _TITLE_PRODUCT[part]
        for raw_part in _TITLE_SEPARATOR.split(cleaned)
        if (part := raw_part.strip().casefold()) in _TITLE_PRODUCT
    }
    return next(iter(products)) if len(products) == 1 else None


def is_allowed_chat_title(title: str) -> bool:
    """Return True only for explicit ChatGPT, Claude, or Codex title segments.

    Examples accepted: ``ChatGPT (Beta)``, ``Draft | Claude``, ``Task - Codex``.
    Terminal/address-bar/browser markers take precedence even when an allowed
    product name is also present.  Browser-hosted chat is denied because its
    top-level HWND/title cannot distinguish page focus from address-bar focus.
    Empty and arbitrary titles are denied.
    """
    return _title_product(title) is not None


def _clean_image_path(image_path: str) -> str:
    cleaned = (image_path or "").strip().replace("/", "\\")
    if cleaned.startswith("\\\\?\\"):
        cleaned = cleaned[4:]
    return cleaned


def is_allowed_app_identity(title: str, image_path: str) -> bool:
    """Bind an allowed title family to its protected packaged executable path."""
    product = _title_product(title)
    path = _clean_image_path(image_path)
    if product == "openai":
        return bool(_OPENAI_APP_PATH.fullmatch(path))
    if product == "claude":
        return bool(_CLAUDE_APP_PATH.fullmatch(path))
    return False


class _Win32Api:
    """Narrow Win32 boundary, replaceable by deterministic fakes in unit tests."""

    def foreground_hwnd(self) -> int:
        return int(user32.GetForegroundWindow() or 0)

    def window_title(self, hwnd: int) -> str:
        if not hwnd:
            return ""
        try:
            length = int(user32.GetWindowTextLengthW(hwnd))
            if length <= 0:
                return ""
            buf = ctypes.create_unicode_buffer(min(length + 1, _MAX_TITLE_CHARS))
            copied = int(user32.GetWindowTextW(hwnd, buf, len(buf)))
            return buf.value if copied > 0 else ""
        except Exception:
            return ""  # unreadable title is never permission to type

    def process_identity(self, hwnd: int) -> tuple[int, str]:
        """Return the HWND owner PID and full executable path, or ``(0, "")``."""
        if not hwnd:
            return 0, ""
        pid = wintypes.DWORD(0)
        try:
            thread_id = int(user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)))
            if not thread_id or not pid.value:
                return 0, ""
            handle = kernel32.OpenProcess(
                _PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value
            )
            if not handle:
                return 0, ""
            try:
                buf = ctypes.create_unicode_buffer(_MAX_TITLE_CHARS)
                size = wintypes.DWORD(len(buf))
                ok = kernel32.QueryFullProcessImageNameW(
                    handle, 0, buf, ctypes.byref(size)
                )
                return (int(pid.value), buf.value[: size.value]) if ok else (0, "")
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            return 0, ""  # unreadable ownership is never permission to type

    def send_input(self, prepared_events) -> int:
        return int(
            user32.SendInput(
                len(prepared_events), prepared_events, ctypes.sizeof(_INPUT)
            )
        )


_win32 = _Win32Api()


def _key_unicode(code: int, up: bool) -> _INPUT:
    flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0)
    return _INPUT(type=INPUT_KEYBOARD,
                  u=_IUNION(ki=_KEYBDINPUT(0, code, flags, 0, 0)))


def _key_vk(vk: int, up: bool) -> _INPUT:
    flags = KEYEVENTF_KEYUP if up else 0
    return _INPUT(type=INPUT_KEYBOARD,
                  u=_IUNION(ki=_KEYBDINPUT(vk, 0, flags, 0, 0)))


def _foreground_target() -> _Target:
    hwnd = _win32.foreground_hwnd()
    title = _win32.window_title(hwnd)
    pid, image_path = _win32.process_identity(hwnd)
    return _Target(hwnd=hwnd, title=title, pid=pid, image_path=image_path)


# --- who decides where dictation may land -----------------------------------
# The original guard hard-coded three chat apps. That is safe, but it also meant
# dictation refused to type into Notepad, Word, a terminal - anything Iddo was
# actually using. The policy is now HIS to set:
#
#   type_anywhere = False  (default)  only the built-in ChatGPT/Claude/Codex apps
#   type_anywhere = True              any foreground window, minus the blocks below
#   type_targets  = [...]             extra title substrings to allow
#
# Two things are refused no matter what: ALMA-MIC's own window (typing into
# itself is a feedback loop) and a window with no readable title or PID.
_ALWAYS_BLOCK_TITLES = ("alma-mic",)

_policy = {"anywhere": False, "targets": ()}

# The last window the user actually dictated into. When ALMA-MIC's own window
# takes focus (it does, every time they look at it) we type here instead of
# refusing - otherwise the app only works while you are NOT looking at it.
_last_external = {"target": None}


def set_policy(anywhere: bool = False, targets=()) -> None:
    """Called by the pipeline from config so this module stays import-light."""
    _policy["anywhere"] = bool(anywhere)
    _policy["targets"] = tuple(t.strip().casefold() for t in (targets or []) if t.strip())


def _extra_target_allowed(title: str) -> bool:
    t = (title or "").casefold()
    return bool(t) and any(x in t for x in _policy["targets"])


def _require_allowed_target() -> _Target:
    target = _foreground_target()
    title_cf = (target.title or "").casefold()

    if not target.hwnd or not target.pid:
        raise FocusGuardError("no usable foreground window")

    if any(b in title_cf for b in _ALWAYS_BLOCK_TITLES):
        # Our own window has focus - which happens constantly, because the user
        # is LOOKING at the mic while speaking. Refusing outright made the app
        # useless. Fall back to the last window they actually dictated into.
        remembered = _last_external.get("target")
        if remembered is not None and _win32.window_title(remembered.hwnd):
            return remembered
        raise FocusGuardError(
            "no target yet - click once into the window you want the text to go "
            f"into, then speak. (focused: {target.title!r})"
        )

    if (is_allowed_app_identity(target.title, target.image_path)
            or _extra_target_allowed(target.title)
            or (_policy["anywhere"] and target.title)):
        _last_external["target"] = target
        return target

    raise FocusGuardError(
        "typing is limited to ChatGPT/Claude/Codex. Turn on 'הקלד לכל חלון' in "
        "settings to allow any window. "
        f"(title={target.title!r}, image={target.image_path!r})"
    )


def _same_target(left: _Target, right: _Target) -> bool:
    return (
        left.hwnd == right.hwnd
        and _clean_title(left.title).casefold() == _clean_title(right.title).casefold()
        and left.pid == right.pid
        and _clean_image_path(left.image_path).casefold()
        == _clean_image_path(right.image_path).casefold()
    )


def _guarded_send(
    events: list[_INPUT], expected_target: _Target | None = None
) -> tuple[int, _Target | None]:
    """Send one burst only after two consistent, allowed foreground snapshots.

    ``expected_target`` links separate bursts (text, then optional Enter) to the
    same original HWND, title, PID, and executable.  The second snapshot is
    deliberately adjacent to the native SendInput call; neither snapshot changes
    focus.
    """
    if not events:
        return 0, expected_target

    before = _require_allowed_target()
    if expected_target is not None and not _same_target(before, expected_target):
        raise FocusChangedError(
            "foreground target changed before typing: "
            f"expected={expected_target!r}, actual={before!r}"
        )

    prepared_events = (_INPUT * len(events))(*events)

    # Re-read after all event preparation and immediately before SendInput.  This
    # closes the common race where the user Alt-Tabs between recognition and typing.
    final = _require_allowed_target()
    if not _same_target(final, before):
        raise FocusChangedError(
            f"foreground target changed during typing guard: before={before!r}, "
            f"final={final!r}"
        )
    if expected_target is not None and not _same_target(final, expected_target):
        raise FocusChangedError(
            "foreground target changed from original target: "
            f"expected={expected_target!r}, actual={final!r}"
        )

    return _win32.send_input(prepared_events), before


def type_text(text: str, enter: bool = False, enter_delay: float = 0.12) -> int:
    """Type `text` into the focused window (Unicode). Optionally press Enter to submit.

    The Enter is sent as a SEPARATE input burst after a short `enter_delay`, so the
    submit never races ahead of the characters — the old single-burst version could
    fire Enter before a slow app (chat box / web field) finished ingesting the Hebrew,
    sending an empty or half line. Text first, let it land, THEN send.
    Returns the number of input events the OS accepted."""
    events: list[_INPUT] = []
    for ch in text:
        for code in _codes(ch):          # surrogate pair for chars outside the BMP
            events.append(_key_unicode(code, up=False))
            events.append(_key_unicode(code, up=True))
    n = 0
    target: _Target | None = None
    if events:
        n, target = _guarded_send(events)
    if enter:
        time.sleep(max(0.0, enter_delay))            # let the app ingest the text first
        entered, _ = _guarded_send(
            [_key_vk(VK_RETURN, up=False), _key_vk(VK_RETURN, up=True)],
            expected_target=target,
        )
        n += entered
    return n


def _codes(ch: str):
    cp = ord(ch)
    if cp > 0xFFFF:                       # encode astral chars as UTF-16 surrogates
        cp -= 0x10000
        return (0xD800 + (cp >> 10), 0xDC00 + (cp & 0x3FF))
    return (cp,)


if __name__ == "__main__":  # manual check: focus an editor within 3s, then run
    import time
    print("focus a text field; typing in 3s…")
    time.sleep(3)
    n = type_text("שלום מ-ALMA-MIC ", enter=False)
    print(f"sent {n} events")
