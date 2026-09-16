// utf8.h — tiny UTF-8 decoder for ALMA-OS text rendering.
// לזכרה של עלמה ז"ל · ALMAWARE
#pragma once
#include <stdint.h>
#include <stddef.h>

// Decode one codepoint from s[*i], advancing *i. Returns 0xFFFD on bad input.
static inline uint32_t utf8Next(const char *s, size_t len, size_t *i) {
  if (*i >= len) return 0;
  uint8_t c = (uint8_t)s[*i];
  (*i)++;
  if (c < 0x80) return c;
  int extra; uint32_t cp;
  if      ((c & 0xE0) == 0xC0) { extra = 1; cp = c & 0x1F; }
  else if ((c & 0xF0) == 0xE0) { extra = 2; cp = c & 0x0F; }
  else if ((c & 0xF8) == 0xF0) { extra = 3; cp = c & 0x07; }
  else return 0xFFFD;
  while (extra--) {
    if (*i >= len) return 0xFFFD;
    uint8_t cc = (uint8_t)s[*i];
    if ((cc & 0xC0) != 0x80) return 0xFFFD;
    cp = (cp << 6) | (cc & 0x3F);
    (*i)++;
  }
  return cp;
}

// Append one codepoint as UTF-8 to buf (must have >=4 free bytes). Returns bytes written.
static inline int utf8Encode(uint32_t cp, char *buf) {
  if (cp < 0x80)      { buf[0] = (char)cp; return 1; }
  if (cp < 0x800)     { buf[0] = 0xC0 | (cp >> 6);  buf[1] = 0x80 | (cp & 0x3F); return 2; }
  if (cp < 0x10000)   { buf[0] = 0xE0 | (cp >> 12); buf[1] = 0x80 | ((cp >> 6) & 0x3F);
                        buf[2] = 0x80 | (cp & 0x3F); return 3; }
  buf[0] = 0xF0 | (cp >> 18); buf[1] = 0x80 | ((cp >> 12) & 0x3F);
  buf[2] = 0x80 | ((cp >> 6) & 0x3F); buf[3] = 0x80 | (cp & 0x3F); return 4;
}

static inline bool cpIsHebrew(uint32_t cp) { return cp >= 0x0590 && cp <= 0x05FF; }
