# ALMA-OS for the LILYGO T-Deck — Architecture

**Hebrew-first, AI-native handheld OS for the T-Deck (ESP32-S3).**
לזכרה של עלמה ז"ל · ALMAWARE

> Status honesty: v0.1 is a compiling firmware skeleton, designed against the
> T-Deck schematic and Semtech/Sitronix datasheets. It has **not yet been
> flashed to hardware**. Everything marked ✅ is implemented in code; ⬜ is roadmap.

---

## 1. What ALMA-OS is (and is not)

The two T-Decks today run **Meshtastic** — excellent, but foreign: English-first UI,
external codebase, phone-centric. ALMA-OS replaces the firmware entirely with our
own stack, per the ALMAWARE purity law: **zero external libraries** — no RadioLib,
no TFT_eSPI, no LVGL, no Meshtastic. The only foundation is the Espressif Arduino
core (toolchain-level, like a compiler).

It is not a general-purpose OS (no MMU, no processes). It is a **firmware-OS**:
one binary, cooperative event loop, "cards" as apps — the right shape for a
520 KB-RAM microcontroller with 8 MB PSRAM.

## 2. Hardware map (T-Deck)

```
ESP32-S3 (16MB flash, 8MB OPI PSRAM)
 ├─ GPIO10  ── POWERON rail  ← must go HIGH first, then wait ~500ms
 ├─ SPI (SCK40/MOSI41/MISO38) shared by:
 │    ├─ ST7789 320x240 TFT   (CS12, DC11, BL42, no reset pin)
 │    ├─ SX1262 LoRa          (CS9, DIO1=45, RST17, BUSY13)
 │    └─ microSD              (CS39)
 ├─ I2C (SDA18/SCL8):
 │    ├─ keyboard co-processor (ESP32-C3 @ 0x55, INT46) — 1 ASCII byte/keypress
 │    └─ GT911 touch (0x5D, INT16)
 ├─ trackball: pulse pins 3/15/1/2 + click on GPIO0
 ├─ audio: MAX98357A speaker (I2S 7/5/6), ES7210 mic ADC (48/21/47/14)
 └─ battery sense: GPIO4 (1:2 divider)
```

All pins live in one place: `src/board_tdeck.h`.

## 3. Boot sequence  ✅

1. `POWERON` (GPIO10) HIGH → peripheral rail up; 500 ms settle (kb co-processor boots).
2. Shared SPI + I2C buses up.
3. Display init (SWRESET → SLPOUT → COLMOD 565 → MADCTL landscape → INVON → DISPON).
4. **Hebrew splash: שלום** (scale-3 glyphs) + memorial line.
5. SX1262 init — result shown honestly on screen (`LoRa:OK` / `LoRa:--`).
6. Enter the Chat card event loop.

## 4. Hebrew rendering & RTL  ✅

The heart of "Hebrew-first". Three layers:

- **Font**: `src/font_hebrew.h` — 8x16 1-bpp bitmap font, 124 glyphs
  (ASCII + full alef-bet incl. finals + geresh/gershayim), ~2 KB. It is
  **generated, not hand-drawn**, by `tools/fontgen.py` from *Frank Ruhl Hofshi*
  (SIL-OFL, free) at 12 px — regenerate any time with a different face/size.
  Renderer scales 1x–4x (splash uses 3x = 24x48 px letters).
- **UTF-8**: `src/utf8.h` — 60-line decoder/encoder, no locale, no ICU.
- **Minimal bidi** (`DisplayST7789::drawTextRTL`): text is stored in logical
  order; layout starts at the right edge and advances leftward; a maximal run of
  Latin/digits inside Hebrew is drawn LTR as a block. This covers chat reality
  ("שלח 3 הודעות ל-COM5") without a full UAX#9 engine. Full bidi is roadmap,
  honest scope cut.

Rendering is glyph-blit over SPI windows — **no framebuffer needed**, works even
before PSRAM is touched; PSRAM stays free for the assistant model.

## 5. Input model  ✅

- I2C poll @ 50 Hz of the keyboard co-processor.
- **Hebrew layout in the OS, not the keyboard**: raw ASCII from the Q10 keyboard
  is mapped through the standard Israeli layout (`src/keyboard.h`); `$` toggles
  HE/EN (shown in the status bar). Backspace strips one *codepoint*, not one byte.
- ⬜ Trackball (pulse-counting on GPIOs 3/15/1/2) → card navigation, v0.2.
- ⬜ GT911 touch, long-press key repeat.

## 6. App model: "cards"  (✅ contract, ⬜ registry)

