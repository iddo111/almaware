# ALMA-EMDR — פרוטוקול הבאזרים / The Buzzer Protocol
### v1.0 · 2026-09-01 · לעמותת המלאכים של ערן

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

> ⚠️ **מצב: תכן בלבד. אין עדיין חומרה. / STATUS: DESIGN ONLY. NO HARDWARE EXISTS YET.**
> כל מספרי הזמן שמסומנים *(design target)* לא נמדדו מול חומרה אמיתית — הם יעדים לבדיקה.
> Every timing number marked *(design target)* is **untested against real hardware**. The
> only numbers measured on this machine are marked *(measured)*.

---

# חלק א׳ — בשפה פשוטה / PART A — IN PLAIN WORDS

## מה בונים

שני כדורים קטנים ביד — אחד שמאל, אחד ימין. כשהעיגול על המסך מגיע לקצה שמאל, הכדור השמאלי
נותן רטט קצר. מגיע לקצה ימין — הכדור הימני. **העין, האוזן והיד עושות את אותו הדבר באותו רגע.**

## What we are building

Two small balls, one in each hand. When the dot on the screen reaches the left edge, the
left ball buzzes. Right edge — the right ball. **Eye, ear and hand all do the same thing at
the same moment.**

## איך זה עובד — בלי מונחים

התוכנה **לא** אומרת לכדור "תדליק" ואחר כך "תכבה". זה מסוכן — אם התוכנה נופלת באמצע, הכדור
נשאר דולק על היד של מישהו. במקום זה התוכנה אומרת, כל שליש שנייה, לחישה אחת:

> *"הרטט הבא: שמאל, בעוד 180 מילישניות, 160 מילישניות אורך."*

הכדור שומר **פעימה אחת ממתינה** בלבד. הלחישה הבאה מחליפה אותה. **אם הלחישות נפסקות —
הכדור נעצר לבד תוך שנייה וחצי.** לכדור אין בכלל מצב "דולק". יש לו רק ספירה לאחור.

## How it works — no jargon

The software never says "turn on" and later "turn off". That is dangerous: if the app dies
mid-session, the ball stays on in someone's hand. Instead, three times a second, the
software whispers one sentence:

> *"Next buzz: left, in 180 ms, 160 ms long."*

The ball holds **exactly one pending buzz**. The next whisper replaces it. **If the
whispering stops, the ball stops by itself within 1.5 seconds.** The ball has no "on"
state at all. It only ever has a countdown.

> 🕯️ **זה כל סוד הבטיחות, וזה גם כל סוד הסנכרון. משפט אחד עושה את שניהם.**
> **That one sentence is the whole safety story and the whole synchronisation story.**

## מה אפשר ומה אי אפשר — האמת

| | |
|---|---|
| 🟢 **אדם אחד, 2 כדורים, בחוט** | עובד. ₪31 חלקים. זה מה שבונים ראשון, כמו שביקשת. |
| 🟢 **אדם אחד, 2 כדורים, אלחוטי** | עובד — מהמחשב, מהטלפון, ומכרום/אדג׳ באתר. |
| 🔴 **20 איש, 40 כדורים, כל אחד מתחבר ישירות** | **בלתי אפשרי.** אנדרואיד וּוינדוס עוצרים ב-7 חיבורים. בדפדפן — חלון אישור אחד לכל כדור, 40 חלונות. אין גרסה של זה שעובדת. |
| 🟢 **20 איש, 40 כדורים, דרך קופסה אחת** | עובד: המחשב מדבר עם **קופסה אחת**, והקופסה משדרת לכולם בבת אחת. אין מגבלת מספר. |
| 🔴 **אייפון / אייפד** | הדפדפן באייפון **לעולם** לא יוכל לדבר עם באזרים. אפל חסמה. באייפון: עיגול וצליל בלבד. |
| 🔴 **קופסה עם 40 חוטים** | לא לבנות. 80 מטר חוט בחדר עם 20 אנשים בטיפול = מכשול פיזי. חוטים עד 2 אנשים. |

