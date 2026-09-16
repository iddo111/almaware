/*
 * emdr_ball.cpp - THE BALL. The thing in the hand.
 * -----------------------------------------------------------------------------
 * One ERM motor. A BLE GATT server (PROTOCOL C.4) and an ESP-NOW listener
 * (C.5). Both feed the SAME 9-byte frame into the SAME motor object, so there
 * is one set of semantics and one set of bugs.
 *
 * Radio coexistence (C.5): the ESP32-C3 has one 2.4 GHz radio time-shared
 * between Wi-Fi and BLE. A ball therefore advertises BLE only while it is
 * unpaired, and shuts BLE down once it is clearly being driven over ESP-NOW.
 */
#include "emdr_config.h"

#if EMDR_ROLE_BALL

#include <Arduino.h>
#include <Preferences.h>
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include <esp_task_wdt.h>

#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>

#include "emdr_frame.h"
#include "emdr_motor.h"
#include "emdr_dedup.h"

/* ---- state -------------------------------------------------------------- */
static EmdrMotor  g_motor;
static EmdrDedup  g_dedup;
static Preferences g_nvs;

static uint8_t  g_room  = DEFAULT_ROOM;
static uint8_t  g_side  = EMDR_SIDE_L;
static uint8_t  g_scale = DEFAULT_SCALE;      /* per-ball intensity %, 0..200 */

static BLECharacteristic *g_tx = nullptr;
static bool     g_ble_connected = false;
static bool     g_ble_advertising = false;
static uint32_t g_last_espnow_ms = 0;
static uint32_t g_last_any_frame_ms = 0;
static uint8_t  g_status_seq = 0;
static uint16_t g_link_flag = 0;

/* Frames arrive on the BLE task and on the Wi-Fi task. Nothing touches the
 * motor from those contexts: they only post 9 bytes into this queue, and
 * loop() is the single owner of all timing. */
static QueueHandle_t g_rx_queue = nullptr;

/* ---- LED ---------------------------------------------------------------- */
static inline void led(bool on) {
#if PIN_LED_ACTIVE_LOW
  digitalWrite(PIN_LED, on ? LOW : HIGH);
#else
  digitalWrite(PIN_LED, on ? HIGH : LOW);
#endif
}

/* ---- battery ------------------------------------------------------------ */
static uint8_t batteryPercent() {
#if PIN_VBAT_ADC >= 0
  uint32_t mv = analogReadMilliVolts(PIN_VBAT_ADC);
  float v = (mv / 1000.0f) * VBAT_DIVIDER;
  float pct = (v - VBAT_EMPTY_V) * 100.0f / (VBAT_FULL_V - VBAT_EMPTY_V);
  if (pct < 0) pct = 0;
  if (pct > 100) pct = 100;
  return (uint8_t)(pct + 0.5f);
#else
  return 100;
#endif
}

/* ---- STATUS (C.2 op 0x06) ----------------------------------------------- */
static uint16_t statusFlags() {
  uint16_t f = 0;
  if (g_motor.motorActive())    f |= EMDR_FLAG_MOTOR;
  if (g_motor.deadmanTripped()) f |= EMDR_FLAG_DEADMAN;
  if (g_motor.dutyLimited())    f |= EMDR_FLAG_DUTY_LIMIT;
  uint8_t b = batteryPercent();
  if (b <= VBAT_LOW_PCT)        f |= EMDR_FLAG_BATT_LOW;
  f |= g_link_flag;
  return f;
}

static void notifyStatus() {
  if (!g_ble_connected || g_tx == nullptr) return;
  uint8_t buf[EMDR_FRAME_LEN];
  emdr_encode_status(buf, g_status_seq++, g_room, g_side,
                     batteryPercent(), EMDR_FW_VERSION, statusFlags());
  g_tx->setValue(buf, EMDR_FRAME_LEN);
  g_tx->notify();
}

