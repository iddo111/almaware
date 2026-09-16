// ALMA-OS for LILYGO T-Deck — v0.1 skeleton
// boot → Hebrew splash → chat card: keyboard echo (Hebrew-first) + LoRa send/recv.
//
// HONESTY: this build is coherent, reviewed C++ but has NOT yet been flashed to
// hardware. Flash order: verify pins in board_tdeck.h, then `pio run -t upload`.
//
// לזכרה של עלמה ז"ל · ALMAWARE
#include <Arduino.h>
#include <SPI.h>
#include <Wire.h>
#include "board_tdeck.h"
#include "display_st7789.h"
#include "keyboard.h"
#include "radio_sx1262.h"
#include "mesh.h"
#include "assistant.h"
#include "utf8.h"
#include "font_hebrew.h"   // FONT_W/FONT_H metrics (unused array is elided by gcc)
#include "cards.h"         // card registry + trackball switching

static DisplayST7789 tft;
static Keyboard      kb;
static RadioSX1262   radio;
static AlmaMesh      mesh;
static Trackball     ball;

static bool radioOk = false;

// ---------- chat state ----------
#define LOG_LINES 8
static String logLines[LOG_LINES];      // ring of finished lines (UTF-8)
static bool   logMine[LOG_LINES];       // true = sent by me (blue), false = received
static int    logCount = 0;
static String input;                    // current input line (UTF-8, logical order)
static uint32_t lastKeyMs = 0;
static bool   screenOn = true;

static const int STATUS_H   = 24;
static const int INPUT_H    = 28;
static const int LINE_H     = FONT_H + 2;   // 18 px, scale 1

static float batteryVolts() {
  // 12-bit ADC, 3.3 V ref, 1:2 divider on PIN_BAT_ADC
  uint32_t mv = analogReadMilliVolts(PIN_BAT_ADC);
  return (mv * 2) / 1000.0f;
}

static void pushLog(const String &line, bool mine) {
  if (logCount < LOG_LINES) {
    logLines[logCount] = line; logMine[logCount] = mine; logCount++;
  } else {
    for (int i = 1; i < LOG_LINES; i++) { logLines[i-1] = logLines[i]; logMine[i-1] = logMine[i]; }
    logLines[LOG_LINES-1] = line; logMine[LOG_LINES-1] = mine;
  }
}

// ---------- UI ----------
static void drawStatusBar() {
  tft.fillRect(0, 0, TFT_WIDTH, STATUS_H, C_ALMA);
  tft.drawTextRTL(TFT_WIDTH - 4, 4, "עלמא", 1, C_WHITE, C_ALMA);
  char left[48];
  snprintf(left, sizeof(left), "%s %.2fV %s",
           radioOk ? "LoRa:OK" : "LoRa:--", batteryVolts(),
           kb.hebrewMode() ? "HE" : "EN");
  tft.drawTextLTR(4, 4, left, 1, C_WHITE, C_ALMA);
}

static void drawLog() {
  int top = STATUS_H + 4;
  tft.fillRect(0, top, TFT_WIDTH, TFT_HEIGHT - STATUS_H - INPUT_H - 8, C_WHITE);
  for (int i = 0; i < logCount; i++) {
    uint16_t fg = logMine[i] ? C_ALMA : C_BLACK;
    tft.drawTextRTL(TFT_WIDTH - 4, top + i * LINE_H, logLines[i].c_str(), 1, fg, C_WHITE);
  }
}

static void drawInput() {
  int y = TFT_HEIGHT - INPUT_H;
  tft.fillRect(0, y, TFT_WIDTH, INPUT_H, rgb565(235, 240, 250));
  tft.fillRect(0, y, TFT_WIDTH, 2, C_ALMA);
  // input renders RTL from the right edge; cursor block at the left end of text
  int leftX = tft.drawTextRTL(TFT_WIDTH - 4, y + 6, input.c_str(), 1, C_BLACK, rgb565(235, 240, 250));
  tft.fillRect(leftX - FONT_W, y + 6, FONT_W, FONT_H, C_AMBER);   // cursor
}

static void drawAll() { drawStatusBar(); drawLog(); drawInput(); }

// ---------- chat card hooks ----------
static void chatEnter() { /* nothing extra: state persists across switches */ }
static void chatDraw()  { drawAll(); }
static void chatTick()  { drawStatusBar(); }
// chatKey / chatTrackball are defined after handleKey (needs KeyEvent).

