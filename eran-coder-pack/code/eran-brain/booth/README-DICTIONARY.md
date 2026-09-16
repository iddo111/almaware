# המילון של ערן / ERAN's Dictionary Rig

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

---

## בעברית — קצר

**מה זה:** תוכנה שמקליטה אותך קורא, הרבה זמן, בלי ללחוץ על כלום.

**למה:** מדדנו ב-23.8. 396 קטעי אודיו מלאכותיים לימדו את ערן **כלום** — 6.1%
מול 4.5% של ניחוש. רק פה אמיתי של בן אדם מזיז אותו. הקול שלך זה החומר.

**מה עושים:**

1. חבר מיקרופון USB. **אוזניות בלוטות' אסורות** — התוכנה תסרב לרוץ עליהן.
2. אם "קשב" פתוח — תסגור אותו. שניים לא יכולים להחזיק מיקרופון אחד.
3. לחיצה כפולה על הקיצור **ERAN Dictionary** בשולחן העבודה.
4. שתי שניות שקט. הוא מודד את החדר.
5. מילה גדולה על המסך. תגיד אותה. תעצור. הוא שומע, שומר, ועובר הלאה לבד.
6. יצא רע? הוא יגיד **"שוב בבקשה"** ויישאר על אותה מילה.
7. מקשים: `s` דלג · `r` שוב · `p` הפסקה · `q` סיום.
8. הכל נשמר מיד. גם אם המחשב ייפול — מה שהקראת נשאר.

**איפה זה נשמר:** בתיקיית `booth\staged\` — כל ישיבה בתיקייה משלה.

---

## In English — short

**What it is:** a program that records you reading, for a long time, hands free.

**Why:** measured 2026-08-23. 396 synthetic clips taught ERAN **nothing** —
6.1% against a 4.5% chance baseline. Only a real human mouth moves him. Your
voice is the material.

**What to do:**

1. Plug in a USB microphone. **Bluetooth headsets are forbidden** — this
   program refuses to run on one.
2. If KESHEV is running, close it. Two programs cannot hold one microphone.
3. Double-click the **ERAN Dictionary** shortcut on the Desktop.
4. Two seconds of quiet. It measures the room.
5. A big word appears. Say it. Stop. It hears, saves, and moves on by itself.
6. Bad take? It says **"again please"** and stays on the same word.
7. Keys: `s` skip · `r` redo · `p` pause · `q` finish.
8. Everything is saved the instant it happens. If the machine dies, everything
   you already read is still there.

**Where it lands:** `booth\staged\` — one folder per sitting.

---

## The exact commands

Run them from the booth folder. Every one is safe to run right now.

```
python dictionary.py --selftest        prove the whole rig. No mic, no person,
                                       no playback. 32 checks, synthetic audio.
python dictionary.py --dryrun          open the real mic, measure the room,
                                       write NOTHING and record nobody.
python dictionary.py --devices         list every mic and show who is refused
                                       and exactly which word got them refused.

python dictionary.py --list lists\dict-alef.txt --id-prefix a --person iddo
python dictionary.py --list lists\core31.txt --takes 3 --person iddo
python dictionary.py --resume t07      continue a crashed sitting: SAME talker,
                                       SAME session id, SAME fold.
```

Double-click launchers, same things:

| file | what it does |
|---|---|
| `RUN-DICTIONARY.cmd` | the dictionary, letter א, ids `a0001…` |
| `RUN-CORE31.cmd` | ERAN's own 31 units and words, 3 takes each |
| `CHECK-MIC.cmd` | the dry run — opens the mic, records nothing |

---

## What it writes

```
booth\staged\t07\
    session.json        who, which mic, which room, which gate, which fold
    manifest.jsonl      one line per clip: text, unit, take, session, timestamp,
                        duration, rms, peak, the gain that was NOT applied
    rejects.jsonl       one line per refused take, and why
    ah_t07_0000.wav     16 000 Hz · mono · 16-bit · RAW
    ...
```

A manifest row, real, from the self-test:

```json
{"file":"ah_t07_0000.wav","unit":"ah","text":"אַה","hint":"כמו נשיפה: אַה",
 "take":0,"talker":"t07","session_id":"t07-20260824T024554Z","person":"iddo",
 "utc":"2026-08-24T02:45:55Z","epoch":1787539555.4,"sample_rate":16000,
 "channels":1,"samples":18720,"duration_ms":1170,"rms_raw":0.033193,
 "peak":0.203321,"would_be_gain":4.672,"seg_id":"t07-...-000001",
 "gate_rms":0.008,"device":"Microphone (Logitech BRIO)"}
