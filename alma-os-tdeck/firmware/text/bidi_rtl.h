// bidi_rtl.h — RTL/bidi shaping logic factored out of display_st7789.cpp's
// drawTextRTL(), per design/04-firmware-os.md §3.2-3.3.
//
// Goal of the split: keep the *layout* algorithm (run detection, run
// ordering, width accounting) testable and reusable independent of the SPI
// glyph-blit calls, so v0.2's layoutParagraph() (word-wrap for assistant
// replies) can share the same run-detection code as the single-line chat
// renderer already in src/display_st7789.cpp.
//
// This is NOT a full UAX#9 engine — same documented scope cut as today's
// drawTextRTL: two levels only (Hebrew base-RTL, embedded LTR runs for
// Latin/digits), no isolates/brackets/combining marks. See design doc §3.2.
//
// STUB: interface only; src/display_st7789.cpp already has a working inline
// implementation of the single-line case — this header is the target shape
// once paragraph wrap is added, not a claim that RTL rendering is unbuilt.
//
// לזכרה של עלמה ז"ל · ALMAWARE
#pragma once
#include <stdint.h>
#include <stddef.h>

enum class RunClass : uint8_t { HEBREW, LTR_NEUTRAL };

struct BidiRun {
  size_t   byteStart;   // offset into the source UTF-8 buffer
  size_t   byteLen;
  RunClass cls;
};

// Split a logical-order UTF-8 string into runs (see design doc §3.2 steps
// 1-3). Returns the number of runs written into `outRuns` (caller-sized
// array; a chat-length line rarely exceeds ~8 runs).
size_t bidiSplitRuns(const char *utf8, size_t len, BidiRun *outRuns, size_t maxRuns);

// Given runs in logical order, returns them in VISUAL draw order (right to
// left overall, each run's internal glyph order handled by the caller based
// on run.cls). This is the array reversal at the heart of step 4.
void bidiRunsToVisualOrder(BidiRun *runs, size_t count);

// Word-wrap a longer logical string (e.g. an assistant reply) into lines
// that fit `maxWidthPx`, without breaking a bidi run across lines where
// avoidable. New in v0.2 — chat/input today assume single-line fit.
struct BidiLine { size_t byteStart; size_t byteLen; };
size_t bidiLayoutParagraph(const char *utf8, size_t len, int maxWidthPx,
                           int scale, BidiLine *outLines, size_t maxLines);
