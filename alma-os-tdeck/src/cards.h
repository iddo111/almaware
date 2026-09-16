// cards.h — ALMA-OS card registry + trackball card switching.
//
// A "card" is one full-screen app surface (chat, about, ...). The registry is a
// fixed array of Card descriptors; each is pure function pointers so adding a
// card costs only its own code, no framework. The trackball LEFT/RIGHT pulses
// move between cards; UP/DOWN/CLICK are forwarded to the active card so a card
// can scroll or act on them.
//
// Wiring: the T-Deck trackball exposes 4 quadrature-ish pulse lines (UP/DOWN/
// LEFT/RIGHT) plus a center click shared with BOOT. Each line idles HIGH
// (internal pull-up) and pulses LOW as the ball rolls. We treat each HIGH->LOW
// edge as one "tick" and debounce in software.
//
// 100% ALMAWARE code. No external libraries.
//
// לזכרה של עלמה ז"ל · ALMAWARE
#pragma once
#include <Arduino.h>
#include "board_tdeck.h"

// Directions the trackball can report in one poll (at most one per poll).
enum class TBDir : uint8_t { NONE = 0, UP, DOWN, LEFT, RIGHT, CLICK };

// One pulse line + its last level + a debounce timestamp.
struct TBLine {
  uint8_t  pin;
  bool     lastHigh;
  uint32_t lastEdgeMs;
};

class Trackball {
public:
  void begin() {
    _init(_up,    PIN_TB_UP);
    _init(_down,  PIN_TB_DOWN);
    _init(_left,  PIN_TB_LEFT);
    _init(_right, PIN_TB_RIGHT);
    _init(_click, PIN_TB_CLICK);
  }

  // Non-blocking: returns at most one direction per call. LEFT/RIGHT are used by
  // the OS for card switching; UP/DOWN/CLICK are passed to the active card.
  TBDir poll() {
    uint32_t now = millis();
    if (_fell(_left,  now)) return TBDir::LEFT;
    if (_fell(_right, now)) return TBDir::RIGHT;
    if (_fell(_up,    now)) return TBDir::UP;
    if (_fell(_down,  now)) return TBDir::DOWN;
    if (_fell(_click, now)) return TBDir::CLICK;
    return TBDir::NONE;
  }

private:
  TBLine _up{}, _down{}, _left{}, _right{}, _click{};
  static const uint32_t DEBOUNCE_MS = 25;

  static void _init(TBLine &l, uint8_t pin) {
    l.pin = pin;
    pinMode(pin, INPUT_PULLUP);
    l.lastHigh = (digitalRead(pin) != 0);
    l.lastEdgeMs = 0;
  }

  // True exactly once per debounced HIGH->LOW edge.
  static bool _fell(TBLine &l, uint32_t now) {
    bool high = (digitalRead(l.pin) != 0);
    bool fell = false;
    if (high != l.lastHigh && (now - l.lastEdgeMs) >= DEBOUNCE_MS) {
      l.lastEdgeMs = now;
      if (!high) fell = true;   // HIGH -> LOW
      l.lastHigh = high;
    } else if (high != l.lastHigh && (now - l.lastEdgeMs) < DEBOUNCE_MS) {
      // within debounce window: swallow but keep tracking level lazily
      l.lastHigh = high;
    }
    return fell;
  }
};

// ---- Card descriptor ------------------------------------------------------
// A card is a set of hooks. All are optional except draw. Hooks receive no state
// object; cards keep their own file-local state (like the chat card in main.cpp).
struct KeyEvent;   // fwd decl (defined in keyboard.h, included by main before cards use)

struct Card {
  const char *nameHe;                 // shown in the card switcher / status
  void (*onEnter)();                  // called once when this card becomes active
  void (*draw)();                     // full redraw of the card surface
  void (*onKey)(const struct KeyEvent &ev);   // keyboard event (may be null)
  void (*onTrackball)(TBDir dir);     // UP/DOWN/CLICK forwarded here (may be null)
  void (*tick)();                     // periodic ~5s refresh (may be null)
};

// The registry is defined in main.cpp (it references chat/about handlers there).
// These are the OS-level accessors implemented in main.cpp.
extern const Card *almaCards();
extern int         almaCardCount();
extern int         almaActiveCard();
void               almaSwitchCard(int delta);   // +1 / -1, wraps
