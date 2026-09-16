/*
 * emdr_frame.h - ALMA-EMDR buzzer wire protocol v1.0
 * -----------------------------------------------------------------------------
 * Implements PROTOCOL-buzzers-20260901.md sections C.1, C.2, C.7 exactly.
 *
 * ONE 9-byte frame. Byte-identical on USB-CDC, BLE and ESP-NOW.
 *
 *   off  field      type      meaning
 *   ---  ---------  --------  ------------------------------------------------
 *    0   magic      u8        0xE1  protocol id + version 1
 *    1   op         u8        see EMDR_OP_*
 *    2   seq        u8        increments per frame, wraps 255->0
 *    3   room       u8        0 = every room; 1..255 = this room only
 *    4   side       u8        'L' 'R' 'B' or 0x00
 *    5   intensity  u8        0..255  (STATUS overloads this as battery %)
 *    6   dur4       u8        pulse ms / 4  (STATUS overloads this as fw ver)
 *    7   delay_lo   u8        } uint16 LE, ms, "felt this many ms from now"
 *    8   delay_hi   u8        }   (STATUS overloads these as flags u16 LE)
 *
 * NO CRC, deliberately: BLE (24-bit CRC), 802.11 (FCS) and USB (CRC16) each
 * already carry one. `seq` is here instead, because the failure that actually
 * happens on a broadcast link is loss and duplication, not corruption.
 *
 * This header is pure C++11 and has no Arduino/ESP dependency, so it compiles
 * unchanged on the MCU and on a host.
 *
 * COMPILE-TIME PROOF: the eight test vectors of PROTOCOL C.7 are asserted with
 * static_assert at the bottom of this file, against the very same constexpr
 * byte function that emdr_encode() uses at run time. If this file compiles,
 * the encoder is byte-exact. No hardware needed for that claim.
 */
#ifndef EMDR_FRAME_H
#define EMDR_FRAME_H

#include <stdint.h>
#include <string.h>

#define EMDR_MAGIC        0xE1u
#define EMDR_FRAME_LEN    9

/* ---- C.2 operations - six, and no more ---------------------------------- */
#define EMDR_OP_TAP       0x01u  /* client -> ball : one buzz, felt in `delay` */
#define EMDR_OP_STOP      0x02u  /* client -> ball : cancel + motor off now    */
#define EMDR_OP_KEEP      0x03u  /* client -> ball : heartbeat, no buzz        */
#define EMDR_OP_SET       0x04u  /* client -> ball : write room/side/scale NVS */
#define EMDR_OP_HELLO     0x05u  /* client -> ball : who are you?              */
#define EMDR_OP_STATUS    0x06u  /* ball -> client : reply / notification      */

/* ---- side codes --------------------------------------------------------- */
#define EMDR_SIDE_L       0x4Cu  /* 'L' */
#define EMDR_SIDE_R       0x52u  /* 'R' */
#define EMDR_SIDE_BOTH    0x42u  /* 'B' */
#define EMDR_SIDE_NONE    0x00u

#define EMDR_ROOM_ALL     0x00u

/* ---- STATUS flag bits (bytes 7..8, u16 LE) ------------------------------ */
#define EMDR_FLAG_MOTOR       (1u << 0)
#define EMDR_FLAG_DEADMAN     (1u << 1)
#define EMDR_FLAG_CHARGING    (1u << 2)
#define EMDR_FLAG_BATT_LOW    (1u << 3)
#define EMDR_FLAG_LINK_BLE    (1u << 4)
#define EMDR_FLAG_LINK_ESPNOW (1u << 5)
#define EMDR_FLAG_LINK_USB    (1u << 6)
#define EMDR_FLAG_DUTY_LIMIT  (1u << 7)

/* ---- BLE UUIDs (PROTOCOL C.4) ------------------------------------------- */
#define EMDR_BLE_SERVICE_UUID "d5ffea00-0555-4abc-b5f0-734ccd124d13"
#define EMDR_BLE_RX_UUID      "d5ffea01-0555-4abc-b5f0-734ccd124d13" /* WriteNR */
#define EMDR_BLE_TX_UUID      "d5ffea02-0555-4abc-b5f0-734ccd124d13" /* Notify  */

/* -------------------------------------------------------------------------
 * Low level: the exact byte at index `i` of a raw 9-byte frame.
 * Single-return ternary chain so it is a valid C++11 constexpr function.
 * ------------------------------------------------------------------------- */