```

The 657 clips already in `staged\t06\` have **no manifest at all** — no text, no
session, no timestamp, no device. That gap is what this closes.

---

## The four rules this rig is built on

**1. USB microphone only.** The device law comes straight out of KESHEV
(`mic-rebuild\client\devices.py`) and it is checked on the device NAME, before
any probe and before any open, with no configuration able to reach it. On this
machine it currently refuses nine inputs: the WH-1000XM4 headset, three
Hands-Free endpoints, the AudioRelay virtual mic, Sound Mapper and Primary
Sound Capture. If no allowed mic exists it goes idle and says so — it never
falls back. Opening a Bluetooth headset's mic flips it to HFP telephone
quality and wrecks Iddo's sound. That happened once. Never again.

**2. One sitting = one talker id = one exam fold.** Talker `t06` currently holds
**six** different sittings across eleven hours (09:12 to 20:12), collapsed into
one tag — so the leave-one-session-out fence cannot see any of the acoustic
variation it exists to hold out. Here a new sitting always gets a new tag, and
`--resume` is the only way back into an old one. The `person` field carries who
was speaking, so a person-level fence can still be reconstructed later.

**3. It refuses dev-fold ids.** `proof/measure.py::is_dev()` says
`int(digits) % 6 == 0`, so `t06`, `t12`, `t18` are the dev fold, and
`body/school.py` drops dev talkers from **both** training menus with no error
and no warning. A whole night recorded into one of those would be eaten by
nobody, silently. This rig skips them and says so out loud.
**The real repair is on eran1, in `measure.py`. This is a guard rail, not a fix.**

**4. Raw audio, and reject when in doubt.** KESHEV peak-normalises before a
decoder; a corpus must not, so the gain is computed, recorded as
`would_be_gain`, and not applied. And where KESHEV's rule is "never lose a real
word", this rig inverts it: a rejected take costs one repeat, a falsely accepted
take is a permanently mislabelled clip. That is not a theory — a six-second
smoke run of this file, with nobody speaking, filed 720 ms of room noise as a
clip of "אַה". The corpus floor (rms 0.012, the p10 of Iddo's measured real
speech) now refuses it.

---

## What it reuses, and from where

Nothing about microphones is re-invented here.

| from `D:\CLAUDE\mic-rebuild\client\` | what it gives |
|---|---|
| `devices.py` | the device law, the refusal list, the WASAPI→DirectSound→WDM-KS fallback chain, the transient-open retry |
| `capture.py` | format negotiation (the BRIO rejects a forced 16 kHz), copy-out in the callback, mono downmix, bounded queue with a visible drop counter, the silent-but-open watch, ABOVE_NORMAL thread priority asserted at runtime |
| `resample.py` | the phase-continuous windowed-sinc FIR down to 16 kHz |
| `segmenter.py` | the utterance segmenter — energy gate, 600 ms hangover, 28 s split, webrtcvad with its measured faint-band bypass, and the blip rule. `PromptSegmenter` subclasses it, so the boundary logic is literally KESHEV's code |
| `config\client.json` | which mic is the good one in this room ("Logitech BRIO") |

And from `booth\booth.py`: the 31 prompts, and its founding decision — **the
prompt IS the label**, no recogniser anywhere in the labelling path. A phone
recogniser was tested on clips whose answer was already known and scored 5 of
22; it heard `na` as "e" and `ma` as "l a r".

---

## Measured, on this machine, 2026-08-24

| check | result |
|---|---|
| self-test, 32 checks | **all pass** |
| BRIO opened, live | 48 000 Hz × 1 ch → 16 000 Hz mono, 202 callbacks, 0 dropped frames, thread priority ABOVE_NORMAL |
| room floor | rms 0.0027 → gate 0.0054 (KESHEV measured 0.0031 the long way) |
| 8 s of an empty room | **0 clips, 0 rejects** — nothing false was filed |
| every wav | 16 000 Hz · mono · 16-bit, matching `staged\t06\` exactly |
| manifest after each clip | complete and parseable on disk: rows readable after clip 1..N = `[1,2,3,4,5,6]` |

---

*לא הקלטנו אותך בלי שאתה יודע. הכל נבדק על אודיו סינתטי ועל חדר ריק.*
*Nobody was recorded to test this. Everything was proven on synthetic audio and an empty room.*
