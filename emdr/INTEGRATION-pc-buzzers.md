# ALMA-EMDR — חיבור הבאזרים לווידג׳ט / Wiring the buzzers into the PC widget
### v1.0 · 2026-09-01 · לעמותת המלאכים של ערן

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

> ⚠️ **אף קובץ קיים לא נגעתי בו. / NO EXISTING FILE WAS MODIFIED.**
> צוות אחר עובד כרגע בתוך `emdr_widget.py`. המסמך הזה הוא **הוראת טלאי** — בן אדם מחיל אותה.
> Another workflow is inside `emdr_widget.py` right now. This document is a **patch
> instruction** for a human to apply. The only new file is `buzzers_ble.py`, which is
> self-contained and touches nothing.

---

## בקצרה / In one paragraph

הכול נמצא בקובץ חדש אחד, `source-emdr-central/buzzers_ble.py`. כדי לחבר אותו צריך
**ארבעה מקומות ב-`emdr_widget.py`, סך הכול 17 שורות**: ארבע לייבוא, שלוש בלולאת
הפריימים, עשר בהתחלת הסבב, שלוש בסופו, ושלוש ביציאה מהאפליקציה. אין שינוי מבנה, אין
שינוי חתימה של אף פונקציה, ואם הקובץ החדש חסר או נופל — הווידג׳ט עובד בדיוק כמו היום.
**ברירת המחדל היא כבוי**, אז החלת הטלאי לבדה לא משנה שום התנהגות.

Everything lives in one new file, `source-emdr-central/buzzers_ble.py`. Wiring it in
touches **four places in `emdr_widget.py`, 17 lines total**: four for the import, three in
the frame loop, ten at the start of a set, three at the end, three on app exit. No
restructuring, no changed signature anywhere, and if the new file is missing or throws,
the widget behaves exactly as it does today. **The default is off**, so applying the patch
alone changes no behaviour.

---

## מה כבר הוכח / What is already proven

הכול נמדד ב-2026-09-01 על המכונה הזאת, בסימולטור. **אין חומרה. שום מספר כאן לא נמדד
מול באזר אמיתי.** / Everything below was measured on this machine on 2026-09-01, in the
simulator. **No hardware exists. Not one number here was measured against a real buzzer.**

| מה / What | תוצאה / Result |
|---|---|
| 8 וקטורי הבדיקה של §C.7 | ✅ **8/8 byte-exact**, plus round-trip of every field |
| סבב מלא 1 Hz, סימולטור נקי | ✅ **12/12 פעימות**, שגיאה ממוצעת **0.8 ms**, מקסימום 1.6 ms |
| קו דמוי-BLE: 15 ms + U(0,45) ms רעד + **20% אובדן חבילות** | ✅ **15/15 פעימות**, ממוצע **17.5 ms**, מקסימום 58 ms — 15/15 בתוך הגבול הקשיח ±80 ms |
| 2 Hz (תקרת ה"דייסה") | ✅ 23/23, ומדווח נכון `haptics distinct: False` |
| §D.4 — זרע 1, שבו הצפצוף של הווידג׳ט **אילם** | ✅ הווידג׳ט צפצף **0 פעמים**, הבאזרים פעלו **12/12** |
| כלל האיש-המת, שכבה 2 (לקוח) | ✅ STOP ×5 אחרי 1200 ms בלי `on_phase` |
| כלל האיש-המת, שכבה 1 (קושחה) | ✅ נעצר 1500 ms אחרי המסגרת האחרונה |
| מגביל ה-duty | ✅ החלון הגרוע ביותר: **60.0%** מול תקרה של 60% |
| **סבב מלא 90 שניות** על קו דמוי-BLE עם 10% אובדן | ✅ **173/173 פעימות, אפס החמצות**, ממוצע 14.3 ms, 173/173 בתוך ±80 ms, בלי סחיפה |
| **`on_phase()` עם מוביל תקוע לגמרי (500 ms לכל שליחה)** | ✅ **p50 0.6 µs, max 38 µs = 0.24% מתקציב הפריים** |

**האחרון הוא העיקר:** גם כשה-BLE תקוע לחלוטין, `on_phase()` עולה 38 מיקרו-שניות במקרה
הגרוע. **רדיו תקוע לא יכול לעצור את העיגול.**
**That last row is the important one:** with the transport fully wedged, `on_phase()` costs
38 µs worst case. **A hung radio cannot stall the orb.**

