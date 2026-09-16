// SPI.h - host shim. Every byte his drivers push goes onto the virtual bus,
// which routes it to whichever chip select is currently LOW.
// לזכרה של עלמה ז"ל · ALMAWARE
#pragma once
#include <stdint.h>
#include "sim_hw.h"

#define SPI_MODE0 0
#define SPI_MODE1 1
#define SPI_MODE2 2
#define SPI_MODE3 3

class SPISettings {
public:
  SPISettings() {}
  SPISettings(uint32_t clock, uint8_t bitOrder, uint8_t dataMode)
      : _clock(clock), _order(bitOrder), _mode(dataMode) {}
  uint32_t _clock = 1000000;
  uint8_t  _order = 1, _mode = 0;
};

class SPIClass {
public:
  void begin(int sck = -1, int miso = -1, int mosi = -1, int ss = -1) {
    (void)sck; (void)miso; (void)mosi; (void)ss;
  }
  void beginTransaction(const SPISettings &) {}
  void endTransaction() {}
  uint8_t transfer(uint8_t b) { return sim::spiTransfer(b); }
};

extern SPIClass SPI;
