# -*- coding: utf-8 -*-
"""The LIVE section's own note claimed "33 עובדים על הצי" -- there are 6.
A page that states a worker count is a page that goes stale; state the rule
instead, and say what the numbers mean so the reader can judge for himself."""
import io
import os
import re

p = os.path.expanduser("~/eran-brain/listen_server.py")
s = io.open(p, encoding="utf-8").read()
m = re.search(r"LIVE_NOTE = \((?:[^()]|\([^()]*\))*\)\n", s)
if m is None:
    raise SystemExit("REFUSING: LIVE_NOTE block not found")
if "refresh_live.py" in m.group(0):
    print("[skip] already replaced")
    raise SystemExit(0)
new = (
    'LIVE_NOTE = ("<h2>&#128293; LIVE &mdash; הפה שלו, '
    'עכשיו</h2>"\n'
    "             \"<div class='note'>כל קליפ = "
    "הניסיון הכי "
    "טוב של עובד "
    "חיפוש אחד, "
    "דרך הצינור של "
    "עצמו &middot; each clip = one search worker's best so "
    'far, through his own tube. Refreshed every 10 min by refresh_live.py.'
    "<br><b>wdist</b> &#8212; נמוך = קרוב "
    "יותר להקלטות "
    "האמיתיות (lower is closer). "
    "<b>vs ma</b> &#8212; המרווח מ-"
    "מָה, חייב "
    "להיות חיובי (must be "
    "positive). <b>closure</b> &#8212; סגירת "
    "השפתיים; עידו "
    "האמיתי = 0.192. "
    "<b>CONTROL</b> &#8212; לא למד "
    "כלום, זו הרצפה "
    "(the floor).</div>\")\n"
)
s = s[:m.start()] + new + s[m.end():]
io.open(p, "w", encoding="utf-8").write(s)
print("[ok] LIVE_NOTE replaced (it claimed 33 workers on the fleet; there are 6)")
