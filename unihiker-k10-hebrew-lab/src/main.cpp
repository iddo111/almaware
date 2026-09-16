#include <Arduino.h>
#include <DFRobot_AHT20.h>
#include <unihiker_k10.h>

#include <cstdio>

#include "dashboard_logic.h"
#include "hebrew_bitmaps.h"

namespace {

constexpr std::uint32_t kBackground = 0x050A14;
constexpr std::uint32_t kHeader = 0x10243E;
constexpr std::uint32_t kCard = 0x0C1A2B;
constexpr std::uint32_t kBorder = 0x285172;
constexpr std::uint32_t kDim = 0x49657A;
constexpr std::uint32_t kWhite = 0xFFFFFF;
constexpr std::uint32_t kCyan = 0x5DEBFF;
constexpr std::uint32_t kYellow = 0xFFDD57;
constexpr std::uint32_t kOrange = 0xFF9F43;
constexpr std::uint32_t kMagenta = 0xFF69D4;
constexpr std::uint32_t kGreen = 0x63F59A;
constexpr std::uint32_t kRed = 0xFF647C;

constexpr std::uint32_t kEnvironmentRetryMs = 10000U;
constexpr int kScreenWidth = 240;

UNIHIKER_K10 k10;
DFRobot_AHT20 environmentSensor;

struct Readings {
  std::uint16_t lightLux = 0U;
  float temperatureC = 0.0F;
  float humidityRh = 0.0F;
  int accelerationX = 0;
  int accelerationY = 0;
  int accelerationZ = 0;
  int accelerationMagnitude = 0;
  bool temperatureValid = false;
  bool humidityValid = false;
  bool buttonA = false;
  bool buttonB = false;
};

Readings readings;
bool environmentReady = false;
std::uint32_t lastEnvironmentAttempt = 0U;
std::uint32_t lastSensorRefresh = 0U;
std::uint32_t lastButtonPoll = 0U;

void fillRectangle(int x, int y, int width, int height,
                   std::uint32_t color) {
  k10.canvas->canvasSetLineWidth(1);
  k10.canvas->canvasRectangle(x, y, width, height, color, color, true);
}

void drawCard(int x, int y, int width, int height,
              std::uint32_t accent) {
  k10.canvas->canvasSetLineWidth(2);
  k10.canvas->canvasRectangle(x, y, width, height, accent, kCard, true);
  k10.canvas->canvasSetLineWidth(1);
}

void drawText(const char* text, int x, int y, std::uint32_t color) {
  k10.canvas->canvasText(text, x, y, color, Canvas::eCNAndENFont16, 50,
                         false);
}

void drawHebrewBitmap(const hebrew::Bitmap& bitmap, int x, int y,
                      std::uint32_t color) {
  k10.canvas->canvasSetLineWidth(1);
  for (std::uint16_t row = 0; row < bitmap.height; ++row) {
    std::uint16_t column = 0U;
    while (column < bitmap.width) {
      while (column < bitmap.width && !hebrew::pixel(bitmap, column, row)) {
        ++column;
      }
      const std::uint16_t runStart = column;
      while (column < bitmap.width && hebrew::pixel(bitmap, column, row)) {
        ++column;
      }
      if (column > runStart) {
        k10.canvas->canvasRectangle(x + runStart, y + row,
                                    column - runStart, 1, color, color, true);
      }
    }
  }
}

void drawHebrewRightAligned(const hebrew::Bitmap& bitmap, int right, int y,
                            std::uint32_t color) {
  drawHebrewBitmap(bitmap, right - bitmap.width, y, color);
}

void drawStaticDashboard() {
  k10.canvas->canvasClear();
  fillRectangle(0, 0, 240, 320, kBackground);
  fillRectangle(0, 0, 240, 49, kHeader);
  fillRectangle(0, 47, 240, 2, kCyan);

  drawHebrewBitmap(hebrew::kTitle,
                   (kScreenWidth - static_cast<int>(hebrew::kTitle.width)) / 2,
                   4, kWhite);

  drawCard(6, 52, 228, 27, kCyan);
  drawHebrewRightAligned(hebrew::kIdentity, 226, 59, kCyan);

  char identity[28];
  const std::uint16_t shortId =
      static_cast<std::uint16_t>(ESP.getEfuseMac() & 0xFFFFU);
  std::snprintf(identity, sizeof(identity), "K10:%04X  OFFLINE", shortId);
  drawText(identity, 12, 57, kWhite);

  drawCard(6, 82, 228, 39, kYellow);
  drawHebrewRightAligned(hebrew::kLight, 226, 87, kYellow);

  drawCard(6, 124, 111, 54, kOrange);
  drawHebrewRightAligned(hebrew::kTemp, 109, 130, kOrange);

  drawCard(123, 124, 111, 54, kCyan);
  drawHebrewRightAligned(hebrew::kHumidity, 226, 127, kCyan);

  drawCard(6, 181, 228, 66, kMagenta);
  drawHebrewRightAligned(hebrew::kAccel, 226, 187, kMagenta);

  drawCard(6, 250, 228, 68, kGreen);
  drawHebrewRightAligned(hebrew::kButtons, 226, 256, kGreen);
}

void renderLight() {
  fillRectangle(12, 85, 150, 19, kCard);
  char value[20];
  std::snprintf(value, sizeof(value), "%5u lux", readings.lightLux);
  drawText(value, 12, 85, kWhite);

  constexpr std::uint16_t kTrackWidth = 210U;
  fillRectangle(12, 108, kTrackWidth, 6, kDim);
  const std::uint16_t active =
      dashboard::lightBarPixels(readings.lightLux, kTrackWidth);
  if (active > 0U) {
    fillRectangle(12, 108, active, 6, kYellow);
  }
}

void renderEnvironment() {
  fillRectangle(12, 150, 98, 19, kCard);
  fillRectangle(129, 150, 98, 19, kCard);

  char value[20];
  if (readings.temperatureValid) {
    std::snprintf(value, sizeof(value), "%5.1f C", readings.temperatureC);
  } else {
    std::snprintf(value, sizeof(value), "--.- C");
  }
  drawText(value, 12, 150, readings.temperatureValid ? kWhite : kRed);

  if (readings.humidityValid) {
    std::snprintf(value, sizeof(value), "%5.1f %%", readings.humidityRh);
  } else {
    std::snprintf(value, sizeof(value), "--.- %%");
  }
  drawText(value, 129, 150, readings.humidityValid ? kWhite : kRed);
}

void renderAcceleration() {
  fillRectangle(12, 204, 152, 37, kCard);

  char value[28];
  std::snprintf(value, sizeof(value), "X:%+5d Y:%+5d",
                readings.accelerationX, readings.accelerationY);
  drawText(value, 12, 204, kWhite);
  std::snprintf(value, sizeof(value), "Z:%+5d M:%4d",
                readings.accelerationZ, readings.accelerationMagnitude);
  drawText(value, 12, 222, kWhite);

  fillRectangle(172, 202, 52, 40, kCard);
  k10.canvas->canvasSetLineWidth(1);
  k10.canvas->canvasLine(177, 222, 219, 222, kDim);
  k10.canvas->canvasLine(198, 202, 198, 242, kDim);
  const int dotX =
      198 + dashboard::accelerometerOffset(readings.accelerationX, 17);
  const int dotY =
      222 + dashboard::accelerometerOffset(readings.accelerationY, 17);
  k10.canvas->canvasCircle(dotX, dotY, 3, kMagenta, kMagenta, true);
}

void drawButtonPill(int x, bool pressed, char buttonName) {
  const std::uint32_t fill = pressed ? kGreen : kHeader;
  const std::uint32_t text = pressed ? kBackground : kWhite;
  k10.canvas->canvasSetLineWidth(2);
  k10.canvas->canvasRectangle(x, 279, 96, 29, kGreen, fill, true);

  char label[12];
  std::snprintf(label, sizeof(label), "%c  %s", buttonName,
                pressed ? "DOWN" : "UP");
  drawText(label, x + 13, 285, text);
}

void renderButtons() {
  fillRectangle(10, 276, 220, 36, kCard);
  drawButtonPill(12, readings.buttonA, 'A');
  drawButtonPill(132, readings.buttonB, 'B');
}

void tryInitializeEnvironment(std::uint32_t now) {
  if (environmentReady) {
    return;
  }
  if (lastEnvironmentAttempt != 0U &&
      !dashboard::refreshDue(now, lastEnvironmentAttempt,
                             kEnvironmentRetryMs)) {
    return;
  }

  lastEnvironmentAttempt = now;
  environmentReady = environmentSensor.begin() == 0U;
  if (!environmentReady) {
    readings.temperatureValid = false;
    readings.humidityValid = false;
  }
}

void sampleSensors(std::uint32_t now) {
  readings.lightLux = k10.readALS();
  readings.accelerationX = k10.getAccelerometerX();
  readings.accelerationY = k10.getAccelerometerY();
  readings.accelerationZ = k10.getAccelerometerZ();
  readings.accelerationMagnitude = k10.getStrength();

  tryInitializeEnvironment(now);
  if (environmentReady && environmentSensor.startMeasurementReady(true)) {
    const float temperature = environmentSensor.getTemperature_C();
    const float humidity = environmentSensor.getHumidity_RH();
    readings.temperatureValid = dashboard::validTemperature(temperature);
    readings.humidityValid = dashboard::validHumidity(humidity);
    if (readings.temperatureValid) {
      readings.temperatureC = temperature;
    }
    if (readings.humidityValid) {
      readings.humidityRh = humidity;
    }
  }
}

bool readButtonA() {
  return k10.buttonA != nullptr && k10.buttonA->isPressed();
}

bool readButtonB() {
  return k10.buttonB != nullptr && k10.buttonB->isPressed();
}

}  // namespace

