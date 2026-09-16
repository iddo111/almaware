/*
 * emdr_bridge.cpp - THE BOX. The one on the desk with the USB cable.
 * -----------------------------------------------------------------------------
 * This single firmware is Phase 1 AND Phase 3 of the build order (PROTOCOL E):
 *
 *   Phase 1 (wired, this week)   USB in  ->  two 3.5 mm jacks, wires, two balls.
 *   Phase 3 (the room, later)    USB in  ->  ESP-NOW broadcast to 40 balls.
 *
 * Nothing is thrown away between them. You unplug the wires and the balls go
 * wireless. That is why Iddo's "wires first, radio later" instinct was right:
 * the wired box IS the bridge.
 *
 * The USB parser looks at the first byte and nothing else (C.6):
 *   0xE1  -> read 8 more, binary frame
 *   else  -> accumulate to '\n', LEGACY ASCII  ? I P L R X
 * 0xE1 is not valid ASCII, so the two can never be confused. This is why
 * today's ALMA-EMDR.html works against this firmware with zero code changes.
 */
#include "emdr_config.h"

#if EMDR_ROLE_BRIDGE

#include <Arduino.h>
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include <esp_task_wdt.h>

#include "emdr_frame.h"
#include "emdr_motor.h"
#include "emdr_dedup.h"

/* An ASCII L/R has no sequence number and no schedule, so the bridge gives it
 * one of its own (seq from its own counter, delay 0) and broadcasts the proper
 * binary frame. A legacy client therefore also reaches wireless balls - at
 * legacy timing quality, with no look-ahead. Set to 0 to keep ASCII strictly
 * on the wires. */
#ifndef EMDR_ASCII_BRIDGES_TO_RADIO
  #define EMDR_ASCII_BRIDGES_TO_RADIO 1
#endif

/* While the bridge is hearing from a client it emits KEEP to the room at 3 Hz,
 * so wireless balls stay awake for a legacy client that knows nothing about
 * KEEP. It stops the moment USB goes quiet - the dead-man is not weakened by
 * more than this window. */
#define BRIDGE_KEEP_WINDOW_MS  1500u
#define BRIDGE_KEEP_PERIOD_MS   333u

static EmdrMotor g_left, g_right;
static EmdrDedup g_dedup;

static uint8_t  g_room      = DEFAULT_ROOM;
static uint8_t  g_intensity = 200;      /* legacy 'I' default */
static uint16_t g_pulse_ms  = 160;      /* legacy 'P' default */
static uint8_t  g_seq       = 0;
static uint32_t g_last_host_ms = 0;
static bool     g_espnow_ok = false;

static const uint8_t BROADCAST[6] = {0xFF,0xFF,0xFF,0xFF,0xFF,0xFF};

static inline void led(bool on) {
#if PIN_LED_ACTIVE_LOW
  digitalWrite(PIN_LED, on ? LOW : HIGH);
#else
  digitalWrite(PIN_LED, on ? HIGH : LOW);
#endif
}

/* ---- radio -------------------------------------------------------------- */
static void startEspNow() {
  WiFi.mode(WIFI_STA);
  WiFi.disconnect(false, false);
  esp_wifi_set_channel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE);
  if (esp_now_init() != ESP_OK) return;

  esp_now_peer_info_t peer;
  memset(&peer, 0, sizeof(peer));
  memcpy(peer.peer_addr, BROADCAST, 6);
  peer.channel = ESPNOW_CHANNEL;
  peer.encrypt = false;
  peer.ifidx   = WIFI_IF_STA;
  /* C.5: the 20-peer limit is a UNICAST limit. Broadcast has none, and every
   * listening ball hears the same radio frame in the same air slot. That is
   * the whole reason 40 balls are possible at all. */
  if (esp_now_add_peer(&peer) == ESP_OK) g_espnow_ok = true;
}

static void broadcast(const uint8_t *frame) {
  if (!g_espnow_ok) return;
  esp_now_send(BROADCAST, frame, EMDR_FRAME_LEN);
}

