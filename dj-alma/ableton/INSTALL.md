> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# DJ_ALMIDO for Ableton Live — installation / התקנה

**עברית:** זהו החלק של DJ ALMIDO שמיקסקראפט לא יכול היה לעשות — יצירת טראק MIDI
וכתיבת תווים לתוכו. אבלטון כן יכול, דרך Remote Script קטן שרץ *בתוך* אבלטון
ופותח שקע (socket) מקומי. שלב ההתקנה **היחיד שדורש את עידו** מתואר למטה.

**English:** this is the half of DJ ALMIDO that Mixcraft could never do —
creating a MIDI track and writing notes into it. Ableton can, through a small
Remote Script that runs *inside* Live and opens a local socket. The **one
installation step that needs Iddo** is described below.

---

## What exists already / מה כבר קיים

- `DJ_ALMIDO/` — the Ableton Live 12 Remote Script package (this folder's
  sibling). Not yet installed into Ableton's Remote Scripts folder.
- `send.py` — a stdlib socket client any Python script can use to talk to
  DJ_ALMIDO once it's running.
- `voice_to_live.py` — the same 18-command Hebrew voice grammar
  (`bridge/grammar.py`, unmodified) wired to `send.py` instead of the
  Mixcraft MIDI path.
- `compose_and_send.py` — asks the Darwish model for a section (via
  `booth/compose.py`, unmodified) and writes it into an Ableton MIDI clip.
- `tests/` — 34 tests, all passing, with NO Ableton running (fake Live
  objects + a real loopback socket). See the test-run report in the status
  message this file's sibling `README` (if any) or the RAMCHAT log entry
  posted 2026-09-08.

## Step 1 — copy the Remote Script (already done automatically / כבר בוצע)

```
D:\CLAUDE\dj-alma\ableton\DJ_ALMIDO\
    -> copied to ->
C:\Users\<user>\Documents\Ableton\User Library\Remote Scripts\DJ_ALMIDO\
```

This is Iddo's own **User Library** folder (not Ableton's own install tree
under `C:\ProgramData\Ableton\...\Resources\MIDI Remote Scripts\`, which was
correctly left untouched) — a normal, safe place for a user-authored Remote
Script, and Ableton itself scans it. If this copy is ever missing or stale
(e.g. after editing `DJ_ALMIDO/` here), re-copy the whole folder — do not
edit the copy in `Documents\...` directly, it will drift from this repo.

## Step 2 — THE ONE STEP THAT IS IDDO'S / השלב היחיד שהוא של עידו

A Remote Script only loads once it is **selected** in Live's own
Preferences, and only takes effect after Live is **restarted or the control
surfaces are re-scanned** — no file copy alone makes Live pick it up.

**עברית:**
1. פתח את Ableton Live (הגרסה המותקנת: **Live 12.4.5 Trial**).
2. לך ל־Preferences (Options → Preferences, או Ctrl+,).
3. בלשונית **Link, Tempo & MIDI**.
4. תחת **Control Surface**, בחר שורה ריקה ובחר **DJ_ALMIDO** מהרשימה הנפתחת.
5. אם DJ_ALMIDO לא מופיע ברשימה — סגור את Live ופתח מחדש (זה מה שגורם לו
   לסרוק מחדש את תיקיית ה-Remote Scripts).
6. אחרי הבחירה, אמור להופיע הודעה בשורת הסטטוס של Live: "DJ_ALMIDO: listening
   on 127.0.0.1:8865" — זה הסימן שהשרת קם בהצלחה.

**English:**
1. Open Ableton Live (installed version: **Live 12.4.5 Trial**).
2. Go to Preferences (Options → Preferences, or Ctrl+,).
3. Open the **Link, Tempo & MIDI** tab.
4. Under **Control Surface**, pick an empty slot and select **DJ_ALMIDO**
   from the dropdown.
5. If DJ_ALMIDO does not appear in the list, close and reopen Live — that is
   what makes it re-scan the Remote Scripts folder.
6. Once selected, Live's own status bar should show: "DJ_ALMIDO: listening
   on 127.0.0.1:8865" — that confirms the socket server started.

This document does **not** launch Ableton for you (Sacred Audio Law — Live
would claim the audio devices the moment it opens, and that decision is
Iddo's alone to make, at a moment of his choosing, not a script's).

## Step 3 — smoke test (after Step 2 is done)

```
cd D:\CLAUDE\dj-alma\ableton
python send.py PING
```
Expect: `{"ok": true, "cmd": "PING", "result": {"pong": true, "n_tracks": N, "n_scenes": M}}`.

Then try the voice path with typed text (no microphone involved):
```
python voice_to_live.py --mode stdin
```
and type a line like `נגן` (play) or `תן דרופ` (drop) — each becomes one
`send.py`-equivalent call into Ableton.

## Known placeholders that need Iddo's real project layout

Exactly like the Mixcraft bridge before it, `bridge/protocol.py`'s
`STEM_TRACK_INDEX` (BASS/LEAD/DRUMS/FX → track index 0/1/2/3) and
`SECTION_COLUMN` (INTRO/BUILD/DROP/BREAK/OUTRO → scene index 0-4) are
**placeholders**, because no real Ableton Live Set with Iddo's actual track
order / Session View layout exists yet on this machine. Edit
`bridge/protocol.py` once such a project exists — both DJ_ALMIDO and the
Mixcraft controller script read the SAME file, so it only needs editing
once.

## What this version does NOT need — loopMIDI

**loopMIDI (or any virtual MIDI port) is NOT needed for this v1.** The
Mixcraft bridge needed one because Mixcraft's JS Controller Script API can
only receive MIDI messages. DJ_ALMIDO instead runs *inside* Ableton's own
process and writes notes straight through the Live Object Model
(`clip.add_new_notes(...)`), so no MIDI cable or virtual port is ever in the
path for writing a clip. loopMIDI only becomes relevant later, if Iddo wants
the composer to STREAM notes live in real time (e.g. playing a synth part as
it's generated) rather than writing finished clips — that is a different,
not-yet-built feature.
