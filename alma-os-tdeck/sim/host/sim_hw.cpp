// sim_hw.cpp - the virtual T-Deck. See sim_hw.h for the honesty map.
// לזכרה של עלמה ז"ל · ALMAWARE
#include "sim_hw.h"
#include "../../src/board_tdeck.h"

#include <chrono>
#include <thread>
#include <cstring>
#include <cstdio>
#include <vector>
#include <algorithm>

#define SIM_HIGH 1
#define SIM_LOW  0

namespace sim {

// ============================ clock =======================================
static std::chrono::steady_clock::time_point T0 = std::chrono::steady_clock::now();

uint64_t micros_() {
  return (uint64_t)std::chrono::duration_cast<std::chrono::microseconds>(
      std::chrono::steady_clock::now() - T0).count();
}
uint32_t millis_() { return (uint32_t)(micros_() / 1000ULL); }
void delay_(uint32_t ms) { std::this_thread::sleep_for(std::chrono::milliseconds(ms)); }
void delayMicroseconds_(uint32_t us) {
  if (us >= 1000) std::this_thread::sleep_for(std::chrono::microseconds(us));
}

// ============================ gpio ========================================
static uint8_t g_level[64];
static uint8_t g_mode[64];
static int     g_tbPulse[64];      // >0 = the next N reads return LOW

static void panelCsEdge(bool low);
static void radioCsEdge(bool low);
static bool g_dirty = true;   // set whenever the VISIBLE panel changes
static int  radioDio1Level();
static bool g_radioPresent = true;

void pinMode_(uint8_t pin, uint8_t mode) {
  if (pin >= 64) return;
  g_mode[pin] = mode;
  if (mode == 2 /*INPUT_PULLUP*/) g_level[pin] = SIM_HIGH;
}

void digitalWrite_(uint8_t pin, uint8_t val) {
  if (pin >= 64) return;
  uint8_t old = g_level[pin];
  g_level[pin] = val ? SIM_HIGH : SIM_LOW;
  if (pin == PIN_TFT_CS  && old != g_level[pin]) panelCsEdge(g_level[pin] == SIM_LOW);
  if (pin == PIN_LORA_CS && old != g_level[pin]) radioCsEdge(g_level[pin] == SIM_LOW);
  // The backlight changes what the panel LOOKS like without touching its RAM,
  // so his 60 s power-save would otherwise leave a stale lit frame on screen.
  if (pin == PIN_TFT_BL  && old != g_level[pin]) g_dirty = true;
}

int digitalRead_(uint8_t pin) {
  if (pin >= 64) return SIM_HIGH;
  if (pin == PIN_LORA_BUSY) return SIM_LOW;              // never busy in the sim
  if (pin == PIN_LORA_DIO1) return radioDio1Level();
  if (g_tbPulse[pin] > 0) { g_tbPulse[pin]--; return SIM_LOW; }   // trackball edge
  if (g_mode[pin] == 2) return SIM_HIGH;                 // INPUT_PULLUP idles HIGH
  return g_level[pin];
}

uint32_t analogReadMilliVolts_(uint8_t pin) {
  // PIN_BAT_ADC sits behind a 1:2 divider; 1950 mV -> 3.90 V reported.
  if (pin == PIN_BAT_ADC) return 1950;
  return 0;
}

void tbPulse(uint8_t pin) { if (pin < 64) g_tbPulse[pin] = 1; }

// ============================ ST7789 panel ================================
// A device model, not a redraw: it consumes the exact byte stream
// display_st7789.cpp emits and reconstructs the picture from it.
#define ST_SWRESET 0x01
#define ST_SLPOUT  0x11
#define ST_NORON   0x13
#define ST_INVON   0x21
#define ST_INVOFF  0x20
#define ST_DISPON  0x29
#define ST_DISPOFF 0x28
#define ST_CASET   0x2A
#define ST_RASET   0x2B
#define ST_RAMWR   0x2C
#define ST_MADCTL  0x36
#define ST_COLMOD  0x3A

static uint16_t g_fb[SCREEN_W * SCREEN_H];
static bool     g_dispOn = false;
static uint8_t  g_madctl = 0, g_colmod = 0;

static uint8_t  p_cmd = 0;
static uint8_t  p_param[8];
static int      p_nparam = 0;
static int      p_x1 = 0, p_x2 = SCREEN_W - 1, p_y1 = 0, p_y2 = SCREEN_H - 1;
static int      p_cx = 0, p_cy = 0;
static bool     p_hiPending = false;
static uint8_t  p_hiByte = 0;

static void panelCsEdge(bool low) { if (low) p_nparam = 0; }

static void panelByte(uint8_t b) {
  bool isCommand = (g_level[PIN_TFT_DC] == SIM_LOW);
  if (isCommand) {
    p_cmd = b; p_nparam = 0; p_hiPending = false;
    if (b == ST_RAMWR)        { p_cx = p_x1; p_cy = p_y1; }
    else if (b == ST_DISPON)  { g_dispOn = true;  g_dirty = true; }
    else if (b == ST_DISPOFF) { g_dispOn = false; g_dirty = true; }
    else if (b == ST_SWRESET) { g_dispOn = false; }
    return;
  }
  switch (p_cmd) {
    case ST_CASET:
      if (p_nparam < 4) p_param[p_nparam++] = b;
      if (p_nparam == 4) {
        p_x1 = (p_param[0] << 8) | p_param[1];
        p_x2 = (p_param[2] << 8) | p_param[3];
      }
      break;
    case ST_RASET:
      if (p_nparam < 4) p_param[p_nparam++] = b;
      if (p_nparam == 4) {
        p_y1 = (p_param[0] << 8) | p_param[1];
        p_y2 = (p_param[2] << 8) | p_param[3];
      }
      break;
    case ST_MADCTL: g_madctl = b; break;
    case ST_COLMOD: g_colmod = b; break;
    case ST_RAMWR: {
      // 16-bit big-endian pixel stream, exactly as pushPixels()/fillRect() emit
      if (!p_hiPending) { p_hiByte = b; p_hiPending = true; break; }
      uint16_t px = ((uint16_t)p_hiByte << 8) | b;
      p_hiPending = false;
      if (p_cx >= 0 && p_cx < SCREEN_W && p_cy >= 0 && p_cy < SCREEN_H) {
        g_fb[p_cy * SCREEN_W + p_cx] = px;
        g_dirty = true;
      }
      if (++p_cx > p_x2) { p_cx = p_x1; if (++p_cy > p_y2) p_cy = p_y1; }
      break;
    }
    default: break;
  }
}

const uint16_t *framebuffer() { return g_fb; }
bool backlightOn() { return g_level[PIN_TFT_BL] == SIM_HIGH; }
bool displayOn()   { return g_dispOn; }
bool frameDirty()  { return g_dirty; }
void clearFrameDirty() { g_dirty = false; }
unsigned madctl()  { return g_madctl; }
unsigned colmod()  { return g_colmod; }

// ============================ virtual SX1262 ==============================
#define OP_SET_STANDBY   0x80
#define OP_SET_RX        0x82
#define OP_SET_TX        0x83
#define OP_CLEAR_IRQ     0x02
#define OP_GET_IRQ       0x12
#define OP_GET_RXBUF     0x13
#define OP_GET_PKTSTAT   0x14
#define OP_WRITE_BUFFER  0x0E
#define OP_READ_BUFFER   0x1E
#define OP_GET_STATUS    0xC0

#define IRQ_TX_DONE (1 << 0)
#define IRQ_RX_DONE (1 << 1)

static int      r_idx = 0;          // byte index inside the current CS-low window
static uint8_t  r_op  = 0;
static uint16_t r_irq = 0;
static bool     r_rxMode = false;
static uint8_t  r_txBuf[256]; static int r_txLen = 0;
static uint8_t  r_rxBuf[256]; static int r_rxLen = 0;
static int      r_txCount = 0;
static std::string r_lastTxHex, r_lastTxText;
static std::mutex  r_mtx;
static std::deque<std::vector<uint8_t> > r_pending;

static int radioDio1Level() {
  if (!g_radioPresent) return SIM_LOW;
  // deliver a queued frame the moment the firmware is actually listening
  if (r_rxMode && r_rxLen == 0) {
    std::lock_guard<std::mutex> lk(r_mtx);
    if (!r_pending.empty()) {
      std::vector<uint8_t> f = r_pending.front(); r_pending.pop_front();
      r_rxLen = (int)std::min<size_t>(f.size(), sizeof(r_rxBuf));
      memcpy(r_rxBuf, f.data(), r_rxLen);
      r_irq |= IRQ_RX_DONE;
    }
  }
  return r_irq ? SIM_HIGH : SIM_LOW;
}

static void radioCsEdge(bool low) { if (low) r_idx = 0; }

static void radioLatchTx() {
  if (r_txLen <= 0) return;
  std::lock_guard<std::mutex> lk(r_mtx);
  char hex[8];
  r_lastTxHex.clear();
  for (int i = 0; i < r_txLen && i < 20; i++) {
    snprintf(hex, sizeof(hex), "%02X ", r_txBuf[i]);
    r_lastTxHex += hex;
  }
  r_lastTxText.clear();
  if (r_txLen > 16 && r_txBuf[0] == 0x41 && r_txBuf[1] == 0x4D) {   // 'A','M'
    int len = r_txBuf[15];
    if (len > r_txLen - 16) len = r_txLen - 16;
    if (len > 0) r_lastTxText.assign((const char *)r_txBuf + 16, len);
  }
}

static uint8_t radioByte(uint8_t out) {
  if (!g_radioPresent) { r_idx++; return 0x00; }   // dead bus: his begin() returns false
  int i = r_idx++;
  if (i == 0) {
    r_op = out;
    switch (r_op) {
      case OP_SET_TX:       r_irq |= IRQ_TX_DONE; r_txCount++; radioLatchTx(); break;
      case OP_SET_RX:       r_rxMode = true;  break;
      case OP_CLEAR_IRQ:    r_irq = 0; r_rxLen = 0; break;
      case OP_SET_STANDBY:  r_rxMode = false; break;
      case OP_WRITE_BUFFER: r_txLen = 0; break;
      default: break;
    }
    return 0x22;                                    // plausible chip status byte
  }
  switch (r_op) {
    case OP_GET_STATUS:  return 0x22;
    case OP_GET_IRQ:     if (i == 2) return (uint8_t)(r_irq >> 8);
                         if (i == 3) return (uint8_t)(r_irq & 0xFF);
                         return 0x22;
    case OP_GET_RXBUF:   if (i == 2) return (uint8_t)r_rxLen;   // len
                         if (i == 3) return 0;                  // offset
                         return 0x22;
    case OP_GET_PKTSTAT: if (i == 2) return 154;                // -77.0 dBm
                         if (i == 3) return (uint8_t)(int8_t)38;// +9.5 dB SNR
                         if (i == 4) return 154;
                         return 0x22;
    case OP_READ_BUFFER: {
      int k = i - 3;                                // op, offset, NOP, then payload
      if (k >= 0 && k < r_rxLen) return r_rxBuf[k];
      return 0x00;
    }
    case OP_WRITE_BUFFER: {
      if (i == 1) return 0x22;                      // buffer offset byte
      if (r_txLen < (int)sizeof(r_txBuf)) r_txBuf[r_txLen++] = out;
      return 0x22;
    }
    default: return 0x22;
  }
}

void radioSetPresent(bool present) { g_radioPresent = present; }
bool radioPresent() { return g_radioPresent; }

void radioInjectRx(const uint8_t *frame, uint8_t len) {
  std::lock_guard<std::mutex> lk(r_mtx);
  r_pending.push_back(std::vector<uint8_t>(frame, frame + len));
}
std::string radioLastTxHex()  { std::lock_guard<std::mutex> lk(r_mtx); return r_lastTxHex; }
std::string radioLastTxText() { std::lock_guard<std::mutex> lk(r_mtx); return r_lastTxText; }
int radioTxCount() { return r_txCount; }

// ============================ SPI router ==================================
uint8_t spiTransfer(uint8_t out) {
  if (g_level[PIN_TFT_CS]  == SIM_LOW) { panelByte(out); return 0x00; }
  if (g_level[PIN_LORA_CS] == SIM_LOW) return radioByte(out);
  return 0x00;
}

// ============================ I2C keyboard ================================
static std::deque<uint8_t> g_keys;
static std::mutex          g_keyMtx;

void kbPush(uint8_t a) { std::lock_guard<std::mutex> lk(g_keyMtx); g_keys.push_back(a); }
uint8_t kbPop() {
  std::lock_guard<std::mutex> lk(g_keyMtx);
  if (g_keys.empty()) return 0;                 // exactly what the real kb sends
  uint8_t a = g_keys.front(); g_keys.pop_front(); return a;
}

// ============================ command queue ===============================
static std::deque<std::string> g_cmds;
static std::mutex              g_cmdMtx;
void pushCommand(const std::string &l) { std::lock_guard<std::mutex> lk(g_cmdMtx); g_cmds.push_back(l); }
bool popCommand(std::string &out) {
  std::lock_guard<std::mutex> lk(g_cmdMtx);
  if (g_cmds.empty()) return false;
  out = g_cmds.front(); g_cmds.pop_front(); return true;
}

// ============================ serial ======================================
static std::string g_serial;
static std::mutex  g_serMtx;
void serialWrite(const std::string &s) {
  std::lock_guard<std::mutex> lk(g_serMtx);
  g_serial += s;
  if (g_serial.size() > 8000) g_serial.erase(0, g_serial.size() - 8000);
}
std::string serialDrain() { std::lock_guard<std::mutex> lk(g_serMtx); return g_serial; }

// ============================ BMP out =====================================
// Windows will refuse remove()/rename() while the HTTP server has the file open
// for a few microseconds. Retry briefly rather than losing the file.
bool atomicReplace(const std::string &tmp, const std::string &path) {
  for (int attempt = 0; attempt < 15; attempt++) {
    remove(path.c_str());
    if (rename(tmp.c_str(), path.c_str()) == 0) return true;
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }
  return false;
}

static void put32(FILE *f, uint32_t v) { fputc(v & 255, f); fputc((v >> 8) & 255, f);
                                         fputc((v >> 16) & 255, f); fputc((v >> 24) & 255, f); }
static void put16(FILE *f, uint16_t v) { fputc(v & 255, f); fputc((v >> 8) & 255, f); }

bool writeBMP(const std::string &path) {
  std::string tmp = path + ".tmp";
  FILE *f = fopen(tmp.c_str(), "wb");
  if (!f) return false;
  const int W = SCREEN_W, H = SCREEN_H;
  const int rowBytes = W * 3;                       // 960, already 4-byte aligned
  const uint32_t dataSize = (uint32_t)rowBytes * H;
  fputc(0x42, f); fputc(0x4D, f);                   // "BM"
  put32(f, 14 + 40 + dataSize); put16(f, 0); put16(f, 0); put32(f, 14 + 40);
  put32(f, 40); put32(f, W); put32(f, H); put16(f, 1); put16(f, 24);
  put32(f, 0); put32(f, dataSize); put32(f, 2835); put32(f, 2835); put32(f, 0); put32(f, 0);

  // Backlight off = the panel goes dark but RAM keeps the image (his 60 s power save).
  const bool lit = backlightOn() && g_dispOn;
  std::vector<uint8_t> row(rowBytes);
  for (int y = H - 1; y >= 0; y--) {                // BMP rows are bottom-up
    for (int x = 0; x < W; x++) {
      uint16_t p = g_fb[y * W + x];
      int r = ((p >> 11) & 0x1F) * 255 / 31;
      int g = ((p >> 5)  & 0x3F) * 255 / 63;
      int b = ( p        & 0x1F) * 255 / 31;
      if (!lit) { r = r * 7 / 100; g = g * 7 / 100; b = b * 9 / 100; }
      row[x * 3 + 0] = (uint8_t)b; row[x * 3 + 1] = (uint8_t)g; row[x * 3 + 2] = (uint8_t)r;
    }
    fwrite(row.data(), 1, rowBytes, f);
  }
  fclose(f);
  return atomicReplace(tmp, path);
}

}  // namespace sim