| | |
|---|---|
| 🟢 **One person, 2 balls, wired** | Works. ~₪31 in parts. Build this first, as you asked. |
| 🟢 **One person, 2 balls, wireless** | Works — from the PC, the phone, and Chrome/Edge on the site. |
| 🔴 **20 people, 40 balls, each connecting directly** | **Impossible.** Android and Windows stop at 7 connections. The browser needs one approval dialog *per device* — 40 dialogs. There is no version of this that works. |
| 🟢 **20 people, 40 balls, through one box** | Works: the PC talks to **one box**, and the box broadcasts to everyone at once. No limit on how many listen. |
| 🔴 **iPhone / iPad** | Safari will **never** talk to buzzers. Apple has refused. On iPhone: dot and sound only. |
| 🔴 **A box with 40 wires** | Do not build it. 80 m of cable in a room with 20 people in therapy is a trip hazard. Wires top out at 2 people. |

---

# חלק ב׳ — ההכרעות / PART B — THE DECISIONS

לא שלוש אפשרויות. הכרעה אחת לכל שאלה. / Not three options. One decision each.

| # | שאלה / Question | ההכרעה / DECIDED |
|---|---|---|
| 1 | פורמט על החוט / Wire format | **מסגרת בינארית קבועה, 9 בתים.** אותם 9 בתים בדיוק על USB, על BLE ועל השידור. One fixed 9-byte binary frame, identical on all three transports. |
| 2 | מה עם הפרוטוקול הקיים? / The existing ASCII protocol | **נשמר על USB בלבד** (`?` `I` `P` `L` `R` `X`, 115200) כדי ש-`ALMA-EMDR.html` הקיים ימשיך לעבוד ביום הראשון בלי שינוי. הוא **לא** עובר ל-BLE — אין בו מספר סידורי ואין בו תזמון. Kept on USB only, so today's HTML keeps working unchanged. **Not** carried to BLE — it has no sequence number and no schedule. |
| 3 | איך מגיעים ל-40 / Reaching 40 | **גשר אחד.** לקוח → BLE/USB → קופסה → **שידור ESP-NOW** לכולם. אף פעם לא 40 חיבורים. One bridge. Never 40 connections. |
| 4 | סוג הפקודה / Command semantics | **"הפעימה הבאה", לא "הדלק/כבה".** אין פקודת ON. "Next tap", never on/off. There is no ON command. |
| 5 | מי סופר את הזמן / Who keeps time | **הכדור.** הלקוח מנצח, הכדור מנגן. זה מה שמנטרל את הרעד של הבלוטות׳. The ball. The client conducts; the ball plays. This is what cancels Bluetooth jitter. |
| 6 | הצפנה וזיווג / Pairing & encryption | **אין.** בלי pairing, בלי bonding, בלי הצפנה. אין מידע רפואי על הקו — זה כדור שרוטט. קוד חדר בן בית אחד מפריד בין קבוצות. None. There is no PHI on this link. A 1-byte room code separates groups. |
| 7 | סדר הבנייה / Build order | **חוטים קודם, בדיוק כמו שאמרת.** אותה קופסה, אותה קושחה, הופכת אחר כך לגשר האלחוטי. Wired first, exactly as you said. The same box, same firmware, later becomes the wireless bridge. |
| 8 | אנדרואיד: WebView או נייטיב? | **נייטיב (Kotlin).** ל-WebView של אנדרואיד **אין** Web Bluetooth — זו החלטה מכוונת של גוגל, לא באג. עוטפים את ה-HTML = אין באזרים. Native. Android WebView has no Web Bluetooth, by design. |
| 9 | משקפי הקרטון / The cardboard glasses | **בונים, אבל לא ב-SDK.** מציירים את הנקודה פעמיים על מסך שחור, הזזה קבועה. ראה אזהרה בחלק ה׳. Build it, but draw the dot twice ourselves — no VR SDK. See the warning in Part E. |

---

# חלק ג׳ — הפרוטוקול / PART C — THE PROTOCOL

## C.1 The frame — 9 bytes, always

Every message in this system, in both directions, on every transport, is exactly 9 bytes.
Fixed size means no length field, no parser state, no truncation bug.

```
off  field      type      meaning
---  ---------  --------  ----------------------------------------------------------
 0   magic      u8        0xE1   protocol id + version 1. Never anything else in v1.
 1   op         u8        see C.2
 2   seq        u8        increments per frame, wraps 255->0. Duplicate suppression.
 3   room       u8        0 = every room; 1..255 = this room only
 4   side       u8        'L'=0x4C  'R'=0x52  'B'=0x42 (both)  0x00 = none
 5   intensity  u8        0..255. 0 = silent. 1..39 is clamped up to 40 (ERM start).
 6   dur4       u8        pulse length / 4  ->  0..1020 ms in 4 ms steps
 7   delay_lo   u8        } uint16 little-endian, milliseconds, 0..65535
 8   delay_hi   u8        } "the person should FEEL it this many ms from now"
```

