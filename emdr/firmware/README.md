# ALMA-EMDR buzzer firmware — קושחת הבאזרים

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

> ⚠️ **סטטוס: הקוד מתקמפל. אין חומרה. / STATUS: THE CODE COMPILES. THERE IS NO HARDWARE.**
> נבנה ואומת כאן ב-2026-09-01 עבור ESP32-C3. **שום שורה כאן לא רצה על מנוע אמיתי.**
> Built and verified here on 2026-09-01 for the ESP32-C3. **Not one line of this has
> ever driven a real motor.** Every timing number is a design target until the first
> board is on the bench.

---

## מה זה / What this is

שתי מכונות, קושחה אחת. / Two machines, one firmware.

| role | what it is | build |
|---|---|---|
| **BALL** — הכדור | The thing in the hand. One ERM motor, a BLE GATT server, an ESP-NOW listener. | `pio run -e ball` |
| **BRIDGE** — הקופסה | The box on the desk. USB in; two **wired** jacks out (Phase 1) *and* an ESP-NOW broadcast (Phase 3). | `pio run -e bridge` |

**הקופסה של שלב 1 היא הגשר של שלב 3.** מוציאים את החוטים — הכדורים ממשיכים אלחוטית.
**The Phase-1 wired box IS the Phase-3 bridge.** You unplug the wires and the balls go
wireless. Nothing is thrown away. That is why "wires first, radio later" was the right
order.

---

## Build — the exact commands

```bash
# Windows: this line is not optional. Without it the PlatformIO CLI throws a
# UnicodeEncodeError before it ever reaches a compiler.
set PYTHONIOENCODING=utf-8

cd D:\CLAUDE\emdr\firmware
pio run -e ball          # the ball
pio run -e bridge        # the USB box
pio run -e ball -t upload --upload-port COM7     # flash
pio device monitor -b 115200
```

Environments: `ball`, `bridge` (ESP32-C3-DevKitM-1) and `ball_xiao`, `bridge_xiao`
(Seeed XIAO ESP32C3). Platform is **pinned** to `espressif32@6.13.0`
(Arduino-ESP32 2.0.16 / ESP-IDF 4.4). The sources also compile on Arduino-ESP32 3.x —
every API that moved (`ledcAttach`, `esp_task_wdt_init`, the ESP-NOW receive callback)
is guarded on `ESP_ARDUINO_VERSION_MAJOR` / `ESP_IDF_VERSION_MAJOR` — but 6.13.0 is
what this was actually built against.

### VERIFIED HERE — 2026-09-01

```
ball    SUCCESS   RAM 18.0% (58 908 B)    Flash 44.2% (1 389 126 B of 3 145 728)
bridge  SUCCESS   RAM 11.6% (37 876 B)    Flash 22.5% (  709 248 B of 3 145 728)
```

**And the wire protocol is proven at compile time.** `include/emdr_frame.h` asserts all
eight PROTOCOL C.7 test vectors with `static_assert`, byte by byte, against the very
`constexpr` function that `emdr_encode()` calls at run time. **If the firmware compiles,
the encoder is byte-exact.** No hardware and no simulator needed for that one claim —
the RISC-V compiler checked it. The Android client proves the same eight vectors on the
JVM (`android/app/src/test/.../BuzzerFrameTest.kt`), so both ends of the link are
verified against identical numbers by two different toolchains.

### Arduino IDE, if you prefer it

There is no second copy of the code. Put every file from `src/` and `include/` into one
folder called `EMDR_Firmware`, rename `main.cpp` to `EMDR_Firmware.ino`, and open it.
Arduino compiles every `.cpp`/`.h` beside the sketch, so nothing else changes. Pick the
role by editing the one marked line in `include/emdr_config.h`:

```c
#define EMDR_ROLE_BALL 1        /* <-- 1 = ball, or swap to EMDR_ROLE_BRIDGE */
```

Board: **ESP32C3 Dev Module**. Set *USB CDC On Boot: Enabled* and *Partition Scheme:
Huge APP (3MB)* — BLE + Wi-Fi + ESP-NOW do not fit the 1.2 MB default.

