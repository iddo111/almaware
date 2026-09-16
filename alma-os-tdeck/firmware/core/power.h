// power.h — ALMA-OS v0.2 power management: light-sleep + radio duty-cycle +
// battery curve. See design/04-firmware-os.md §6.
//
// v0.1 baseline (already in src/main.cpp): backlight off after 60s idle,
// continuous LoRa RX, delay(2) cooperative loop. This module is the upgrade
// path — replaces the busy-wait with GPIO-wakeup light sleep and adds a
// real LiPo discharge-curve lookup instead of linear voltage-to-percent.
//
// STUB: interface only, not yet wired into src/ or platformio.ini.
//
// לזכרה של עלמה ז"ל · ALMAWARE
#pragma once
#include <Arduino.h>

enum class PowerProfile : uint8_t {
  ALWAYS_LISTENING,   // radio RX continuous — lowest mesh latency, most power
  BALANCED,           // radio duty-cycled, moderate wake window
  BATTERY_SAVER,      // aggressive duty-cycle, longest light-sleep windows
};

// Call once from setup() after PIN_KB_INT and SX1262 DIO1 are configured as
// inputs, to register them as light-sleep GPIO wakeup sources.
void almaPowerInit();

// Enter light sleep until KB_INT or DIO1 (or timeoutMs) fires. Replaces the
// v0.1 `delay(2)` in the main loop. Returns the wake reason for the caller
// to decide whether to poll keyboard, radio, or just re-check ticks.
enum class WakeReason : uint8_t { TIMEOUT, KEY, RADIO };
WakeReason almaPowerLightSleep(uint32_t timeoutMs);

// Backlight PWM dimming step (called from the idle-timeout tick):
// 0-19s: full brightness, 20-59s: dimmed, 60s+: off. Any key/trackball
// activity resets to full immediately (see src/main.cpp screenOn logic).
void almaPowerSetProfile(PowerProfile p);
PowerProfile almaPowerGetProfile();

// Battery: reads PIN_BAT_ADC (see board_tdeck.h) and maps through a LiPo
// discharge-curve table (non-linear — linear volts-to-percent is misleading
// near the curve knees around 3.7-3.5V). Returns 0-100.
int   almaBatteryPercent();
float almaBatteryVolts();
bool  almaBatteryLow();   // true below ~3.4V — triggers Settings/status banner