**No CRC, deliberately.** BLE has a 24-bit link CRC with retransmission, 802.11 (ESP-NOW)
has an FCS, and USB has a per-packet CRC16. A fourth checksum would only add bytes and the
illusion of safety. What we *do* add is `seq`, because the failure mode that actually
happens on a broadcast link is **loss and duplication**, not corruption.

**Idempotence rule.** A ball keeps the last 8 `(op, seq)` pairs it has acted on for 2000 ms
and **silently ignores a repeat**. Therefore: *the client sends every frame 3 times, ~8 ms
apart.* The first copy to arrive wins — which is also the lowest-latency copy — and the
other two cost nothing. This is how we survive an unacknowledged broadcast without
acknowledgements.

## C.2 Operations — six, and no more

| op | name | direction | meaning |
|---|---|---|---|
| `0x01` | **TAP** | client → ball | One buzz: `side`, `intensity`, `dur4`, felt in `delay` ms. Replaces the pending tap. Arms the dead-man. |
| `0x02` | **STOP** | client → ball | Cancel the pending tap, motor off now. Idempotent. Send 5×. |
| `0x03` | **KEEP** | client → ball | Heartbeat. No buzz. Only resets the dead-man timer — used between sets so the ball stays awake and silent. |
| `0x04` | **SET** | client → ball, **direct link only** | Write `room`, side assignment (`side`), and local intensity scale (`intensity`) to NVS. Never broadcast. |
| `0x05` | **HELLO** | client → ball, direct link only | "Who are you?" Ball answers with STATUS. |
| `0x06` | **STATUS** | ball → client | Reply / notification. Field overload: `4`=side, `5`=battery %, `6`=firmware version, `7-8`=flags u16 LE. |

**STATUS flags (bit → meaning):** 0 motor active · 1 dead-man tripped · 2 charging ·
3 battery low · 4 link=BLE · 5 link=ESP-NOW · 6 link=USB · 7 duty limiter engaged.

## C.3 The pending-tap rule — this is the heart of it

Each ball holds **at most one** pending tap. On receiving a TAP frame:

```
target = now + delay_ms                    (when the person should FEEL it)
fire_at = target - ERM_LEAD_MS             (firmware owns its own actuator lag)

if a pending tap exists with the same side
   and |target - pending_target| < HYSTERESIS_MS:
        keep the pending target       # this is link jitter, not a tempo change
else:
        pending_target = target       # a real change: adopt it

deadman_deadline = now + DEADMAN_MS
```

`HYSTERESIS_MS = 30`. That single line is what converts a Bluetooth connection interval's
0–50 ms of random jitter into a smooth, even rhythm: repeated whispers that agree to within
30 ms are treated as *the same beat restated*, not as a new beat. A real tempo change from
the therapist moves the target far more than 30 ms and is adopted immediately.

## C.4 BLE — service and characteristics

```
Service    d5ffea00-0555-4abc-b5f0-734ccd124d13   ALMA-EMDR Buzzer Service
  RX       d5ffea01-0555-4abc-b5f0-734ccd124d13   Write Without Response   client -> ball
  TX       d5ffea02-0555-4abc-b5f0-734ccd124d13   Notify                   ball -> client
```

- **Write Without Response**, never Write-with-Response. We do not want an ATT round trip
  per buzz; `seq` + triple-send already give us reliability without stalling the link.
- 9 bytes fits inside the default 23-byte ATT MTU. **No MTU negotiation is ever needed** —
  which removes the single most common cross-platform BLE failure.
- **No pairing, no bonding, no encryption.** Justification: bleak issue #1880 (Windows 11
  pairing prompts break connects, `0x800704C7`), and there is no protected health
  information on this link. Accepted residual risk: someone within ~10 m with the right app
  could buzz a ball. The `room` byte and a physical power switch are the mitigation. Say
  this out loud to the עמותה rather than hiding it.

**Advertising.** The 128-bit UUID alone is 18 bytes of a 31-byte ADV packet, so:

- **ADV packet:** Flags (3 B) + Complete 128-bit Service UUID list (18 B) = 21 B.
- **SCAN RESPONSE:** Complete Local Name `EMDR-<room>-<L|R>` + Manufacturer Specific Data
  with company ID `0xFFFF` (the SIG's reserved-for-testing ID — honest for a non-member
  project) carrying `[0x01 proto, room, battery%]`.
- **Advertising interval 20–100 ms.** Not optional: bleak's own docs warn that peripherals
  advertising slower than 1 s take *tens of seconds* to connect on Windows, or never.

**Connection interval:** request 15–30 ms where the platform allows it (Android
`CONNECTION_PRIORITY_BALANCED`, not `HIGH` — `HIGH` fights A2DP for airtime and buys
nothing at 4 events/second). On Windows you cannot set it at all from Python; take the OS
default and let §C.3 absorb it. **Connect using the scanned `BLEDevice` object, never an
address string** — bleak documents that address-based connects break with multiple devices,
and two balls is exactly that case.

## C.5 ESP-NOW — how one box reaches everyone

- Destination `FF:FF:FF:FF:FF:FF` (broadcast). The 20-peer limit applies to *unicast* only;
  broadcast has no peer limit and every listening ball hears the **same radio frame in the
  same air slot**, so ball-to-ball skew is ~1 ms *(design target — the easiest number in
  this whole document to hit, and the one that matters most in a group)*.
- Payload = the same 9 bytes. Nothing is translated at the bridge; it is a repeater, not a
  protocol converter. One firmware, one frame, one set of bugs.
- Fixed channel 1 for the bridge and all balls.
- Not acknowledged — which is exactly why §C.1's triple-send and §C.3's pending-tap design
  exist. A lost frame costs at most one buzz, never a stuck motor and never a stutter.
- **Radio coexistence:** the ESP32-C3 has one 2.4 GHz radio time-shared between Wi-Fi and
  BLE. The **bridge** must run both. Each **ball** advertises BLE only while unpaired, and
  shuts BLE down once it has joined a room over ESP-NOW.

## C.6 USB — the wired box, and backward compatibility

115200 8N1, USB CDC. The parser looks at the first byte:

- `0xE1` → read 8 more bytes, binary frame as above.
- anything else → accumulate until `\n`, parse as **legacy ASCII**:
  `?` identify · `I<40..255>` intensity · `P<40..400>` pulse ms · `L` · `R` · `X` all-off.

`0xE1` is not valid ASCII, so the two modes can never be confused. **This is why today's
`ALMA-EMDR.html` (lines 328–366) works against the new firmware on day one with zero code
changes** — and it is the cheapest reuse available to us.

## C.7 Test vectors — check any implementation against these

```
TAP left,  room 1, seq 7,  intensity 200, 160 ms, now         E1 01 07 01 4C C8 28 00 00
TAP right, room 1, seq 8,  intensity 200, 160 ms, in 120 ms   E1 01 08 01 52 C8 28 78 00
TAP left,  ALL rooms, seq 9, intensity 255, 200 ms, in 250 ms E1 01 09 00 4C FF 32 FA 00
KEEP       room 1, seq 10                                     E1 03 0A 01 00 00 00 00 00
STOP       room 1, seq 11                                     E1 02 0B 01 00 00 00 00 00
STOP       ALL rooms, seq 12                                  E1 02 0C 00 00 00 00 00 00
HELLO      room 1, seq 13                                     E1 05 0D 01 00 00 00 00 00
STATUS     room 1, L, 91% batt, fw 1, link=BLE                E1 06 0D 01 4C 5B 01 10 00
```

Checks: `160/4 = 40 = 0x28` · `120 = 0x0078` → LE `78 00` · `250 = 0x00FA` → LE `FA 00` ·
`91 = 0x5B` · flags `0x0010` = bit 4 = link BLE. **A simulator that reproduces these eight
lines byte-for-byte is protocol-conformant.** Write that simulator before the parts arrive.

✅ **All eight vectors were machine-verified on 2026-09-01** against an independent reference
encoder/decoder (Python 3.12.10) — 8/8 byte-exact, and the three TAP frames round-trip
back to their source fields. The reference codec is 12 lines:

