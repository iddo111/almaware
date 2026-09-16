# ALMA-OS · T-Deck  🕊️

**מערכת הפעלה עברית, AI-native, ל-LILYGO T-Deck.**
100% ALMAWARE code — our display driver, our LoRa driver, our Hebrew font pipeline,
our mesh protocol. Zero external libraries.

לזכרה של עלמה ז"ל

---

## What it does (v0.1 skeleton)

- Boots to a Hebrew **שלום** splash (real RTL rendering, generated 8x16 Hebrew font).
- Chat card: type on the Q10 keyboard — **Hebrew layout built into the OS**
  (`$` toggles עברית/English), live echo with RTL layout and an amber cursor.
- Enter sends the line over **ALMA-MESH** (our LoRa framing on a from-scratch
  SX1262 driver); received messages appear with sender id, RSSI/SNR on serial.
- `?` prefix talks to **עלמא**, the on-device assistant (offline rules now:
  `?עזרה` `?שעה` `?סוללה` `?מי אתה`; unhandled questions go out over LoRa for a
  PC gateway to answer).
- Status bar: radio state, battery volts, HE/EN. Backlight sleeps after 60 s.

**Honest status:** compiles as coherent C++; **not yet flashed to real hardware.**
Hardware-truth checklist before trusting it: panel orientation (MADCTL), radio
TCXO variant, keyboard firmware rev — all three have marked fallbacks in the code.

## Build & flash

```powershell
cd D:\CLAUDE\alma-os-tdeck
pio run                    # build
pio run -t upload          # flash (T-Deck on USB; hold trackball-click while
                           #        powering on if it doesn't enter bootloader)
pio device monitor         # 115200 baud logs
```

Requirements: PlatformIO Core (already on this PC), USB-C cable. First build
downloads the Espressif toolchain.

⚠️ Flashing **replaces Meshtastic** on that T-Deck. ALMA-MESH does not speak the
Meshtastic protocol — flash **both** T-Decks to chat between them. To go back,
re-flash Meshtastic with their web flasher; nothing is bricked.

Set the radio (must match on both units) in `src/board_tdeck.h`:
`ALMA_LORA_FREQ_MHZ` (default 868.0), SF/BW/CR, power.

## Regenerate the Hebrew font

```powershell
python tools\fontgen.py    # re-renders src/font_hebrew.h (needs Pillow)
```

Default face: Frank Ruhl Hofshi (SIL-OFL). Swap candidates at the top of the script.

## Roadmap

1. **v0.1 (this)** — boot, שלום splash, Hebrew keyboard echo, LoRa send/recv. ⬅
2. **v0.2 — mesh** — TTL flood rebroadcast (multi-hop), ACK+retry, message
   chunking, AES encryption; trackball card-switching; Settings card.
3. **v0.3 — עלמא offline** — tiny quantized byte-LM (Eran/Ada family) in the
   8 MB PSRAM behind the same assistant hook; PC gateway answering `?` uplinks
   (evolves `D:\CLAUDE\lora-mesh\lora_autoresponder.py`).
4. **v0.4 — voice** — ES7210 mic capture → alma-ozen-style Hebrew ASR on the
   gateway; speaker replies (I2S).
5. **v1.0 — ALMA-language apps** — cards authored in the ALMA language,
   compiled into the firmware; the T-Deck becomes the pocket sibling of
   ALMAPHONE.

## Relation to existing work

- `D:\CLAUDE\lora-mesh\` — the current PC↔Meshtastic bridge (COM5, inbox/outbox
  files, auto-chunking). Untouched and still valid while the T-Decks run
  Meshtastic; its gateway role carries over to ALMA-MESH in v0.3.
- ALMAPHONE — the Jetson big brother; ALMA-OS T-Deck is the low-power scout.
