// sd_storage.h — SD card mount + raw block helpers for ALMA-OS storage layer.
// See design/04-firmware-os.md §5 for the directory layout this backs:
//   SD:/alma/db/{messages,contacts}.db, keys/device.key, maps/, voice/
//
// This is the thin HAL layer (mount, open/read/write/append, free-space
// check); message_db.h and contacts_db.h (firmware/storage/) build the
// actual record formats on top of it.
//
// STUB: interface only, no implementation yet.
//
// לזכרה של עלמה ז"ל · ALMAWARE
#pragma once
#include <Arduino.h>
#include "hal/board_tdeck.h"

bool almaSdBegin();                    // SPI.begin() already done by caller; mounts FS on PIN_SD_CS
bool almaSdReady();
uint64_t almaSdFreeBytes();
uint64_t almaSdTotalBytes();

// Ensures the SD:/alma/{db,keys,maps,voice} directory tree exists (idempotent).
bool almaSdEnsureLayout();

// Thin append/read helpers used by message_db.cpp / contacts_db.cpp — avoid
// pulling SD.h into every storage module directly, so the mount point / lib
// choice stays isolated to this one file.
bool almaSdAppend(const char *path, const uint8_t *data, size_t len);
int  almaSdReadAt(const char *path, uint32_t offset, uint8_t *buf, size_t len);
uint32_t almaSdFileSize(const char *path);
