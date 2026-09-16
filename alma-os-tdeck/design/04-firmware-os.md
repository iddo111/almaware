# 04 — Firmware / OS Architecture + Hebrew UI

לזכרה של עלמה ז"ל · ALMAWARE
Companion to `ARCHITECTURE.md` (v0.1 skeleton, already flashed-ready code under
`src/`). This doc formalizes the v0.2+ **OS shape**: FreeRTOS tasks, an event
bus, and a concrete plan for Hebrew RTL on the ST7789 — plus a scaffold under
`firmware/` for the next phase of work. It does not replace `src/` (which
stays the buildable v0.1); it is the blueprint the swarm grows `src/` into.

---

## 1. ESP-IDF vs Arduino-ESP32 — recommendation: **stay on Arduino-ESP32**

v0.1 already made this call (`platformio.ini`, `framework = arduino`) and it
is the right one to keep, for concrete reasons:

- **Arduino-ESP32 *is* FreeRTOS underneath.** `setup()`/`loop()` runs as a
  FreeRTOS task (`loopTask`) on core 1; `xTaskCreatePinnedToCore` is available
  today, no framework swap needed to add more tasks. We lose nothing by
  staying.
- **Peripheral drivers we already wrote** (`display_st7789.cpp`,
  `radio_sx1262.cpp`, keyboard/trackball polling) sit directly on
  `SPI.h`/`Wire.h`/`digitalRead` — thin HAL calls that exist identically in
  ESP-IDF's `driver/spi_master.h` etc., but rewriting them buys us nothing;
  the purity law is about *our logic*, not which init macro toggles a GPIO.
- **ESP-IDF's advantage (finer partition/component control, native
  menuconfig)** matters at 100+ files and multiple binaries. We are one
  firmware image; PlatformIO's `board_build.partitions=default_16MB.csv`
  already gives us full flash-layout control without IDF's build complexity.
- **Team velocity**: swarm agents write drivers and cards fastest in the
  Arduino idiom already established. A framework migration mid-flight would
  freeze feature work for a purity gain of approximately zero (IDF is also
  Apache-2.0 Espressif code sitting *below* our layer, exactly like the
  Arduino core is now).

**Verdict: Arduino-ESP32 core = toolchain, like the compiler. Everything
above `Arduino.h`/`SPI.h`/`Wire.h` is ours.** Revisit only if we ever need
IDF-only features (e.g. ESP-NOW mesh fallback, coex with BLE mesh) — not
currently planned.

## 2. Task / RTOS structure

v0.1 is a single cooperative loop (`loop()` does kb-poll → trackball-poll →
mesh-poll → tick, each non-blocking, `delay(2)`). That is correct for v0.1's
scope but two things don't cooperate well as we add voice and a bigger
assistant: **blocking SPI transactions** (display full-screen redraw ~15 ms,
LoRa TX ~50-200 ms at SF9) and **I2S audio capture/playback** which wants a
steady real-time cadence. v0.2 moves to real FreeRTOS tasks, still on one
core-pinning scheme that keeps radio/audio realtime-safe and UI/assistant
best-effort:

```
Core 0 (protocol core, PRO_CPU)          Core 1 (app core, APP_CPU)
──────────────────────────────           ──────────────────────────────
alma_radio_task   (prio 5, 4KB)          alma_ui_task      (prio 3, 8KB)
  - SX1262 IRQ-driven RX/TX                - kb + trackball + touch poll
  - mesh framing/dedupe/routing             - draw dirty regions only
  - posts RX events to bus                 - consumes bus events -> redraw

alma_audio_task   (prio 5, 4KB)          alma_assistant_task (prio 1, 8-16KB,
  - I2S mic capture / speaker out            uses PSRAM for model buffers)
  - VAD + framing, posts to bus              - tier-0 rules now; tier-1 byte-LM
                                              later; never blocks UI

(WiFi/BT stacks, unused, disabled)       alma_storage_task (prio 2, 4KB)
                                            - SD/LittleFS writes, batched
                                            - message DB, contacts, keys
```

