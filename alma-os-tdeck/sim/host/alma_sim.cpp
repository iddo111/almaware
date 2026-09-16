// alma_sim.cpp - the ALMA-OS simulator entry point.
//
// It runs Iddo's real setup()/loop() from src/main.cpp against the virtual
// T-Deck in sim_hw.cpp, and speaks a one-line-per-command protocol on stdin so
// a browser front end (sim/alma_web.py) can type on the keyboard, roll the
// trackball, and drop frames onto the virtual LoRa air.
//
// Commands (one per line):
//   K <ascii>        one keypress, as the I2C co-processor would report it
//   TB L|R|U|D|C     one trackball edge
//   RX <utf8 text>   deliver an ALMA-MESH frame from another node
//   RADIO 0|1        pull the SX1262 off the bus / put it back
//   SHOT <path>      write a BMP right now
//   QUIT
//
// לזכרה של עלמה ז"ל · ALMAWARE
#include "sim_hw.h"
#include "Arduino.h"
#include "SPI.h"
#include "Wire.h"
#include "../../src/board_tdeck.h"

#include <thread>
#include <iostream>
#include <sstream>
#include <string>
#include <cstdio>
#include <cstring>

// the globals his firmware expects
SimSerial Serial;
SimEsp    ESP;
SPIClass  SPI;
TwoWire   Wire;

// his firmware
extern void setup();
extern void loop();

static std::string g_outDir = ".";

// ---------------------------------------------------------------------------
static std::string jsonEscape(const std::string &s) {
  std::string o;
  for (size_t i = 0; i < s.size(); i++) {
    unsigned char c = (unsigned char)s[i];
    if (c == '"')       o += "\\\"";
    else if (c == '\\') o += "\\\\";
    else if (c == '\n') o += "\\n";
    else if (c == '\r') o += "\\r";
    else if (c == '\t') o += "\\t";
    else if (c < 0x20)  { char b[8]; snprintf(b, sizeof(b), "\\u%04x", c); o += b; }
    else o += (char)c;
  }
  return o;
}

static void writeStatus() {
  // Written in place, not via tmp+rename: it is ~300 bytes, so a reader either
  // sees the whole thing or gets a short read it can detect (alma_web.py
  // JSON-validates and falls back to the last good copy). Renaming it 2.5x a
  // second fought the HTTP server for the Windows file lock and lost.
  std::string path = g_outDir + "/status.json";
  FILE *f = fopen(path.c_str(), "wb");
  if (!f) return;
  fprintf(f,
    "{\"uptime_ms\":%u,\"backlight\":%s,\"display_on\":%s,"
    "\"radio_present\":%s,\"tx_count\":%d,"
    "\"last_tx_hex\":\"%s\",\"last_tx_text\":\"%s\",\"serial\":\"%s\"}",
    (unsigned)millis(),
    sim::backlightOn() ? "true" : "false",
    sim::displayOn()   ? "true" : "false",
    sim::radioPresent()? "true" : "false",
    sim::radioTxCount(),
    jsonEscape(sim::radioLastTxHex()).c_str(),
    jsonEscape(sim::radioLastTxText()).c_str(),
    jsonEscape(sim::serialDrain()).c_str());
  fclose(f);
}

// Build a real ALMA-MESH v0 frame (mesh.h layout) from a second virtual node.
static void injectMeshText(const std::string &text) {
  static uint16_t msgid = 0x1000;
  const uint32_t src = 0x5D0E12C4u;      // shows up as "12C4" in his chat log
  uint8_t f[16 + 200];
  size_t len = text.size();
  if (len > 200) len = 200;
  f[0] = 0x41; f[1] = 0x4D; f[2] = 1; f[3] = 1;          // 'A','M', ver 1, MSG
  f[4] = (uint8_t)(src >> 24); f[5] = (uint8_t)(src >> 16);
  f[6] = (uint8_t)(src >> 8);  f[7] = (uint8_t)src;
  f[8] = f[9] = f[10] = f[11] = 0xFF;                    // broadcast
  msgid++;
  f[12] = (uint8_t)(msgid >> 8); f[13] = (uint8_t)(msgid & 0xFF);
  f[14] = 1;                                             // ttl
  f[15] = (uint8_t)len;
  memcpy(f + 16, text.data(), len);
  sim::radioInjectRx(f, (uint8_t)(16 + len));
}

