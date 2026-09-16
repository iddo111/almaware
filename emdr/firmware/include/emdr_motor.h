/*
 * emdr_motor.h - one ERM channel, and every safety layer that guards it.
 * -----------------------------------------------------------------------------
 * IRON RULE (PROTOCOL D.5): the ball has no ON state. It only ever has a
 * countdown. There is deliberately no `on()` method on this class. The only
 * way to make the motor move is to schedule a tap that is already carrying its
 * own end time, and the only way to keep the channel alive at all is to keep
 * feeding it.
 *
 * The five independent layers, and which line of code is each one:
 *   1. dead-man        tick(): no feed() for DEADMAN_MS  -> hardOff() forever
 *   2. link loss       the transport calls stop() on disconnect
 *   3. watchdog        esp_task_wdt, armed in emdr_motor_boot_safe()
 *   4. hardware        10 kOhm gate pull-down on the board - not software
 *   5. duty limiter    fire(): refuses a tap that would exceed DUTY_MAX_PCT
 *   + DUR_MAX_MS clamp: the one-shot end time is written BEFORE the PWM starts.
 */
#ifndef EMDR_MOTOR_H
#define EMDR_MOTOR_H

#include <Arduino.h>
#include "emdr_config.h"

/* Set every motor pin LOW as an ordinary GPIO before anything else runs.
 * Called first thing in setup(), before Serial, before the radio. */
void emdr_motor_boot_safe(const uint8_t *pins, uint8_t n);

class EmdrMotor {
 public:
  void begin(uint8_t pin, uint8_t ledc_channel);

  /* C.3 - the pending-tap rule. `felt_at_ms` is when the PERSON should feel
   * it, on this MCU's millis() clock. The ERM lead is subtracted inside. */
  void scheduleTap(uint32_t felt_at_ms, uint8_t intensity, uint16_t dur_ms);

  /* Cancel the pending tap and drop the PWM to zero this instant. */
  void stop();

  /* Any valid frame for this ball resets the dead-man. */
  void feed();

  /* Call from loop(), as often as possible. Everything time-based happens
   * here: firing, ending, overdrive step-down, dead-man, duty accounting. */
  void tick();

  bool motorActive()   const { return motor_on_; }
  bool deadmanTripped() const { return deadman_tripped_; }
  bool dutyLimited()   const { return duty_limited_; }
  bool hasPending()    const { return has_pending_; }
  uint8_t lastIntensity() const { return last_intensity_; }

 private:
  void setPwm_(uint8_t duty);
  void hardOff_();
  bool dutyAllows_(uint32_t now, uint16_t dur_ms);
  void dutyRecord_(uint32_t start, uint16_t dur_ms);

  uint8_t  pin_      = 255;
  uint8_t  channel_  = 0;
  bool     ready_    = false;

  bool     motor_on_ = false;
  uint32_t pulse_end_ = 0;
  uint32_t overdrive_end_ = 0;
  bool     overdriving_ = false;
  uint8_t  target_duty_ = 0;
  uint8_t  last_intensity_ = 0;

  bool     has_pending_ = false;
  uint32_t pending_felt_ = 0;
  uint8_t  pending_intensity_ = 0;
  uint16_t pending_dur_ = 0;

  uint32_t deadman_deadline_ = 0;
  bool     deadman_tripped_  = true;   /* boots tripped: silent until fed */
  bool     duty_limited_     = false;

  /* rolling duty window: start time + length of the last few pulses */
  uint32_t duty_start_[SEQ_MEMORY_DEPTH] = {0};
  uint16_t duty_len_[SEQ_MEMORY_DEPTH]   = {0};
  uint8_t  duty_head_ = 0;
};

#endif /* EMDR_MOTOR_H */