- **Why this split**: SX1262 IRQ (DIO1) and I2S DMA callbacks are
  latency-sensitive; pinning them to core 0 (which also hosts the WiFi/BT
  RTOS internals we don't use) keeps them away from UI redraw jank on core 1.
  UI, assistant and storage are not latency-critical — a 20 ms UI hiccup is
  invisible; a missed LoRa symbol is a lost packet.
- **Stack sizes** are conservative starting points (`xTaskCreatePinnedToCore`
  last-but-one arg); tune via `uxTaskGetStackHighWaterMark()` once real code
  lands.
- **Priorities**: radio/audio (5) > storage (2) > UI (3, above storage so
  input feels responsive) > assistant (1, background/best-effort — it must
  never starve the radio task since mesh delivery is the core promise).
- **No dynamic task creation.** All five tasks are created once in `setup()`
  and live forever — matches the "one binary, no process model" firmware-OS
  philosophy in `ARCHITECTURE.md` §1.

### Event bus

A single bounded FreeRTOS queue (`xQueueCreate`) of a tagged union
`AlmaEvent`, **not** five separate queues — keeps fan-out simple (UI is the
only many-to-one consumer that matters; radio/audio/storage are producers).

```c
typedef enum {
  EVT_KEY, EVT_TRACKBALL, EVT_MESH_RX, EVT_MESH_TX_DONE,
  EVT_AUDIO_FRAME, EVT_ASSISTANT_REPLY, EVT_BATTERY, EVT_TICK_1S,
} AlmaEventType;

typedef struct {
  AlmaEventType type;
  uint32_t      ts_ms;
  union {
    KeyEvent      key;
    TBDir         trackball;
    AlmaMessage   mesh_rx;
    AudioFrame    audio;      // small header + SD/PSRAM offset, not raw samples
    AssistantReply assistant;
    float         battery_v;
  } data;
} AlmaEvent;

extern QueueHandle_t g_alma_bus;   // xQueueCreate(32, sizeof(AlmaEvent))
```

Producers `xQueueSend` (non-blocking, drop-oldest policy on full — a queue
full of unconsumed events means UI is wedged, and dropping is safer than
blocking the radio task). `alma_ui_task` is the sole consumer and dispatches
to the active card's `onEvent()`, replacing the current direct
`kb.poll()`/`ball.poll()` calls inside `loop()`. This is the direct
successor to today's `Card` struct in `cards.h` — same shape, driven by the
bus instead of being polled inline in `main.cpp`.

## 3. Hebrew RTL rendering — the differentiator, concretely

This is already working in v0.1; this section documents *why* it works and
what v0.2 adds.

### 3.1 Font: ours, generated, bitmap

`tools/fontgen.py` rasterizes *Frank Ruhl Hofshi* (SIL-OFL license — free,
redistributable, not a runtime dependency, purity-clean) at 12px into
`src/font_hebrew.h`: a flat `uint8_t` array, 8×16 1-bpp cells, 124 glyphs
(ASCII 0x20-0x7E + Hebrew alef-bet + 5 finals + geresh U+05F3/gershayim
U+05F4 + a few niqqud-free punctuation). ~2 KB total — this is the entire
"font engine": no TTF parser on-device, no FreeType, no LVGL font decoder.
The glyph table is a `const uint32_t codepoint[]` parallel array + bitmap
offset, so lookup is a linear scan over 124 entries (fine at 50 Hz keyboard
rates; a binary search is a trivial upgrade if we ever have >500 glyphs for
Arabic/extended Latin).

**Why bitmap, not vector**: an ESP32-S3 at 240 MHz redrawing a 320×240
screen has no budget for on-the-fly rasterization. A blitted 8×16 (or scaled
16×32, 24×48) glyph is a tight loop of `pushPixels()` calls straight over
SPI — this is what makes "no framebuffer" possible (§3.4).

### 3.2 RTL shaping — the actual algorithm

Text is stored **in logical (typed) order** in memory the whole time
(`String input` in `main.cpp`) — never reversed in the buffer. Reversal only
happens at *draw time*, in `DisplayST7789::drawTextRTL()`:

1. Start a cursor at `xRight` (the right edge of the text box — RTL's home
   position) and a **run scanner** over the logical string.
2. Walk the string decoding UTF-8 codepoints (`utf8Next`, `src/utf8.h`).
   Classify each codepoint: Hebrew block (U+0590–U+05FF, `cpIsHebrew()`) vs.
   "LTR/neutral" (ASCII letters, digits, punctuation, spaces).
3. Group consecutive codepoints of the **same class** into a *run*. This is
   a simplified version of the UAX#9 "explicit levels" pass: two
   embedding levels only (RTL base paragraph, LTR runs for numbers/Latin),
   no override/isolate characters, no combining marks. Sufficient for the
   real chat traffic this device will see (Hebrew sentences with embedded
   COM ports, numbers, English tech words).
4. Runs are emitted **right to left**: take the last run in logical order
   first. Within a Hebrew run, glyphs are blitted right-to-left (cursor
   decreases by glyph width each step, matching reading direction). Within
   an embedded LTR run, glyphs are blitted **left-to-right relative to each
   other** but the whole run is still positioned before (visually left of)
   the run that logically follows it in the Hebrew flow — i.e. "3 COM" stays
   "3 COM" and not "MOC 3", while sitting in its correct RTL slot.
5. Advance the cursor leftward by the total run width after each run;
   return final leftmost x (used today to place the input-line cursor block
   in `main.cpp:drawInput()`).

This is deliberately **not** a full UAX#9 bidi engine (no bracket pairing,
no isolates, no vertical text, no Arabic joining forms) — an honest, scoped
cut, called out in `ARCHITECTURE.md` §4 already. It is complete enough for:
mixed Hebrew/English/numeric chat lines, status bars, and Hebrew punctuation
(maqaf, geresh, gershayim, quotes around English words).