static void splash() {
  tft.fillScreen(C_WHITE);
  // big centered שלום — 4 glyphs @ scale 3 = 96 px wide
  int w = tft.textWidth("שלום", 3);
  tft.drawTextRTL((TFT_WIDTH + w) / 2, 60, "שלום", 3, C_ALMA, C_WHITE);
  int w2 = tft.textWidth("עלמא · ALMA-OS v0.1", 1);
  tft.drawTextRTL((TFT_WIDTH + w2) / 2, 125, "עלמא · ALMA-OS v0.1", 1, C_BLACK, C_WHITE);
  int w3 = tft.textWidth("לזכרה של עלמה ז\"ל", 1);
  tft.drawTextRTL((TFT_WIDTH + w3) / 2, 150, "לזכרה של עלמה ז\"ל", 1, C_GRAY, C_WHITE);
}

// ---------- input handling ----------
static void submitLine() {
  if (input.length() == 0) return;
  String line = input;
  input = "";

  if (line[0] == '?') {
    // assistant query: local rules first, else uplink over the mesh
    String q = line.substring(1);
    AssistantReply r = almaAssistantReply(q, millis(), batteryVolts());
    pushLog("אני: " + line, true);
    if (r.handled) {
      pushLog("עלמא: " + r.text, false);
    } else if (radioOk && mesh.sendText(line.c_str())) {
      pushLog("עלמא: שלחתי את השאלה לרשת...", false);
    } else {
      pushLog("עלמא: לא הבנתי עדיין. נסה: ?עזרה", false);
    }
    return;
  }

  bool sent = radioOk && mesh.sendText(line.c_str());
  pushLog((sent ? "אני: " : "אני (לא שודר): ") + line, true);
}

static void handleKey(const KeyEvent &ev) {
  lastKeyMs = millis();
  if (!screenOn) {                       // any key wakes the screen
    screenOn = true; tft.setBacklight(true); drawAll(); return;
  }
  if (ev.enter) { submitLine(); drawLog(); drawInput(); return; }
  if (ev.backspace) {
    // strip one UTF-8 codepoint from the end
    int n = input.length();
    while (n > 0 && ((uint8_t)input[n-1] & 0xC0) == 0x80) n--;
    if (n > 0) n--;
    input = input.substring(0, n);
    drawInput(); return;
  }
  if (ev.langToggled) { drawStatusBar(); return; }
  if (ev.cp) {
    char b[5]; int k = utf8Encode(ev.cp, b); b[k] = 0;
    if (input.length() < 180) input += b;   // fits one LoRa frame
    drawInput();
  }
}

// ---------- chat card key/trackball (need KeyEvent + handleKey above) ----------
static void chatKey(const KeyEvent &ev) { handleKey(ev); }
static void chatTrackball(TBDir dir) {
  // Center click submits the current line; up/down reserved for future scroll.
  if (dir == TBDir::CLICK) { submitLine(); drawLog(); drawInput(); }
}

// ---------- about/system card ----------
static void aboutDraw() {
  tft.fillScreen(C_WHITE);
  tft.fillRect(0, 0, TFT_WIDTH, STATUS_H, C_ALMA);
  tft.drawTextRTL(TFT_WIDTH - 4, 4, "מערכת", 1, C_WHITE, C_ALMA);
  tft.drawTextLTR(4, 4, "ALMA-OS v0.1", 1, C_WHITE, C_ALMA);

  int y = STATUS_H + 12;
  const int dy = LINE_H;
  char buf[48];
  tft.drawTextRTL(TFT_WIDTH - 6, y, "עלמא · מערכת עברית", 1, C_BLACK, C_WHITE); y += dy;
  snprintf(buf, sizeof(buf), "%s %.2fV", radioOk ? "LoRa OK" : "LoRa --", batteryVolts());
  tft.drawTextLTR(6, y, buf, 1, C_BLACK, C_WHITE); y += dy;
  snprintf(buf, sizeof(buf), "uptime %lus", (unsigned long)(millis() / 1000UL));
  tft.drawTextLTR(6, y, buf, 1, C_GRAY, C_WHITE); y += dy;
  snprintf(buf, sizeof(buf), "freq %.1f MHz  SF%d", ALMA_LORA_FREQ_MHZ, ALMA_LORA_SF);
  tft.drawTextLTR(6, y, buf, 1, C_GRAY, C_WHITE); y += dy;
  tft.drawTextRTL(TFT_WIDTH - 6, y, "כדור-מסלול ◀ ▶ להחלפת כרטיס", 1, C_ALMA, C_WHITE); y += dy;
  tft.drawTextRTL(TFT_WIDTH - 6, y, "לזכרה של עלמה ז\"ל", 1, C_GRAY, C_WHITE);
}
static void aboutTick() { aboutDraw(); }   // live uptime/battery

