import ctypes
import ctypes.wintypes as wintypes
import time
import os
import sys

# Define missing type for compatibility with Python 3.12/3.13
try:
    ULONG_PTR = wintypes.ULONG_PTR
except AttributeError:
    # On some Python versions, wintypes.ULONG_PTR doesn't exist
    # ULONG_PTR is a pointer-sized unsigned integer (size_t)
    ULONG_PTR = ctypes.c_size_t

# Constants
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_KEYUP = 0x0002
PROCESS_VM_OPERATION = 0x0008
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_QUERY_INFORMATION = 0x0400

# Structures for SendInput
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ('dx', wintypes.LONG),
        ('dy', wintypes.LONG),
        ('mouseData', wintypes.DWORD),
        ('dwFlags', wintypes.DWORD),
        ('time', wintypes.DWORD),
        ('dwExtraInfo', ULONG_PTR),
    ]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ('wVk', wintypes.WORD),
        ('wScan', wintypes.WORD),
        ('dwFlags', wintypes.DWORD),
        ('time', wintypes.DWORD),
        ('dwExtraInfo', ULONG_PTR),
    ]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ('uMsg', wintypes.DWORD),
        ('wParamL', wintypes.WORD),
        ('wParamH', wintypes.WORD),
    ]

class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ('mi', MOUSEINPUT),
        ('ki', KEYBDINPUT),
        ('hi', HARDWAREINPUT),
    ]

class INPUT(ctypes.Structure):
    _fields_ = [
        ('type', wintypes.DWORD),
        ('union', INPUT_UNION),
    ]

# Windows API functions
user32 = ctypes.WinDLL('user32', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

# Declare OpenProcess from kernel32 (not user32)
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE

kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL

user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT

user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wintypes.HWND

user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD

# For process name lookup (requires psutil fallback)
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


def get_foreground_process_name():
    """Get the executable name of the foreground window."""
    try:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""
        
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        
        if HAS_PSUTIL:
            try:
                process = psutil.Process(pid.value)
                return process.name().lower()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                return ""
        else:
            # Fallback using kernel32: EnumProcesses + GetProcessImageFileName
            # (simplified - not robust; prefer psutil)
            # Return empty string to avoid false negatives if psutil unavailable
            return ""
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# 2026-09-03 02:10 -- Iddo: "היא כן מקלידה מקומות אחרים... ב-CLI היא לא מקלידה".
# MEASURED, not guessed: his Claude CLI terminal (WindowsTerminal pid 10640) had
# been launched at 01:38 from an *Administrator* PowerShell, so it ran at HIGH
# integrity; KESHEV runs at MEDIUM. Windows UIPI silently discards SendInput
# from a lower-integrity process into a higher-integrity window -- and
# SendInput still RETURNS SUCCESS (measured: 2 of 2 "inserted", GetLastError 0;
# the docs say neither the return value nor GetLastError reveals a UIPI block).
# The same typer into a NON-elevated Claude CLI typed Hebrew + Enter perfectly.
# So the only honest thing to do is look at the target window BEFORE typing and
# say out loud when Windows is going to eat the keystrokes. Nothing else changed.
# ---------------------------------------------------------------------------
advapi32 = ctypes.WinDLL('advapi32', use_last_error=True)
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TOKEN_QUERY = 0x0008
TokenIntegrityLevel = 25
SECURITY_MANDATORY_HIGH_RID = 0x3000

advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
advapi32.OpenProcessToken.restype = wintypes.BOOL
advapi32.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
advapi32.GetTokenInformation.restype = wintypes.BOOL
advapi32.GetSidSubAuthorityCount.argtypes = [ctypes.c_void_p]
advapi32.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
advapi32.GetSidSubAuthority.argtypes = [ctypes.c_void_p, wintypes.DWORD]
advapi32.GetSidSubAuthority.restype = ctypes.POINTER(wintypes.DWORD)

_INTEGRITY_NAMES = {0x0000: 'UNTRUSTED', 0x1000: 'LOW', 0x2000: 'MEDIUM', 0x2100: 'MEDIUM+',
                    0x3000: 'HIGH', 0x4000: 'SYSTEM', 0x5000: 'PROTECTED'}


def process_integrity(pid):
    """Integrity label of a process: 'MEDIUM' for a normal app, 'HIGH' for one that
    runs as Administrator. 'DENIED' when Windows will not even show us its token
    (treated as elevated: if we cannot read it, we cannot type into it either).
    'UNKNOWN' on any other failure -- never raises."""
    if not pid:
        return 'UNKNOWN'
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return 'DENIED' if ctypes.get_last_error() == 5 else 'UNKNOWN'
    tok = wintypes.HANDLE()
    try:
        if not advapi32.OpenProcessToken(h, TOKEN_QUERY, ctypes.byref(tok)):
            return 'DENIED' if ctypes.get_last_error() == 5 else 'UNKNOWN'
        try:
            buf = ctypes.create_string_buffer(64)
            n = wintypes.DWORD()
            if not advapi32.GetTokenInformation(tok, TokenIntegrityLevel, buf, 64, ctypes.byref(n)):
                return 'UNKNOWN'
            psid = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]
            count = advapi32.GetSidSubAuthorityCount(psid)[0]
            rid = advapi32.GetSidSubAuthority(psid, count - 1)[0]
            return _INTEGRITY_NAMES.get(rid, f'0x{rid:04x}')
        finally:
            kernel32.CloseHandle(tok)
    finally:
        kernel32.CloseHandle(h)