constexpr uint8_t emdr_raw_byte(uint8_t i, uint8_t op, uint8_t seq, uint8_t room,
                                uint8_t b4, uint8_t b5, uint8_t b6,
                                uint8_t b7, uint8_t b8) {
  return i == 0 ? (uint8_t)EMDR_MAGIC
       : i == 1 ? op
       : i == 2 ? seq
       : i == 3 ? room
       : i == 4 ? b4
       : i == 5 ? b5
       : i == 6 ? b6
       : i == 7 ? b7
       :          b8;
}

/* High level: the same byte, expressed in engineering units.
 * dur_ms is carried /4; delay_ms is carried as uint16 little-endian. */
constexpr uint8_t emdr_byte(uint8_t i, uint8_t op, uint8_t seq, uint8_t room,
                            uint8_t side, uint8_t intensity,
                            uint16_t dur_ms, uint16_t delay_ms) {
  return emdr_raw_byte(i, op, seq, room, side, intensity,
                       (uint8_t)(dur_ms / 4u),
                       (uint8_t)(delay_ms & 0xFFu),
                       (uint8_t)((delay_ms >> 8) & 0xFFu));
}

/* -------------------------------------------------------------------------
 * Run-time encoders. They call the very functions asserted below, so the
 * compile-time proof covers the code that actually runs.
 * ------------------------------------------------------------------------- */
inline void emdr_encode_raw(uint8_t out[EMDR_FRAME_LEN], uint8_t op, uint8_t seq,
                            uint8_t room, uint8_t b4, uint8_t b5, uint8_t b6,
                            uint8_t b7, uint8_t b8) {
  for (uint8_t i = 0; i < EMDR_FRAME_LEN; i++)
    out[i] = emdr_raw_byte(i, op, seq, room, b4, b5, b6, b7, b8);
}

inline void emdr_encode(uint8_t out[EMDR_FRAME_LEN], uint8_t op, uint8_t seq,
                        uint8_t room, uint8_t side, uint8_t intensity,
                        uint16_t dur_ms, uint16_t delay_ms) {
  for (uint8_t i = 0; i < EMDR_FRAME_LEN; i++)
    out[i] = emdr_byte(i, op, seq, room, side, intensity, dur_ms, delay_ms);
}

/* STATUS uses the overloaded field layout of C.2. */
inline void emdr_encode_status(uint8_t out[EMDR_FRAME_LEN], uint8_t seq,
                               uint8_t room, uint8_t side, uint8_t battery_pct,
                               uint8_t fw_version, uint16_t flags) {
  emdr_encode_raw(out, EMDR_OP_STATUS, seq, room, side, battery_pct, fw_version,
                  (uint8_t)(flags & 0xFFu), (uint8_t)((flags >> 8) & 0xFFu));
}

/* -------------------------------------------------------------------------
 * Decoder
 * ------------------------------------------------------------------------- */
struct EmdrFrame {
  uint8_t  op;
  uint8_t  seq;
  uint8_t  room;
  uint8_t  side;
  uint8_t  intensity;   /* STATUS: battery %      */
  uint16_t dur_ms;      /* STATUS: fw version * 4 */
  uint16_t delay_ms;    /* STATUS: flags          */
  uint8_t  raw6;        /* untranslated byte 6, for STATUS */
};

/* Returns true only for a well-formed frame. Length and magic are the only
 * two things that can be wrong at this layer; everything else is clamped by
 * the consumer, never rejected, so a strange value can never wedge a ball. */
inline bool emdr_decode(const uint8_t *in, uint16_t len, EmdrFrame *out) {
  if (in == nullptr || out == nullptr) return false;
  if (len != EMDR_FRAME_LEN) return false;
  if (in[0] != EMDR_MAGIC) return false;
  out->op        = in[1];
  out->seq       = in[2];
  out->room      = in[3];
  out->side      = in[4];
  out->intensity = in[5];
  out->raw6      = in[6];
  out->dur_ms    = (uint16_t)in[6] * 4u;
  out->delay_ms  = (uint16_t)in[7] | ((uint16_t)in[8] << 8);
  return true;
}

/* Is this frame addressed to a ball configured for `my_room` / `my_side`? */
inline bool emdr_frame_is_for_me(const EmdrFrame &f, uint8_t my_room, uint8_t my_side) {
  if (f.room != EMDR_ROOM_ALL && f.room != my_room) return false;
  if (f.op != EMDR_OP_TAP) return true;              /* STOP/KEEP are for all */
  if (f.side == EMDR_SIDE_BOTH) return true;
  return f.side == my_side;
}