static void handleCommand(const std::string &line) {
  if (line.empty()) return;
  std::istringstream is(line);
  std::string op; is >> op;

  if (op == "K") {
    int v = 0; is >> v;
    if (v > 0 && v < 256) sim::kbPush((uint8_t)v);
  } else if (op == "TB") {
    std::string d; is >> d;
    if      (d == "L") sim::tbPulse(PIN_TB_LEFT);
    else if (d == "R") sim::tbPulse(PIN_TB_RIGHT);
    else if (d == "U") sim::tbPulse(PIN_TB_UP);
    else if (d == "D") sim::tbPulse(PIN_TB_DOWN);
    else if (d == "C") sim::tbPulse(PIN_TB_CLICK);
  } else if (op == "RX") {
    std::string rest;
    std::getline(is, rest);
    if (!rest.empty() && rest[0] == ' ') rest.erase(0, 1);
    if (!rest.empty()) injectMeshText(rest);
  } else if (op == "RADIO") {
    int v = 1; is >> v;
    sim::radioSetPresent(v != 0);
  } else if (op == "SHOT") {
    std::string p; is >> p;
    sim::writeBMP(p.empty() ? (g_outDir + "/frame.bmp") : p);
  } else if (op == "QUIT") {
    exit(0);
  }
}

// ---------------------------------------------------------------------------
// Disk I/O runs on its OWN thread. The firmware loop must never wait on a file
// lock: when it did, his millis() drifted 0.7 s behind the wall clock and the
// command pipe back-pressured until the browser timed out. A real panel refresh
// does not stall the CPU either.
static volatile bool g_ioRun = true;

static void ioThread() {
  const std::string framePath = g_outDir + "/frame.bmp";
  uint32_t lastFrame = 0, lastStatus = 0;
  while (g_ioRun) {
    uint32_t now = millis();
    if (sim::frameDirty() && now - lastFrame >= 70) {
      lastFrame = now;
      sim::clearFrameDirty();
      sim::writeBMP(framePath);
    }
    if (now - lastStatus >= 400) { lastStatus = now; writeStatus(); }
    std::this_thread::sleep_for(std::chrono::milliseconds(15));
  }
}

static void stdinThread() {
  std::string line;
  while (std::getline(std::cin, line)) {
    if (!line.empty() && line[line.size() - 1] == '\r') line.erase(line.size() - 1);
    sim::pushCommand(line);
  }
}

int main(int argc, char **argv) {
  if (argc > 1) g_outDir = argv[1];
  // Optional headless mode: run N ms, write one BMP, exit. Used to prove the
  // boot screen without a browser.
  int headlessMs = 0;
  for (int i = 2; i < argc; i++) if (!strcmp(argv[i - 1], "--headless")) headlessMs = atoi(argv[i]);

  std::thread(stdinThread).detach();

  fprintf(stderr, "[sim] virtual T-Deck up; running his setup()\n");
  setup();
  fprintf(stderr, "[sim] setup() returned; entering loop()\n");

  std::thread io(ioThread);
  const std::string framePath = g_outDir + "/frame.bmp";

  for (;;) {
    std::string cmd;
    while (sim::popCommand(cmd)) handleCommand(cmd);

    loop();                     // his event loop, at real time, never blocked

    if (headlessMs && (int)millis() > headlessMs) {
      g_ioRun = false; io.join();
      sim::writeBMP(framePath);
      writeStatus();
      fprintf(stderr, "[sim] headless run complete -> %s\n", framePath.c_str());
      return 0;
    }
  }
}
