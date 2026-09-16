// assistant_lm.h — tier-1 on-device byte-LM hook for עלמא, behind the SAME
// almaAssistantReply() contract defined in src/assistant.h (tier-0 rules,
// unchanged). See ARCHITECTURE.md §8 and design/04-firmware-os.md §2
// (alma_assistant_task, core 1, lowest priority, PSRAM-backed stack).
//
// This is the Eran/Ada-family tiny quantized byte model mentioned in the
// roadmap (README.md "v0.3 — עלמא offline"). Model weights live in PSRAM
// (int8, <=4MB per the smart-compression rule already applied project-wide),
// loaded once at boot from SD:/alma/model/*.bin (falls back to tier-0 rules
// if absent — the device must stay useful with zero model file present).
//
// STUB: interface only, no model format or inference loop implemented yet.
//
// לזכרה של עלמה ז"ל · ALMAWARE
#pragma once
#include <Arduino.h>

struct AssistantReply;   // src/assistant.h (or firmware/assistant/assistant.h once moved)

// Attempts to load quantized weights from SD into PSRAM. Returns false (and
// the assistant stays tier-0-only) if the file is missing or PSRAM budget
// would be exceeded — never a hard failure of the whole device.
bool almaAssistantLmLoad(const char *sdPath);
bool almaAssistantLmReady();

// Greedy-decode a short reply for `query`. Only called from
// alma_assistant_task (never the ui/radio tasks) since inference may take
// hundreds of ms on an ESP32-S3 — matches the "never blocks UI" design
// constraint (§2). Falls back to signalling !handled so the existing
// mesh-uplink-to-PC-gateway path (assistant.h's tier-2) still applies.
AssistantReply almaAssistantLmReply(const String &query, uint32_t uptimeMs, float batV);