```python
import struct
MAGIC = 0xE1
TAP, STOP, KEEP, SET, HELLO, STATUS = 1, 2, 3, 4, 5, 6
SIDE_L, SIDE_R, SIDE_BOTH, SIDE_NONE = 0x4C, 0x52, 0x42, 0x00

def encode(op, seq, room, side=0, intensity=0, dur_ms=0, delay_ms=0):
    assert 0 <= dur_ms <= 1020 and dur_ms % 4 == 0
    assert 0 <= delay_ms <= 65535
    return (bytes([MAGIC, op, seq & 0xFF, room, side, intensity, dur_ms // 4])
            + struct.pack('<H', delay_ms))

def decode(b):
    assert len(b) == 9 and b[0] == MAGIC
    return dict(op=b[1], seq=b[2], room=b[3], side=b[4], intensity=b[5],
                dur_ms=b[6] * 4, delay_ms=struct.unpack('<H', b[7:9])[0])
```

Range check, also verified: `dur4` reaches 1020 ms; `delay` as u16 reaches 65535 ms, which
covers the slowest half-cycle either client can request (**3333 ms at the browser's 0.15 Hz
minimum**) with room to spare.

---

# חלק ד׳ — סנכרון ובטיחות / PART D — SYNC AND SAFETY

## D.1 מה זה "מסונכרן" במספרים / What "synchronised" means, numerically

הרגע המוגדר: **הרגע שבו העיגול נמצא בקצה.** שלושת החושים צריכים לפגוש אותו.
The defined instant: **the moment the dot is at the edge.** All three senses must meet it.

| pair | target | hard limit | why |
|---|---|---|---|
| **hand ↔ ear** | ±25 ms | ±50 ms | the tightest human window; audio-tactile fusion breaks first |
| **hand ↔ eye** | ±50 ms | ±80 ms | the display itself is quantised at 16.7 ms; vision is more forgiving |
| **ball ↔ ball, across a group** | ±10 ms | ±25 ms | in a group, everyone feeling the *same* beat is the whole point |

"Onset" means **perceived** onset, not electrical onset. An ERM coin motor takes 20–50 ms
to reach useful amplitude, so the firmware owns that lag itself:

```
ERM_LEAD_MS   = 30      fire the PWM 30 ms before the felt target
OVERDRIVE_MS  = 20      first 20 ms (or dur/3, whichever is less) at 255
                        then drop to the commanded intensity
```

This turns the actuator's physics into one firmware constant instead of a system-wide
timing problem that every client would otherwise have to model.

## D.2 The budget, per client

| path | accounting | total *(design target)* |
|---|---|---|
| **PC + wired USB box** | frame quantisation ±8 ms *(measured: QTimer p50 15.7 ms, sd 2.3 ms)* + USB CDC 1–2 ms + ERM lead compensated | **±15 ms** ✅ |
| **PC + BLE, 2 balls** | above + BLE interval jitter 0–50 ms, rejected down to ~±10 ms by §C.3 | **±20 ms** ✅ |
| **Browser + Web Serial** (Chrome/Edge desktop, already implemented) | rAF ±8 ms + serial 1–2 ms | **±15 ms** ✅ |
| **Browser + Web Bluetooth** (Chrome/Edge, Android Chrome) | rAF ±8 ms + BLE, rejected by §C.3 | **±20 ms** ✅ |
| **Group: bridge + ESP-NOW** | PC path + 1–10 ms broadcast; ball-to-ball ~1 ms | **±25 ms absolute, ±10 ms between people** ✅ |
| **Android + Bluetooth headphones, uncompensated** | A2DP end-to-end **308 ms SBC / 369 ms AAC mean, up to 484 ms** on some handsets (SoundGuys, WALT rig, 2 800 samples) | **100–450 ms ❌ FAILS — the buzz beats the sound by up to a whole half-cycle** |
| **Android + BT headphones, compensated (§D.3)** | look-ahead scheduler + per-headphone calibration | **±20 ms** ✅ |

## D.3 A2DP compensation — mandatory on Android, not a nice-to-have

Bluetooth headphones are the **slowest** pipe in the system by an order of magnitude. You
cannot speed audio up, so everything else must **wait for it**. The app therefore runs one
master timeline and schedules *ahead*:

```
for each beat at timeline time T:
    write audio into AudioTrack so it PRESENTS at T   ->  issued at T - L_audio
    draw the dot at T                                 ->  issued at T - 1 frame
    send TAP with delay = 120                         ->  issued at T - 120 ms
```

