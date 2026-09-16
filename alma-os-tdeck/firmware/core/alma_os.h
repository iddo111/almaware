// alma_os.h — ALMA-OS v0.2 task bring-up: creates the five pinned FreeRTOS
// tasks described in design/04-firmware-os.md §2 and owns the event bus.
//
// v0.1 (src/main.cpp) runs everything cooperatively inside loop(); this is
// the target shape once radio/audio need real-time isolation from UI/
// assistant work. Migration is incremental — almaOsBegin() can be called
// from src/main.cpp's setup() once the hal/ modules below exist, without
// discarding the current single-loop code (it becomes alma_ui_task's body).
//
// STUB: interface only, not yet wired into src/ or platformio.ini.
//
// לזכרה של עלמה ז"ל · ALMAWARE
#pragma once
#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

// Core assignment (see design doc §2 table):
//   core 0: alma_radio_task (prio 5), alma_audio_task (prio 5)
//   core 1: alma_ui_task (prio 3), alma_storage_task (prio 2),
//           alma_assistant_task (prio 1)
#define ALMA_CORE_PROTOCOL   0
#define ALMA_CORE_APP        1

#define ALMA_PRIO_RADIO      5
#define ALMA_PRIO_AUDIO      5
#define ALMA_PRIO_UI         3
#define ALMA_PRIO_STORAGE    2
#define ALMA_PRIO_ASSISTANT  1

#define ALMA_STACK_RADIO      4096
#define ALMA_STACK_AUDIO      4096
#define ALMA_STACK_UI         8192
#define ALMA_STACK_STORAGE    4096
#define ALMA_STACK_ASSISTANT  16384   // largest: byte-LM working buffers (PSRAM-backed)

// Bring up bus + all five tasks. Call once from setup(), after board power
// rail + shared SPI/I2C buses are up (same ordering as src/main.cpp today).
void almaOsBegin();

// Task entry points (bodies live in firmware/core/alma_os.cpp once implemented).
void almaRadioTask(void *arg);
void almaAudioTask(void *arg);
void almaUiTask(void *arg);
void almaStorageTask(void *arg);
void almaAssistantTask(void *arg);