לשחזור / To reproduce:

```bash
cd D:\CLAUDE\emdr\source-emdr-central
python buzzers_ble.py vectors
python buzzers_ble.py sweep --secs 6 --hz 1.0 --seed 42
python buzzers_ble.py sweep --secs 6 --hz 1.0 --seed 1        # the silent-beep seed
python buzzers_ble.py sweep --secs 8 --air-latency 15 --air-jitter 45 --loss 20 --link-latency 30
python buzzers_ble.py deadman
python buzzers_ble.py ports                                    # read-only
```

---

## הטלאי / THE PATCH — four hunks, 17 lines

הטלאי מיושר לפי **שמות פונקציות**, לא לפי מספרי שורות, כי הצוות השני עורך את הקובץ
עכשיו. / The patch is anchored on **function names, not line numbers**, because the other
workflow is editing the file right now — **the file's md5 changed under me during this
work**, from `229cafd49281c22c6842e0c009ac8f95` to `65c4932aa53b67c7053a9c897e014201`,
which is exactly why nothing here cites a line number. Every hunk below was re-verified
against the **live** file at `65c4932a…`: their `sequence.start()` gained a `click_mode`
argument, `on_sequence_finished()` gained an early-return guard, and a new
`stop_sequence()` and `_edge()` appeared. The hunks match what is on disk now.

### Hunk 1 — the import (next to the existing `soundcard_pan` import, ~line 57)

```diff
 try:
     import soundcard_pan  # type: ignore
     _SCP_OK = True
 except Exception:
     soundcard_pan = None
     _SCP_OK = False
+
+try:
+    import buzzers_ble  # type: ignore
+    _BUZZ_OK = True
+except Exception:
+    buzzers_ble = None
+    _BUZZ_OK = False
```

### Hunk 2 — one line in the frame loop, `EmdrSequence._tick`

Put it **immediately after `self._orb_x` is computed** and **before `self.update()`.
Do not attach to the `edge_thresh` block below it** — see "Why not the edge test", below.

```diff
         phase = 2 * math.pi * t * 1000.0 / self._period_ms
         self._orb_x = mid + amp * math.sin(phase)
+
+        # buzzers: PROTOCOL §D.4 - phase crossing, never a pixel threshold.
+        _bz = getattr(self.controller, "buzzers", None)
+        if _bz is not None:
+            _bz.on_phase(phase, 1000.0 / self._period_ms)
 
         if base_amp > 0:
             pan = (self._orb_x - mid) / base_amp
```

`getattr(..., None)` means this line is safe even if Hunk 3 was never applied, or if the
controller is an older build. Cost measured at 38 µs worst case with a wedged radio.

### Hunk 3a — start a set, in `EmdrController.start_sequence`

Put it **immediately before the last two lines** of the method (`beep = ...` /
`self.sequence.start(...)`):

```diff
+        # buzzers (optional; never allowed to stop a session from starting)
+        self.buzzers = None
+        if _BUZZ_OK:
+            try:
+                self.buzzers = buzzers_ble.BuzzerClient.from_settings(self.settings,
+                                                                      logger=log)
+                if self.buzzers is not None:
+                    self.buzzers.reset_phase()
+                    self.buzzers.start()
+            except Exception as exc:
+                log(f"buzzers unavailable ({exc}); sweep continues without haptics")
+                self.buzzers = None
+
         beep = self.beep_paths.get(self.settings.get("edge_sound", "Beep"),
                                    self.beep_paths["Beep"])
         self.sequence.start(self.settings, beep, consumers, click_mode)
```

### Hunk 3b — end a set, in `EmdrController.on_sequence_finished`

```diff
     def on_sequence_finished(self):
         if not self._running:
             return
         self._running = False
+        if getattr(self, "buzzers", None) is not None:
+            try: self.buzzers.stop()
+            except Exception: pass
         if self._soundcard_active and _SCP_OK:
             try:
                 soundcard_pan.stop_pan()
```