Since the rhythm is periodic and known from `t0` and the sweep rate, look-ahead is free —
the whole beat sequence is computable a second in advance.

Getting `L_audio`:

1. **`AudioTrack.getTimestamp()`** — the Android CDD requires this to be accurate to **±2 ms**
   (±1 ms strongly recommended) on any device declaring `android.hardware.audio.output`.
   Use it to anchor the timeline. Seed the offset from it.
2. **A calibration slider is mandatory before first clinical use.** There is no public
   Android API that returns end-to-end A2DP latency — the HAL knows encoder offsets only.
   Do what rhythm games do: *"tap when the buzz and the beep feel like one thing"*, ±10 ms
   steps, 0–500 ms range, **stored per paired headphone**. Twenty seconds, once.
3. **If measured `L_audio` > 250 ms, the app must warn and recommend wired headphones.**
   Do not silently deliver a badly-timed session to someone in trauma processing.
4. Escape hatches: wired USB-C/3.5 mm (latency ≈ 0, and the right default for clinical use);
   or LE Audio/LC3 at 20–30 ms where both phone and buds support it — a bonus, never a
   dependency.

## D.4 A client-side requirement that is part of this protocol

**Clients MUST derive taps from phase crossing, never from a pixel or position threshold.**

This is not style. In `emdr_widget.py` the current edge test is a 6-pixel band combined
with a random amplitude jitter of ±2% (`_amp_jitter`, set in `EmdrSequence.start`). When the
jitter is negative the orb **never reaches the band**, and the edge event never fires — for
the entire session, silently. Measured share of seeds affected: **32.8 % at 1920 px, 37.3 %
at 2560 px, 41.6 % at 3840 px.** The default seed 42 happens to work, which is why nobody
has caught it. A buzzer attached to that test would simply never buzz for a third of users,
and more often on bigger screens.

The correct form, in every client:

```
crossings = floor((phase - lead_rad + PI/2) / PI) - floor((phase_prev - lead_rad + PI/2) / PI)
if crossings > 0:  fire once, side = sign(cos at the crossing)
lead_rad = 2*PI * hz * lead_seconds
```

Immune to amplitude jitter, cannot be skipped by a dropped frame (the current 6 px window is
open for only **25 ms at 2 Hz** — shorter than the measured p99 frame of 31 ms), and it turns
the existing systematic early-fire (25.1 ms on the PC, 27.6 ms in the browser at 1 Hz) from
an accident into `lead_seconds`, an explicit calibration knob we can spend on link latency.

## D.5 The dead-man rule — five independent layers

**כלל הברזל: לכדור אין מצב "דולק". יש לו רק ספירה לאחור.**
**Iron rule: the ball has no ON state. It only ever has a countdown.**

| failure | what saves the person |
|---|---|
| the app crashes, the laptop sleeps | **dead-man: no frame for 1500 ms → pending tap cancelled, PWM zero, LED amber** |
| BLE drops mid-set | dead-man, **plus** BLE `onDisconnect` → immediate all-off |
| a STOP packet is lost | dead-man, **plus** STOP is repeated 5× |
| the firmware hangs | **MCU watchdog, 2000 ms → reboot → GPIO low** |
| brown-out, dead MCU, flat battery | **10 kΩ gate pull-down to ground on the MOSFET** — a floating or dead pin is motor OFF, in hardware |
| a corrupt frame asks for 10 seconds of buzz | firmware clamp `DUR_MAX = 600 ms`, one-shot timer armed in the *same instruction* that starts the PWM |
| a command storm cooks the hand or the motor | **duty limiter: max 60 % over any rolling 2000 ms window**; excess taps are *refused*, not truncated, and STATUS bit 7 is raised |
| someone else's box in radio range | `room` byte |
| everything, always | **a physical slide switch on each ball** |

Firmware constants, all of them:

```
DEADMAN_MS      1500     no frame for this long -> stop and stay stopped
HYSTERESIS_MS     30     jitter rejection band (§C.3)
DUR_MIN_MS        40     below this the ERM does not move at all
DUR_MAX_MS       600     hard clamp regardless of what was asked
DELAY_MAX_MS    8000     hard clamp
INTENSITY_FLOOR   40     below this the ERM will not start; 1..39 clamps up
DUTY_MAX_PCT      60     over a rolling 2000 ms window
WDT_MS          2000     MCU watchdog
ERM_LEAD_MS       30     actuator lead (§D.1)
OVERDRIVE_MS      20     start-of-pulse kick at 255
```

