// card_settings.h — הגדרות (Settings) card. See design/04-firmware-os.md §4.
// A simple trackball-navigable list: radio params (freq/SF/BW/power, mirrors
// board_tdeck.h ALMA_LORA_* defaults), HE/EN default boot language, backlight
// timeout, power profile (firmware/core/power.h PowerProfile enum).
//
// Changes persist to SD (small key-value file, reusing
// firmware/hal/sd_storage.h helpers) so they survive reboot — separate from
// the compiled-in board_tdeck.h defaults, which remain the fallback if the
// settings file is absent/corrupt.
//
// STUB: no list-rendering or persistence implemented yet.
//
// לזכרה של עלמה ז"ל · ALMAWARE
#pragma once

void cardSettingsEnter();
void cardSettingsDraw();
struct KeyEvent; void cardSettingsKey(const KeyEvent &ev);
enum class TBDir : uint8_t; void cardSettingsTrackball(TBDir dir);
void cardSettingsTick();
