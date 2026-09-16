"""alma-mic / grok.py — ask Grok, straight from the mic.

ALMAWARE-pure APP code: every line ours. We only INVOKE the Grok CLI brain
(`grok.exe` from xAI) — a MODEL, the same model-not-app category as the Whisper
recogniser and as Eran (allowed under the purity law). No third-party app/library:
our own thin, honest wrapper over a single-turn headless call.

    ans, who = ask("מה השעה הכי טובה לרוץ?")   # who = "grok" | "—"

The headless invocation mirrors our own verified grok-web-router shim, which solved
two real grok.exe gotchas the hard way:
  • grok.exe keys its chat SESSION by the process working directory. Reusing a dir
    poisons/grows that session until grok.exe HANGS. → run each call from a FRESH
    temp cwd, and pass the prompt via --prompt-file (no TTY needed).
  • the bundled XAI_API_KEY belongs to a creditless team (403). → drop it from the
    env so grok.exe uses its own OIDC login (~/.grok/auth.json), which is free.

Graceful + honest: on any failure we return ("<reason>", "—") — never a silent fake,
never a different model pretending to be Grok. Re-login is one line:  grok
"""
from __future__ import annotations
import os
import shutil
import subprocess
import sys
import tempfile

# Locate grok.exe: env override -> known install -> PATH.
_GROK_BIN = (
    os.environ.get("GROK_BIN")
    or next((p for p in (
        os.path.expandvars(r"%USERPROFILE%\.grok\bin\grok.exe"),
        r"C:\Users\YOURUSER\.grok\bin\grok.exe",
    ) if os.path.exists(p)), "grok")
)
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
LABEL = "grok"


def available() -> bool:
    """True if the Grok binary is present (session liveness is proven only by asking)."""
    return _GROK_BIN == "grok" or os.path.exists(_GROK_BIN)


def ask(prompt: str, *, timeout: float = 90.0) -> tuple[str, str]:
    """Single-turn ask. Returns (answer_text, who). `who` is "grok" on success,
    "—" on any failure (with the reason as the answer text). Never raises."""
    prompt = (prompt or "").strip()
    if not prompt:
        return ("", "—")
    if not available():
        return ("גרוק לא מותקן (חסר grok.exe). הרץ `grok` בטרמינל פעם אחת.", "—")

    # fresh, unique working dir per call → grok.exe starts a clean session and
    # never hangs on a poisoned one (and we delete it + the prompt file after).
    call_cwd = tempfile.mkdtemp(prefix="alma_grok_")
    fd, fpath = tempfile.mkstemp(prefix="prompt_", suffix=".txt", dir=call_cwd)
    os.close(fd)
    try:
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(prompt)
        env = dict(os.environ)
        env["PYTHONUTF8"] = "1"
        env.pop("XAI_API_KEY", None)   # force grok.exe's own (credited) OIDC login
        cmd = [_GROK_BIN, "--no-memory", "--output-format", "plain", "--verbatim",
               "--prompt-file", fpath]
        cp = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, creationflags=_NO_WINDOW, env=env,
            stdin=subprocess.DEVNULL, cwd=call_cwd)
        out = (cp.stdout or "").strip()
        if cp.returncode == 0 and out:
            return (out, LABEL)
        if cp.returncode == 0:   # exit 0, no text → session expired
            return ("גרוק חזר ריק (אולי הסשן פג). הרץ `grok` בטרמינל פעם אחת.", "—")
        err = (cp.stderr or "").strip() or f"rc={cp.returncode}"
        return (f"גרוק לא ענה ({err[:200]}). אולי צריך להתחבר מחדש: הרץ `grok`.", "—")
    except subprocess.TimeoutExpired:
        return (f"גרוק לא ענה תוך {int(timeout)} שניות.", "—")
    except Exception as e:   # honest, never crash the GUI
        return (f"שגיאת גרוק: {e!r}", "—")
    finally:
        shutil.rmtree(call_cwd, ignore_errors=True)


_CLEANUP_INSTRUCTION = (
    "אתה עורך תמלול. לפניך טקסט עברי שהוכתב בקול ותומלל אוטומטית, ולכן עלול להכיל "
    "שגיאות הומופונים (למשל 'לא' מול 'ל\"ו' מול 'ל\"א'), גבולות-מילים שגויים, מילה אחת "
    "שפוצלה לשתיים או להפך, וחוסר פיסוק. תקן את הטקסט לעברית תקנית וברורה. "
    "שמור בדיוק על המשמעות והמילים שנאמרו — אל תוסיף תוכן, אל תמציא, אל תקצר. "
    "החזר אך ורק את הטקסט המתוקן, בלי שום הסבר ובלי מרכאות עוטפות.\n\n---\n"
)


def cleanup(text: str, *, timeout: float = 120.0) -> tuple[str, str]:
    """Grok-heavy pass over a raw Hebrew transcript: fixes homophones, word
    boundaries and punctuation while preserving meaning. Returns (clean, who)."""
    text = (text or "").strip()
    if not text:
        return ("", "—")
    return ask(_CLEANUP_INSTRUCTION + text, timeout=timeout)