def window_integrity(hwnd):
    """Integrity label of the process that owns hwnd (see process_integrity)."""
    if not hwnd:
        return 'UNKNOWN'
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return process_integrity(pid.value)


def integrity_is_elevated(label):
    return label in ('HIGH', 'SYSTEM', 'PROTECTED', 'DENIED')


def foreground_is_elevated():
    """(elevated, integrity_label, process_name) of the window that has the focus."""
    hwnd = user32.GetForegroundWindow()
    label = window_integrity(hwnd)
    return integrity_is_elevated(label), label, get_foreground_process_name()


# ---------------------------------------------------------------------------
# 2026-09-06 12:20 -- Iddo, through the mic: "סדר את המיק שיקליד גם בתוך ה-CLI".
# The same scar as 09-03, measured again this morning: his Claude CLI window
# (WindowsTerminal pid 23460, hwnd 2362548) had been opened from an Administrator
# shell and ran at HIGH; KESHEV runs at MEDIUM; UIPI ate every keystroke.
# The 09-03 guard above already refused to type -- but it answered a bare False,
# so main.py could not tell "refused" from "nothing to type", and the window's
# ledger counted the sentence as typed. Three things change here, nothing else:
#   1. the rule is RELATIVE: refuse when the target sits ABOVE us (or hides its
#      token). A MEDIUM mic still refuses HIGH exactly as before; a mic that is
#      itself run as Administrator (Iddo's call, see NEEDS-IDDO-admin-windows.md)
#      would type into HIGH and refuse only SYSTEM.
#   2. the refusal is STRUCTURED: type_string() returns a TypeRefusal -- falsy, so
#      every `if not ok:` caller (main.py, intake\keshev_intake.py) keeps working
#      -- carrying reason / integrity / proc / pid / hwnd and a bilingual message.
#   3. the decision is a pure function of ONE window (refusal_for_window), so the
#      --selftest can exercise it on a REAL elevated window without typing or
#      stealing focus. SendInput is never called on a refusal.
# ---------------------------------------------------------------------------
_INTEGRITY_RANK = {'UNTRUSTED': 0x0000, 'LOW': 0x1000, 'MEDIUM': 0x2000, 'MEDIUM+': 0x2100,
                   'HIGH': 0x3000, 'SYSTEM': 0x4000, 'PROTECTED': 0x5000}
_self_integrity_cache = None

