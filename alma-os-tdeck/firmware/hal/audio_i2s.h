// audio_i2s.h — mic capture (ES7210 ADC) + speaker playback (MAX98357A) over
// I2S, for the alma_audio_task described in design/04-firmware-os.md §2.
// Pins already defined in board_tdeck.h (PIN_I2S_*, PIN_ES7210_*).
//
// This is new hardware surface (v0.1 has no audio code yet). Voice notes are
// captured, lightly compressed (our own codec — no external lib), and either
// written to SD (firmware/storage) or streamed for on-device VAD ahead of
// the assistant's tier-1 model.
//
// STUB: interface only, no implementation yet.
//
// לזכרה של עלמה ז"ל · ALMAWARE
#pragma once
#include <Arduino.h>
#include "hal/board_tdeck.h"

// A captured frame: raw PCM16 mono samples, fixed short duration (e.g. 20ms
// @ 16kHz = 320 samples) to keep latency and RAM bounded — matches typical
// VAD frame sizing.
#define ALMA_AUDIO_FRAME_SAMPLES 320
#define ALMA_AUDIO_SAMPLE_RATE_HZ 16000

struct AudioFrame {
  int16_t samples[ALMA_AUDIO_FRAME_SAMPLES];
  uint32_t ts_ms;
  bool     voice_detected;   // simple energy-based VAD result, filled by capture
};

class AudioI2S {
public:
  bool begin();                          // configure I2S peripheral, both directions
  bool captureFrame(AudioFrame &out);     // non-blocking; false if no frame ready
  bool playSamples(const int16_t *pcm, size_t n);  // blocking write to speaker DMA

  // Simple energy-threshold VAD — no ML, matches tier-0 assistant philosophy.
  // Real voice-activity heuristics tuned once mic hardware is validated.
  bool isVoiceFrame(const AudioFrame &f) const;

private:
  bool _ready = false;
};

// Voice compression is Codec2 (David Rowe, GPL/LGPL, patent-free — open
// standard, not "someone else's product"), per design/03-voice-lora.md,
// NOT reimplemented here: this header only captures/plays raw PCM16 frames.
// The mesh-bound encode/decode (700-1200bps Codec2, FEC, jitter buffer) is
// specified in 03-voice-lora.md §"pipeline" and lands in firmware/mesh/ as
// its own module once implemented — audio_i2s.h stays HAL-only (mic in,
// speaker out, VAD), matching the layering in design/04-firmware-os.md §2.
