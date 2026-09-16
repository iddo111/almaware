// radio_sx1262.cpp — minimal SX1262 LoRa driver (see header for scope/honesty notes).
// לזכרה של עלמה ז"ל · ALMAWARE
#include "radio_sx1262.h"

// SX126x opcodes (Semtech datasheet ch. 13)
#define OP_SET_STANDBY          0x80
#define OP_SET_RX               0x82
#define OP_SET_TX               0x83
#define OP_SET_RF_FREQUENCY     0x86
#define OP_CALIBRATE            0x89
#define OP_SET_PACKET_TYPE      0x8A
#define OP_SET_MOD_PARAMS       0x8B
#define OP_SET_PKT_PARAMS       0x8C
#define OP_SET_TX_PARAMS        0x8E
#define OP_SET_BUF_BASE         0x8F
#define OP_SET_PA_CONFIG        0x95
#define OP_SET_REGULATOR_MODE   0x96
#define OP_SET_DIO3_TCXO        0x97
#define OP_CALIBRATE_IMAGE      0x98
#define OP_SET_DIO2_RF_SWITCH   0x9D
#define OP_SET_DIO_IRQ_PARAMS   0x08
#define OP_CLEAR_IRQ            0x02
#define OP_GET_IRQ_STATUS       0x12
#define OP_GET_RX_BUF_STATUS    0x13
#define OP_GET_PKT_STATUS       0x14
#define OP_WRITE_REGISTER       0x0D
#define OP_WRITE_BUFFER         0x0E
#define OP_READ_BUFFER          0x1E
#define OP_GET_STATUS           0xC0

// IRQ bits
#define IRQ_TX_DONE   (1 << 0)
#define IRQ_RX_DONE   (1 << 1)
#define IRQ_CRC_ERR   (1 << 6)
#define IRQ_TIMEOUT   (1 << 9)

#define REG_LORA_SYNCWORD_MSB 0x0740

static const SPISettings kRadioSpi(8000000, MSBFIRST, SPI_MODE0);

bool RadioSX1262::waitBusy(uint32_t timeoutMs) {
  uint32_t t0 = millis();
  while (digitalRead(PIN_LORA_BUSY) == HIGH) {
    if (millis() - t0 > timeoutMs) return false;
    delayMicroseconds(50);
  }
  return true;
}

void RadioSX1262::writeCmd(uint8_t op, const uint8_t *d, uint8_t n) {
  waitBusy();
  _spi->beginTransaction(kRadioSpi);
  digitalWrite(PIN_LORA_CS, LOW);
  _spi->transfer(op);
  for (uint8_t i = 0; i < n; i++) _spi->transfer(d[i]);
  digitalWrite(PIN_LORA_CS, HIGH);
  _spi->endTransaction();
  waitBusy();
}

void RadioSX1262::readCmd(uint8_t op, uint8_t *d, uint8_t n) {
  waitBusy();
  _spi->beginTransaction(kRadioSpi);
  digitalWrite(PIN_LORA_CS, LOW);
  _spi->transfer(op);
  _spi->transfer(0x00);                       // status byte
  for (uint8_t i = 0; i < n; i++) d[i] = _spi->transfer(0x00);
  digitalWrite(PIN_LORA_CS, HIGH);
  _spi->endTransaction();
}

void RadioSX1262::writeReg(uint16_t addr, const uint8_t *d, uint8_t n) {
  waitBusy();
  _spi->beginTransaction(kRadioSpi);
  digitalWrite(PIN_LORA_CS, LOW);
  _spi->transfer(OP_WRITE_REGISTER);
  _spi->transfer(addr >> 8);
  _spi->transfer(addr & 0xFF);
  for (uint8_t i = 0; i < n; i++) _spi->transfer(d[i]);
  digitalWrite(PIN_LORA_CS, HIGH);
  _spi->endTransaction();
  waitBusy();
}

uint16_t RadioSX1262::irqStatus() {
  uint8_t b[2];
  readCmd(OP_GET_IRQ_STATUS, b, 2);
  return ((uint16_t)b[0] << 8) | b[1];
}

