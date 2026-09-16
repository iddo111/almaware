"""alma-mic / voice_commands.py — turn spoken words into slash-commands & keys.

ALMAWARE-pure: ours. Runs on the recognized text just before it is typed, so the
mic can DRIVE commands by voice, in Hebrew and English:

  "slash help"      -> "/help"      (say "slash"/"סלאש" -> a literal "/" glued on)
  "by the way ..."  -> "/btw ..."   (phrase map, configurable in config.json)
  "דרך אגב ..."     -> "/btw ..."
  "new line"        -> newline       "שורה חדשה" -> newline

Only the TYPED text is transformed; the on-screen transcript + the voice corpus
keep the natural words (so training data stays clean).
"""
from __future__ import annotations
import re

# spoken "slash" / Hebrew "סלאש" -> "/" with the following spaces eaten, so
# "slash help" becomes "/help" (not "/ help").
_SLASH = re.compile(r"(?<!\w)(?:slash|סלאש)(?!\w)\s*", re.IGNORECASE)


def apply(text: str, cfg) -> str:
    if not getattr(cfg, "enable_voice_commands", True):
        return text
    t = text or ""
    # phrase map first (longest phrases first so "by the way" wins over "way")
    mapping = getattr(cfg, "voice_commands", None) or {}
    for phrase, repl in sorted(mapping.items(), key=lambda kv: -len(kv[0])):
        if not phrase:
            continue
        t = re.sub(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", repl, t, flags=re.IGNORECASE)
    # then the spoken "slash" -> "/"
    t = _SLASH.sub("/", t)
    return t
