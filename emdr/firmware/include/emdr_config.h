/*
 * emdr_config.h - every tunable constant of the ALMA-EMDR buzzer firmware.
 * -----------------------------------------------------------------------------
 * The numeric block below is PROTOCOL-buzzers-20260901.md section D.5, verbatim.
 * Do not change one of these without changing the protocol document, because
 * three clients (PC, browser, Android) are written against them.
 */
#ifndef EMDR_CONFIG_H
#define EMDR_CONFIG_H

#include <stdint.h>

/* =========================================================================
 * ROLE  -  which of the two devices is this?
 *
 *   BALL   = the thing in the hand. One ERM motor. BLE peripheral + ESP-NOW
 *            listener. Phase 2 and 3 of the build order.
 *   BRIDGE = the box on the desk. USB-CDC in, two WIRED motor channels out
 *            (Phase 1), and ESP-NOW broadcast out (Phase 3). The same board.
 *
 * PlatformIO sets this from platformio.ini (-D EMDR_ROLE_BALL / _BRIDGE).
 * ARDUINO IDE USERS: change the line marked below, there is no other switch.
 * ========================================================================= */
#if !defined(EMDR_ROLE_BALL) && !defined(EMDR_ROLE_BRIDGE)
  #define EMDR_ROLE_BALL 1        /* <-- Arduino IDE: 1 = ball, or swap to  */
  /* #define EMDR_ROLE_BRIDGE 1 */ /*     EMDR_ROLE_BRIDGE for the USB box   */
#endif

#define EMDR_FW_VERSION   1       /* reported in STATUS byte 6              */

/* =========================================================================
 * D.5 - THE SAFETY AND TIMING CONSTANTS.  All of them.
 * ========================================================================= */
#define DEADMAN_MS        1500u   /* no frame for this long -> stop, stay stopped */
#define HYSTERESIS_MS       30u   /* jitter rejection band (C.3)                  */
#define DUR_MIN_MS          40u   /* below this the ERM does not move at all      */
#define DUR_MAX_MS         600u   /* hard clamp regardless of what was asked      */
#define DELAY_MAX_MS      8000u   /* hard clamp                                   */
#define INTENSITY_FLOOR     40u   /* below this the ERM will not start            */
#define DUTY_MAX_PCT        60u   /* over a rolling DUTY_WINDOW_MS window         */
#define DUTY_WINDOW_MS    2000u
#define WDT_MS            2000u   /* MCU watchdog                                 */
#define ERM_LEAD_MS         30u   /* actuator lead (D.1) - fire the PWM this      */
                                  /* many ms BEFORE the felt target               */
#define OVERDRIVE_MS        20u   /* start-of-pulse kick at 255                   */

/* C.1 idempotence: remember this many (op,seq) pairs for this long. */
#define SEQ_MEMORY_DEPTH     8
#define SEQ_MEMORY_MS     2000u

/* =========================================================================
 * PWM  (LEDC)
 * An ERM coin motor is driven through a logic-level N-MOSFET with a flyback
 * diode. 20 kHz is above hearing, so the motor does not whine.
 * ========================================================================= */
#define PWM_FREQ_HZ      20000u
#define PWM_RES_BITS         8    /* 0..255 == the protocol's intensity byte */
#define PWM_CH_A             0
#define PWM_CH_B             1

/* =========================================================================
 * PINS
 * Defaults are for the ESP32-C3 SuperMini Plus / Seeed XIAO ESP32C3.
 * -------------------------------------------------------------------------
 *  IRON RULE FROM D.5: the MOSFET gate MUST have a 10 kOhm pull-down to GND
 *  on the board. A dead or floating MCU pin is then motor-OFF in hardware,
 *  with no software involved at all. This is the layer that survives a
 *  brown-out. Do not omit it because "the firmware sets it low on boot".
 * ========================================================================= */
#ifndef PIN_MOTOR_A
  #define PIN_MOTOR_A        3    /* ball: the only motor. bridge: LEFT jack  */
#endif
#ifndef PIN_MOTOR_B
  #define PIN_MOTOR_B        4    /* bridge only: RIGHT jack                  */
#endif
#ifndef PIN_LED
  #define PIN_LED            8    /* SuperMini onboard LED (active LOW)       */
#endif
#ifndef PIN_LED_ACTIVE_LOW
  #define PIN_LED_ACTIVE_LOW 1
#endif
#ifndef PIN_SIDE_SELECT
  #define PIN_SIDE_SELECT    5    /* ball: jumper to GND = RIGHT, open = LEFT */
#endif                            /*       (INPUT_PULLUP). NVS overrides it.  */
#ifndef PIN_VBAT_ADC
  #define PIN_VBAT_ADC       2    /* ball: 2:1 divider from the LiPo, or -1   */
#endif

/* Battery scaling for the STATUS byte. 2:1 divider -> full scale 2*3.3 V. */
#define VBAT_DIVIDER      2.0f
#define VBAT_EMPTY_V      3.30f
#define VBAT_FULL_V       4.15f
#define VBAT_LOW_PCT        15u

/* =========================================================================
 * RADIO
 * ========================================================================= */
#define ESPNOW_CHANNEL       1    /* fixed for the bridge and every ball      */
#define BLE_ADV_MIN_MS      20    /* C.4: 20..100 ms. Slower than 1 s and     */
#define BLE_ADV_MAX_MS     100    /* Windows takes tens of seconds to connect */

/* Default identity before anything is written to NVS. */
#define DEFAULT_ROOM         1u
#define DEFAULT_SCALE      100u   /* per-ball intensity scale, percent        */

/* USB */
#define SERIAL_BAUD     115200u
#define ASCII_LINE_MAX      32    /* legacy line parser buffer (C.6)          */

#endif /* EMDR_CONFIG_H */