// ---------- card registry ----------
static const Card CARDS[] = {
  { "צ'אט",  chatEnter, chatDraw,  chatKey, chatTrackball, chatTick  },
  { "מערכת", nullptr,   aboutDraw, nullptr, nullptr,       aboutTick },
};
static const int  CARD_COUNT   = (int)(sizeof(CARDS) / sizeof(CARDS[0]));
static int        activeCard   = 0;

const Card *almaCards()      { return CARDS; }
int         almaCardCount()  { return CARD_COUNT; }
int         almaActiveCard() { return activeCard; }

static void drawActive() {
  const Card &c = CARDS[activeCard];
  if (c.draw) c.draw();
}

void almaSwitchCard(int delta) {
  if (CARD_COUNT <= 1) return;
  activeCard = (activeCard + delta % CARD_COUNT + CARD_COUNT) % CARD_COUNT;
  const Card &c = CARDS[activeCard];
  if (c.onEnter) c.onEnter();
  tft.fillScreen(C_WHITE);
  drawActive();
  Serial.printf("[card] -> %d\n", activeCard);
}

// ---------- arduino ----------
void setup() {
  pinMode(PIN_BOARD_POWERON, OUTPUT);
  digitalWrite(PIN_BOARD_POWERON, HIGH);   // power the peripheral rail FIRST
  delay(500);                              // let kb co-processor + panel boot

  Serial.begin(115200);
  Serial.println("[alma-os] boot");

  SPI.begin(PIN_SPI_SCK, PIN_SPI_MISO, PIN_SPI_MOSI);
  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, 400000);

  tft.begin(SPI);
  splash();

  kb.begin(Wire);
  ball.begin();
  radioOk = radio.begin(SPI);
  Serial.printf("[alma-os] radio %s\n", radioOk ? "OK" : "FAILED");
  mesh.begin(&radio);

  delay(1500);                             // let the splash breathe
  tft.fillScreen(C_WHITE);
  pushLog(radioOk ? "עלמא: הרשת פעילה. כתוב הודעה ↵"
                  : "עלמא: הרדיו לא עלה — בדקו חיווט/תדר", false);
  drawActive();
  lastKeyMs = millis();
}

void loop() {
  // keyboard -> active card
  static uint32_t lastKbPoll = 0;
  if (millis() - lastKbPoll >= 20) {
    lastKbPoll = millis();
    KeyEvent ev = kb.poll();
    if (ev.valid) {
      const Card &c = CARDS[activeCard];
      if (c.onKey) c.onKey(ev);
    }
  }

  // trackball: LEFT/RIGHT switch cards; UP/DOWN/CLICK -> active card
  TBDir d = ball.poll();
  if (d != TBDir::NONE) {
    lastKeyMs = millis();
    if (!screenOn) {                       // any trackball motion wakes screen
      screenOn = true; tft.setBacklight(true); drawActive();
    } else if (d == TBDir::LEFT) {
      almaSwitchCard(-1);
    } else if (d == TBDir::RIGHT) {
      almaSwitchCard(+1);
    } else {
      const Card &c = CARDS[activeCard];
      if (c.onTrackball) c.onTrackball(d);
    }
  }

  // mesh receive
  AlmaMessage m;
  if (mesh.poll(m)) {
    char who[16];
    snprintf(who, sizeof(who), "%04X", (unsigned)(m.src & 0xFFFF));
    pushLog(String("מ-") + who + ": " + m.text, false);
    if (screenOn && activeCard == 0) { drawLog(); }   // only if chat card visible
    Serial.printf("[rx] %s rssi=%.0f snr=%.1f\n", m.text, m.rssi, m.snr);
  }

  // status refresh + screen dim (60 s idle)
  static uint32_t lastTick = 0;
  if (millis() - lastTick >= 5000) {
    lastTick = millis();
    if (screenOn && millis() - lastKeyMs > 60000) {
      screenOn = false; tft.setBacklight(false);
    }
    if (screenOn) {
      const Card &c = CARDS[activeCard];
      if (c.tick) c.tick();
    }
  }

  delay(2);   // cooperative loop; light-sleep power path is on the roadmap
}
