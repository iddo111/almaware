#pragma once

#include <cmath>
#include <cstdint>

namespace dashboard {

constexpr std::uint32_t kSensorRefreshMs = 1000U;
constexpr std::uint32_t kButtonPollMs = 50U;
constexpr int kOneGApproxRaw = 1024;

inline bool refreshDue(std::uint32_t now, std::uint32_t last,
                       std::uint32_t interval) {
  return static_cast<std::uint32_t>(now - last) >= interval;
}

inline int clampInt(int value, int low, int high) {
  return value < low ? low : (value > high ? high : value);
}

inline int accelerometerOffset(int rawValue, int radiusPixels) {
  const int limited = clampInt(rawValue, -kOneGApproxRaw, kOneGApproxRaw);
  return (limited * radiusPixels) / kOneGApproxRaw;
}

inline bool validTemperature(float celsius) {
  return std::isfinite(celsius) && celsius >= -40.0F && celsius <= 85.0F;
}

inline bool validHumidity(float relativeHumidity) {
  return std::isfinite(relativeHumidity) && relativeHumidity >= 0.0F &&
         relativeHumidity <= 100.0F;
}

// A piecewise scale keeps typical indoor readings visible while still showing
// that the documented 64,000-lux range extends far beyond room lighting.
inline std::uint16_t lightBarPixels(std::uint16_t lux,
                                    std::uint16_t widthPixels) {
  std::uint32_t percent = 0U;

  if (lux <= 100U) {
    percent = (static_cast<std::uint32_t>(lux) * 25U) / 100U;
  } else if (lux <= 1000U) {
    percent = 25U +
              (static_cast<std::uint32_t>(lux - 100U) * 35U) / 900U;
  } else if (lux <= 10000U) {
    percent = 60U +
              (static_cast<std::uint32_t>(lux - 1000U) * 25U) / 9000U;
  } else {
    const std::uint32_t capped = lux > 64000U ? 64000U : lux;
    percent = 85U + ((capped - 10000U) * 15U) / 54000U;
  }

  return static_cast<std::uint16_t>(
      (static_cast<std::uint32_t>(widthPixels) * percent) / 100U);
}

}  // namespace dashboard
