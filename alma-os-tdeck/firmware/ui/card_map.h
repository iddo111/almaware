// card_map.h — מפה (Map) card. See design/04-firmware-os.md §4/§5. Renders
// pre-baked offline RGB565 tiles from SD:/alma/maps/<region>.tiles, overlaid
// with recent mesh BEACON positions (once beacon-with-GPS is added to
// mesh.h — not yet designed, out of scope for this stub).
//
// Trackball UP/DOWN/LEFT/RIGHT pans (note: LEFT/RIGHT are normally reserved
// by the OS for card switching — the Map card claims them locally while
// active in v0.2's onTrackball, same override pattern the chat card could
// use for scroll; needs a small addition to cards.h's dispatch rule, noted
// as a v0.2 open item, not yet resolved here).
//
// STUB: no tile format, no draw implementation yet.
//
// לזכרה של עלמה ז"ל · ALMAWARE
#pragma once

void cardMapEnter();
void cardMapDraw();
struct KeyEvent; void cardMapKey(const KeyEvent &ev);
enum class TBDir : uint8_t; void cardMapTrackball(TBDir dir);
void cardMapTick();