/* ---- local wired channels ----------------------------------------------- */
static void driveLocal(const EmdrFrame &f) {
  const uint32_t now = millis();
  uint16_t delay_ms = f.delay_ms;
  if (delay_ms > DELAY_MAX_MS) delay_ms = DELAY_MAX_MS;

  switch (f.op) {
    case EMDR_OP_TAP:
      if (f.side == EMDR_SIDE_L || f.side == EMDR_SIDE_BOTH)
        g_left.scheduleTap(now + delay_ms, f.intensity, f.dur_ms);
      if (f.side == EMDR_SIDE_R || f.side == EMDR_SIDE_BOTH)
        g_right.scheduleTap(now + delay_ms, f.intensity, f.dur_ms);
      g_left.feed(); g_right.feed();
      break;
    case EMDR_OP_STOP:
      g_left.stop(); g_right.stop();
      g_left.feed(); g_right.feed();
      break;
    case EMDR_OP_KEEP:
    case EMDR_OP_SET:
    case EMDR_OP_HELLO:
      g_left.feed(); g_right.feed();
      break;
    default: break;
  }
}

static void sendStatusOverUsb() {
  uint8_t buf[EMDR_FRAME_LEN];
  uint16_t flags = EMDR_FLAG_LINK_USB;
  if (g_left.motorActive() || g_right.motorActive()) flags |= EMDR_FLAG_MOTOR;
  if (g_left.deadmanTripped() && g_right.deadmanTripped()) flags |= EMDR_FLAG_DEADMAN;
  if (g_left.dutyLimited() || g_right.dutyLimited())       flags |= EMDR_FLAG_DUTY_LIMIT;
  if (g_espnow_ok) flags |= EMDR_FLAG_LINK_ESPNOW;
  emdr_encode_status(buf, g_seq++, g_room, EMDR_SIDE_BOTH, 100,
                     EMDR_FW_VERSION, flags);
  Serial.write(buf, EMDR_FRAME_LEN);
}

/* ---- binary path -------------------------------------------------------- */
static void onBinaryFrame(const uint8_t *raw) {
  EmdrFrame f;
  if (!emdr_decode(raw, EMDR_FRAME_LEN, &f)) return;
  g_last_host_ms = millis();

  /* Relay EVERY copy to the air, unchanged. The client triple-sends on
   * purpose (C.1); the balls de-duplicate. The bridge is a repeater, not a
   * protocol converter - one frame, one set of bugs. */
  broadcast(raw);

  /* Locally, act once per (op,seq). */
  if (!g_dedup.accept(f.op, f.seq, millis())) return;
  if (f.room != EMDR_ROOM_ALL && f.room != g_room) return;

  if (f.op == EMDR_OP_HELLO) { sendStatusOverUsb(); return; }
  if (f.op == EMDR_OP_SET) {
    if (f.room != EMDR_ROOM_ALL) g_room = f.room;
    sendStatusOverUsb();
    return;
  }
  driveLocal(f);
}

/* ---- legacy ASCII path (C.6) -------------------------------------------- */
static void onAsciiLine(char *line) {
  g_last_host_ms = millis();
  switch (line[0]) {
    case '?':
      Serial.printf("ALMA-EMDR bridge fw%u room=%u proto=1 espnow=%u\n",
                    EMDR_FW_VERSION, g_room, g_espnow_ok ? 1 : 0);
      break;
    case 'I': {
      long v = atol(line + 1);
      if (v < INTENSITY_FLOOR) v = INTENSITY_FLOOR;
      if (v > 255) v = 255;
      g_intensity = (uint8_t)v;
      break;
    }
    case 'P': {
      long v = atol(line + 1);
      if (v < DUR_MIN_MS) v = DUR_MIN_MS;
      if (v > 400) v = 400;              /* the legacy client's own ceiling */
      g_pulse_ms = (uint16_t)v;
      break;
    }
    case 'L':
    case 'R': {
      uint8_t side = (line[0] == 'L') ? EMDR_SIDE_L : EMDR_SIDE_R;
      const uint32_t now = millis();
      if (side == EMDR_SIDE_L) g_left.scheduleTap(now, g_intensity, g_pulse_ms);
      else                     g_right.scheduleTap(now, g_intensity, g_pulse_ms);
      g_left.feed(); g_right.feed();
#if EMDR_ASCII_BRIDGES_TO_RADIO
      { /* give the legacy command the seq and schedule it never had */
        uint8_t buf[EMDR_FRAME_LEN];
        emdr_encode(buf, EMDR_OP_TAP, g_seq++, g_room, side, g_intensity,
                    g_pulse_ms, 0);
        broadcast(buf); broadcast(buf); broadcast(buf);
      }
#endif
      break;
    }
    case 'X': {
      g_left.stop(); g_right.stop();
      uint8_t buf[EMDR_FRAME_LEN];
      for (int i = 0; i < 5; i++) {            /* D.5: STOP is repeated 5x */
        emdr_encode(buf, EMDR_OP_STOP, g_seq++, EMDR_ROOM_ALL, EMDR_SIDE_NONE,
                    0, 0, 0);
        broadcast(buf);
      }
      break;
    }
    default: break;
  }
}