**A UI rule that follows from the motor, not from software:** pulse length must satisfy
`150 ms ≤ dur ≤ min(400, 250/hz)`. At 2 Hz that ceiling is 125 ms, which is *below* the
150 ms ERM floor — so **above about 1.6 Hz the taps stop feeling distinct.** All three
clients should clamp the slider and say so plainly rather than delivering mush. Visual and
audio remain fine at any rate; only the haptics degrade.

---

# חלק ה׳ — סדר הבנייה / PART E — BUILD ORDER

## שלב 1 — חוטים. השבוע. ~₪31. / Phase 1 — wires. This week. ~₪31.

לוח ESP32-C3 אחד כ-USB, שני שקעי 3.5 מ״מ, שני מנועי רטט, שני חוטים, שני כדורים.
המחשב מדבר דרך `pyserial` (כבר מותקן, גרסה 3.5 — אפס תלויות חדשות), והדפדפן דרך Web Serial
(כבר כתוב ב-`ALMA-EMDR.html`). **בלי רדיו בכלל.** זו אמת המידה: כל טענת זמן על השלבים
הבאים נמדדת מול המספר הזה.

One ESP32-C3 as a USB device, two 3.5 mm jacks, two ERM motors, two cables, two balls. The
PC uses `pyserial` *(verified installed here: 3.5, Python 3.12.10 — zero new dependencies)*;
the browser uses Web Serial, **already written**. **No radio at all.** This is the ground
truth every later latency claim is measured against.

## שלב 2 — אלחוטי לזוג אחד / Phase 2 — wireless, one pair

אותו לוח, אותה קושחה, מוסיפים BLE. שני כדורים ישירות מהמחשב / מהטלפון / מכרום.
מוכיח את שלושת הלקוחות מול פרוטוקול אחד.
Same board, same firmware, BLE added. Two balls, direct. Proves all three clients against
one protocol.

## שלב 3 — הקבוצה / Phase 3 — the room

**קופסת ה-USB משלב 1 *היא* הגשר.** לא זורקים כלום — מוציאים את החוטים והכדורים ממשיכים
אלחוטית. מודדים ב-4 כדורים, אחר כך 12, אחר כך 40, **בחדר האמיתי.** לא מבטיחים 40 עד שמדדנו 40.

**The USB box from Phase 1 *is* the bridge.** Nothing is thrown away — you unplug the wires
and the balls go wireless. Measure at 4 balls, then 12, then 40, **in the actual room.**
Do not promise 40 to the עמותה until 40 has been measured.

A mixed room works by construction: the therapist's own pair on wires, everyone else on the
broadcast, all from the same box and the same frame.

## שלב 4 — אנדרואיד + הקרטון / Phase 4 — Android + the cardboard

Native Kotlin. Reuse the **protocol and the timing model**, not the HTML — Android WebView
has no Web Bluetooth and that is Google's deliberate position, not an oversight.

**⚠️ אזהרה כנה על משקפי הקרטון / An honest warning about the cardboard glasses**

אני בונה את זה אם תרצה, אבל אני חייב לומר שלושה דברים לפני:

1. **האופטיקה נלחמת בטיפול.** ב-EMDR צריך שהעין תנוע רחב לצדדים. בקרטון הזול, בדיוק הקצוות
   — החלק שחשוב — נופלים בשולי העדשה, במקום הכי מטושטש והכי מעוות.
2. **זה מסתיר את הפנים של המטופל.** מטפל ב-EMDR מסתכל על הפנים כדי לדעת מתי לעצור. לעמותה,
   עם אנשים אמיתיים במצוקה אמיתית — זו **נסיגה בבטיחות**, לא תוספת.
3. **שום דבר ב-EMDR לא צריך תלת-ממד.** אין ראיה שנקודה תלת-ממדית עדיפה על נקודה רגילה.

I will build it if you want it, but three things first:

1. **The optics fight the therapy.** EMDR needs a wide horizontal sweep. In cheap cardboard,
   the extremes — exactly the part that matters — land at the lens edge, the blurriest and
   most distorted region.
