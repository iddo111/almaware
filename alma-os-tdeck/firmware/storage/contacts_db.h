// contacts_db.h — node_id -> display_name (+ pubkey, last_seen) table, per
// design doc §5. Backed by SD:/alma/db/contacts.db (append-with-compaction),
// mirrored into a PSRAM hash table at boot for O(1) lookup while rendering
// chat lines (mapping AlmaMessage.src -> a human name instead of a hex id).
//
// STUB: interface only, no implementation yet. Builds on hal/sd_storage.h.
//
// לזכרה של עלמה ז"ל · ALMAWARE
#pragma once
#include <Arduino.h>

#define ALMA_CONTACT_NAME_BYTES 32

struct ContactRecord {
  uint32_t node_id;
  char     display_name[ALMA_CONTACT_NAME_BYTES];   // UTF-8, Hebrew ok
  uint8_t  pubkey[32];    // reserved for future asymmetric identity, may be zero
  uint32_t last_seen_ms;
};

bool almaContactsLoad();                          // SD -> PSRAM table, called once at boot
bool almaContactsUpsert(const ContactRecord &c);  // update-or-insert, persists to SD
bool almaContactsLookup(uint32_t node_id, ContactRecord &out);
size_t almaContactsCount();
size_t almaContactsList(ContactRecord *out, size_t maxCount);  // for the Contacts card
