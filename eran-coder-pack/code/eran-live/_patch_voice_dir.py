"""One-shot patch: make data.py honor ERAN_VOICE_DIR env var (DGX/Linux move).
Voice-only guard logic is left UNTOUCHED. Default stays the Windows path so the
PC copy is unaffected if this ever runs there. Idempotent."""
import io, os, sys

p = "/home/iddo1/eran/eran-live/data.py"
s = io.open(p, encoding="utf-8").read()

old = '# --- hard allow-list of voice sources. Nothing else is ever read. ---\nVOICE_DIR = r"D:\\CLAUDE\\voice-input"'
new = (
    '# --- hard allow-list of voice sources. Nothing else is ever read. ---\n'
    '# VOICE_DIR may be overridden via the ERAN_VOICE_DIR env var (for the DGX/Linux\n'
    '# move). The voice-only guard below is UNCHANGED: only Iddo\'s voice sources are\n'
    '# ever read, never a book corpus.\n'
    'VOICE_DIR = os.environ.get("ERAN_VOICE_DIR", r"D:\\CLAUDE\\voice-input")'
)

if 'ERAN_VOICE_DIR' in s:
    print("already patched")
    sys.exit(0)

if old not in s:
    print("ANCHOR NOT FOUND", file=sys.stderr)
    sys.exit(3)

s = s.replace(old, new)
io.open(p, "w", encoding="utf-8").write(s)
print("patched OK")
