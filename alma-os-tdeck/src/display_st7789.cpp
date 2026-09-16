// display_st7789.cpp — minimal ST7789 driver + RTL text renderer.
// לזכרה של עלמה ז"ל · ALMAWARE
#include "display_st7789.h"
#include "font_hebrew.h"
#include "utf8.h"

// ST7789 commands
#define ST_SWRESET 0x01
#define ST_SLPOUT  0x11
#define ST_NORON   0x13
#define ST_INVON   0x21
#define ST_DISPON  0x29
#define ST_CASET   0x2A
#define ST_RASET   0x2B
#define ST_RAMWR   0x2C
#define ST_MADCTL  0x36
#define ST_COLMOD  0x3A

static const SPISettings kTftSpi(40000000, MSBFIRST, SPI_MODE0);

void DisplayST7789::cmd(uint8_t c) {
  _spi->beginTransaction(kTftSpi);
  digitalWrite(PIN_TFT_DC, LOW);
  digitalWrite(PIN_TFT_CS, LOW);
  _spi->transfer(c);
  digitalWrite(PIN_TFT_CS, HIGH);
  _spi->endTransaction();
}

void DisplayST7789::cmdData(uint8_t c, const uint8_t *d, size_t n) {
  _spi->beginTransaction(kTftSpi);
  digitalWrite(PIN_TFT_DC, LOW);
  digitalWrite(PIN_TFT_CS, LOW);
  _spi->transfer(c);
  digitalWrite(PIN_TFT_DC, HIGH);
  for (size_t i = 0; i < n; i++) _spi->transfer(d[i]);
  digitalWrite(PIN_TFT_CS, HIGH);
  _spi->endTransaction();
}

void DisplayST7789::begin(SPIClass &spi) {
  _spi = &spi;
  pinMode(PIN_TFT_CS, OUTPUT); digitalWrite(PIN_TFT_CS, HIGH);
  pinMode(PIN_TFT_DC, OUTPUT); digitalWrite(PIN_TFT_DC, HIGH);
  pinMode(PIN_TFT_BL, OUTPUT); digitalWrite(PIN_TFT_BL, LOW);

  cmd(ST_SWRESET); delay(150);
  cmd(ST_SLPOUT);  delay(120);
  uint8_t colmod = 0x55;                  // 16-bit RGB565
  cmdData(ST_COLMOD, &colmod, 1);
  // Landscape, keyboard below screen. If your panel shows mirrored/rotated
  // output, try 0xA0 / 0x70 / 0xC0 here (MADCTL MY/MX/MV combinations).
  uint8_t madctl = 0x60 | 0x08;           // MX|MV + BGR order (T-Deck panel)
  cmdData(ST_MADCTL, &madctl, 1);
  cmd(ST_INVON);                          // T-Deck IPS panel needs inversion
  cmd(ST_NORON);  delay(10);
  cmd(ST_DISPON); delay(10);

  fillScreen(C_WHITE);
  setBacklight(true);
}

void DisplayST7789::setBacklight(bool on) {
  digitalWrite(PIN_TFT_BL, on ? HIGH : LOW);   // v0.2: LEDC PWM dimming
}

void DisplayST7789::setWindow(int x, int y, int w, int h) {
  uint16_t x1 = x, x2 = x + w - 1, y1 = y, y2 = y + h - 1;
  uint8_t ca[4] = {(uint8_t)(x1 >> 8), (uint8_t)x1, (uint8_t)(x2 >> 8), (uint8_t)x2};
  uint8_t ra[4] = {(uint8_t)(y1 >> 8), (uint8_t)y1, (uint8_t)(y2 >> 8), (uint8_t)y2};
  cmdData(ST_CASET, ca, 4);
  cmdData(ST_RASET, ra, 4);
}

void DisplayST7789::pushPixels(const uint16_t *px, size_t n) {
  _spi->beginTransaction(kTftSpi);
  digitalWrite(PIN_TFT_DC, LOW);
  digitalWrite(PIN_TFT_CS, LOW);
  _spi->transfer(ST_RAMWR);
  digitalWrite(PIN_TFT_DC, HIGH);
  // big-endian 16-bit stream
  for (size_t i = 0; i < n; i++) {
    _spi->transfer(px[i] >> 8);
    _spi->transfer(px[i] & 0xFF);
  }
  digitalWrite(PIN_TFT_CS, HIGH);
  _spi->endTransaction();
}