/* ---- setup / loop ------------------------------------------------------- */
void emdr_bridge_setup() {
  const uint8_t pins[] = { PIN_MOTOR_A, PIN_MOTOR_B };
  emdr_motor_boot_safe(pins, 2);

  pinMode(PIN_LED, OUTPUT);
  led(false);

  Serial.begin(SERIAL_BAUD);

  g_left.begin(PIN_MOTOR_A, PWM_CH_A);
  g_right.begin(PIN_MOTOR_B, PWM_CH_B);

  startEspNow();

#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
  esp_task_wdt_config_t wdt_cfg = { WDT_MS, (1 << portNUM_PROCESSORS) - 1, true };
  esp_task_wdt_reconfigure(&wdt_cfg);
#else
  esp_task_wdt_init(WDT_MS / 1000, true);
#endif
  esp_task_wdt_add(NULL);
}

void emdr_bridge_loop() {
  esp_task_wdt_reset();

  /* --- the USB parser: one byte decides which protocol this is --------- */
  static uint8_t  bin[EMDR_FRAME_LEN];
  static uint8_t  bin_n = 0;
  static bool     in_binary = false;
  static char     line[ASCII_LINE_MAX];
  static uint8_t  line_n = 0;

  while (Serial.available() > 0) {
    int c = Serial.read();
    if (c < 0) break;

    if (in_binary) {
      bin[bin_n++] = (uint8_t)c;
      if (bin_n == EMDR_FRAME_LEN) { in_binary = false; bin_n = 0; onBinaryFrame(bin); }
      continue;
    }
    if ((uint8_t)c == EMDR_MAGIC) {
      in_binary = true; bin[0] = (uint8_t)c; bin_n = 1; line_n = 0;
      continue;
    }
    if (c == '\n' || c == '\r') {
      if (line_n > 0) { line[line_n] = '\0'; onAsciiLine(line); }
      line_n = 0;
      continue;
    }
    if (line_n < ASCII_LINE_MAX - 1) line[line_n++] = (char)c;
    /* a line longer than the buffer is simply truncated; it can never
     * overflow and can never wedge the parser */
  }

  g_left.tick();
  g_right.tick();

  const uint32_t now = millis();

  /* --- KEEP the room awake while the host is talking to us -------------- */
  static uint32_t keep_ms = 0;
  if (g_espnow_ok && (uint32_t)(now - g_last_host_ms) < BRIDGE_KEEP_WINDOW_MS &&
      (uint32_t)(now - keep_ms) >= BRIDGE_KEEP_PERIOD_MS) {
    keep_ms = now;
    uint8_t buf[EMDR_FRAME_LEN];
    emdr_encode(buf, EMDR_OP_KEEP, g_seq++, g_room, EMDR_SIDE_NONE, 0, 0, 0);
    broadcast(buf);
  }

  static uint32_t led_ms = 0;
  static bool led_on = false;
  bool live = (uint32_t)(now - g_last_host_ms) < BRIDGE_KEEP_WINDOW_MS;
  if (g_left.motorActive() || g_right.motorActive()) {
    led(true);
  } else if ((uint32_t)(now - led_ms) >= (live ? 1200u : 150u)) {
    led_ms = now; led_on = !led_on; led(led_on);
  }
}

#endif /* EMDR_ROLE_BRIDGE */