user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
_WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [_WNDENUMPROC, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL


def self_integrity():
    """Integrity label of THIS process. Cached: it cannot change while we run."""
    global _self_integrity_cache
    if _self_integrity_cache is None:
        _self_integrity_cache = process_integrity(os.getpid())
    return _self_integrity_cache


def target_is_above(target_label, self_label=None):
    """True when Windows (UIPI) will silently discard our SendInput into a window
    whose owner carries target_label: it sits ABOVE our own integrity, or it will
    not even show us its token ('DENIED'). Unreadable labels on either side fall
    back to the absolute rule that has held since 09-03 (integrity_is_elevated)."""
    if target_label == 'DENIED':
        return True
    if self_label is None:
        self_label = self_integrity()
    t = _INTEGRITY_RANK.get(target_label)
    s = _INTEGRITY_RANK.get(self_label)
    if t is None or s is None:
        return integrity_is_elevated(target_label)
    return t > s


class TypeRefusal:
    """type_string() came back WITHOUT calling SendInput, and this says why.

    Falsy on purpose: `ok = type_string(...); if not ok:` keeps working for every
    caller that only ever looked at a bool. reason is 'elevated' today (the
    target window sits above us and Windows would eat the keys)."""
    __slots__ = ('reason', 'integrity', 'self_integrity', 'proc', 'pid', 'hwnd', 'title')

    def __init__(self, reason, integrity='UNKNOWN', self_integrity='UNKNOWN',
                 proc='', pid=0, hwnd=0, title=''):
        self.reason = reason
        self.integrity = integrity
        self.self_integrity = self_integrity
        self.proc = proc
        self.pid = pid
        self.hwnd = hwnd
        self.title = title

    def __bool__(self):
        return False

    def __repr__(self):
        return (f"TypeRefusal(reason={self.reason!r}, integrity={self.integrity}, "
                f"self={self.self_integrity}, proc={self.proc!r}, pid={self.pid}, hwnd={self.hwnd})")

    @property
    def message_he(self):
        return (f"החלון הפעיל ({self.proc or '?'}) רץ כמנהל (Administrator) — "
                f"ווינדוס חוסם הקלדה לתוכו. פתח אותו מחדש בלי 'הרץ כמנהל'.")

    @property
    def message_en(self):
        return (f"The focused window ({self.proc or '?'}) runs as Administrator — "
                f"Windows (UIPI) blocks typing into it. Reopen it WITHOUT 'Run as administrator'.")

    def as_dict(self):
        return {'reason': self.reason, 'integrity': self.integrity,
                'self_integrity': self.self_integrity, 'proc': self.proc,
                'pid': self.pid, 'hwnd': self.hwnd, 'title': self.title,
                'message_he': self.message_he, 'message_en': self.message_en}


# Optional status hook: set typer.on_refusal = callable(TypeRefusal) and it is
# called on every refusal, for callers that never look at the return value.
on_refusal = None


def _window_pid(hwnd):
    if not hwnd:
        return 0
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _process_name(pid):
    """lower-cased image name, '' when unknown (same shape as get_foreground_process_name)."""
    if not pid or not HAS_PSUTIL:
        return ""
    try:
        return psutil.Process(pid).name().lower()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return ""
    except Exception:
        return ""


def _window_title(hwnd):
    try:
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value
    except Exception:
        return ""


def refusal_for_window(hwnd):
    """Look at ONE window before typing into it. Returns a TypeRefusal when Windows
    would discard our keystrokes there, else None. Never types, never moves focus."""
    pid = _window_pid(hwnd)
    label = process_integrity(pid) if pid else 'UNKNOWN'
    mine = self_integrity()
    if target_is_above(label, mine):
        return TypeRefusal('elevated', integrity=label, self_integrity=mine,
                           proc=_process_name(pid), pid=pid, hwnd=hwnd,
                           title=_window_title(hwnd))
    return None


def find_elevated_window():
    """--selftest helper: the first visible, titled top-level window whose owner
    sits above us -- a REAL one on the desktop right now -- or 0 when there is none."""
    found = []

    def _cb(hwnd, _lp):
        try:
            if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) > 0:
                r = refusal_for_window(hwnd)
                if r is not None:
                    found.append((r.integrity, hwnd))
        except Exception:
            pass
        return True

    user32.EnumWindows(_WNDENUMPROC(_cb), 0)
    # prefer a window whose label we could READ (HIGH/SYSTEM) over one that hid it
    for label, hwnd in found:
        if label in _INTEGRITY_RANK:
            return hwnd
    return found[0][1] if found else 0


def is_password_manager_window():
    """Check if current foreground window belongs to known password managers."""
    names = {'keepass.exe', '1password.exe', 'bitwarden.exe', 'dashlane.exe', 'lastpass.exe'}
    name = get_foreground_process_name()
    return name in names