void RadioSX1262::clearIrq(uint16_t mask) {
  uint8_t d[2] = {(uint8_t)(mask >> 8), (uint8_t)(mask & 0xFF)};
  writeCmd(OP_CLEAR_IRQ, d, 2);
}

void RadioSX1262::startRx() {
  clearIrq();
  uint8_t rx[3] = {0xFF, 0xFF, 0xFF};        // continuous RX
  writeCmd(OP_SET_RX, rx, 3);
}

bool RadioSX1262::begin(SPIClass &spi) {
  _spi = &spi;
  pinMode(PIN_LORA_CS, OUTPUT);   digitalWrite(PIN_LORA_CS, HIGH);
  pinMode(PIN_LORA_BUSY, INPUT);
  pinMode(PIN_LORA_DIO1, INPUT);
  pinMode(PIN_LORA_RST, OUTPUT);

  // hardware reset
  digitalWrite(PIN_LORA_RST, LOW);  delay(2);
  digitalWrite(PIN_LORA_RST, HIGH); delay(5);
  if (!waitBusy(2000)) return false;

  uint8_t d1 = 0x00;                          // STDBY_RC
  writeCmd(OP_SET_STANDBY, &d1, 1);

  // sanity: chip answers on SPI?
  uint8_t status;
  readCmd(OP_GET_STATUS, &status, 1);
  if (status == 0x00 || status == 0xFF) return false;

  d1 = 0x01;                                  // DC-DC regulator
  writeCmd(OP_SET_REGULATOR_MODE, &d1, 1);

  // TCXO on DIO3: 1.8 V, 5 ms startup (320 * 15.625 us).
  // LilyGo SX1262 modules ship with a TCXO; if init fails on your unit,
  // comment these two commands out (crystal variant) or try 0x07 (3.3 V).
  { uint8_t t[4] = {0x02, 0x00, 0x01, 0x40}; writeCmd(OP_SET_DIO3_TCXO, t, 4); }
  { uint8_t c = 0x7F; writeCmd(OP_CALIBRATE, &c, 1); delay(5); waitBusy(); }

  d1 = 0x01;                                  // DIO2 drives the RF switch
  writeCmd(OP_SET_DIO2_RF_SWITCH, &d1, 1);

  d1 = 0x01;                                  // packet type: LoRa
  writeCmd(OP_SET_PACKET_TYPE, &d1, 1);

  // frequency: freq * 2^25 / 32 MHz
  {
    uint32_t frf = (uint32_t)((double)ALMA_LORA_FREQ_MHZ * 1e6 * (1 << 25) / 32e6);
    uint8_t f[4] = {(uint8_t)(frf >> 24), (uint8_t)(frf >> 16), (uint8_t)(frf >> 8), (uint8_t)frf};
    writeCmd(OP_SET_RF_FREQUENCY, f, 4);
  }
  // image calibration for the band
  {
    uint8_t im[2];
    if (ALMA_LORA_FREQ_MHZ < 900.0f) { im[0] = 0xD7; im[1] = 0xDB; }   // 863-870
    else                             { im[0] = 0xE1; im[1] = 0xE9; }   // 902-928
    writeCmd(OP_CALIBRATE_IMAGE, im, 2);
  }
  { uint8_t pa[4] = {0x04, 0x07, 0x00, 0x01}; writeCmd(OP_SET_PA_CONFIG, pa, 4); }  // SX1262 +22 dBm PA
  { uint8_t tp[2] = {(uint8_t)ALMA_LORA_POWER_DBM, 0x04}; writeCmd(OP_SET_TX_PARAMS, tp, 2); } // 200 us ramp
  { uint8_t bb[2] = {0x00, 0x00}; writeCmd(OP_SET_BUF_BASE, bb, 2); }

  // modulation: SF9 / 125 kHz / CR 4/7, LDRO off (symbol time 4.1 ms < 16.38 ms)
  {
    uint8_t bw = (ALMA_LORA_BW_KHZ == 500) ? 0x06 : (ALMA_LORA_BW_KHZ == 250) ? 0x05 : 0x04;
    uint8_t mp[4] = {ALMA_LORA_SF, bw, (uint8_t)(ALMA_LORA_CR - 4), 0x00};
    writeCmd(OP_SET_MOD_PARAMS, mp, 4);
  }
  // packet params: 12-sym preamble, explicit header, max len, CRC on, normal IQ
  { uint8_t pp[6] = {0x00, 0x0C, 0x00, 0xFF, 0x01, 0x00}; writeCmd(OP_SET_PKT_PARAMS, pp, 6); }

  // private sync word 0x1424 (Meshtastic/public nets use a different one — intentional)
  { uint8_t sw[2] = {0x14, 0x24}; writeReg(REG_LORA_SYNCWORD_MSB, sw, 2); }

  // route TxDone|RxDone|CrcErr|Timeout to DIO1
  {
    uint16_t m = IRQ_TX_DONE | IRQ_RX_DONE | IRQ_CRC_ERR | IRQ_TIMEOUT;
    uint8_t irq[8] = {(uint8_t)(m >> 8), (uint8_t)m, (uint8_t)(m >> 8), (uint8_t)m, 0, 0, 0, 0};
    writeCmd(OP_SET_DIO_IRQ_PARAMS, irq, 8);
  }

  startRx();
  return true;
}