void DisplayST7789::fillRect(int x, int y, int w, int h, uint16_t color) {
  if (x < 0) { w += x; x = 0; }
  if (y < 0) { h += y; y = 0; }
  if (x + w > TFT_WIDTH)  w = TFT_WIDTH - x;
  if (y + h > TFT_HEIGHT) h = TFT_HEIGHT - y;
  if (w <= 0 || h <= 0) return;
  setWindow(x, y, w, h);
  _spi->beginTransaction(kTftSpi);
  digitalWrite(PIN_TFT_DC, LOW);
  digitalWrite(PIN_TFT_CS, LOW);
  _spi->transfer(ST_RAMWR);
  digitalWrite(PIN_TFT_DC, HIGH);
  uint8_t hi = color >> 8, lo = color & 0xFF;
  for (long i = (long)w * h; i > 0; i--) { _spi->transfer(hi); _spi->transfer(lo); }
  digitalWrite(PIN_TFT_CS, HIGH);
  _spi->endTransaction();
}

void DisplayST7789::fillScreen(uint16_t color) {
  fillRect(0, 0, TFT_WIDTH, TFT_HEIGHT, color);
}

int DisplayST7789::drawGlyph(int x, int y, uint32_t cp, int scale, uint16_t fg, uint16_t bg) {
  if (scale < 1) scale = 1;
  if (scale > 4) scale = 4;
  const int gw = FONT_W * scale, gh = FONT_H * scale;
  if (x < 0 || y < 0 || x + gw > TFT_WIDTH || y + gh > TFT_HEIGHT) return gw;

  int gi = fontGlyphIndex(cp);
  static uint16_t buf[FONT_W * 4 * FONT_H * 4];   // max 32x64 px = 4KB (static, not stack)
  for (int ry = 0; ry < FONT_H; ry++) {
    uint8_t bits = (gi >= 0) ? FONT8X16[gi][ry]
                 // unknown glyph: hollow box
                 : ((ry >= 4 && ry <= 12) ? ((ry == 4 || ry == 12) ? 0x7E : 0x42) : 0x00);
    for (int sy = 0; sy < scale; sy++) {
      uint16_t *row = &buf[((ry * scale) + sy) * gw];
      for (int rx = 0; rx < FONT_W; rx++) {
        uint16_t c = (bits & (0x80 >> rx)) ? fg : bg;
        for (int sx = 0; sx < scale; sx++) row[rx * scale + sx] = c;
      }
    }
  }
  setWindow(x, y, gw, gh);
  pushPixels(buf, (size_t)gw * gh);
  return gw;
}

int DisplayST7789::textWidth(const char *utf8, int scale) {
  size_t i = 0, len = strlen(utf8);
  int n = 0;
  while (i < len) { if (utf8Next(utf8, len, &i)) n++; }
  return n * FONT_W * scale;
}

int DisplayST7789::drawTextLTR(int x, int y, const char *utf8, int scale, uint16_t fg, uint16_t bg) {
  size_t i = 0, len = strlen(utf8);
  while (i < len) {
    uint32_t cp = utf8Next(utf8, len, &i);
    if (!cp) break;
    x += drawGlyph(x, y, cp, scale, fg, bg);
  }
  return x;
}

// Minimal bidi for a Hebrew-first UI:
//  - decode into codepoints
//  - walk logical order; Hebrew (and neutral chars attached to it) advance leftwards
//  - a maximal run of LTR chars (ASCII letters/digits) is drawn LTR as a block
int DisplayST7789::drawTextRTL(int xRight, int y, const char *utf8, int scale, uint16_t fg, uint16_t bg) {
  static uint32_t cps[256];
  size_t n = 0, i = 0, len = strlen(utf8);
  while (i < len && n < 256) {
    uint32_t cp = utf8Next(utf8, len, &i);
    if (!cp) break;
    cps[n++] = cp;
  }
  const int adv = FONT_W * scale;
  int x = xRight;

  auto isLTR = [](uint32_t cp) {
    return (cp >= '0' && cp <= '9') || (cp >= 'A' && cp <= 'Z') || (cp >= 'a' && cp <= 'z');
  };

  size_t k = 0;
  while (k < n) {
    if (isLTR(cps[k])) {
      // find the LTR run (letters/digits plus interior neutrals like '.' ':')
      size_t e = k;
      size_t lastStrong = k;
      while (e < n && !cpIsHebrew(cps[e])) {
        if (isLTR(cps[e])) lastStrong = e;
        e++;
      }
      e = lastStrong + 1;                       // trailing neutrals belong to context
      int runW = (int)(e - k) * adv;
      int rx = x - runW;
      for (size_t j = k; j < e; j++) rx += drawGlyph(rx, y, cps[j], scale, fg, bg);
      x -= runW;
      k = e;
    } else {
      x -= adv;
      drawGlyph(x, y, cps[k], scale, fg, bg);
      k++;
    }
  }
  return x;
}
