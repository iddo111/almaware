// card_contacts.h — אנשי קשר (Contacts) card. See design/04-firmware-os.md
// §4 screen table. Lists known node IDs -> display names from
// firmware/storage/contacts_db.h; trackball UP/DOWN to select, Enter/CLICK
// jumps to the Chat card pre-filtered to that node's messages.
//
// STUB: draw()/onKey()/onTrackball() bodies not yet implemented. Follows the
// existing Card{} struct contract from src/cards.h (nameHe, onEnter, draw,
// onKey, onTrackball, tick — all optional except draw).
//
// לזכרה של עלמה ז"ל · ALMAWARE
#pragma once

void cardContactsEnter();
void cardContactsDraw();
struct KeyEvent; void cardContactsKey(const KeyEvent &ev);
enum class TBDir : uint8_t; void cardContactsTrackball(TBDir dir);
void cardContactsTick();