An app is a **card**: a struct of callbacks over a shared event loop —
`onKey(KeyEvent)`, `onMessage(AlmaMessage)`, `onTick()`, `draw(Display&)`.
Cooperative, single-threaded, no dynamic loading (ESP32 flash apps are
compiled in). v0.1 hardwires one card (Chat) in `main.cpp`; the registry +
trackball switching between Chat / עלמא Assistant / Settings / Files(SD)
is v0.2. ALMA-language authored cards are the long-range goal (see roadmap).

## 7. ALMA-MESH: the LoRa messaging layer  ✅ v0

Our own framing (`src/mesh.h`), 16-byte header + UTF-8 payload ≤ 200 B:

```
'A' 'M' ver type | src:4 | dst:4 | msgid:2 | ttl | len | payload…
```

- Node id = low 32 bits of the efuse MAC. Broadcast dst = `0xFFFFFFFF`.
- Dedupe cache of (src,msgid) — ready for ⬜ TTL flood-rebroadcast (multi-hop) in v0.2.
- Radio: our own **from-scratch SX1262 driver** (`src/radio_sx1262.cpp`) —
  standby/TCXO/calibration/PA/modulation/packet-params/sync-word/IRQ routing,
  blocking TX, continuous RX polled on DIO1. Defaults: 868 MHz, SF9/125 kHz/CR4:7,
  17 dBm, private sync word `0x1424`.
- **Interop honesty**: ALMA-MESH ≠ Meshtastic protocol. Flash ALMA-OS on **both**
  T-Decks. The Meshtastic build can always be re-flashed — nothing is lost.
- ⬜ ACK + retry, ⬜ chunking >200 B (reuse the (i/n) convention from
  `D:\CLAUDE\lora-mesh\lora_bridge.py`), ⬜ AES-CTR payload encryption.

## 8. עלמא — the on-device assistant  ✅ hook, ⬜ brain

Three-tier design, the interface (`src/assistant.h`) is the contract:

1. **Tier 0 (now)**: rule-based Hebrew matcher, fully offline — `?עזרה`, `?שעה`,
   `?סוללה`, `?מי אתה`. Zero ML, instant, honest about being rules.
2. **Tier 1 (⬜)**: a tiny quantized byte-LM (Eran/Ada family) resident in the
   8 MB PSRAM behind the *same* `almaAssistantReply()` call. Smart-compression
   rule applies: int8, ≤4 MB weights, greedy decode.
3. **Tier 2 (✅ path, ⬜ gateway)**: unhandled `?` queries are sent over the mesh;
   a PC gateway (evolution of `lora-mesh/lora_autoresponder.py` + local model)
   answers as a normal mesh message. The handheld stays useful offline and gets
   smarter near home — AI-native without pretending an ESP32 is a DGX.

## 9. Power management  ✅ basics, ⬜ deep

- ✅ Backlight off after 60 s idle; any key wakes.
- ✅ LoRa stays in continuous RX (the radio is the point of the device);
  DC-DC regulator mode selected.
- ⬜ Light-sleep between loop ticks with wake on KB_INT (GPIO46) + DIO1.
- ⬜ SX1262 duty-cycled RX (RxDutyCycle opcode), backlight PWM dimming,
  battery-percent curve + low-battery banner.

## 10. File layout

```
alma-os-tdeck/
├── platformio.ini          # ESP32-S3, 16MB/OPI-PSRAM, zero lib_deps
├── ARCHITECTURE.md         # this file
├── README.md               # build/flash/roadmap
├── src/
│   ├── main.cpp            # boot, splash שלום, Chat card loop
│   ├── board_tdeck.h       # every pin + radio defaults, one place
│   ├── display_st7789.h/.cpp  # our ST7789 driver + RTL text renderer
│   ├── font_hebrew.h       # generated 8x16 ASCII+Hebrew bitmap font
│   ├── utf8.h              # tiny UTF-8 codec
│   ├── keyboard.h          # I2C kb + Israeli layout + $ toggle
│   ├── radio_sx1262.h/.cpp # from-scratch SX1262 LoRa driver
│   ├── mesh.h              # ALMA-MESH v0 framing + dedupe
│   └── assistant.h         # עלמא tier-0 rules + uplink contract
└── tools/
    └── fontgen.py          # regenerate font_hebrew.h from any TTF/OTF
```

## 11. Known risks (before first flash)

- **MADCTL/inversion**: if the panel is mirrored or colors are wrong, adjust the
  `0x60|0x08` MADCTL value / INVON in `display_st7789.cpp` (documented inline).
- **TCXO**: driver assumes DIO3-powered TCXO @1.8 V (LilyGo standard). If radio
  init fails, the two fallbacks are commented at the exact spot in `begin()`.
- **Keyboard firmware variance**: some kb co-processor builds need an I2C wake
  poke; if `poll()` reads nothing, check KB_INT and the LilyGo kb firmware rev.
- Regulatory: confirm 868 MHz parameters for Israel before extended use.
