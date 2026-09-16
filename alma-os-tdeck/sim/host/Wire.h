// Wire.h - host shim for the T-Deck I2C keyboard co-processor (ESP32-C3 @ 0x55).
// Contract copied from the real part: every poll returns exactly one byte, and
// that byte is 0 when no key is pending. His keyboard.h is unmodified.
// לזכרה של עלמה ז"ל · ALMAWARE
#pragma once
#include <stdint.h>
#include "sim_hw.h"
#include "../../src/board_tdeck.h"

class TwoWire {
public:
  void begin(int sda = -1, int scl = -1, uint32_t freq = 0) {
    (void)sda; (void)scl; (void)freq;
  }
  uint8_t requestFrom(uint8_t addr, uint8_t n) {
    _addr = addr;
    if (addr != KB_I2C_ADDR) return 0;      // nothing else answers on the sim bus
    _pending = sim::kbPop();
    _have = 1;
    return (n >= 1) ? 1 : 0;
  }
  int read() {
    if (!_have) return -1;
    _have = 0;
    return (int)_pending;
  }
  int available() { return _have; }

private:
  uint8_t _addr = 0, _pending = 0, _have = 0;
};

extern TwoWire Wire;