`stop()` is non-blocking — it asks the worker to send `STOP` ×5 and returns. Put it
**first** after the `_running` flag so the hands stop before anything else is torn down.
The new `stop_sequence()` (the user's Abort button) ends by calling
`on_sequence_finished()`, so this one hunk covers that path too — I checked.

### Hunk 3c — `exit_app`, the path that does NOT route through `on_sequence_finished`

`exit_app()` calls `self.sequence.stop()` and `soundcard_pan.stop_pan()` directly and
**never reaches `on_sequence_finished`**. Closing the app mid-set would therefore never
call `buzzers.stop()`:

```diff
     def exit_app(self):
         log("exit_app requested")
         try: self.sequence.stop()
         except Exception as e: log(f"sequence.stop on exit: {e!r}")
         self._running = False
+        if getattr(self, "buzzers", None) is not None:
+            try: self.buzzers.close(wait_ms=400)
+            except Exception: pass
         if _SCP_OK:
             try: soundcard_pan.stop_pan()
```

Two safety layers already cover this even if the hunk is skipped — the module's `atexit`
handler sends `STOP` ×5, and the firmware dead-man stops the balls 1500 ms after the last
frame — but **1500 ms of buzzing in someone's hand after they closed the app is not
acceptable when three lines prevent it.**

### That is the whole patch. Nothing else in `emdr_widget.py` changes.

---

## הגדרות / Settings — five new keys, all optional

הוסף ל-`DEFAULT_SETTINGS` (~line 101). **ברירת המחדל היא `"off"` — הטלאי לא משנה שום
התנהגות עד שמישהו מדליק אותו במפורש.** / Add to `DEFAULT_SETTINGS`. **The default is
`"off"`, so applying the patch changes no behaviour at all until someone explicitly
turns the buzzers on.**

```diff
     "pan_output_mode": "Soundcard",  # "Soundcard" | "In-widget" | "Off"
+    # buzzers - see PROTOCOL-buzzers-20260901.md
+    "buzzer_transport": "off",       # "off" | "sim" | "serial" | "serial:COM5" | "ble"
+    "buzzer_room": 1,                # 1..255; 0 = every room
+    "buzzer_intensity": 200,         # 40..255 (below 40 an ERM will not start)
+    "buzzer_pulse_ms": 0,            # 0 = derive from sweep_hz automatically
+    "buzzer_lookahead_ms": 250,      # how far ahead a tap is announced
 }
```

`"sim"` is safe to leave on for testing: it drives the software balls and writes a
timestamped packet log, and touches no port, no radio and no audio device.

A Settings-tab combo box is a one-liner next to the existing `pan_out` combo, but that
widget belongs to the other workflow right now, so **hand-edit `settings.json` for the
first test** and add the combo box afterwards.

---

## למה לא להיתלות על גלאי-הקצה הקיים / Why NOT the existing edge test

זה החלק שהכי חשוב לא לפספס. / This is the part not to get wrong.

הבדיקה הקיימת ב-`_tick` היא רצועת 6 פיקסלים סביב `_x_min`/`_x_max`. `EmdrSequence.start`
מגריל `_amp_jitter = rng.uniform(-0.02, 0.02)`. **כשהג׳יטר שלילי, העיגול פשוט לא מגיע
לרצועה — והאירוע לא קורה אף פעם, בשקט, לכל הסבב.**

The existing test in `_tick` is a 6-pixel band around `_x_min`/`_x_max`. `start()` draws
`_amp_jitter = rng.uniform(-0.02, 0.02)`. **When the jitter is negative the orb never
reaches the band, and the event never fires — silently, for the whole session.**

| רוחב מסך | אחוז הזרעים שמשתיקים את האירוע |
|---|---|
| 1920 px | **32.8 %** |
| 2560 px | **37.3 %** |
| 3840 px | **41.6 %** |

זרע 42 (ברירת המחדל) במקרה עובד — ולכן אף אחד לא תפס את זה.
Seed 42 (the default) happens to work, which is why nobody has caught it.

**ויש מצב שלישי, גרוע מהשקט — גמגום.** כשהג׳יטר שלילי אבל זעיר, העיגול *בקושי* נוגע
ברצועה, ורק פריים שנוחת ממש על השיא תופס אותו. מדוד על זרע 7: הצפצוף של הווידג׳ט פעל
**5 מתוך 10** בסבב קצר, ו-**86 מתוך 173** בסבב מלא של 90 שניות — קצב לא סדיר, בערך חצי.
ב-EMDR הקצב **הוא** המנגנון, ולכן פעימה מגומגמת גרועה יותר משתיקה: היא נשמעת כאילו
המכשיר עובד. הלקוח החדש פעל 10/10 ו-173/173 באותם זרעים בדיוק.

**And there is a third state, worse than silence — stutter.** When the jitter is negative
but tiny, the orb *barely* grazes the band and only a frame landing right on the apex
catches it. Measured on seed 7: the widget's beep fired **5 of 10** in a short set and
**86 of 173** across a full 90-second session — an irregular, roughly half-rate cue. In
EMDR the rhythm **is** the mechanism, so a stuttering beat is worse than a silent one: it
sounds like the device is working. The new client fired 10/10 and 173/173 on those same
seeds.

> 🚩 **אזהרה, נכון לגרסה החיה של הצוות השני:** הם מיזגו את הקצה לפונקציה אחת,
> `EmdrSequence._edge(side)`. היא **נראית** כמו נקודת החיבור המושלמת — משפך אחד, צד אחד.
> **אל תתלו עליה את הבאזרים.** היא נקראת מתוך אותה בדיקת 6-פיקסלים, ויורשת את הבאג
> במלואו. המשפך יפה; מה שמזין אותו שבור.
> 🚩 **Warning, against the other team's live version:** they have refactored the edge
> into a single `EmdrSequence._edge(side)`. It **looks** like the perfect hook — one
> funnel, one side. **Do not attach the buzzers to it.** It is called from inside the same
> 6-pixel test and inherits the bug whole. The funnel is fine; what feeds it is broken.

**מדוד, לא משוער** — הרצה של `python buzzers_ble.py sweep --secs 6 --seed 1`:

```
  seed 1 -> _amp_jitter = -0.01463
  the widget's own 6-px edge test fired 0 time(s) in this sweep
  this phase-crossing client fired  12 time(s)
  ==> the widget's beep is SILENT for this seed; the buzzers still work.
```

באזר שתלוי בבדיקה הזאת פשוט לא היה רוטט לשליש מהאנשים. הפתרון הוא חציית פאזה: העיגול
נמצא ב-`mid + amp*sin(phase)`, אז הקצוות הם **בדיוק** `phase = π/2 + kπ`, בלי קשר לאמפליטודה.

A buzzer hung off that test would simply never buzz for a third of users. The fix is phase
crossing: the orb is at `mid + amp*sin(phase)`, so the edges are **exactly** at
`phase = π/2 + kπ`, regardless of amplitude.

> 🪟 **חלון שבור, מדווח ולא תוקן / A broken window, reported not fixed.** הצפצוף האילם הוא
> באג ב**מוצר הקיים**, לפני שקיים באזר אחד. הוא לא בקובץ שלי ואני לא נוגע בקובץ של הצוות
> השני. **התיקון בשורה אחת** ב-`_tick` הוא להחליף את בדיקת ה-6-פיקסלים באותה חציית פאזה
> שהמודול הזה עושה — `buzzers_ble` מייצא את החשבון. **זה ראוי לתיקון בלי קשר לבאזרים.**
> The silent beep is a bug in the **existing product**, before any buzzer exists. The
> one-line fix is to replace the 6-px test in `_tick` with the same phase crossing this
> module does. **It is worth fixing whether or not the buzzers are ever built.**

---

## איך זה בנוי / How the module is built

```
    UI thread (Qt, 60 Hz)                     worker thread (daemon)
    ─────────────────────                     ──────────────────────
    _tick()                                   opens the transport
      └─ on_phase(phase, hz)                  sends every byte
           ├─ pure float arithmetic           whispers TAP 3x/s
           ├─ deque.append()      ──────────► restates the pending beat
           └─ Event.set()                     KEEP when idle
                                              STOP x5 on stop/close
    max 38 µs, measured                       may block freely - nobody waits on it
```

**חוזה החוטים / The threading contract, verbatim from the module:**

- `on_phase()`, `tap_now()`, `stop()`, `start()` נקראים מחוט ה-UI ו**לא עושים I/O, לא
  ממתינים, ולא נועלים שום דבר שמוביל איטי יכול להחזיק.**
- כל בית שיוצא נכתב על ידי `_worker`, חוט דמון. פורט טורי תקוע או מחסנית BLE תלויה
  מעכבים אותו ואת אף אחד אחר.
- רק `close(wait_ms=...)` ממתין, ורק בכיבוי.

**שלוש שכבות של איש-מת בצד הלקוח**, מעל החמש של הקושחה (§D.5):

1. העובד לוחש `TAP`/`KEEP`. **מפסיקים ללחוש — כל כדור עוצר את עצמו תוך 1500 ms.** זו
   השכבה ששורדת קריסה של כל האפליקציה.
2. אם `on_phase()` מפסיק להגיע בזמן שהסבב אמור לרוץ (חוט ה-UI נתקע), העובד שם לב אחרי
   1200 ms ושולח `STOP` ×5 — מהר יותר מהמתנה לאיש-המת של הקושחה.
3. `atexit` סוגר כל לקוח חי עם `STOP` ×5 אחרון.

1. The worker whispers `TAP`/`KEEP`. **Stop whispering and every ball stops itself within
   1500 ms.** This is the layer that survives the whole application dying.
2. If `on_phase()` stops arriving while the sweep should be running, the worker notices
   after 1200 ms and sends `STOP` ×5.
3. `atexit` closes every live client with a final `STOP` ×5.

---

## שלושת המובילים / The three transports

| | מצב / Status |
|---|---|
| **`sim`** — `LoopbackTransport` | ✅ **עובד ונמדד.** שני כדורים בתוכנה שמממשים §C.3 ו-§D.5, ולוג חבילות עם חותמות זמן. לולאת ה-MCU המדומה רצה ב-p50 **1.53 ms** — זו רצפת הדיוק של הלוג. |
| **`serial`** — `SerialTransport` | 🟡 **כתוב, לא נבדק מול חומרה.** מול `pyserial 3.5` שכבר מותקן — **אפס תלויות חדשות**, וזה בדיוק למה שביקשת חוטים קודם. יש גם `legacy_identify()` / `legacy_send()` לפרוטוקול ה-ASCII הישן, ל-bring-up. |
| **`ble`** — `BleTransport` | 🔴 **כתוב, ו-`bleak` בכלל לא מותקן פה.** `pip install bleak` לפני שלב 2. חוט asyncio ייעודי (bleak נתקע לנצח אם החוט אינו MTA — ו-PyQt מאתחל את החוט הראשי כ-STA, זו בדיוק המלכודת), חיבור לפי אובייקט `BLEDevice` ולא לפי כתובת, ו-Write Without Response. |

---

## שלוש הבהרות לפרוטוקול שהסימולציה מצאה / Three protocol clarifications found by simulating

הסימולטור תפס שלושה דברים שהמסמך לא אמר במפורש. **שלושתם צריכים להיכנס לקושחה.**
The simulator caught three things the protocol did not say explicitly. **All three belong
in the firmware.**

1. **חזרה על פעימה שכבר נוגנה חייבת להידחות.** לחישה אחרונה של פעימה יכולה לנחות *אחרי*
   שהמנוע כבר פעל, להצטייד ב-`delay` 0 ולרטוט את היד **פעמיים**. הכלל: הכדור זוכר את
   `target` האחרון שנוגן, וכל `target` חדש בתוך `HYSTERESIS_MS` ממנו נדחה.
   **A restatement of a beat that already played must be dropped**, or the hand buzzes
   twice. The ball remembers the last played `target` and drops any new target within
   `HYSTERESIS_MS` of it.

2. **מנוע אחד, פעימה אחת.** פעימה שמתחילה בזמן שהמנוע עוד רץ **מתמזגת** איתו לרטט רציף
   אחד ארוך מ-`DUR_MAX` — ומנטרלת בדיוק את התפסנית שעליה §D.5 נשען. אם המנוע פועל, הפעימה
   החדשה נדחית. נמדד: אחרי התיקון, החלון הגרוע ביותר הוא **60.0%** מול תקרה של 60%, והפעימה
   הרציפה הארוכה ביותר היא בדיוק 600 ms.
   **One motor, one pulse.** A pulse starting while the motor still runs merges into a
   single continuous buzz longer than `DUR_MAX`, defeating the one-shot clamp. Measured
   after the fix: worst rolling window **60.0 %** against a 60 % cap, longest continuous
   pulse exactly 600 ms.

3. **מאפסים את האיש-המת לפני בדיקת הכפילויות, לא אחריה.** כל מסגרת תקינה לחדר שלנו היא
   הוכחה שהקו חי, גם אם היא עותק. לא קריטי היום (שלושת העותקים במרחק 8 ms), אבל קושחה
   שמאפסת רק על מסגרות חדשות נמצאת מרחק מקור-אחד-אבוד מהשבתה מיותרת.
   **Reset the dead-man before duplicate suppression, not after.** Any well-formed frame
   for our room is proof the link is alive, copy or not.

---

## שתי אזהרות / Two warnings

**1. 🎧 חוק השמע הקדוש — `soundcard_pan.py` הוא מסלול ברירת המחדל של הווידג׳ט.**
הוא קורא ל-`IAudioEndpointVolume::SetChannelVolumeLevelScalar` על **התקן הפלט הראשי של
המערכת** בערך 55 פעמים בשנייה לאורך כל הסבב, ומוריד ערוץ אחד ל-0.15 — כלומר מפנרר את **כל**
היישומים במחשב. **לא נגעתי בזה.** אבל הבאזרים הם בדיוק הטיעון לכבות אותו: רטט על הידיים נותן
את הרמז הדו-צדדי בלי לגעת בכרטיס הקול בכלל. `pan_output_mode: "Off"` + באזרים הוא גם נקי
מבחינת החוק וגם בעל השהיה נמוכה יותר.
**`soundcard_pan.py` is the widget's default audio path** and modulates the system render
endpoint's channel volumes ~55×/s for a whole session. **Not touched.** The buzzers are the
argument for switching it off: `pan_output_mode: "Off"` + buzzers is both law-clean and
lower-latency.

**2. מעל ~1.6 Hz הרטט מפסיק להרגיש כמו פעימות נפרדות.** הכלל מ-§D.5 הוא
`150 ms ≤ dur ≤ min(400, 250/hz)`, וב-2 Hz התקרה היא 125 ms — **מתחת** לרצפה של 150 ms
שמנוע ERM צריך כדי לזוז בכלל. המודול מדווח את זה (`haptics_distinct(hz)`) ומהדק לבד.
הראייה והשמע תקינים בכל קצב; רק ההפטיקה מתדרדרת. **תגידו את זה בפה מלא במקום להגיש דייסה.**
**Above ~1.6 Hz the taps stop feeling distinct.** At 2 Hz the ceiling is 125 ms, below the
150 ms an ERM needs to move at all. `haptics_distinct(hz)` reports this and the module
clamps. Visual and audio are fine at any rate; only haptics degrade. Say so plainly.

---

## מה עוד לא מוכח / What is NOT proven

| | |
|---|---|
| קצב פריימים, בטיחות חוטים, חשבון הפאזה, מכונת המצבים | ✅ **נמדד בסימולטור** |
| 8 וקטורי §C.7 | ✅ **8/8 byte-exact** |
| `SerialTransport` מול קופסה אמיתית | 🔴 **לא נבדק. אין קופסה.** |
| `BleTransport` מול כדור אמיתי | 🔴 **לא נבדק, ו-`bleak` לא מותקן.** |
| כל מספר השהיה על חומרה אמיתית | 🔴 **לא נבדק.** מנוע ERM אמיתי, רדיו אמיתי, MCU אמיתי — אף אחד מהם לא קיים. |
| `ERM_LEAD_MS = 30` | 🔴 **מספר מהספר, לא מדידה.** מודדים אותו עם מיקרופון או מד-תאוצה כשהמנוע הראשון מגיע, ומעדכנים קבוע אחד בקושחה. |

**הצעד הבא הוא לא עוד קוד.** הצעד הבא הוא קופסת שלב-1 — ESP32-C3 אחד, שני שקעים, שני
מנועים, ~₪31 — ואז מריצים את אותו `sweep` מול חומרה אמיתית ומשווים לטבלה למעלה.
**לא קניתי כלום ולא הזמנתי כלום.**

**The next step is not more code.** It is the Phase-1 box — one ESP32-C3, two jacks, two
motors, ~₪31 — and then running the same `sweep` against real hardware and comparing to
the table above. **Nothing was bought or ordered.**

---

**קבצים / Files**
`D:\CLAUDE\emdr\source-emdr-central\buzzers_ble.py` — new, self-contained, 0 project files touched
`D:\CLAUDE\emdr\PROTOCOL-buzzers-20260901.md` — the binding protocol this implements
`D:\CLAUDE\emdr\INTEGRATION-pc-buzzers.md` — this file

**לא פורסם כלום, לא נפתח שום התקן שמע, ולא נגעתי ב-`emdr_widget.py`.**
**Nothing published, no audio device opened, `emdr_widget.py` not touched.**
