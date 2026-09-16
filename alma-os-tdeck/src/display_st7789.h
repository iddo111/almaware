// display_st7789.h — minimal ST7789 driver + Hebrew/RTL text renderer for T-Deck.
// 100% ALMAWARE code: no TFT_eSPI, no LVGL. SPI direct, glyph-blit rendering
// (no full framebuffer, so it runs even without PSRAM).
//
// לזכרה של עלמה ז"ל · ALMAWARE
#pragma once
#include <Arduino.h>
#include <SPI.h>
#include "board_tdeck.h"

// RGB565 helpers
static inline uint16_t rgb565(uint8_t r, uint8_t g, uint8_t b) {
  return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3);
}
#define C_WHITE  0xFFFF
#define C_BLACK  0x0000
#define C_ALMA   rgb565(0, 90, 200)    // ALMA blue
#define C_GRAY   rgb565(120, 120, 120)
#define C_GREEN  rgb565(0, 160, 60)
#define C_AMBER  rgb565(230, 140, 0)

class DisplayST7789 {
public:
  void begin(SPIClass &spi);
  void fillScreen(uint16_t color);
  void fillRect(int x, int y, int w, int h, uint16_t color);
  void setBacklight(bool on);

  // Draw a single codepoint glyph at (x,y). scale = integer zoom (1..4).
  // Returns advance width in pixels. Unknown glyphs draw a hollow box.
  int drawGlyph(int x, int y, uint32_t cp, int scale, uint16_t fg, uint16_t bg);

  // LTR text (ASCII/status). Returns end x.
  int drawTextLTR(int x, int y, const char *utf8, int scale, uint16_t fg, uint16_t bg);

  // RTL-aware text: lays out starting from xRight growing leftwards.
  // Minimal bidi: Hebrew flows RTL; embedded ASCII/digit runs stay LTR.
  // Returns the leftmost x reached.
  int drawTextRTL(int xRight, int y, const char *utf8, int scale, uint16_t fg, uint16_t bg);

  // Pixel width of a UTF-8 string at a given scale (monospace cells).
  int textWidth(const char *utf8, int scale);

private:
  SPIClass *_spi = nullptr;
  void cmd(uint8_t c);
  void cmdData(uint8_t c, const uint8_t *d, size_t n);
  void setWindow(int x, int y, int w, int h);
  void pushPixels(const uint16_t *px, size_t n);
};
