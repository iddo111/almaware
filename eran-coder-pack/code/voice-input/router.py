"""router.py - voice-controlled dictation TARGET routing for the Hebrew mic.

Two jobs:
1) Parse wake-phrases + mode commands out of a transcript.
2) Resolve logical targets to real windows and focus them.

"""
from __future__ import annotations

import ctypes
import logging
import re
from ctypes import wintypes

logger = logging.getLogger("voiceinput.router")

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# ── target definitions ───────────────────────────────────────────────────────
DEFAULT_TARGETS = {
    "claude": {
        "titles": ["claude", "claude code", "windows powershell", "powershell",
                   "cmd", "windows terminal"],
        "procs": ["windowsterminal.exe", "powershell.exe", "pwsh.exe",
                  "cmd.exe", "claude.exe", "conhost.exe"],
        "aliases": ["קלוד", "claude", "קולד", "כלוד", "קלוו"],
    },
    "grok": {
        "titles": ["grok", "x.ai", "xai"],
        "procs": ["chrome.exe", "msedge.exe", "firefox.exe"],
        "aliases": ["גרוק", "grok", "גרק", "גראק"],
    },
    "eran": {
        "titles": ["eran", "ערן", "eran console"],
        "procs": ["python.exe", "eran.exe"],
        "aliases": ["ערן", "eran", "עירן"],
    },
    "whatsapp": {
        "titles": ["whatsapp", "וואטסאפ"],
        "procs": ["whatsapp.exe"],
        "aliases": ["וואטסאפ", "ווצאפ", "whatsapp", "ואטסאפ", "וטסאפ"],
    },
    "notepad": {
        "titles": ["notepad", "פנקס רשימות", "- notepad"],
        "procs": ["notepad.exe", "notepad++.exe"],
        "aliases": ["נוטפד", "notepad", "פנקס", "פנקס רשימות"],
    },
}

# ── wake-word variants ────────────────────────────────────────────────────────
_WAKE = ["שירי", "שירה", "שיר י", "שירית", "שירל", "siri", "shiri", "שרי"]

# ── arm / disarm ─────────────────────────────────────────────────────────────
DISARM_PHRASES = [
    "claude end", "קלוד סוף", "קולד סוף",
    "grok end",   "גרוק סוף", "גרק סוף",
    "microphone end", "shiri end",
    "שירי סוף", "שירה סוף",
    "מיקרופון סוף", "מיקרפון סוף",
]
ARM_PHRASES = ["microphone", "מיקרופון", "מיקרפון"]

_DISARM_TARGET = {
    "claude end": "claude", "קלוד סוף": "claude", "קולד סוף": "claude",
    "grok end": "grok",     "גרוק סוף": "grok",   "גרק סוף": "grok",
}

# ── prompt mode ───────────────────────────────────────────────────────────────
# "שירי פרומפט" / "claude prompt" / "grok prompt" → start accumulating
# "פרומפט סוף" / "prompt end" → flush + send
PROMPT_START_PHRASES = [
    "שירי פרומפט", "שירי פרמפט", "שירי פרמוט",
    "claude prompt", "קלוד פרומפט",
    "grok prompt",   "גרוק פרומפט",
    "prompt mode", "מצב פרומפט",
]
PROMPT_END_PHRASES = [
    "פרומפט סוף", "prompt end",
    "שלח פרומפט", "send prompt",
    "שירי שלח פרומפט",
]

# ── feature mode commands ────────────────────────────────────────────────────
# Each maps to a __cmd__ token returned from parse_command
_MODE_COMMANDS: list[tuple[str, list[str]]] = [
    # (command_token,  trigger_phrases)
    ("__fast_start__", ["שירי מהיר", "fast mode", "מצב מהיר"]),
    ("__fast_send__",  ["שירי שלח", "send now", "שלח עכשיו"]),
    ("__clipboard__",  ["שירי קליפבורד", "clipboard mode", "למטמון", "copy mode"]),
    ("__silent__",     ["שירי שקט", "silent mode", "מצב שקט"]),
    ("__undo__",       ["שירי בטל", "undo last", "בטל אחרון"]),
    ("__history__",    ["שירי היסטוריה", "show history", "היסטוריה"]),
]

# ── language switching: "<Claude/שירי> <language>" → set the STT language ─────
LANG_WAKE = ["שירי", "קלוד", "claude", "siri", "shiri", "קולד", "כלוד", "קלואד"]
LANG_ALIASES = {
    "en":   ["english", "אנגלית", "אינגליש", "inglish", "אנגלי"],
    "he":   ["hebrew", "עברית", "היברו", "ivrit", "עברי"],
    "fr":   ["french", "francais", "français", "צרפתית", "פרנסס", "פרנץ", "צרפתי"],
    "ru":   ["russian", "русский", "רוסית", "רסיה", "רוסי", "רוסיה"],
    "ar":   ["arabic", "عربي", "ערבית", "ערבי", "עארבי", "ערבישׁ"],
    "de":   ["german", "deutsch", "גרמנית", "גרמני"],
    "es":   ["spanish", "espanol", "español", "ספרדית", "ספרדי"],
    "it":   ["italian", "italiano", "איטלקית"],
    "zh":   ["chinese", "mandarin", "סינית", "מנדרינית", "סיני"],
    "ja":   ["japanese", "יפנית", "יפני"],
    "pt":   ["portuguese", "פורטוגזית", "פורטוגלית"],
    "auto": ["auto", "אוטומטי", "אוטו", "כל השפות", "multi", "automatic", "אוטומט"],
}

