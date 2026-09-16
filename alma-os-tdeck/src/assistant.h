// assistant.h — עלמא: the on-device tiny assistant hook for ALMA-OS.
//
// v0.1 = rule-based Hebrew command matcher, fully offline, zero ML.
// The interface is the contract: later versions swap in a real tiny LM
// (an Eran/Ada-family byte model quantized for ESP32-S3 PSRAM) behind the
// SAME almaAssistantReply() call, plus an optional LoRa uplink: a message
// that starts with '?' is answered locally if possible, otherwise forwarded
// over the mesh to the PC gateway (lora-mesh bridge + local model) which
// replies as a normal mesh message.
//
// לזכרה של עלמה ז"ל · ALMAWARE
#pragma once
#include <Arduino.h>

struct AssistantReply {
  bool   handled = false;   // false => caller may uplink the query over LoRa
  String text;
};

static inline bool containsHe(const String &s, const char *needle) {
  return s.indexOf(needle) >= 0;
}

static inline AssistantReply almaAssistantReply(const String &q, uint32_t uptimeMs, float batV) {
  AssistantReply r;
  unsigned long mins = uptimeMs / 60000UL;

  if (containsHe(q, "עזרה") || containsHe(q, "help")) {
    r.handled = true;
    r.text = "פקודות: שעה · סוללה · מי אתה · $ מחליף שפה · ?שאלה עולה לרשת";
  } else if (containsHe(q, "שעה") || containsHe(q, "זמן")) {
    r.handled = true;
    r.text = "פעיל כבר " + String(mins) + " דקות (אין שעון-אמת עדיין — RTC במפת הדרכים)";
  } else if (containsHe(q, "סוללה") || containsHe(q, "battery")) {
    r.handled = true;
    r.text = "סוללה: " + String(batV, 2) + "V";
  } else if (containsHe(q, "מי אתה") || containsHe(q, "מי את")) {
    r.handled = true;
    r.text = "אני עלמא — מערכת עברית של ALMAWARE, לזכרה של עלמה ז\"ל";
  } else if (containsHe(q, "שלום")) {
    r.handled = true;
    r.text = "שלום! כתוב עזרה לרשימת פקודות";
  }
  // not handled -> caller decides: show "לא הבנתי" or uplink to the PC gateway
  return r;
}