/* ---- the one place a frame is acted on ---------------------------------- */
static void handleFrame(const uint8_t *data, uint16_t len, uint16_t link_flag) {
  EmdrFrame f;
  if (!emdr_decode(data, len, &f)) return;
  const uint32_t now = millis();

  if (!emdr_frame_is_for_me(f, g_room, g_side)) return;
  if (!g_dedup.accept(f.op, f.seq, now)) return;    /* C.1 triple-send arrives */

  g_link_flag = link_flag;
  g_last_any_frame_ms = now;

  switch (f.op) {
    case EMDR_OP_TAP: {
      /* Feed FIRST and unconditionally. scheduleTap() legitimately refuses a
       * tap (intensity 0 = silent, dur 0 = no-op), and a refused tap is still
       * proof that a client is alive and talking to us. Without this line a
       * client running with the buzzers switched off would let the ball trip
       * its dead-man and blink the 'nobody is talking to me' pattern. */
      g_motor.feed();
      uint16_t delay_ms = f.delay_ms;
      if (delay_ms > DELAY_MAX_MS) delay_ms = DELAY_MAX_MS;   /* D.5 clamp */
      uint32_t inten = ((uint32_t)f.intensity * g_scale) / 100u;
      if (inten > 255) inten = 255;
      g_motor.scheduleTap(now + delay_ms, (uint8_t)inten, f.dur_ms);
      break;
    }
    case EMDR_OP_STOP:
      g_motor.stop();
      g_motor.feed();          /* stay awake and silent, do not trip dead-man */
      break;

    case EMDR_OP_KEEP:
      g_motor.feed();
      break;

    case EMDR_OP_SET:
      /* C.2: direct link only. A broadcast must never rewrite identity, or a
       * therapist reconfiguring one ball would reconfigure the whole room. */
      if (link_flag == EMDR_FLAG_LINK_BLE) {
        if (f.room != EMDR_ROOM_ALL) g_room = f.room;
        if (f.side == EMDR_SIDE_L || f.side == EMDR_SIDE_R) g_side = f.side;
        if (f.intensity > 0 && f.intensity <= 200) g_scale = f.intensity;
        g_nvs.begin("emdr", false);
        g_nvs.putUChar("room", g_room);
        g_nvs.putUChar("side", g_side);
        g_nvs.putUChar("scale", g_scale);
        g_nvs.end();
        g_motor.feed();
        notifyStatus();
      }
      break;

    case EMDR_OP_HELLO:
      g_motor.feed();
      notifyStatus();
      break;

    default:
      break;                    /* unknown op: ignore, never wedge */
  }
}

/* ---- BLE ---------------------------------------------------------------- */
class BallServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer *) override {
    g_ble_connected = true;
    g_link_flag = EMDR_FLAG_LINK_BLE;
  }
  void onDisconnect(BLEServer *server) override {
    /* SAFETY LAYER 2 (D.5): link loss is an immediate all-off, without
     * waiting for the dead-man. */
    g_ble_connected = false;
    g_motor.stop();
    g_dedup.reset();
    server->startAdvertising();
    g_ble_advertising = true;
  }
};

class BallRxCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *c) override {
    uint8_t *d = c->getData();
    size_t   n = c->getLength();
    if (d == nullptr || n != EMDR_FRAME_LEN || g_rx_queue == nullptr) return;
    uint8_t pkt[EMDR_FRAME_LEN + 1];
    memcpy(pkt, d, EMDR_FRAME_LEN);
    pkt[EMDR_FRAME_LEN] = 0;                 /* 0 = came in over BLE */
    xQueueSend(g_rx_queue, pkt, 0);          /* never block the BLE task */
  }
};