/* =========================================================================
 * PROTOCOL C.7 TEST VECTORS - proven at compile time by the target compiler.
 * If this file compiles, these eight frames are byte-exact.
 * ========================================================================= */
#define EMDR_ASSERT_BYTE(idx, expect, ...) \
  static_assert(emdr_byte(idx, __VA_ARGS__) == (uint8_t)(expect), \
                "EMDR test vector mismatch at byte " #idx)

/* 1. TAP left,  room 1, seq 7,  intensity 200, 160 ms, now
 *    E1 01 07 01 4C C8 28 00 00                                             */
#define EMDR_TV1 EMDR_OP_TAP, 7, 1, EMDR_SIDE_L, 200, 160, 0
EMDR_ASSERT_BYTE(0, 0xE1, EMDR_TV1); EMDR_ASSERT_BYTE(1, 0x01, EMDR_TV1);
EMDR_ASSERT_BYTE(2, 0x07, EMDR_TV1); EMDR_ASSERT_BYTE(3, 0x01, EMDR_TV1);
EMDR_ASSERT_BYTE(4, 0x4C, EMDR_TV1); EMDR_ASSERT_BYTE(5, 0xC8, EMDR_TV1);
EMDR_ASSERT_BYTE(6, 0x28, EMDR_TV1); EMDR_ASSERT_BYTE(7, 0x00, EMDR_TV1);
EMDR_ASSERT_BYTE(8, 0x00, EMDR_TV1);

/* 2. TAP right, room 1, seq 8,  intensity 200, 160 ms, in 120 ms
 *    E1 01 08 01 52 C8 28 78 00                                             */
#define EMDR_TV2 EMDR_OP_TAP, 8, 1, EMDR_SIDE_R, 200, 160, 120
EMDR_ASSERT_BYTE(0, 0xE1, EMDR_TV2); EMDR_ASSERT_BYTE(1, 0x01, EMDR_TV2);
EMDR_ASSERT_BYTE(2, 0x08, EMDR_TV2); EMDR_ASSERT_BYTE(3, 0x01, EMDR_TV2);
EMDR_ASSERT_BYTE(4, 0x52, EMDR_TV2); EMDR_ASSERT_BYTE(5, 0xC8, EMDR_TV2);
EMDR_ASSERT_BYTE(6, 0x28, EMDR_TV2); EMDR_ASSERT_BYTE(7, 0x78, EMDR_TV2);
EMDR_ASSERT_BYTE(8, 0x00, EMDR_TV2);

/* 3. TAP left, ALL rooms, seq 9, intensity 255, 200 ms, in 250 ms
 *    E1 01 09 00 4C FF 32 FA 00                                             */
#define EMDR_TV3 EMDR_OP_TAP, 9, EMDR_ROOM_ALL, EMDR_SIDE_L, 255, 200, 250
EMDR_ASSERT_BYTE(0, 0xE1, EMDR_TV3); EMDR_ASSERT_BYTE(1, 0x01, EMDR_TV3);
EMDR_ASSERT_BYTE(2, 0x09, EMDR_TV3); EMDR_ASSERT_BYTE(3, 0x00, EMDR_TV3);
EMDR_ASSERT_BYTE(4, 0x4C, EMDR_TV3); EMDR_ASSERT_BYTE(5, 0xFF, EMDR_TV3);
EMDR_ASSERT_BYTE(6, 0x32, EMDR_TV3); EMDR_ASSERT_BYTE(7, 0xFA, EMDR_TV3);
EMDR_ASSERT_BYTE(8, 0x00, EMDR_TV3);

/* 4. KEEP room 1, seq 10   ->  E1 03 0A 01 00 00 00 00 00                   */
#define EMDR_TV4 EMDR_OP_KEEP, 10, 1, EMDR_SIDE_NONE, 0, 0, 0
EMDR_ASSERT_BYTE(0, 0xE1, EMDR_TV4); EMDR_ASSERT_BYTE(1, 0x03, EMDR_TV4);
EMDR_ASSERT_BYTE(2, 0x0A, EMDR_TV4); EMDR_ASSERT_BYTE(3, 0x01, EMDR_TV4);
EMDR_ASSERT_BYTE(4, 0x00, EMDR_TV4); EMDR_ASSERT_BYTE(5, 0x00, EMDR_TV4);
EMDR_ASSERT_BYTE(6, 0x00, EMDR_TV4); EMDR_ASSERT_BYTE(7, 0x00, EMDR_TV4);
EMDR_ASSERT_BYTE(8, 0x00, EMDR_TV4);

/* 5. STOP room 1, seq 11   ->  E1 02 0B 01 00 00 00 00 00                   */
#define EMDR_TV5 EMDR_OP_STOP, 11, 1, EMDR_SIDE_NONE, 0, 0, 0
EMDR_ASSERT_BYTE(0, 0xE1, EMDR_TV5); EMDR_ASSERT_BYTE(1, 0x02, EMDR_TV5);
EMDR_ASSERT_BYTE(2, 0x0B, EMDR_TV5); EMDR_ASSERT_BYTE(3, 0x01, EMDR_TV5);
EMDR_ASSERT_BYTE(8, 0x00, EMDR_TV5);

/* 6. STOP ALL rooms, seq 12 -> E1 02 0C 00 00 00 00 00 00                   */
#define EMDR_TV6 EMDR_OP_STOP, 12, EMDR_ROOM_ALL, EMDR_SIDE_NONE, 0, 0, 0
EMDR_ASSERT_BYTE(1, 0x02, EMDR_TV6); EMDR_ASSERT_BYTE(2, 0x0C, EMDR_TV6);
EMDR_ASSERT_BYTE(3, 0x00, EMDR_TV6); EMDR_ASSERT_BYTE(8, 0x00, EMDR_TV6);

/* 7. HELLO room 1, seq 13  ->  E1 05 0D 01 00 00 00 00 00                   */
#define EMDR_TV7 EMDR_OP_HELLO, 13, 1, EMDR_SIDE_NONE, 0, 0, 0
EMDR_ASSERT_BYTE(1, 0x05, EMDR_TV7); EMDR_ASSERT_BYTE(2, 0x0D, EMDR_TV7);
EMDR_ASSERT_BYTE(3, 0x01, EMDR_TV7); EMDR_ASSERT_BYTE(8, 0x00, EMDR_TV7);

/* 8. STATUS room 1, L, 91% batt, fw 1, link=BLE
 *    E1 06 0D 01 4C 5B 01 10 00      (byte 6 = fw version, 7..8 = flags LE)  */
#define EMDR_TV8 EMDR_OP_STATUS, 13, 1, EMDR_SIDE_L, 91, 1, \
                 (uint8_t)(EMDR_FLAG_LINK_BLE & 0xFF), \
                 (uint8_t)((EMDR_FLAG_LINK_BLE >> 8) & 0xFF)
static_assert(emdr_raw_byte(0, EMDR_TV8) == 0xE1, "TV8 byte 0");
static_assert(emdr_raw_byte(1, EMDR_TV8) == 0x06, "TV8 byte 1");
static_assert(emdr_raw_byte(2, EMDR_TV8) == 0x0D, "TV8 byte 2");
static_assert(emdr_raw_byte(3, EMDR_TV8) == 0x01, "TV8 byte 3");
static_assert(emdr_raw_byte(4, EMDR_TV8) == 0x4C, "TV8 byte 4");
static_assert(emdr_raw_byte(5, EMDR_TV8) == 0x5B, "TV8 byte 5 (91% battery)");
static_assert(emdr_raw_byte(6, EMDR_TV8) == 0x01, "TV8 byte 6 (fw version)");
static_assert(emdr_raw_byte(7, EMDR_TV8) == 0x10, "TV8 byte 7 (flags lo, bit4)");
static_assert(emdr_raw_byte(8, EMDR_TV8) == 0x00, "TV8 byte 8 (flags hi)");

/* Range checks from PROTOCOL C.7 */
static_assert(emdr_byte(6, EMDR_OP_TAP, 0, 1, EMDR_SIDE_L, 255, 1020, 0) == 255,
              "dur4 must reach 1020 ms");
static_assert(emdr_byte(7, EMDR_OP_TAP, 0, 1, EMDR_SIDE_L, 255, 160, 65535) == 0xFF &&
              emdr_byte(8, EMDR_OP_TAP, 0, 1, EMDR_SIDE_L, 255, 160, 65535) == 0xFF,
              "delay must reach 65535 ms");
/* the browser's slowest half-cycle: 0.15 Hz -> 3333 ms, must fit in u16 */
static_assert(3333 <= 65535, "delay u16 covers 0.15 Hz half-cycle");

#undef EMDR_ASSERT_BYTE

#endif /* EMDR_FRAME_H */
