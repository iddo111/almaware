// trackball.h — split out of src/cards.h per design/04-firmware-os.md §7
// target layout (HAL concerns separated from the Card/UI registry).
//
// This is a straight move, not a redesign: the Trackball class + TBDir enum
// are copied verbatim from src/cards.h (pulse-pin debounce over
// PIN_TB_UP/DOWN/LEFT/RIGHT/CLICK). Once firmware/ui/cards.h exists it will
// `#include "hal/trackball.h"` instead of defining Trackball inline.
//
// STUB: header mirrors src/cards.h's Trackball contract; body to be moved
// (not reimplemented) when firmware/ becomes the active tree.
//
// לזכרה של עלמה ז"ל · ALMAWARE
#pragma once
#include <Arduino.h>
#include "hal/board_tdeck.h"

enum class TBDir : uint8_t { NONE = 0, UP, DOWN, LEFT, RIGHT, CLICK };

struct TBLine {
  uint8_t  pin;
  bool     lastHigh;
  uint32_t lastEdgeMs;
};

class Trackball {
public:
  void begin();
  // Non-blocking: at most one direction per call. LEFT/RIGHT reserved by the
  // OS for card switching; UP/DOWN/CLICK forwarded to the active card.
  TBDir poll();

private:
  TBLine _up{}, _down{}, _left{}, _right{}, _click{};
  static const uint32_t DEBOUNCE_MS = 25;
  static void _init(TBLine &l, uint8_t pin);
  static bool _fell(TBLine &l, uint32_t now);
};
