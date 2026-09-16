Write file 5 of your build order: `app/segmenter.py`, plus `tests/test_segmenter.py`,
implementing EXACTLY the §3 you just redesigned (VAD + adaptive floor + hysteresis,
pre-roll 300 ms, hangover 600 ms, MEASURED/ASSUMED tags in comments).

Constraints:
- `webrtcvad` must be OPTIONAL at import time: if it is not installed, fall back to
  the adaptive-floor energy path and say so in a journalled event, never crash.
  The class takes an injectable `vad` object so tests need no native library.
- Input is a stream of PCM blocks (bytes, int16 mono 16 kHz, arbitrary length).
  Output is closed utterances carrying their PCM including the pre-roll.
- It must never raise into the audio callback that feeds it.
- No file I/O, no network, no knowledge of decoding or typing.

The tests are the point. Write at least these, each named after the law it defends:
- a 400 ms internal pause does NOT split an utterance (today's real bug);
- a 1.5 s silence DOES close it;
- speech at his p25 level (RMS 0.0034) with room noise at p90 (0.0592) present —
  assert the documented behaviour, whatever your design says it is;
- the pre-roll is present in the emitted PCM (onset is not clipped);
- max-duration force-closes;
- a block that would raise inside the VAD is absorbed, not propagated.

Output exactly two complete files with `FILE:` headers as before. Python 3.13,
stdlib + optional webrtcvad, unittest. No ellipses.
