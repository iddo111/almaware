// sim_hw.h — THE VIRTUAL T-DECK.
//
// This is the only new code in the ALMA-OS simulator. Everything above it —
// display_st7789.cpp, radio_sx1262.cpp, main.cpp, keyboard.h, mesh.h,
// assistant.h, font_hebrew.h, utf8.h — is Iddo's real firmware, compiled
// unmodified for the host.
//
// What is modelled here, and how faithfully:
//   * GPIO levels               — exact (a 64-entry level/mode table)
//   * SPI bus + chip select     — exact (byte stream, routed by which CS is LOW)
//   * ST7789 panel              — a real device model: it decodes CASET/RASET/
//                                 RAMWR out of the driver's own byte stream and
//                                 paints RGB565 into a 320x240 framebuffer.
//                                 The pixels you see were addressed by his driver.
//   * SX1262 LoRa               — a *simulated peripheral*: it answers the SPI
//                                 command set his driver actually issues, so the
//                                 ALMA-MESH framing is exercised end to end.
//                                 IT IS NOT RF. It proves protocol, not radio.
//   * I2C keyboard @ 0x55       — exact contract (one ASCII byte per poll, 0 = none)
//   * Trackball pulse lines     — exact (HIGH idle, one LOW read = one edge)
//
// לזכרה של עלמה ז"ל · ALMAWARE
#pragma once
#include <stdint.h>
#include <stddef.h>
#include <string>
#include <deque>
#include <mutex>

namespace sim {

static const int SCREEN_W = 320;
static const int SCREEN_H = 240;

// ---- clock ---------------------------------------------------------------
uint32_t millis_();
uint64_t micros_();
void     delay_(uint32_t ms);
void     delayMicroseconds_(uint32_t us);

// ---- gpio ----------------------------------------------------------------
void     pinMode_(uint8_t pin, uint8_t mode);
void     digitalWrite_(uint8_t pin, uint8_t val);
int      digitalRead_(uint8_t pin);
uint32_t analogReadMilliVolts_(uint8_t pin);

// ---- spi -----------------------------------------------------------------
uint8_t  spiTransfer(uint8_t out);

// ---- panel ---------------------------------------------------------------
const uint16_t *framebuffer();       // SCREEN_W*SCREEN_H RGB565
bool     backlightOn();
bool     displayOn();
bool     frameDirty();
void     clearFrameDirty();
bool     writeBMP(const std::string &path);   // atomic (.tmp + rename)
bool     atomicReplace(const std::string &tmp, const std::string &path);

// ---- keyboard (I2C 0x55) -------------------------------------------------
void     kbPush(uint8_t ascii);
uint8_t  kbPop();                    // 0 = no key, exactly like the real co-processor

// ---- trackball -----------------------------------------------------------
void     tbPulse(uint8_t pin);       // make the next digitalRead of `pin` read LOW

// ---- virtual SX1262 ------------------------------------------------------
void     radioSetPresent(bool present);   // false = pull the chip off the bus
bool     radioPresent();
void     radioInjectRx(const uint8_t *frame, uint8_t len);
std::string radioLastTxHex();             // last frame handed to the "air"
std::string radioLastTxText();            // its ALMA-MESH payload, decoded
int      radioTxCount();

// ---- host <-> sim command queue -----------------------------------------
void     pushCommand(const std::string &line);
bool     popCommand(std::string &out);

// ---- serial capture ------------------------------------------------------
void     serialWrite(const std::string &s);
std::string serialDrain();

}  // namespace sim
