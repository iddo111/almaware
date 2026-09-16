// event_bus.h — ALMA-OS v0.2 event bus: one bounded queue, tagged-union events.
// See design/04-firmware-os.md §2 "Event bus" for the full rationale.
//
// Producers (radio task, audio task, kb/trackball poll in ui task, storage
// task) call almaBusSend() — non-blocking, drop-oldest on full. The ui task
// is the sole consumer and dispatches to the active Card's onEvent().
//
// STUB: interface only, not yet wired into src/ or platformio.ini.
//
// לזכרה של עלמה ז"ל · ALMAWARE
#pragma once
#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>

// fwd decls — real definitions live in the modules that own each payload.
struct KeyEvent;        // firmware/hal/keyboard.h (moved from src/keyboard.h)
enum class TBDir : uint8_t;   // firmware/hal/trackball.h
struct AlmaMessage;     // firmware/mesh/mesh.h (moved from src/mesh.h)
struct AudioFrame;      // firmware/hal/audio_i2s.h
struct AssistantReply;  // firmware/assistant/assistant.h (moved from src/assistant.h)

typedef enum {
  EVT_KEY,
  EVT_TRACKBALL,
  EVT_MESH_RX,
  EVT_MESH_TX_DONE,
  EVT_AUDIO_FRAME,
  EVT_ASSISTANT_REPLY,
  EVT_BATTERY,
  EVT_TICK_1S,
} AlmaEventType;

// Payload union kept deliberately small (event bus is a fixed-size ring —
// no pointers into task-local stack memory). Large payloads (audio samples,
// full mesh text) live in PSRAM/SD and are referenced by offset/handle, not
// copied into the event.
typedef struct {
  AlmaEventType type;
  uint32_t      ts_ms;
  union {
    uint8_t  key_placeholder[8];   // KeyEvent is small; direct copy once moved
    uint8_t  trackball_dir;         // TBDir as uint8_t
    uint8_t  mesh_rx_placeholder[32]; // AlmaMessage header fields, not full text
    uint32_t audio_frame_handle;    // index into a ring buffer, not raw samples
    uint8_t  assistant_placeholder[16];
    float    battery_v;
  } data;
} AlmaEvent;

#define ALMA_BUS_DEPTH 32

// Call once from setup() before any task starts producing/consuming.
void almaBusInit();

// Non-blocking send. Returns false (and drops) if the queue is full — a full
// queue means the UI task is wedged; dropping protects the radio/audio tasks
// from ever blocking on a UI stall.
bool almaBusSend(const AlmaEvent &ev);

// Blocking receive with timeout, called only from alma_ui_task.
bool almaBusReceive(AlmaEvent &out, uint32_t timeoutMs);

extern QueueHandle_t g_alma_bus;