**v0.2 additions to the shaper**:
- Word-wrap: current draw calls assume one line fits the box (chat/input
  are short-form); a `layoutParagraph()` helper will do RTL-aware wrapping
  for longer assistant replies (breaking at spaces, keeping LTR runs intact).
- Niqqud (vowel points) are out of scope — they're combining marks requiring
  glyph composition; the font has none. Modern Hebrew UI text is
  unpointed, so this is a non-issue for chat/menus.

### 3.3 Mixed bidi + numbers — worked example

Input `"שלח 3 הודעות ל-COM5"` (logical/typed order, left-to-right in the
source file because that's how UTF-8 bytes sit):

```
runs (logical order):  [שלח](HE) [ ](neutral→attaches to neighbor) [3](LTR)
                       [ הודעות ל-](HE, includes the hyphen as neutral-in-HE)
                       [COM5](LTR)
draw order (right to left): "שלח" → "3" → " הודעות ל-" → "COM5"
visual result (screen, right to left reading):  שלח 3 הודעות ל-COM5
```

Numbers and the Latin "COM5" render left-to-right *within their own run*
while the run itself sits in the correct rightward position relative to the
Hebrew words around it — exactly the visual convention native Hebrew
speakers expect from typed chat.

### 3.4 Why no framebuffer

`display_st7789.cpp` sets an SPI addressing window (`setWindow`) per glyph
and streams pixels directly — 320×240×2 bytes (150 KB) is not allocated
anywhere. This matters because:
- It works identically before/after PSRAM init (glyphs render during boot
  before `psramInit()` even runs).
- The full 8 MB PSRAM stays reserved for the assistant's model weights
  (§8 of `ARCHITECTURE.md`) and audio buffers — not spent on a framebuffer
  we don't strictly need for a mostly-text UI.
- Trade-off, stated honestly: partial/diffed redraws are harder without a
  backing buffer (today we just `fillRect` + redraw the dirty region, which
  can flicker slightly on full-log redraws). v0.2 may add a **small
  scanline-strip buffer** (e.g. one glyph row, 320×16×2 = 10 KB) for
  flicker-free scrolling without paying for a full frame — a middle ground,
  not a reversal of the no-framebuffer design.

### 3.5 Keyboard input for Hebrew

Already implemented (`src/keyboard.h`): the kb co-processor sends raw
US-QWERTY ASCII; `Keyboard::mapKey()` remaps through the **standard Israeli
physical layout** (same key positions typists already know: q→/, w→geresie,
e→ק, r→ר, t→א …) entirely in OS software — the kb firmware itself is
untouched/unknown-vendor code we don't need to modify. `$` toggles HE/EN
mode (a rarely-used key on the Q10 physical layout, safe to repurpose).
Backspace strips one **UTF-8 codepoint** (not one byte) — critical for
Hebrew since every letter is a 2-byte UTF-8 sequence
(`0xD7 0x90`-`0xD7 0xAA` range).

## 4. App / UI framework

**Recommendation: keep our own immediate-mode card renderer; do not adopt
LVGL, even as "tooling."** Reasoning:

- LVGL's font/text pipeline assumes its own bidi and font-decoder path;
  bolting our from-scratch Hebrew shaping *underneath* LVGL means fighting
  its text layout rather than reusing it — we'd get none of LVGL's benefit
  (its Hebrew/RTL/BiDi support is incomplete and not why we'd pull it in)
  while inheriting ~40 KB+ of flash and a widget model built for touchscreens
  with a framebuffer, which conflicts directly with §3.4's no-framebuffer
  design.
- The ALMAWARE purity law (`ARCHITECTURE.md` §1: "zero external libraries")
  is explicit about **display** already; LVGL is a rendering *and* input
  *and* styling framework — much closer to "product IP" than a toolchain.
  The Arduino-ESP32 core is infrastructure (compiler-adjacent); LVGL is a
  competing UI product. Keep the line where v0.1 already drew it.
- Our card model (`src/cards.h`) already gives us screens, a switcher, and
  per-card event hooks at ~120 lines total. It costs far less than
  LVGL's config surface for what a 2.8" single-focus device needs: no
  overlapping windows, no animation engine, no complex layout — five to
  eight screens, redrawn top-to-bottom.

**v0.2 screen set** (extends the `Card` array in `main.cpp`):

| Card (Hebrew name) | Purpose | Key/trackball behavior |
|---|---|---|
| צ'אט (Chat) | mesh messaging, existing | type+Enter send; trackball scroll log |
| אנשי קשר (Contacts) | known node IDs → display names | trackball select, Enter = open chat filtered to node |
| מפה (Map) | offline SD-tile map + node beacons | trackball pan; +/- zoom (keys) |
| קול (Voice) | mic capture, playback, voice notes over mesh | Enter = record/stop |
| הגדרות (Settings) | radio params, HE/EN default, backlight timeout, keys | trackball navigate list, Enter = edit |
| מערכת (About/System) | existing | read-only, tick-refreshed |

Each new card is just a new `Card{}` entry + its own `.cpp/.h` — no registry
change beyond appending to the array, per the existing extensibility model.

## 5. Storage

SD card (SPI, shared bus, `PIN_SD_CS`) holds everything that must outlive
reboots and exceed PSRAM comfortably; PSRAM/flash NVS holds hot/small state.

```
SD:/alma/
├── db/
│   ├── messages.db      # append-only log, one record per line (see below)
│   └── contacts.db      # node_id -> display_name, pubkey, last_seen
├── keys/
│   └── device.key       # this node's mesh keypair (generated on first boot)
├── maps/
│   └── <region>.tiles   # offline map tiles, pre-baked, our own simple format
└── voice/
    └── <timestamp>.alma-voice   # captured voice notes (compressed, see below)
```

- **Message DB**: flat append-only file, fixed-width binary records
  (ts:4, src:4, dst:4, id:2, flags:1, len:1, text:200) — a real "database"
  (SQLite) is flash/RAM overkill and another external dependency; append+
  linear-scan is plenty for a device that will hold thousands, not millions,
  of short messages. Rotation: keep last N MB, archive/delete oldest.
- **Contacts**: same append-only-with-compaction pattern; small (<1000
  entries realistically), loaded into a PSRAM hash table at boot for O(1)
  lookup during chat rendering (mapping `src` node id → display name).
- **Keys**: device keypair for the AES-CTR/asymmetric-signing layer
  (`ARCHITECTURE.md` §7 roadmap item); written once, read-only after;
  never transmitted.
- **Offline maps**: our own tile format (not MBTiles/external lib) — raw
  RGB565 tiles pre-cropped to screen-sized chunks, indexed by a simple
  `region.idx` header. Generation is an offline PC tool (Python), not
  on-device.
- **Voice notes**: mic capture (ES7210 → I2S) is Codec2-encoded (700-1200 bps,
  David Rowe, GPL/LGPL, patent-free — see `design/03-voice-lora.md` for the
  full pipeline/FEC/jitter-buffer design) before writing to SD or sending
  over the mesh; raw 16-bit PCM would eat both SD bandwidth and LoRa airtime.
  `firmware/hal/audio_i2s.h` owns only raw capture/playback + VAD; the codec
  itself is a mesh-layer concern per that doc, not duplicated here.

## 6. Power management

Already-implemented baseline (`ARCHITECTURE.md` §9): backlight off after 60 s
idle, continuous LoRa RX, DC-DC mode. v0.2 concrete additions:

- **Light-sleep between loop ticks**: replace `delay(2)` busy-wait with
  `esp_light_sleep_start()` gated by `esp_sleep_enable_gpio_wakeup()` on
  `PIN_KB_INT` (kb co-processor asserts on keypress) and the SX1262's DIO1
  (packet-received IRQ) — the CPU sleeps until either a key or a radio
  packet needs handling, cutting active-core power between events. This is
  the direct successor to today's fixed `delay(2)` cooperative loop.
- **Radio duty-cycling**: SX1262 `SetRxDutyCycle` opcode — sleep the radio
  chip itself between short RX windows when no traffic is expected
  (configurable per power profile: "always listening" vs "battery saver").
  Trades mesh latency for battery life; user-selectable in Settings card.
  Beacon/heartbeat cadence from peers determines a safe duty-cycle window.
- **Backlight PWM dimming** (not just on/off): step down brightness after
  20 s idle before cutting fully at 60 s — softer UX, same power curve
  intent.
- **Battery curve + banner**: `analogReadMilliVolts(PIN_BAT_ADC)` already
  reads volts; v0.2 adds a LiPo discharge-curve lookup table (not linear —
  a raw voltage-to-percent line is misleading near the knees of a Li-ion
  curve) and a persistent low-battery banner card overlay below 3.4 V.

## 7. File / module structure (target, v0.2+)

Builds on — does not replace — `src/`. The scaffold created under
`firmware/` (§8) mirrors this target shape; migration from `src/` happens
incrementally, one module at a time, keeping `src/` buildable throughout.

```
alma-os-tdeck/
├── platformio.ini
├── ARCHITECTURE.md
├── README.md
├── design/
│   └── 04-firmware-os.md        # this file
├── src/                          # CURRENT v0.1 buildable skeleton (unchanged)
│   └── ...                       # (see ARCHITECTURE.md §10)
├── firmware/                     # v0.2 scaffold — target module layout
│   ├── core/
│   │   ├── alma_os.h/.cpp        # setup(): task creation, bus init
│   │   ├── event_bus.h/.cpp      # AlmaEvent + queue wrappers
│   │   └── power.h/.cpp          # light-sleep, duty-cycle, battery curve
│   ├── hal/
│   │   ├── board_tdeck.h         # pin map (moved from src/, unchanged)
│   │   ├── display_st7789.h/.cpp
│   │   ├── radio_sx1262.h/.cpp
│   │   ├── keyboard.h/.cpp
│   │   ├── trackball.h/.cpp      # split out of cards.h
│   │   ├── audio_i2s.h/.cpp      # mic capture + speaker out (new)
│   │   └── sd_storage.h/.cpp     # SD mount + raw block helpers (new)
│   ├── text/
│   │   ├── utf8.h
│   │   ├── font_hebrew.h
│   │   └── bidi_rtl.h/.cpp       # shaping logic factored out of display_st7789
│   ├── mesh/
│   │   ├── mesh.h/.cpp           # framing/dedupe (moved from src/)
│   │   └── mesh_crypto.h/.cpp    # AES-CTR + keys (new, v0.2 roadmap item)
│   ├── assistant/
│   │   ├── assistant.h           # contract (moved from src/)
│   │   ├── assistant_rules.cpp   # tier-0 (moved)
│   │   └── assistant_lm.h/.cpp   # tier-1 byte-LM hook (stub, v0.3)
│   ├── storage/
│   │   ├── message_db.h/.cpp     # append-only message log
│   │   └── contacts_db.h/.cpp    # contact table
│   ├── ui/
│   │   ├── cards.h               # Card struct + registry (moved from src/)
│   │   ├── card_chat.cpp
│   │   ├── card_contacts.cpp     # new
│   │   ├── card_map.cpp          # new
│   │   ├── card_voice.cpp        # new
│   │   ├── card_settings.cpp     # new
│   │   └── card_about.cpp        # (moved out of main.cpp)
│   └── main.cpp                  # thin: begin HAL, create tasks, hand off
└── tools/
    └── fontgen.py
```

## 8. Scaffold created

Under `firmware/` (stub headers/empty `.cpp` with signatures + comments —
not wired into `platformio.ini`, does not need to compile yet; this is the
blueprint the next implementation pass fills in module-by-module while
`src/` keeps building):

- `firmware/core/alma_os.h`, `event_bus.h`, `power.h`
- `firmware/hal/audio_i2s.h`, `sd_storage.h`, `trackball.h`
- `firmware/text/bidi_rtl.h`
- `firmware/mesh/mesh_crypto.h`
- `firmware/assistant/assistant_lm.h`
- `firmware/storage/message_db.h`, `contacts_db.h`
- `firmware/ui/card_contacts.h`, `card_map.h`, `card_voice.h`, `card_settings.h`

Each stub declares the concrete interface described in this document so the
next agent/session can implement bodies against a fixed contract, and cross-
references the existing `src/` file it will eventually absorb.
