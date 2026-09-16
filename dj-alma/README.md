# DJ-ALMA — Mixcraft bridge / הגשר למיקסקראפט

> 🪟 **BROKEN WINDOWS LAW:** if something here stops working, fix it immediately — don't wait to be told.

## שלוש שורות פתיחה / three-line summary

- **Mixcraft is NOT installed on this machine.** Checked Program Files, Program Files (x86), ProgramData, the registry (HKLM + HKCU, both 32/64-bit uninstall keys), Start Menu shortcuts, AppData, and file associations for `.mx10`/`.mx9`/`.mxc` — all empty. **מיקסקראפט לא מותקן על המחשב הזה.**
- **No virtual MIDI port exists either** — `mido.get_output_names()` returns only `['Microsoft GS Wavetable Synth 0']` (Windows' built-in synth), zero MIDI inputs. **אין פורט MIDI וירטואלי (כמו loopMIDI) מותקן.**
- **What is real and tested right now, with zero installs:** the Hebrew voice-command grammar (`bridge/grammar.py`), the wire protocol (`bridge/protocol.py`), the MIDI-sending code (`bridge/midi_out.py`, dry-run verified), the focused-window KESHEV listener (`bridge/listener_console.py`, a real Tk event verified), and the Mixcraft-side script (`controller/ALMA/dj_alma_control.js`, written against the full official API docs, command table cross-checked by `smoke_test.py` against the Python side — but **never loaded by an actual running Mixcraft**, because there isn't one here). Run `smoke_test.py` — every check that can run without Mixcraft passes.

---

## 0. THE BOOTH — `booth/`, added 2026-09-05. This one MAKES A SOUND today.

Everything above is the **DAW arm**, and it is finished, tested and **mute**: it
speaks MIDI to a Mixcraft controller script, and Mixcraft and loopMIDI are both
still uninstalled. Two installs stand between it and its first sound, and that
is Iddo's call, not ours.

`booth/` is the **other arm**. Same 18-command Hebrew grammar — `booth/almido.py`
does `import grammar` from `bridge/`, it does not re-implement it — routed to the
one path that can produce audio on this machine right now:

```
Hebrew command  ->  the Darwish model composes  ->  psy_render_v4 masters it
                ->  an .mp3 on a page Iddo presses PLAY on
```

**Live at `http://127.0.0.1:8863/`** (port claimed in RAMCHAT), plus a
`DJ-ALMIDO` shortcut on the Desktop. Start it with:

```
cd D:\CLAUDE\dj-almaooth && python almido.py
```

| file | what it is |
|---|---|
| `booth/almido.py` | the stdlib HTTP server, the bilingual page, the piano roll, the take log |
| `booth/compose.py` | model tokens -> a Score -> a .mid, plus the chord list the renderer needs |
| `booth/takes/` | every take: `.mid`, `.wav`, `.mp3` and a `.json` of its measured numbers |

**Wired:** the five `SECTION_*` commands (they choose which passage of the
model's output becomes the take, by measuring its density and polyphony),
`EXTEND_SECTION` (8/16/32 bars), `SET_TEMPO` and both tempo nudges.
**Not wired, and the page says so on its face:** the five volume/mute commands
and PLAY/STOP/RECORD — those address a DAW mixer and a transport, and there is
no DAW.

**Audio law.** The booth never opens an output device and never opens a
microphone. It writes files. The page's `<audio>` element has no `autoplay` and
no script ever calls `.play()` — Iddo presses it or nothing is heard.

**One dependency changed outside this tree.** `psy_render_v4.py` gained a single
default-off keyword, `chord_notes=`, plus a pad voice. It was necessary because
v4 ingests notes with `while probe in occ: probe += 1` — one note per sixteenth,
collisions bumped forward — so a chord came out as an arpeggio and the new
polyphonic tokenizer would have been inaudible through it. With `chord_notes`
unset the render is **byte-identical** to the pre-patch version (verified by
SHA-256 against `psy_render_v4.py.bak-prepad-20260905`).

## 1. What the Mixcraft 10 Controller Script API can and cannot do

Read in full from the primary source (not the marketing page): the actual doc
files at `github.com/acousticainc/controller-script-api-docs` — `docs/API
Sections/{Globals,MIDI,MM,Mixcraft,Track,Perform,functions-called-by-mixcraft}.md`
and `docs/Example Script/example-script.md` (a real Novation Launch Control XL
script). Pulled and read in full 2026-09-04, not summarized from the landing
page.

### Prerequisite
Explicitly stated: **"A copy of Mixcraft 10"**. This is a Mixcraft-10-only
API. Older Mixcraft versions do not have it (undocumented whether 9 has a
subset — the docs never say, so treat it as absent until proven otherwise).

### CAN do
| Area | Functions | Notes |
|---|---|---|
| **Transport** | `Mixcraft.Play()`, `TogglePlay()`, `Record()`, `Undo()`, `Redo()`, `Save()` | No dedicated `Stop()` — see gap below |
| **Tempo/time** | `GetTempo()`/`SetTempo()`, `GetTime()`/`SetTime()`, time signature get/set, `ConvertMeasureToTime()`/`ConvertTimeToMeasure()` | Full read+write |
| **Loop points** | `GetLoopStart/End/Length()`, `SetLoopStart/End/Length()`, `IsLoopOn()` | see gap below — no documented loop-enable setter |
| **Markers** | `AddMarker()`, `GetMarkerName()`, `SeekToMarker()`, `NumMarkers()` | |
| **Track mixer state** | volume, pan, mute, solo, arm, gain, drive, compressor, EQ (low/mid/high), send levels, color, name — full get+set | by track index; `bAbsoluteFlag` controls relative-to-bank vs absolute indexing |
| **Plugin params** | `GetPluginName/NumPluginParams/GetPluginParamName/GetPluginParamValue/SetPluginParamValue` | params are normalized 0.0–1.0 |
| **Project read** | `NumTracks()`, `GetTrackType()`, `NumTracksOfType()`, track IDs/names/colors | basic structural info only |
| **Clip/scene launch (Performance panel)** | `Perform.TriggerSlot(row,col,down)`, `TriggerSet(col)` (launch a whole column/scene), `StopSlot`, `StopRow`, `StopAll`, `ArmRow`, `DeleteClip`, `GetSlotState`, quantized launch via `SetGlobalQueueMode` (bar/beat-synced, like Ableton's session view) | **This is the mechanism for "דרופ"/"drop" style commands** — pre-built clips in a grid, triggered live |
| **Bidirectional feedback** | `Notify(notificationType, data1, data2)` fires when Mixcraft's own UI changes something (fader moved, track muted, etc.) | for LED/motorized-fader feedback on real hardware; we don't have hardware, logged only |
| **MIDI in/out** | `OnMIDI()` receives from the bound input device; `SendMIDI()`/`SendSysEx()` send to the bound output device | **only to/from the ONE device pair chosen in Preferences > Control Surfaces**, not arbitrary ports |

### CANNOT do (confirmed absent, not a guess — grepped the full doc set for `AddTrack`/`CreateTrack`/`AddNote`/`InsertNote`/etc., zero hits)
- **No track creation or deletion.** No `AddTrack`/`CreateTrack`/`InsertTrack`/`DeleteTrack` anywhere in the API. A script can only manipulate tracks that already exist in the project.
- **No writing MIDI notes into a track's piano roll / clip.** `SendMIDI()` sends to the bound hardware **output** device (for LED feedback etc.), not into a Mixcraft track. There is no `Track.AddNote()` or clip-content API of any kind. **This is the single biggest constraint and it decides the architecture** (see §2) — ALMA's composed notes cannot reach Mixcraft through this API at all.
- **`Perform.DeleteClip()` exists but there is no matching create/populate-clip function.** You can only trigger and delete pre-existing clips, never author one from script.
- **No documented `SetLoopOn()`/loop-enable setter.** `IsLoopOn()` (getter) exists; nothing sets it. `ShowLoop(bool)` only toggles the GUI loop-region indicator, not playback looping itself — untested whether it has a side effect on actual loop-enable; treat as unconfirmed.
- **No explicit `Stop()`.** Only `TogglePlay()` — a script must check `IsPlaying()` first and toggle conditionally (implemented this way in `dj_alma_control.js`).

### Undocumented / internally inconsistent (flagged honestly, not resolved by guessing)
- **MIDI channel numbering is inconsistent between two of the API's own pages.** `OnMIDI(messageType, midiChannel, ...)`'s `midiChannel` is documented as `0x0`–`0xF` (0-based). `MIDI.SendMIDI(type, chan, data1, data2)`'s `chan` is documented as `1`–`16` (1-based). Both name the same physical channel differently. `dj_alma_control.js` uses the 0-based `OnMIDI` convention throughout and says so in a comment.
- **The scripting language is a restricted ES5-ish subset.** Documented keyword list: `var if else do while for break continue null undefined function return true false new typeof`. **No `switch`/`case`, no `try`/`catch`, no `let`/`const`, no classes, no arrow functions are listed as available.** `dj_alma_control.js` avoids all of them on purpose (if/else chains, plain `var`, no exception handling) rather than risk a script that fails to compile.
- **Install location, confirmed from docs, not guessed:** `%programdata%\Acoustica\Mixcraft\controllers\scripts\<manufacturer>\*.js`.
- **One script = one bound MIDI input + one bound MIDI output device**, chosen in Preferences > Control Surfaces > Add New. Not a multi-port API.

---

## 2. Architecture decision

**v1 = a hybrid, not a pure pick of (a) or (b) — because the two solve different halves of the problem, and the API map above shows why one alone can't do the whole job:**

1. **Note delivery (ALMA's composed music → Mixcraft, sounding)**: this is **candidate (b), plain virtual MIDI**, and it is not optional — the Controller Script API **cannot write notes into a track under any circumstance** (§1, "CANNOT do"). The only way notes reach a Mixcraft track is Mixcraft's own ordinary per-track MIDI input routing: create a MIDI track, arm it, set its input to a virtual MIDI port, put a VST instrument on it, and whatever plays into that port gets recorded/monitored like any other MIDI keyboard. This needs **no script, no Mixcraft 10 requirement** — it works on any Mixcraft version, or any DAW at all. **This part is not built in this deliverable** (the composer emits files today per `project_darwish_alma_midi_model.md`, not a live note stream) — documented here as the confirmed mechanism for when it is.

2. **Live control (voice commands → transport / mixer / clip-launch / plugin params)**: this is **candidate (a), the Mixcraft 10 Controller Script**, and it is the only documented way to reach `Perform.TriggerSet()` (quantized clip launch — the actual mechanism behind "דרופ"), track mixer state, and plugin parameters from outside Mixcraft's own UI. Plain MIDI-Learn (a generic DAW feature, not part of the scripting API, undocumented in this doc set so not assumed to exist for clip-launch) might cover *some* mixer mappings without any script — but **nothing in the docs suggests MIDI-Learn can trigger a quantized Performance-panel column**, so the script is the only confirmed path for the "drop on the beat" behavior a DJ tool needs.

**Why not pure (b) for everything:** plain MIDI-Learn (if Mixcraft even exposes it — unverified, no Mixcraft here to check) gives at best simple fader mappings, not bar-quantized clip launching, not conditional logic ("if playing, toggle"), not `Notify()` feedback, not reading track state before acting. The whole point of "עוד 8 בר" / "דרופ" as *voice* commands (not literally holding a controller) is that the DAW-side logic needs to be smarter than a 1:1 CC-to-fader map.

**Why not pure (a) for everything:** because it structurally cannot deliver notes — building only the script and pretending note delivery is solved would be a broken window on day one.

**Loud flag, per the task's own instruction:** *the Controller Script half needs Mixcraft 10, and Mixcraft is not installed on this machine at all* (neither 10 nor any other version — see the three-line summary). If Iddo runs Mixcraft on a **different** physical computer (his music PC, not this coding PC), that changes nothing about the code but means steps 3–5 below happen there, not here.

---

## 3. Install steps (nothing was installed automatically — every step below needs your go-ahead)

**חוק בטיחות: לא הותקן שום דבר על המחשב באופן אוטומטי. כל שלב למטה טעון אישור שלך.**

### Step 0 — confirm which machine runs Mixcraft
This bridge was written and tested on a machine with **no** Mixcraft install. Before anything else: is Mixcraft 10 on a different computer? If so, everything below (steps 2–5) happens there, and only `bridge/` (the Python side) needs to run on whichever machine has the mic / KESHEV.

### Step 1 — install a virtual MIDI driver (needed either way)
Not installed here. **loopMIDI** (Tobias Erichsen, the de facto standard, free) is the natural choice — small, no config file, creates named ports instantly. Not downloaded or installed by this session (installing software is your call). If you approve: `https://www.tobias-erichsen.de/software/loopmidi.html`. After installing, create a port named exactly **`ALMA-DJ-Control`** (matches `bridge/protocol.py` and `dj_bridge.py`'s `--port` default).

### Step 2 — copy the controller script into Mixcraft (one file, your click)
Copy `controller/ALMA/dj_alma_control.js` from this folder to:
```
%programdata%\Acoustica\Mixcraft\controllers\scripts\ALMA\dj_alma_control.js
```
This session did **not** write into `%programdata%\Acoustica\` — that's the one copy step left for you, per the task's own instruction not to touch Mixcraft's install/config directly.

### Step 3 — register the script in Mixcraft
Mixcraft Preferences → Control Surfaces → Add New → select `dj_alma_control.js`. Choose MIDI input **and** output = the `ALMA-DJ-Control` loopMIDI port for both (output is used only for optional log/feedback in v1, not required to function). The in-app script editor opens automatically (because the script has `Globals.SetDebug(true)` on line 1) — leave it open the first time so you can watch `Globals.Log()` lines appear.

### Step 4 — edit the placeholder track/section layout
`bridge/protocol.py`'s `STEM_TRACK_INDEX` and `SECTION_COLUMN`, **and** the matching `TRACK_*`/`COL_*` constants near the top of `controller/ALMA/dj_alma_control.js`, are placeholders (0,1,2,3 / 0,1,2,3,4) — nobody has built the real project yet. Edit both files together to match your actual track order and Performance-grid layout, then re-Compile the script in Mixcraft's editor.

### Step 5 — install the Python bridge dependencies (already done on this machine)
```
"C:\Program Files\Python312\python.exe" -m pip install -r requirements.txt
```
Already run here (`mido` was present; `python-rtmidi` 1.5.8 was installed 2026-09-04).

### Step 6 — run the smoke test
```
"C:\Program Files\Python312\python.exe" smoke_test.py
```
Runs everything that doesn't need Mixcraft (grammar, protocol/JS drift check, MIDI library, listener window). Add `--port ALMA-DJ-Control --send-real` once the loopMIDI port exists and Mixcraft has the script loaded, to send one real `PLAY` and confirm it in Mixcraft's own Log window by eye.

### Step 7 — run the bridge for real
```
"C:\Program Files\Python312\python.exe" bridge\dj_bridge.py --mode console --port ALMA-DJ-Control
```
Opens the DJ-ALMA console window. **Keep it focused** while KESHEV is listening (see §5) — that's how recognized speech reaches it. Type into it yourself to test without the mic.

---

## 4. What v1 does NOT do (said plainly, not hidden)

- Does not deliver ALMA's composed notes into Mixcraft yet (§2, part 1 — the plain-MIDI note path is documented but not wired to the composer's live output).
- `EXTEND_SECTION` ("עוד 8 בר") is logged but does not yet pick a differently-sized clip — needs Iddo's real Performance-grid layout (which columns hold 8/16/32-bar variants), which doesn't exist yet.
- `*_VOL` commands are relative nudges, not "set the bass to exactly X%" — there's no read-back channel in v1 to know the current value before choosing an absolute target (see `protocol.nudge_param()`'s docstring).
- Nothing here has been confirmed against a running Mixcraft. Every claim about what the `.js` file will do when loaded is derived from the API docs, not observed.

---

## 5. How KESHEV (the mic) reaches this bridge

Read `D:\CLAUDE\keshev-next\app\main.py` and `typer.py` before writing this
(not guessed): KESHEV's only output path is `typer.type_string(text,
auto_enter=True)` — Windows `SendInput`, typing the recognized sentence plus
a real Enter keypress **into whatever window currently has OS focus**. There
is no separate event bus or clean-text log a second process can subscribe to.

So `bridge/listener_console.py` is a small always-on-top window with a text
field — **KESHEV's output reaches it because it's the focused window**, not
through any KESHEV code change (KESHEV was not touched, and neither was the
mic). Practical consequence: **Iddo must keep the DJ-ALMA console focused**
while DJing for voice commands to land there. Documented as a real
constraint, not hidden.

**STT REST interface, for reference (not used by this bridge — it would need
mic capture, which this task must not touch):** `POST /v1/transcribe` on
`:8737` (`http://<lan-ip>:8737/v1/transcribe` primary /
`http://127.0.0.1:8737/v1/transcribe` fallback per `RUN-KESHEV.cmd`) — body
is raw PCM s16le 16kHz mono, headers `Authorization`, `X-Request-Id`
(mandatory), optional `X-Lang-Hint`; JSON response has `text`, `lang`,
`lang_prob`, `avg_logprob`, `decode_ms`, etc. (read from
`D:\CLAUDE\mic-rebuild\server\stt_server.py`).

---

## 6. Voice command grammar (v1) — הגרמטיקה הקולית

Hebrew first, per how Iddo speaks to it. Keyword-based (substring match, not
strict phrasing) because real STT output is noisy. Implemented in
`bridge/grammar.py`, every row below is a passing test case in
`smoke_test.py`.

| Hebrew (say any of) | English gist | Command sent | Param |
|---|---|---|---|
| קצב 142 / טמפו 142 | set tempo to 142 BPM | `SET_TEMPO` | BPM→0-127 linear (120-160 range) |
| מהר יותר / תאיץ | faster | `TEMPO_NUDGE_UP` | +1 BPM step |
| לאט יותר / תאט | slower | `TEMPO_NUDGE_DOWN` | −1 BPM step |
| נגן / תריץ / פליי | play | `PLAY` | — |
| עצור / סטופ | stop | `STOP` | — |
| עצור הכל / סטופ הכל | stop everything (all clips) | `STOP_ALL_CLIPS` | — |
| הקלטה / רקורד | toggle record | `RECORD_TOGGLE` | — |
| תוריד את הבס | lower the bass | `BASS_VOL` | nudge down |
| תעלה בייס | raise the bass | `BASS_VOL` | nudge up |
| השתק תופים / מיוט דראמס | mute drums | `DRUMS_MUTE_TOGGLE` | — |
| תוריד ליד / תעלה מלודיה | lower/raise the lead | `LEAD_VOL` | nudge |
| תוריד אפקטים | lower FX | `FX_VOL` | nudge down |
| תוריד הכל / תעלה הכל (as master) | master volume down/up | `MASTER_VOL` | nudge |
| דרופ / תן דרופ עכשיו | drop | `SECTION_DROP` | — |
| בילד אפ / רייזר / עלייה | build/riser | `SECTION_BUILD` | — |
| ברייקדאון / ירידה / נשימה | breakdown | `SECTION_BREAK` | — |
| אינטרו / פתיחה | intro | `SECTION_INTRO` | — |
| אאוטרו / סיום | outro | `SECTION_OUTRO` | — |
| עוד 8 בר / עוד 16 בארים | extend N more bars | `EXTEND_SECTION` | bar-count code (v1: logged only, see §4) |

Anything not matching any row is **ignored, not guessed** — `grammar.parse()`
returns `None` and the bridge logs `IGNORED ... (no grammar match)` rather
than firing a wrong command.

---

## Files in this folder

```
dj-alma/
  README.md                              -- this file
  requirements.txt                       -- mido, python-rtmidi
  smoke_test.py                          -- run this first
  controller/ALMA/dj_alma_control.js     -- copy into %programdata%\Acoustica\... (Step 2)
  bridge/protocol.py                     -- shared wire-format contract (edit with the .js file)
  bridge/grammar.py                      -- Hebrew utterance -> command
  bridge/midi_out.py                     -- sends commands out over MIDI
  bridge/listener_console.py             -- the focused window KESHEV types into
  bridge/dj_bridge.py                    -- main entry point (--mode console|stdin)
  state/dj_bridge.log                    -- created at runtime, every utterance + outcome
```
