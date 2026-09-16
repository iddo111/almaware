/*
 * main.cpp - ALMA-EMDR buzzer firmware entry point.
 * -----------------------------------------------------------------------------
 * Two roles, one binary source tree. See emdr_config.h to pick the role.
 *
 * ARDUINO IDE: rename this file to match the sketch folder (e.g. put every
 * file from src/ and include/ into a folder called EMDR_Firmware and rename
 * this one to EMDR_Firmware.ino). Arduino compiles every .cpp/.h beside the
 * sketch, so nothing else changes.
 */
#include <Arduino.h>
#include "emdr_config.h"

#if EMDR_ROLE_BALL
void emdr_ball_setup();
void emdr_ball_loop();
#endif
#if EMDR_ROLE_BRIDGE
void emdr_bridge_setup();
void emdr_bridge_loop();
#endif

void setup() {
#if EMDR_ROLE_BALL
  emdr_ball_setup();
#elif EMDR_ROLE_BRIDGE
  emdr_bridge_setup();
#else
  #error "Define EMDR_ROLE_BALL or EMDR_ROLE_BRIDGE (see include/emdr_config.h)"
#endif
}

void loop() {
#if EMDR_ROLE_BALL
  emdr_ball_loop();
#elif EMDR_ROLE_BRIDGE
  emdr_bridge_loop();
#endif
  /* No delay() anywhere in this firmware. Every deadline is a comparison
   * against millis(), because a delay() is a window in which the dead-man
   * cannot fire. */
}