# walkie-talkie end-of-message marker: stripped + sent immediately
OVER_MARKERS = ["over", "עבור", "אובר", "אוֹבר", "אובער"]

# ── helpers ───────────────────────────────────────────────────────────────────
def _norm(s: str) -> str:
    s = re.sub(r"[֑-ׇ]", "", s or "")
    return re.sub(r"\s+", " ", s).strip(" .,!?־-")

def apply_text_shortcuts(text: str) -> str:
    """Spoken text shortcuts. 'by the way' / 'דרך אגב' at the START of a sentence
    becomes '/btw ' (the slash + btw the user asked for)."""
    return re.sub(r"^\s*(?:by the way|ביי דה וויי|דרך אגב|בידה ווי)\b[,\s]*",
                  "/btw ", text or "", flags=re.IGNORECASE).strip()

def strip_over(text: str):
    """If the utterance ends with an 'over'/'עבור' marker, strip it and signal an
    immediate send (walkie-talkie style). Returns (clean_text, is_over)."""
    t = (text or "").rstrip(" .,!?־-")
    low = _norm(t).lower()
    for m in OVER_MARKERS:
        mm = _norm(m).lower()
        if low == mm or low.endswith(" " + mm):
            cut = len(t)
            # remove the trailing marker word from the ORIGINAL text
            idx = t.lower().rfind(m.lower())
            if idx >= 0:
                cut = idx
            return t[:cut].rstrip(" .,!?־-"), True
    return text, False

def _contains(haystack: str, needle: str) -> bool:
    return _norm(needle).lower() in haystack

# ── main parse ────────────────────────────────────────────────────────────────
def parse_command(text: str, targets: dict | None = None):
    """Parse a voice utterance for all commands.

    Returns (command, extra) where command is one of:
      target name            → switch + focus window
      "__no_target__"        → wake heard, no known target
      "__disarm__"           → pause mic output; extra = cleared target or ""
      "__arm__"              → resume output
      "__prompt_start__"     → enter prompt accumulation mode
      "__prompt_end__"       → flush prompt buffer to window
      "__translate__"        → toggle translation mode
      "__fast_start__"       → enter fast-accumulate mode
      "__fast_send__"        → send fast buffer now
      "__clipboard__"        → next utterance → clipboard only
      "__silent__"           → toggle silent (no indicator prints)
      "__undo__"             → send Ctrl+Z to current window
      "__history__"          → open today's history file
      None                   → normal dictation; extra == original text
    """
    targets = targets or DEFAULT_TARGETS
    t = _norm(text)
    low = t.lower()

    # ── 1. Disarm (before wake-word so "שירי סוף" disarms) ──────────────────
    for phrase in DISARM_PHRASES:
        if _contains(low, phrase):
            return "__disarm__", _DISARM_TARGET.get(phrase, "")

    # ── 2. Prompt end ────────────────────────────────────────────────────────
    for phrase in PROMPT_END_PHRASES:
        if _contains(low, phrase):
            return "__prompt_end__", ""

    # ── 3. Stand-alone arm ───────────────────────────────────────────────────
    for phrase in ARM_PHRASES:
        if low.strip() == _norm(phrase).lower():
            return "__arm__", ""

    # ── 3a. Translation: AUTO-VOICE-TRIGGER DISABLED (Iddo 2026-06-19) ────────
    # The old substring match flipped the mic into translate mode whenever the
    # word "translate"/"תרגם" appeared in normal speech (even just TALKING ABOUT
    # translation) — so the mic translated instead of transcribing, and got stuck.
    # Translation is now controlled ONLY by the deliberate UI toggle (🌐 Translate
    # ON/OFF). To restore voice control, un-comment the block below.
    # if any(_norm(w).lower() in low for w in ("תרגם", "translate", "תרגום")):
    #     if any(_norm(w).lower() in low for w in
    #            ("כבוי", "off", "בלי", "cancel", "ביטול", "stop", "כבה")):
    #         return "__translate_off__", ""
    #     for code, names in LANG_ALIASES.items():
    #         if code != "auto" and any(_norm(nm).lower() in low for nm in names):
    #             return "__translate_to__", code
    #     return "__translate_to__", "en"

    # ── 3b. Language switch: "<Claude/שירי> <language>" → ("__lang__", code) ──
    words = low.split()
    if words and any(_norm(w).lower() in words[0] for w in LANG_WAKE) and len(words) <= 4:
        for code, names in LANG_ALIASES.items():
            if any(_norm(nm).lower() in low for nm in names):
                return "__lang__", code

    # ── 4. Feature mode commands (need wake word OR exact phrase) ────────────
    has_wake = any(w in " ".join(low.split()[:3]) for w in _WAKE)
    for cmd_token, phrases in _MODE_COMMANDS:
        for phrase in phrases:
            p = _norm(phrase).lower()
            if p in low:
                return cmd_token, ""

    # ── 5. Prompt start ──────────────────────────────────────────────────────
    for phrase in PROMPT_START_PHRASES:
        if _contains(low, phrase):
            return "__prompt_start__", ""

    # ── 6. Must have wake-word for routing ───────────────────────────────────
    if not has_wake:
        return None, text

    # wake word alone (≤2 tokens) → arm
    if len(low.split()) <= 2:
        return "__arm__", ""

    # "שירי כאן" / "שירי here" / "focused" → type into the window in use right now
    if any(a in low for a in ("כאן", " here", "focused", "פוקוס", "במסך")):
        return "focused", ""

    # ── 7. Target routing ────────────────────────────────────────────────────
    chosen = None
    pos = -1
    for name, spec in targets.items():
        for alias in spec.get("aliases", []):
            a = _norm(alias).lower()
            m = re.search(r"(?:^|\s|[בלומה])" + re.escape(a) + r"(?:\W|$)", low)
            if m and m.start() > pos:
                chosen, pos = name, m.start()

    if not chosen:
        logger.info("wake heard but no known target in: %r", t)
        return "__no_target__", ""

    return chosen, ""

