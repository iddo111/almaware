#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <limits>

#include "dashboard_logic.h"
#include "hebrew_bitmaps.h"

namespace {

int failures = 0;

void check(bool condition, const char* description) {
  if (!condition) {
    std::cerr << "FAIL: " << description << '\n';
    ++failures;
  }
}

std::size_t litPixelCount(const hebrew::Bitmap& bitmap) {
  std::size_t count = 0U;
  for (std::uint16_t y = 0U; y < bitmap.height; ++y) {
    for (std::uint16_t x = 0U; x < bitmap.width; ++x) {
      count += hebrew::pixel(bitmap, x, y) ? 1U : 0U;
    }
  }
  return count;
}

void testRefreshTiming() {
  check(!dashboard::refreshDue(999U, 0U, 1000U),
        "refresh waits for interval");
  check(dashboard::refreshDue(1000U, 0U, 1000U),
        "refresh fires at interval");
  check(dashboard::refreshDue(0x00000010U, 0xFFFFFFF0U, 0x20U),
        "refresh handles uint32 wraparound");
}

void testEnvironmentalValidation() {
  check(dashboard::validTemperature(-40.0F), "minimum temperature is valid");
  check(dashboard::validTemperature(85.0F), "maximum temperature is valid");
  check(!dashboard::validTemperature(-40.1F), "too-low temperature is rejected");
  check(!dashboard::validTemperature(85.1F), "too-high temperature is rejected");
  check(!dashboard::validTemperature(
            std::numeric_limits<float>::quiet_NaN()),
        "NaN temperature is rejected");
  check(dashboard::validHumidity(0.0F), "zero humidity is valid");
  check(dashboard::validHumidity(100.0F), "100 percent humidity is valid");
  check(!dashboard::validHumidity(100.1F), "too-high humidity is rejected");
}

void testLightScale() {
  constexpr std::uint16_t width = 200U;
  check(dashboard::lightBarPixels(0U, width) == 0U,
        "zero lux gives empty bar");
  check(dashboard::lightBarPixels(100U, width) == 50U,
        "100 lux maps to 25 percent");
  check(dashboard::lightBarPixels(1000U, width) == 120U,
        "1000 lux maps to 60 percent");
  check(dashboard::lightBarPixels(10000U, width) == 170U,
        "10000 lux maps to 85 percent");
  check(dashboard::lightBarPixels(64000U, width) == width,
        "documented maximum fills bar");
  check(dashboard::lightBarPixels(65535U, width) == width,
        "out-of-range input remains capped");

  std::uint16_t previous = 0U;
  for (std::uint32_t lux = 0U; lux <= 65535U; ++lux) {
    const std::uint16_t current =
        dashboard::lightBarPixels(static_cast<std::uint16_t>(lux), width);
    check(current >= previous, "light scale is monotonic");
    check(current <= width, "light scale stays in bounds");
    previous = current;
  }
}

void testAccelerationMapping() {
  check(dashboard::accelerometerOffset(0, 17) == 0,
        "zero acceleration is centered");
  check(dashboard::accelerometerOffset(1024, 17) == 17,
        "positive one-g raw reference reaches edge");
  check(dashboard::accelerometerOffset(-1024, 17) == -17,
        "negative one-g raw reference reaches edge");
  check(dashboard::accelerometerOffset(4096, 17) == 17,
        "positive acceleration is clamped");
  check(dashboard::accelerometerOffset(-4096, 17) == -17,
        "negative acceleration is clamped");
}

void testHebrewBitmaps() {
  const hebrew::Bitmap bitmaps[] = {
      hebrew::kTitle,    hebrew::kIdentity, hebrew::kLight,
      hebrew::kTemp,     hebrew::kHumidity, hebrew::kAccel,
      hebrew::kButtons,
  };

  for (const hebrew::Bitmap& bitmap : bitmaps) {
    check(bitmap.byteCount ==
              hebrew::requiredBytes(bitmap.width, bitmap.height),
          "bitmap byte count matches dimensions");
    check(litPixelCount(bitmap) > 20U, "bitmap contains visible glyph pixels");
    check(bitmap.width <= 228U, "bitmap fits dashboard width");
  }
  check(hebrew::kTitle.width == 161U && hebrew::kTitle.height == 20U,
        "Hebrew title dimensions stay stable");
}

}  // namespace

int main() {
  testRefreshTiming();
  testEnvironmentalValidation();
  testLightScale();
  testAccelerationMapping();
  testHebrewBitmaps();

  if (failures != 0) {
    std::cerr << failures << " host test(s) failed\n";
    return EXIT_FAILURE;
  }
  std::cout << "PASS: dashboard pure logic and Hebrew bitmap invariants\n";
  return EXIT_SUCCESS;
}