---

## Files

```
include/emdr_frame.h    the 9-byte wire protocol + the C.7 vectors as static_asserts
include/emdr_config.h   every tunable constant, and the role switch
include/emdr_motor.h    one ERM channel and all five safety layers
include/emdr_dedup.h    C.1 idempotence: last 8 (op,seq) pairs for 2000 ms
src/emdr_motor.cpp      the countdown, the overdrive, the dead-man, the duty limiter
src/emdr_ball.cpp       GATT server, ESP-NOW listener, NVS identity, STATUS
src/emdr_bridge.cpp     USB parser (binary + legacy ASCII), ESP-NOW broadcast, 2 jacks
src/main.cpp            setup()/loop() dispatch
```

---

## 🩺 The safety design, in one screen

> **חוק הברזל: לכדור אין מצב "דולק". יש לו רק ספירה לאחור.**
> **Iron rule: the ball has no ON state. It only ever has a countdown.**

There is deliberately **no `on()` method** on `EmdrMotor`. The only way to make the
motor move is to schedule a tap that already carries its own end time.

| # | layer | where |
|---|---|---|
| 1 | **dead-man** — no frame for `DEADMAN_MS` (1500) → motor off, and it stays off | `EmdrMotor::tick()` |
| 2 | **link loss** — BLE `onDisconnect` is an immediate all-off, without waiting | `BallServerCallbacks::onDisconnect` |
| 3 | **MCU watchdog** — 2000 ms → reboot → GPIO low | `esp_task_wdt_*` |
| 4 | **hardware** — a 10 kΩ gate pull-down to GND. A dead or floating MCU is motor-OFF *in hardware*, with no software involved | **the board, not this repo** |
| 5 | **duty limiter** — max 60 % over any rolling 2000 ms. Excess taps are **refused, not truncated**, and STATUS bit 7 is raised | `EmdrMotor::dutyAllows_` |
| + | `DUR_MAX_MS` 600 clamp, with the end time written **before** the PWM starts | `EmdrMotor::tick()` |
| + | a physical slide switch on each ball | the board |

**Layer 4 is not optional and it is not in this repository.** Do not skip the 10 kΩ
pull-down because "the firmware sets the pin low on boot" — the whole point of that
resistor is the moment when there is no firmware running at all.

Two more details that are easy to get wrong and are done right here:

- **Every deadline is a signed difference** (`(int32_t)(now - deadline) >= 0`), never
  `now > deadline`. `millis()` wraps every 49.7 days and a therapy box may well be left
  plugged in that long.
- **There is no `delay()` anywhere in this firmware.** A `delay()` is a window in which
  the dead-man cannot fire.

---

## 🔌 Wiring — one channel

```
   GPIO 3  ──[ 100 Ω ]──┬── gate    N-ch logic-level MOSFET (AO3400A / 2N7002)
                        │
                     [ 10 kΩ ]      ← THE SAFETY RESISTOR. Gate to GND.
                        │              Without it a dead MCU can leave the
                       GND             gate floating and the motor twitching.

   V+  ──┬── motor + ───────┐
         │                  │
      [ 1N4148 ]            │        flyback diode, cathode to V+
         │                  │
         └── motor - ───────┴── drain

   source ── GND
```

Pins are in `include/emdr_config.h` and can be overridden with `-D` without touching
the code:

| | ball | bridge |
|---|---|---|
| `PIN_MOTOR_A` | GPIO 3 — the only motor | GPIO 3 — LEFT jack |
| `PIN_MOTOR_B` | — | GPIO 4 — RIGHT jack |
| `PIN_LED` | GPIO 8 (active LOW) | GPIO 8 |
| `PIN_SIDE_SELECT` | GPIO 5 — jumper to GND = RIGHT, open = LEFT | — |
| `PIN_VBAT_ADC` | GPIO 2, through a 2:1 divider | — |

**LED language:** solid while a pulse is out · slow blink (1.2 s) = idle and healthy ·
**fast blink (150 ms) = the dead-man has tripped, nobody is talking to me.**