static void startBle() {
  char name[24];
  snprintf(name, sizeof(name), "EMDR-%u-%c", (unsigned)g_room,
           g_side == EMDR_SIDE_R ? 'R' : 'L');

  BLEDevice::init("");                       /* name lives in the scan response */
  BLEServer *server = BLEDevice::createServer();
  server->setCallbacks(new BallServerCallbacks());

  BLEService *svc = server->createService(BLEUUID(EMDR_BLE_SERVICE_UUID), 20);

  BLECharacteristic *rx = svc->createCharacteristic(
      EMDR_BLE_RX_UUID,
      BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
  rx->setCallbacks(new BallRxCallbacks());

  g_tx = svc->createCharacteristic(EMDR_BLE_TX_UUID,
                                   BLECharacteristic::PROPERTY_NOTIFY);
  g_tx->addDescriptor(new BLE2902());

  svc->start();

  /* C.4 advertising budget:
   *   ADV  = flags(3) + complete 128-bit service UUID list(18)      = 21 B
   *   SCAN = local name "EMDR-<room>-<L|R>" + mfr data 0xFFFF{proto,room,batt}
   * No pairing, no bonding, no encryption - deliberately (C.4). */
  BLEAdvertising *adv = BLEDevice::getAdvertising();
  adv->addServiceUUID(BLEUUID(EMDR_BLE_SERVICE_UUID));
  adv->setScanResponse(true);

  BLEAdvertisementData scanResp;
  scanResp.setName(name);
  char mfr[5];
  mfr[0] = (char)0xFF; mfr[1] = (char)0xFF;      /* SIG "reserved for testing" */
  mfr[2] = (char)0x01;                           /* protocol version           */
  mfr[3] = (char)g_room;
  mfr[4] = (char)batteryPercent();
  scanResp.setManufacturerData(std::string(mfr, sizeof(mfr)));
  adv->setScanResponseData(scanResp);

  /* 20-100 ms, in 0.625 ms units. Not optional: a peripheral advertising
   * slower than 1 s takes tens of seconds to connect on Windows, or never. */
  adv->setMinInterval((uint16_t)(BLE_ADV_MIN_MS * 1000 / 625));
  adv->setMaxInterval((uint16_t)(BLE_ADV_MAX_MS * 1000 / 625));

  BLEDevice::startAdvertising();
  g_ble_advertising = true;
}

/* ---- ESP-NOW ------------------------------------------------------------ */
#if defined(ESP_IDF_VERSION_MAJOR) && ESP_IDF_VERSION_MAJOR >= 5
static void onEspNowRecv(const esp_now_recv_info_t *, const uint8_t *data, int len) {
#else
static void onEspNowRecv(const uint8_t *, const uint8_t *data, int len) {
#endif
  if (data == nullptr || len != EMDR_FRAME_LEN || g_rx_queue == nullptr) return;
  uint8_t pkt[EMDR_FRAME_LEN + 1];
  memcpy(pkt, data, EMDR_FRAME_LEN);
  pkt[EMDR_FRAME_LEN] = 1;                    /* 1 = came in over ESP-NOW */
  xQueueSend(g_rx_queue, pkt, 0);
}

static void startEspNow() {
  WiFi.mode(WIFI_STA);
  WiFi.disconnect(false, false);
  esp_wifi_set_channel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE);
  if (esp_now_init() == ESP_OK) {
    esp_now_register_recv_cb(onEspNowRecv);
  }
}

/* ---- setup / loop ------------------------------------------------------- */
void emdr_ball_setup() {
  /* SAFETY LAYER 0: motor pin low as plain GPIO before anything else boots. */
  const uint8_t pins[] = { PIN_MOTOR_A };
  emdr_motor_boot_safe(pins, 1);

  pinMode(PIN_LED, OUTPUT);
  led(false);
  pinMode(PIN_SIDE_SELECT, INPUT_PULLUP);

  Serial.begin(SERIAL_BAUD);

  /* identity: NVS wins; the jumper is the fallback for a fresh board */
  g_nvs.begin("emdr", true);
  g_room  = g_nvs.getUChar("room",  DEFAULT_ROOM);
  g_side  = g_nvs.getUChar("side",  0);
  g_scale = g_nvs.getUChar("scale", DEFAULT_SCALE);
  g_nvs.end();
  if (g_side != EMDR_SIDE_L && g_side != EMDR_SIDE_R) {
    g_side = (digitalRead(PIN_SIDE_SELECT) == LOW) ? EMDR_SIDE_R : EMDR_SIDE_L;
  }
  if (g_scale == 0 || g_scale > 200) g_scale = DEFAULT_SCALE;

  g_rx_queue = xQueueCreate(12, EMDR_FRAME_LEN + 1);

  g_motor.begin(PIN_MOTOR_A, PWM_CH_A);

  startEspNow();
  startBle();

  /* SAFETY LAYER 3: MCU watchdog. A hang reboots the chip, and the reboot
   * puts the gate low again. */
#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
  esp_task_wdt_config_t wdt_cfg = { WDT_MS, (1 << portNUM_PROCESSORS) - 1, true };
  esp_task_wdt_reconfigure(&wdt_cfg);
#else
  esp_task_wdt_init(WDT_MS / 1000, true);
#endif
  esp_task_wdt_add(NULL);

  Serial.printf("ALMA-EMDR ball  fw%u  room=%u side=%c scale=%u%%\n",
                EMDR_FW_VERSION, g_room, (g_side == EMDR_SIDE_R ? 'R' : 'L'), g_scale);
}

void emdr_ball_loop() {
  esp_task_wdt_reset();

  /* drain everything the radios posted */
  uint8_t pkt[EMDR_FRAME_LEN + 1];
  while (g_rx_queue && xQueueReceive(g_rx_queue, pkt, 0) == pdTRUE) {
    uint16_t link = pkt[EMDR_FRAME_LEN] ? EMDR_FLAG_LINK_ESPNOW : EMDR_FLAG_LINK_BLE;
    if (link == EMDR_FLAG_LINK_ESPNOW) g_last_espnow_ms = millis();
    handleFrame(pkt, EMDR_FRAME_LEN, link);
  }

  g_motor.tick();

  const uint32_t now = millis();

  /* C.5 radio coexistence: once a ball is plainly being driven by the room
   * bridge, stop advertising so the single 2.4 GHz radio belongs to ESP-NOW. */
  if (!g_ble_connected && g_ble_advertising &&
      g_last_espnow_ms != 0 && (int32_t)(now - g_last_espnow_ms) < 5000) {
    BLEDevice::stopAdvertising();
    g_ble_advertising = false;
  } else if (!g_ble_connected && !g_ble_advertising &&
             (g_last_espnow_ms == 0 || (int32_t)(now - g_last_espnow_ms) > 10000)) {
    BLEDevice::startAdvertising();
    g_ble_advertising = true;
  }

  /* status LED: solid while a pulse is out, slow blink when idle and healthy,
   * fast blink when the dead-man has tripped (nothing is talking to us). */
  static uint32_t led_ms = 0;
  static bool led_on = false;
  uint32_t period = g_motor.deadmanTripped() ? 150 : 1200;
  if (g_motor.motorActive()) {
    led(true);
  } else if ((uint32_t)(now - led_ms) >= period) {
    led_ms = now;
    led_on = !led_on;
    led(led_on);
  }

  /* periodic STATUS while connected */
  static uint32_t status_ms = 0;
  if (g_ble_connected && (uint32_t)(now - status_ms) >= 2000) {
    status_ms = now;
    notifyStatus();
  }
}

#endif /* EMDR_ROLE_BALL */
