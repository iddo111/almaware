// message_db.h — append-only chat message log on SD, per design doc §5.
// SD:/alma/db/messages.db, fixed-width binary records:
//   ts:4  src:4  dst:4  id:2  flags:1  len:1  text:200   (216 bytes/record)
//
// Deliberately not SQLite/a real DB — append + linear scan is plenty for a
// device holding thousands (not millions) of short messages, and avoids
// pulling in an external DB engine (purity law).
//
// STUB: interface only, no implementation yet. Builds on hal/sd_storage.h.
//
// לזכרה של עלמה ז"ל · ALMAWARE
#pragma once
#include <Arduino.h>
#include "mesh/mesh.h"   // AlmaMessage — reuse the same struct shape on disk

#define ALMA_MSG_RECORD_BYTES 216
#define ALMA_MSG_TEXT_BYTES   200

// flags bit 0: mine (sent) vs received; bit 1: encrypted-at-rest (future)
struct MessageRecord {
  uint32_t ts_ms;
  uint32_t src;
  uint32_t dst;
  uint16_t id;
  uint8_t  flags;
  uint8_t  len;
  char     text[ALMA_MSG_TEXT_BYTES];
};

bool almaMsgDbAppend(const MessageRecord &rec);

// Iterate the most recent `count` records (for chat card scrollback) without
// loading the whole file — reads backward from EOF in fixed-size chunks.
size_t almaMsgDbReadRecent(MessageRecord *out, size_t count);

// Rotation: if file exceeds a size budget, archive or truncate oldest
// records. Called periodically from alma_storage_task, not the UI task.
void almaMsgDbRotateIfNeeded(uint32_t maxBytes);