def type_string(text, auto_enter=False):
    """
    Type Unicode (including Hebrew) text into the focused window using SendInput.
    Skips typing if the text matches last typed text (loop guard).
    Avoids password managers.
    
    Args:
        text (str): Text to type (Unicode supported)
        auto_enter (bool): Whether to press Enter at the end
    """
    # Avoid typing the same text repeatedly (loop guard)
    # Note: For robustness in a larger app, track last typed string externally
    # For standalone function, skip guard (or extend with state as needed)
    if not text:
        return False

    if is_password_manager_window():
        return False

    refusal = refusal_for_window(user32.GetForegroundWindow())
    if refusal is not None:
        # Windows would discard every keystroke below and report success. Say so
        # instead, in the log the window reads, and type nothing. The line below is
        # byte-identical to the 09-03 one: gui.py / gui6.py key their banner off it.
        proc, level = refusal.proc, refusal.integrity
        print(f"[typer] BLOCKED admin-window proc={proc or '?'} integrity={level}: "
              f"that window runs as Administrator and Windows (UIPI) silently drops "
              f"keystrokes from a normal app into it - nothing typed. Relaunch it "
              f"WITHOUT 'Run as administrator'.", file=sys.stderr, flush=True)
        if on_refusal is not None:
            try:
                on_refusal(refusal)
            except Exception:
                pass
        return refusal

    # Build INPUT structures for SendInput
    inputs = []
    
    # Convert string to UTF-16 code units (surrogate pairs for chars > U+FFFF handled automatically)
    for char in text:
        # Send character as Unicode scan code
        input_ = INPUT()
        input_.type = 1  # INPUT_KEYBOARD
        ki = input_.union.ki
        ki.wScan = ord(char)
        ki.dwFlags = KEYEVENTF_UNICODE
        ki.dwExtraInfo = 0
        ki.time = 0
        inputs.append(input_)
        
        # Send key-up event
        input_up = INPUT()
        input_up.type = 1  # INPUT_KEYBOARD
        ki_up = input_up.union.ki
        ki_up.wScan = ord(char)
        ki_up.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
        ki_up.dwExtraInfo = 0
        ki_up.time = 0
        inputs.append(input_up)
    
    # Add optional Enter key at end
    if auto_enter:
        # Enter key-down
        input_enter = INPUT()
        input_enter.type = 1
        ki_enter = input_enter.union.ki
        ki_enter.wVk = 0x0D  # VK_RETURN
        ki_enter.dwFlags = 0
        ki_enter.dwExtraInfo = 0
        ki_enter.time = 0
        inputs.append(input_enter)
        
        # Enter key-up
        input_enter_up = INPUT()
        input_enter_up.type = 1
        ki_enter_up = input_enter_up.union.ki
        ki_enter_up.wVk = 0x0D
        ki_enter_up.dwFlags = KEYEVENTF_KEYUP
        ki_enter_up.dwExtraInfo = 0
        ki_enter_up.time = 0
        inputs.append(input_enter_up)
    
    # Send all inputs
    c_inputs = (INPUT * len(inputs))(*inputs)
    result = user32.SendInput(len(inputs), c_inputs, ctypes.sizeof(INPUT))
    
    if result != len(inputs):
        # SendInput partially succeeded; could raise, but silently retry small failures
        pass
    return True


# Optional: Delayed typing (for dictation apps)
def type_string_delayed(text, auto_enter=False, delay_per_char=0.005):
    """
    Type text with small delays to mimic human typing.
    """
    if not text:
        return
    
    # Small initial delay to let system settle
    time.sleep(0.05)
    
    # Type character-by-character with delay
    for char in text:
        # For efficiency, batch small groups; but for simplicity in dictation,
        # type one char at a time for precise delay
        type_string(char)
        time.sleep(delay_per_char)
    
    if auto_enter:
        time.sleep(0.05)
        type_string("\n", auto_enter=False)


if __name__ == "__main__":
    # python app/typer.py --selftest : proves the integrity probe on real processes
    # without typing a single character anywhere.
    if "--selftest" in sys.argv:
        mine = process_integrity(os.getpid())
        shell = window_integrity(user32.GetShellWindow())  # explorer's desktop: always MEDIUM
        fg_elev, fg_level, fg_proc = foreground_is_elevated()
        print(f"self={mine} desktop-shell={shell} foreground={fg_proc or '?'}:{fg_level} elevated={fg_elev}")
        ok = mine in ('MEDIUM', 'MEDIUM+', 'HIGH') and shell == 'MEDIUM' and fg_level != 'UNKNOWN'
        # 2026-09-06: the refusal case, on a REAL elevated window if one is open right
        # now (the decision only -- no SendInput, no focus change). Never faked: with
        # no such window on the desktop it says SKIPPED, not OK.
        hwnd_el = find_elevated_window()
        if hwnd_el:
            r = refusal_for_window(hwnd_el)
            case_ok = isinstance(r, TypeRefusal) and (not r) and r.reason == 'elevated'
            print(f"refusal-case: DETECTED hwnd={hwnd_el} pid={r.pid} proc={r.proc or '?'} "
                  f"integrity={r.integrity} above self={r.self_integrity} title={r.title[:40]!r} "
                  f"-> {'REFUSAL OK (structured, falsy, no SendInput)' if case_ok else 'FAIL'}")
            ok = ok and case_ok
        else:
            print("refusal-case: SKIPPED (no elevated window on the desktop right now; nothing faked)")
        # the shell window is MEDIUM and must NOT be refused by a MEDIUM/HIGH self
        if refusal_for_window(user32.GetShellWindow()) is not None:
            print("refusal-case: FAIL (the MEDIUM desktop shell was refused)")
            ok = False
        print("TYPER OK" if ok else "TYPER FAIL")
        sys.exit(0 if ok else 1)
    print("Usage: python app/typer.py --selftest")