bool RadioSX1262::transmit(const uint8_t *data, uint8_t len) {
  if (!_spi || len == 0) return false;
  uint8_t d1 = 0x00;
  writeCmd(OP_SET_STANDBY, &d1, 1);
  clearIrq();

  // set exact payload length for this packet
  { uint8_t pp[6] = {0x00, 0x0C, 0x00, len, 0x01, 0x00}; writeCmd(OP_SET_PKT_PARAMS, pp, 6); }

  // write payload at offset 0
  waitBusy();
  _spi->beginTransaction(kRadioSpi);
  digitalWrite(PIN_LORA_CS, LOW);
  _spi->transfer(OP_WRITE_BUFFER);
  _spi->transfer(0x00);
  for (uint8_t i = 0; i < len; i++) _spi->transfer(data[i]);
  digitalWrite(PIN_LORA_CS, HIGH);
  _spi->endTransaction();
  waitBusy();

  // TX with 5 s timeout (5e6 / 15.625 us = 320000 = 0x04E200)
  { uint8_t tx[3] = {0x04, 0xE2, 0x00}; writeCmd(OP_SET_TX, tx, 3); }

  uint32_t t0 = millis();
  bool ok = false;
  while (millis() - t0 < 6000) {
    if (digitalRead(PIN_LORA_DIO1) == HIGH) {
      uint16_t irq = irqStatus();
      if (irq & IRQ_TX_DONE) { ok = true; break; }
      if (irq & IRQ_TIMEOUT) break;
    }
    delay(1);
  }
  startRx();                                   // always return to listening
  return ok;
}

int RadioSX1262::receive(uint8_t *buf, uint8_t maxLen) {
  if (!_spi) return 0;
  if (digitalRead(PIN_LORA_DIO1) == LOW) return 0;
  uint16_t irq = irqStatus();
  if (!(irq & IRQ_RX_DONE)) { clearIrq(); return 0; }
  if (irq & IRQ_CRC_ERR)    { clearIrq(); return 0; }

  uint8_t st[2];
  readCmd(OP_GET_RX_BUF_STATUS, st, 2);        // [len, offset]
  uint8_t len = st[0], off = st[1];
  if (len > maxLen) len = maxLen;

  waitBusy();
  _spi->beginTransaction(kRadioSpi);
  digitalWrite(PIN_LORA_CS, LOW);
  _spi->transfer(OP_READ_BUFFER);
  _spi->transfer(off);
  _spi->transfer(0x00);                        // NOP/status
  for (uint8_t i = 0; i < len; i++) buf[i] = _spi->transfer(0x00);
  digitalWrite(PIN_LORA_CS, HIGH);
  _spi->endTransaction();

  uint8_t ps[3];
  readCmd(OP_GET_PKT_STATUS, ps, 3);           // rssi, snr, signalRssi
  _rssi = -((float)ps[0]) / 2.0f;
  _snr  = ((int8_t)ps[1]) / 4.0f;

  clearIrq();                                  // stay in continuous RX
  return len;
}