def is_route_only(text: str, targets: dict | None = None) -> bool:
    tgt, _ = parse_command(text, targets)
    return tgt is not None

# ── window discovery + focus ──────────────────────────────────────────────────
def _proc_name(pid: int) -> str:
    PROCESS_QUERY_LIMITED = 0x1000
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED, False, pid)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(512)
        size = wintypes.DWORD(512)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value.split("\\")[-1].lower()
    finally:
        kernel32.CloseHandle(h)
    return ""

def _enum_windows():
    out = []
    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        out.append((hwnd, buf.value, _proc_name(pid.value)))
        return True

    user32.EnumWindows(EnumWindowsProc(cb), 0)
    return out

def find_window(target: str, targets: dict | None = None):
    targets = targets or DEFAULT_TARGETS
    spec = targets.get(target)
    if not spec:
        return None
    wins = _enum_windows()
    title_subs = [s.lower() for s in spec.get("titles", [])]
    procs = [p.lower() for p in spec.get("procs", [])]
    for hwnd, title, proc in wins:
        if any(s in title.lower() for s in title_subs):
            return hwnd, title
    for hwnd, title, proc in wins:
        if proc in procs:
            return hwnd, title
    return None

def focus_window(hwnd) -> bool:
    # No-hijack contract (2026-06-15, Iddo's explicit rule): NEVER raise a window
    # the user didn't DELIBERATELY target.
    #   • Default target is "focused" → the resolved hwnd already IS the
    #     foreground window, so we take the fast-path below and do NOTHING. This
    #     keeps the LKG "WORKING" dictation behaviour byte-for-byte: it cannot
    #     steal focus, because there is nothing to raise.
    #   • Only when the user EXPLICITLY picks a different window (e.g. "שירי גרוק"
    #     or the UI window-picker) is hwnd != foreground — and then bringing that
    #     window forward is exactly what they asked for, not a hijack.
    # auto_focus_target is null in config, so this is never invoked on startup.
    try:
        if not hwnd or user32.GetForegroundWindow() == hwnd:
            return True
        SW_RESTORE = 9
        user32.ShowWindow(hwnd, SW_RESTORE)
        fg = user32.GetForegroundWindow()
        cur_tid = kernel32.GetCurrentThreadId()
        tgt_tid = user32.GetWindowThreadProcessId(hwnd, None)
        fg_tid = user32.GetWindowThreadProcessId(fg, None)
        user32.AttachThreadInput(cur_tid, fg_tid, True)
        user32.AttachThreadInput(cur_tid, tgt_tid, True)
        user32.BringWindowToTop(hwnd)
        ok = bool(user32.SetForegroundWindow(hwnd))
        user32.AttachThreadInput(cur_tid, fg_tid, False)
        user32.AttachThreadInput(cur_tid, tgt_tid, False)
        return ok
    except Exception as e:  # noqa: BLE001
        logger.warning("focus_window failed: %s", e)
        return False

def focus_target(target: str, targets: dict | None = None):
    found = find_window(target, targets)
    if not found:
        return False, f"no window for target {target!r}"
    hwnd, title = found
    ok = focus_window(hwnd)
    return ok, title

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    tests = [
        "שירי עכשיו הקלדה בקלוד",
        "שירי פרומפט",
        "פרומפט סוף",
        "שירי תרגם",
        "שירי מהיר",
        "שירי שלח",
        "שירי בטל",
        "שירי קליפבורד",
        "שירי שקט",
        "קלוד סוף",
        "מיקרופון",
        "שלום עידו מה שלומך",
    ]
    for t in tests:
        cmd, extra = parse_command(t)
        print(f"{t!r:45} -> {cmd!r}  extra={extra!r}")
