// radio_sx1262.h — minimal from-scratch SX1262 LoRa driver for the T-Deck.
// 100% ALMAWARE code, no RadioLib. Implements just what ALMA-MESH needs:
// init, transmit, continuous receive (polled via DIO1), RSSI/SNR readout.
//
// Datasheet: Semtech SX1261/2, DS.SX1261-2.W.APP (command opcodes referenced inline).
// UNTESTED-ON-HARDWARE: TCXO voltage (DIO3) is set to 1.8 V which matches LilyGo
// SX1262 modules; if RX is dead on your unit, try 2.4 V or no-TCXO (see begin()).
//
// לזכרה של עלמה ז"ל · ALMAWARE
#pragma once
#include <Arduino.h>
#include <SPI.h>
#include "board_tdeck.h"

class RadioSX1262 {
public:
  bool begin(SPIClass &spi);                       // full LoRa init; true on success
  bool transmit(const uint8_t *data, uint8_t len); // blocking TX, then back to RX
  int  receive(uint8_t *buf, uint8_t maxLen);      // poll; >0 = bytes received
  float lastRssi() const { return _rssi; }
  float lastSnr()  const { return _snr; }

private:
  SPIClass *_spi = nullptr;
  float _rssi = 0, _snr = 0;

  bool waitBusy(uint32_t timeoutMs = 1000);
  void writeCmd(uint8_t op, const uint8_t *d, uint8_t n);
  void readCmd(uint8_t op, uint8_t *d, uint8_t n);
  void writeReg(uint16_t addr, const uint8_t *d, uint8_t n);
  uint16_t irqStatus();
  void clearIrq(uint16_t mask = 0xFFFF);
  void startRx();
};
