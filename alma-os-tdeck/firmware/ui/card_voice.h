// card_voice.h — קול (Voice) card. See design/04-firmware-os.md §4/§6.
// Enter/CLICK toggles record (via firmware/hal/audio_i2s.h) -> compress ->
// write to SD:/alma/voice/ (firmware/storage) and/or send in chunks over
// ALMA-MESH (reusing mesh.h's chunking convention noted as roadmap in
// ARCHITECTURE.md §7). Playback of received voice notes also lives here.
//
// STUB: no recording/playback wiring yet — depends on audio_i2s.h landing
// first.
//
// לזכרה של עלמה ז"ל · ALMAWARE
#pragma once

void cardVoiceEnter();
void cardVoiceDraw();
struct KeyEvent; void cardVoiceKey(const KeyEvent &ev);
enum class TBDir : uint8_t; void cardVoiceTrackball(TBDir dir);
void cardVoiceTick();
