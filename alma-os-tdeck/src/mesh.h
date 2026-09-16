// mesh.h — ALMA-MESH v0: tiny LoRa messaging layer for ALMA-OS.
//
// Frame (max 200 B payload keeps airtime sane at SF9/125k):
//   [0]  'A'   magic
//   [1]  'M'   magic
//   [2]  ver   (1)
//   [3]  type  (1=MSG 2=ACK 3=BEACON)
//   [4..7]   src node id  (low 32 bits of efuse MAC)
//   [8..11]  dst node id  (0xFFFFFFFF = broadcast)
//   [12..13] msg id       (per-node counter)
//   [14] ttl              (hops remaining; v0 sends 1 = single hop)
//   [15] len
//   [16..]   UTF-8 payload
//
// INTEROP NOTE (honest): this is NOT the Meshtastic protocol. A T-Deck running
// ALMA-OS will not exchange messages with one still running Meshtastic —
// flash ALMA-OS on both, or keep Meshtastic and use the PC bridge instead.
//
// לזכרה של עלמה ז"ל · ALMAWARE
#pragma once
#include <Arduino.h>
#include "radio_sx1262.h"

#define ALMA_MESH_HDR   16
#define ALMA_MESH_MAXP  200
#define ALMA_BCAST      0xFFFFFFFFu

enum AlmaMsgType : uint8_t { ALMA_MSG = 1, ALMA_ACK = 2, ALMA_BEACON = 3 };

struct AlmaMessage {
  uint32_t src = 0, dst = 0;
  uint16_t id  = 0;
  uint8_t  type = ALMA_MSG, ttl = 1;
  char     text[ALMA_MESH_MAXP + 1] = {0};
  float    rssi = 0, snr = 0;
};

class AlmaMesh {
public:
  void begin(RadioSX1262 *radio) {
    _radio = radio;
    uint64_t mac = ESP.getEfuseMac();
    _self = (uint32_t)(mac & 0xFFFFFFFF);
  }
  uint32_t selfId() const { return _self; }

  bool sendText(const char *utf8, uint32_t dst = ALMA_BCAST) {
    size_t len = strlen(utf8);
    if (len > ALMA_MESH_MAXP) len = ALMA_MESH_MAXP;   // caller should chunk
    uint8_t f[ALMA_MESH_HDR + ALMA_MESH_MAXP];
    f[0] = 'A'; f[1] = 'M'; f[2] = 1; f[3] = ALMA_MSG;
    put32(f + 4, _self); put32(f + 8, dst);
    _seq++;
    f[12] = _seq >> 8; f[13] = _seq & 0xFF;
    f[14] = 1;                                        // ttl: single hop in v0
    f[15] = (uint8_t)len;
    memcpy(f + ALMA_MESH_HDR, utf8, len);
    return _radio && _radio->transmit(f, ALMA_MESH_HDR + len);
  }

  // Poll the radio; returns true and fills `out` when a fresh MSG for us arrives.
  bool poll(AlmaMessage &out) {
    if (!_radio) return false;
    uint8_t f[ALMA_MESH_HDR + ALMA_MESH_MAXP + 1];
    int n = _radio->receive(f, sizeof(f) - 1);
    if (n < ALMA_MESH_HDR) return false;
    if (f[0] != 'A' || f[1] != 'M' || f[2] != 1) return false;
    uint32_t src = get32(f + 4), dst = get32(f + 8);
    if (dst != ALMA_BCAST && dst != _self) return false;
    uint16_t id = ((uint16_t)f[12] << 8) | f[13];
    if (isDup(src, id)) return false;
    out.type = f[3]; out.src = src; out.dst = dst; out.id = id; out.ttl = f[14];
    uint8_t len = f[15];
    if ((int)len > n - ALMA_MESH_HDR) len = (uint8_t)(n - ALMA_MESH_HDR);
    memcpy(out.text, f + ALMA_MESH_HDR, len);
    out.text[len] = 0;
    out.rssi = _radio->lastRssi(); out.snr = _radio->lastSnr();
    return out.type == ALMA_MSG || out.type == ALMA_BEACON;
  }

private:
  RadioSX1262 *_radio = nullptr;
  uint32_t _self = 0;
  uint16_t _seq = 0;

  // small dedupe cache (src,id) — floods/rebroadcast come in v0.2
  struct { uint32_t src; uint16_t id; } _seen[16] = {};
  uint8_t _seenIdx = 0;
  bool isDup(uint32_t src, uint16_t id) {
    for (auto &s : _seen) if (s.src == src && s.id == id) return true;
    _seen[_seenIdx] = {src, id};
    _seenIdx = (_seenIdx + 1) % 16;
    return false;
  }

  static void put32(uint8_t *p, uint32_t v) {
    p[0] = v >> 24; p[1] = v >> 16; p[2] = v >> 8; p[3] = v;
  }
  static uint32_t get32(const uint8_t *p) {
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | p[3];
  }
};