2. **It hides the client's face.** An EMDR clinician watches the face to know when to stop a
   set. For real people in real distress, occluding the face is a **safety regression**.
3. **Nothing in EMDR needs stereo depth.** There is no evidence a 3D dot beats a flat one.

If you still want it — and you may have a reason I do not, like cutting out the room, or
the appeal for kids — the least-effort path is a plain `SurfaceView` drawing the same dot at
±IPD/2 on a black field. **No Cardboard SDK, no Unity.** For one dot on black you genuinely
do not need lens profiles or a distortion mesh, and black hides the edge artefacts. The
buzzers and the headphones work identically either way — they do not care what the screen is
mounted in.

---

# חלק ו׳ — מה עוד לא נבדק / PART F — WHAT IS NOT PROVEN

| claim | status |
|---|---|
| Frame format, ops, test vectors | ✅ **specified and self-consistent** — checkable today by a simulator |
| PC frame timing, QTimer jitter | ✅ **measured on this machine** (p50 15.7 ms, sd 2.3 ms, p99 31 ms) |
| The `_amp_jitter` seed defect (§D.4) | ✅ **measured** — 32.8 % / 37.3 % / 41.6 % of seeds silent at 1920 / 2560 / 3840 px |
| `pyserial` present, `bleak` absent | ✅ **verified** — 3.5 present; `pip install bleak` still needed for Phase 2 |
| `EMDR1.ino` is prior art | ❌ **FALSE.** It is the stock Arduino `Blink` example, header comment and all, four pins toggling on a 1000 ms `delay()`. No serial, no protocol, no motor driver. It is a statement of intent. The firmware is written from scratch. |
| Every latency number marked *(design target)* | ⚠️ **UNTESTED AGAINST REAL HARDWARE.** No hardware exists. Build the Phase-1 box and re-measure before quoting any of these to the עמותה. |
| ESP-NOW skew ~1 ms at 40 balls | ⚠️ **untested.** Vendor figure. Verify at 4, 12, 40, in the real room, with 20 phones present. |
| ESP32-C3 SuperMini antenna | 🔴 **known hardware defect.** Buy the "SuperMini **Plus**" (U.FL + FPC antenna) or the Seeed XIAO ESP32C3 — not the cheapest generic board. At 5 m across a room this is the difference between working and not. |
| A2DP latency figures | ✅ independently measured (SoundGuys/WALT, 2 800 samples) — but **on other handsets.** Calibrate on his. |

## Broken windows found while writing this — reported, not fixed

The other workflow owns `emdr_widget.py` right now, so nothing was touched.

1. 🔴 **The PC edge beep silently never fires for ~1/3 of seeds** (§D.4). This is the one to fix first, and it is a bug in the *existing* product, before any buzzer exists.
2. 🟡 **The edge window is 25 ms at 2 Hz, shorter than the p99 frame (31 ms)** — one stalled frame near the apex skips a beat entirely.
3. 🟡 **`soundcard_pan.py` is the widget's default audio path** and calls `IAudioEndpointVolume::SetChannelVolumeLevelScalar` on the **default system render endpoint** ~55 times a second for a whole session, dipping one channel to 0.15 — panning every application on the machine. That is a process modulating Iddo's output-device channel volumes, which is exactly what the **Sacred Audio Law** forbids. It was not changed. **The buzzers are the argument for switching it off:** haptics on the hands deliver the bilateral cue without touching the soundcard at all. `pan_output_mode: "Off"` + buzzers is both law-clean and lower-latency.
4. 🟢 Cosmetic: the orb visibly jumps left-to-centre at t=0 (`start()` paints at `x_min`, the first tick puts it at `sin(0)=0`), and `ALMA-EMDR.html` line 391 computes a `side` variable that is never used.

---

**Files this protocol touches (none were modified by this document):**
`D:\CLAUDE\emdr\source-emdr-central\emdr_widget.py` · `D:\CLAUDE\emdr\source-emdr-central\soundcard_pan.py` ·
`D:\CLAUDE\emdr\app\ALMA-EMDR.html` · `D:\CLAUDE\emdr\source-emdr-central\EMDR1_Arduino\EMDR1.ino`

**Nothing was bought, ordered, deployed or published. No audio device was opened.**
**לא נקנה כלום, לא פורסם כלום, ולא נפתח שום התקן שמע.**
