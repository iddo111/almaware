// Arduino.h - host shim for the ALMA-OS simulator.
// Provides exactly the Arduino surface Iddo's firmware actually uses, backed by
// the virtual T-Deck in sim_hw.cpp. His sources are compiled UNMODIFIED against it.
// לזכרה של עלמה ז"ל · ALMAWARE
#pragma once
#include <stdint.h>
#include <stddef.h>
#include <string>
#include <cstring>
#include <cstdio>
#include <cstdlib>
#include <cstdarg>
#include "sim_hw.h"

#define HIGH 1
#define LOW  0
#define INPUT        0
#define OUTPUT       1
#define INPUT_PULLUP 2
#define MSBFIRST 1
#define LSBFIRST 0

// ---- timing / gpio (thin forwarders to the virtual board) ----------------
static inline uint32_t millis() { return sim::millis_(); }
static inline uint32_t micros() { return (uint32_t)sim::micros_(); }
static inline void delay(uint32_t ms) { sim::delay_(ms); }
static inline void delayMicroseconds(uint32_t us) { sim::delayMicroseconds_(us); }
static inline void pinMode(uint8_t p, uint8_t m) { sim::pinMode_(p, m); }
static inline void digitalWrite(uint8_t p, uint8_t v) { sim::digitalWrite_(p, v); }
static inline int  digitalRead(uint8_t p) { return sim::digitalRead_(p); }
static inline uint32_t analogReadMilliVolts(uint8_t p) { return sim::analogReadMilliVolts_(p); }

// ---- Arduino String ------------------------------------------------------
class String {
public:
  String() {}
  String(const char *s) : _s(s ? s : "") {}
  String(const std::string &s) : _s(s) {}
  String(char c) { _s = std::string(1, c); }
  String(int v)           { char b[24]; snprintf(b, sizeof(b), "%d", v);   _s = b; }
  String(unsigned int v)  { char b[24]; snprintf(b, sizeof(b), "%u", v);   _s = b; }
  String(long v)          { char b[24]; snprintf(b, sizeof(b), "%ld", v);  _s = b; }
  String(unsigned long v) { char b[24]; snprintf(b, sizeof(b), "%lu", v);  _s = b; }
  String(float v, int dec = 2)  { char b[40]; snprintf(b, sizeof(b), "%.*f", dec, (double)v); _s = b; }
  String(double v, int dec = 2) { char b[40]; snprintf(b, sizeof(b), "%.*f", dec, v);         _s = b; }

  const char *c_str() const { return _s.c_str(); }
  size_t length() const { return _s.size(); }
  char operator[](int i) const { return (i >= 0 && (size_t)i < _s.size()) ? _s[i] : 0; }

  String &operator+=(const String &o) { _s += o._s; return *this; }
  String &operator+=(const char *o)   { if (o) _s += o; return *this; }
  String &operator+=(char c)          { _s += c; return *this; }

  int indexOf(const char *needle) const {
    size_t p = _s.find(needle);
    return (p == std::string::npos) ? -1 : (int)p;
  }
  String substring(int from) const {
    if (from < 0) from = 0;
    if ((size_t)from >= _s.size()) return String();
    return String(_s.substr(from));
  }
  String substring(int from, int to) const {
    if (from < 0) from = 0;
    if ((size_t)from >= _s.size()) return String();
    if (to < from) to = from;
    if ((size_t)to > _s.size()) to = (int)_s.size();
    return String(_s.substr(from, to - from));
  }
  const std::string &std_str() const { return _s; }

private:
  std::string _s;
};

inline String operator+(const String &a, const String &b) { String r(a); r += b; return r; }
inline String operator+(const String &a, const char *b)   { String r(a); r += b; return r; }
inline String operator+(const char *a, const String &b)   { String r(a); r += b; return r; }
inline String operator+(const String &a, char b)          { String r(a); r += b; return r; }

// ---- Serial --------------------------------------------------------------
class SimSerial {
public:
  void begin(unsigned long) {}
  void println(const char *s) { sim::serialWrite(std::string(s ? s : "") + "\n"); }
  void println(const String &s) { println(s.c_str()); }
  void println() { sim::serialWrite("\n"); }
  void print(const char *s) { sim::serialWrite(s ? s : ""); }
  void print(const String &s) { print(s.c_str()); }
  int printf(const char *fmt, ...) {
    char buf[1024];
    va_list ap; va_start(ap, fmt);
    int n = vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    sim::serialWrite(buf);
    return n;
  }
};
extern SimSerial Serial;

// ---- ESP (efuse MAC only) ------------------------------------------------
class SimEsp {
public:
  // A stable fake MAC so the ALMA-MESH node id is deterministic in the sim.
  uint64_t getEfuseMac() const { return 0x0C8B95A17E42ULL; }
};
extern SimEsp ESP;
