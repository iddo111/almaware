// keyboard.h — T-Deck I2C keyboard (ESP32-C3 co-processor @ 0x55) + Hebrew layout.
// The kb firmware sends one ASCII byte per keypress (0 = none, 8 = backspace,
// 13 = enter). ALMA-OS maps a-z to the standard Israeli Hebrew layout when
// Hebrew mode is on. '$' toggles layout (rarely-typed key on the Q10 keyboard).
//
// לזכרה של עלמה ז"ל · ALMAWARE
#pragma once
#include <Arduino.h>
#include <Wire.h>
#include "board_tdeck.h"

struct KeyEvent {
  bool     valid = false;
  uint8_t  raw   = 0;      // raw ASCII from kb controller
  uint32_t cp    = 0;      // codepoint after layout mapping (0 for control keys)
  bool     enter = false;
  bool     backspace = false;
  bool     langToggled = false;
};

class Keyboard {
public:
  void begin(TwoWire &wire) { _wire = &wire; }
  bool hebrewMode() const { return _hebrew; }

  KeyEvent poll() {
    KeyEvent ev;
    if (!_wire) return ev;
    if (_wire->requestFrom((uint8_t)KB_I2C_ADDR, (uint8_t)1) != 1) return ev;
    int c = _wire->read();
    if (c <= 0) return ev;
    ev.valid = true;
    ev.raw = (uint8_t)c;
    if (c == '\r' || c == '\n') { ev.enter = true; return ev; }
    if (c == 8 || c == 127)     { ev.backspace = true; return ev; }
    if (c == '$') { _hebrew = !_hebrew; ev.langToggled = true; return ev; }
    ev.cp = mapKey((uint8_t)c);
    return ev;
  }

private:
  TwoWire *_wire = nullptr;
  bool _hebrew = true;       // Hebrew-first OS: boots in Hebrew mode

  // Standard Israeli layout, QWERTY position -> Hebrew letter.
  uint32_t mapKey(uint8_t c) {
    if (!_hebrew) return c;
    switch (c) {
      case 'q': return '/';    case 'w': return 0x05F3; // geresh
      case 'e': return 0x5E7;  case 'r': return 0x5E8;  case 't': return 0x5D0;
      case 'y': return 0x5D8;  case 'u': return 0x5D5;  case 'i': return 0x5DF;
      case 'o': return 0x5DD;  case 'p': return 0x5E4;
      case 'a': return 0x5E9;  case 's': return 0x5D3;  case 'd': return 0x5D2;
      case 'f': return 0x5DB;  case 'g': return 0x5E2;  case 'h': return 0x5D9;
      case 'j': return 0x5D7;  case 'k': return 0x5DC;  case 'l': return 0x5DA;
      case ';': return 0x5E3;
      case 'z': return 0x5D6;  case 'x': return 0x5E1;  case 'c': return 0x5D1;
      case 'v': return 0x5D4;  case 'b': return 0x5E0;  case 'n': return 0x5DE;
      case 'm': return 0x5E6;  case ',': return 0x5EA;  case '.': return 0x5E5;
      default:  return c;      // digits, symbols, uppercase pass through
    }
  }
};