### ⚡ One honest electrical warning

A 3 V ERM coin motor run straight off a full 4.2 V LiPo is being over-volted by 40 %.
It will work and it will feel strong, and it will wear out early. Either fit a **10 Ω
series resistor**, or leave the per-ball intensity scale (the `SET` command) at about
**70 %**. The firmware cannot see the difference, so this is a build decision, not a
software one.

---

## 🧾 Parts — indicative prices, not quotes. Nothing has been ordered.

**Phase 1, the wired box + two balls — the whole thing:**

| part | qty | ≈ each |
|---|---|---|
| ESP32-C3 SuperMini **Plus** or Seeed XIAO ESP32C3 | 1 | ₪12–25 |
| ERM coin motor, 10 mm, 3 V | 2 | ₪3–6 |
| AO3400A / 2N7002 MOSFET | 2 | ₪0.5 |
| 1N4148 diode, 10 kΩ, 100 Ω, 10 Ω | — | pennies |
| 3.5 mm TRS jack + plug + cable | 2 | ₪4–8 |
| a ball to put it in | 2 | ₪0–10 |

Roughly **₪31–70** depending on where you buy and whether the balls cost anything.
Phase 2 (wireless) adds one board, one LiPo (150–400 mAh), one TP4056 and one slide
switch **per ball** — about ₪25–40 each.

> 🔴 **Buy the "SuperMini **Plus**" (U.FL + FPC antenna) or the Seeed XIAO ESP32C3 — not
> the cheapest generic SuperMini.** The plain SuperMini has a known bad on-board
> antenna. At 5 m across a therapy room that is the difference between working and not.

---

## The USB protocol, and why today's browser app still works

`src/emdr_bridge.cpp` looks at **one byte**:

| first byte | meaning |
|---|---|
| `0xE1` | read 8 more — the binary frame (PROTOCOL C.1) |
| anything else | accumulate to `\n` — **legacy ASCII**: `?` `I<40..255>` `P<40..400>` `L` `R` `X` |

`0xE1` is not valid ASCII, so the two can never be confused. **That is why
`D:\CLAUDE\emdr\app\ALMA-EMDR.html` (lines 328–366) drives this firmware on day one
with zero code changes.**

One extension, flagged rather than hidden: an ASCII `L`/`R` has no sequence number and
no schedule, so the bridge gives it one of its own (`seq` from its own counter,
`delay = 0`) and broadcasts a proper binary frame. A legacy client therefore reaches
wireless balls too — **at legacy timing quality, with no look-ahead**. Set
`-D EMDR_ASCII_BRIDGES_TO_RADIO=0` to keep ASCII strictly on the wires.

---

## ❌ What is NOT proven

| claim | status |
|---|---|
| It compiles for ESP32-C3, both roles | ✅ **verified here**, 2026-09-01 |
| The 8 C.7 test vectors are byte-exact | ✅ **proven at compile time** by the RISC-V compiler |
| Anything about a motor, a hand, a battery or a radio | 🔴 **untested against real hardware — no hardware exists** |
| `ERM_LEAD_MS = 30` is the right actuator lead | ⚠️ a book number. Measure it on the first ball and change the constant. |
| ESP-NOW ball-to-ball skew ~1 ms at 40 balls | ⚠️ vendor figure. Measure at 4, then 12, then 40, **in the real room, with 20 phones present.** |
| BLE + Wi-Fi coexistence on one C3 radio | ⚠️ compiles and is configured correctly; **never run** |
| Nothing was bought, ordered or flashed | ✅ |

**`EMDR1_Arduino/EMDR1.ino` is not prior art.** It is the stock Arduino `Blink`
example, header comment and all, four pins toggling on a 1000 ms `delay()`. No serial,
no protocol, no motor driver. This firmware was written from scratch.

---

**הפרוטוקול המחייב / The binding protocol:** `D:\CLAUDE\emdr\PROTOCOL-buzzers-20260901.md`
**הלקוח לאנדרואיד / The Android client:** `D:\CLAUDE\emdr\android\`
