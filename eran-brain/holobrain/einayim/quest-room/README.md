> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# ⚠️ אין כאן חדר. / THERE IS NO ROOM HERE.

**נבדק 2026-09-05. כל הקבצים בתיקייה הזאת הם בדיקת לולאה של השרת — לא סריקה של הקווסט.**
**Checked 2026-09-05. Every file in this folder is a server loopback test — not a Quest scan.**

## הראיה / The evidence

שני קבצי ה-JSON אומרים את זה בעצמם, בשדה `capturedAt`:
*Both JSON files say so themselves, in their own `capturedAt` field:*

| file | `capturedAt` | `mode` | what the "mesh" actually is |
|---|---|---|---|
| `room-20260903-193612.json` | **`synthetic-test`** | *(absent)* | a unit cube labelled `wall` + a small box labelled `table` |
| `room-20260903-194423.json` | **`http-endpoint-test`** | `mesh-detection` | the same two boxes |

Both `.obj` files are **72 vertices / 24 triangles** — two axis-aligned boxes with
coordinates like `-0.5 -0.5 -0.5` and `0.8 -0.2 -0.2`. A Quest 3 room scan is
thousands of triangles at real room scale. These are the shapes someone types by
hand to check that a `POST` handler writes a file.

The `-stl/` subfolders (`wall.stl`, `table.stl`) are those same two boxes.

## למה זה חשוב / Why this matters

`QUEST-MESH-HOWTO.md` describes a real, working delivery rig — HTTPS server, a
signed CA, a cloudflared tunnel, token-gated writes — and it says, correctly,
that those parts were verified. **What it does not say, and what this file is
here to say, is that the headset has never been on the other end of it.**
`quest-drop`'s own `visits.log` and `access-https.log` contain no `OculusBrowser`
user-agent: every recorded hit is `curl`, desktop Chrome from the PC itself
(<lan-ip>), or a literally fake `TestUA/curl-simulated-quest`.

So a file named `room-<timestamp>.obj` sitting in a folder named `quest-room` is
exactly the kind of thing this workspace has been burned by before — a plausible
artefact that a later pipeline picks up and treats as ground truth. It would have
been a *measured* room. It is two boxes.

## מה צריך לקרות כדי שיהיה כאן חדר אמיתי / What has to happen for a real room

עידו לבד יכול לעשות את זה — צריך את הקסדה על הראש:
*Only Iddo can do this; it needs the headset on his head:*

1. בקווסט: **Settings → Physical Space → Space Setup** — סריקה מלאה של החדר, לא רק Guardian.
2. לפתוח את `quest-mesh.html` דרך הקיצור בשולחן העבודה (או המנהרה).
3. לאשר את בקשת ההרשאה למרחב, ולהסתכל לאט על כל החדר.
4. "💾 שמור את החדר".

**איך תדעו שזה אמיתי / How to know it is real** — three checks, and all three must pass:
- the new file's `capturedAt` is an **ISO timestamp**, not `synthetic-test` /
  `http-endpoint-test`;
- `quest-drop/visits.log` contains an **`OculusBrowser`** user-agent at that time;
- the `.obj` has **thousands** of vertices, not 72.

Until then, nothing in this folder may be used as input to anything — not to
EINAYIM, not to KAV, not to TZELEM.
