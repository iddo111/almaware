/*
 * emdr_dedup.h - PROTOCOL C.1 idempotence rule.
 * -----------------------------------------------------------------------------
 * "A ball keeps the last 8 (op, seq) pairs it has acted on for 2000 ms and
 *  silently ignores a repeat. Therefore the client sends every frame 3 times,
 *  ~8 ms apart. The first copy to arrive wins - which is also the lowest-
 *  latency copy - and the other two cost nothing."
 *
 * This is how an unacknowledged broadcast survives loss without acknowledgements.
 */
#ifndef EMDR_DEDUP_H
#define EMDR_DEDUP_H

#include <stdint.h>
#include "emdr_config.h"

class EmdrDedup {
 public:
  /* Returns true the FIRST time an (op,seq) pair is seen inside the window,
   * false for every repeat. Call it once per received frame and act only on
   * a true. */
  bool accept(uint8_t op, uint8_t seq, uint32_t now_ms) {
    for (uint8_t i = 0; i < SEQ_MEMORY_DEPTH; i++) {
      if (!used_[i]) continue;
      if ((int32_t)(now_ms - stamp_[i]) > (int32_t)SEQ_MEMORY_MS) {
        used_[i] = false;                       /* expired */
        continue;
      }
      if (op_[i] == op && seq_[i] == seq) return false;   /* a repeat */
    }
    op_[head_]    = op;
    seq_[head_]   = seq;
    stamp_[head_] = now_ms;
    used_[head_]  = true;
    head_ = (uint8_t)((head_ + 1) % SEQ_MEMORY_DEPTH);
    return true;
  }

  void reset() {
    for (uint8_t i = 0; i < SEQ_MEMORY_DEPTH; i++) used_[i] = false;
    head_ = 0;
  }

 private:
  uint8_t  op_[SEQ_MEMORY_DEPTH]    = {0};
  uint8_t  seq_[SEQ_MEMORY_DEPTH]   = {0};
  uint32_t stamp_[SEQ_MEMORY_DEPTH] = {0};
  bool     used_[SEQ_MEMORY_DEPTH]  = {false};
  uint8_t  head_ = 0;
};

#endif /* EMDR_DEDUP_H */