void setup() {
  k10.begin();
  k10.initScreen(2);
  k10.creatCanvas();
  k10.setScreenBackground(kBackground);

  drawStaticDashboard();

  const std::uint32_t now = millis();
  lastEnvironmentAttempt = 0U;
  sampleSensors(now);
  readings.buttonA = readButtonA();
  readings.buttonB = readButtonB();
  renderLight();
  renderEnvironment();
  renderAcceleration();
  renderButtons();
  k10.canvas->updateCanvas();

  lastSensorRefresh = now;
  lastButtonPoll = now;
}

void loop() {
  const std::uint32_t now = millis();
  bool changed = false;

  if (dashboard::refreshDue(now, lastSensorRefresh,
                            dashboard::kSensorRefreshMs)) {
    lastSensorRefresh = now;
    sampleSensors(now);
    renderLight();
    renderEnvironment();
    renderAcceleration();
    changed = true;
  }

  if (dashboard::refreshDue(now, lastButtonPoll, dashboard::kButtonPollMs)) {
    lastButtonPoll = now;
    const bool buttonA = readButtonA();
    const bool buttonB = readButtonB();
    if (buttonA != readings.buttonA || buttonB != readings.buttonB) {
      readings.buttonA = buttonA;
      readings.buttonB = buttonB;
      renderButtons();
      changed = true;
    }
  }

  if (changed) {
    k10.canvas->updateCanvas();
  }
  delay(5);
}

