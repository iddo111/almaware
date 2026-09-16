#include "emdr_motor.h"

/* millis() wraps every ~49.7 days. Every deadline test in this file is written
 * as a SIGNED difference so the wrap is a non-event. Never write `now > x`. */
static inline bool reached(uint32_t now, uint32_t deadline) {
  return (int32_t)(now - deadline) >= 0;
}

void emdr_motor_boot_safe(const uint8_t *pins, uint8_t n) {
  for (uint8_t i = 0; i < n; i++) {
    pinMode(pins[i], OUTPUT);
    digitalWrite(pins[i], LOW);
  }
}

void EmdrMotor::begin(uint8_t pin, uint8_t ledc_channel) {
  pin_ = pin;
  channel_ = ledc_channel;

  /* plain GPIO low first, so attaching the timer cannot glitch the gate */
  pinMode(pin_, OUTPUT);
  digitalWrite(pin_, LOW);

#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcAttach(pin_, PWM_FREQ_HZ, PWM_RES_BITS);
#else
  ledcSetup(channel_, PWM_FREQ_HZ, PWM_RES_BITS);
  ledcAttachPin(pin_, channel_);
#endif
  setPwm_(0);

  deadman_tripped_  = true;
  deadman_deadline_ = millis();   /* stays tripped until the first feed() */
  ready_ = true;
}

void EmdrMotor::setPwm_(uint8_t duty) {
  if (pin_ == 255) return;
#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWrite(pin_, duty);
#else
  ledcWrite(channel_, duty);
#endif
}

void EmdrMotor::hardOff_() {
  setPwm_(0);
  motor_on_    = false;
  overdriving_ = false;
  has_pending_ = false;
}

void EmdrMotor::stop() {
  hardOff_();
}

void EmdrMotor::feed() {
  deadman_deadline_ = millis() + DEADMAN_MS;
  deadman_tripped_  = false;
}

/* ---- C.3 the pending-tap rule ------------------------------------------- */
void EmdrMotor::scheduleTap(uint32_t felt_at_ms, uint8_t intensity, uint16_t dur_ms) {
  if (!ready_) return;

  /* clamps first, so nothing downstream ever sees an out-of-range value */
  if (dur_ms == 0) return;                       /* a zero-length tap is a no-op */
  if (dur_ms < DUR_MIN_MS) dur_ms = DUR_MIN_MS;  /* the ERM cannot move below it */
  if (dur_ms > DUR_MAX_MS) dur_ms = DUR_MAX_MS;  /* hard clamp, D.5             */
  if (intensity == 0) return;                    /* 0 means silent, by protocol  */
  if (intensity < INTENSITY_FLOOR) intensity = INTENSITY_FLOOR;

  if (has_pending_) {
    int32_t drift = (int32_t)(felt_at_ms - pending_felt_);
    if (drift < 0) drift = -drift;
    if (drift < (int32_t)HYSTERESIS_MS) {
      /* Same beat restated. This is link jitter, not a tempo change - keep the
       * target we already have. THIS one line is what turns 0-50 ms of
       * Bluetooth jitter into an even rhythm. */
      pending_intensity_ = intensity;   /* amplitude may still be updated */
      pending_dur_       = dur_ms;
      feed();
      return;
    }
  }
  pending_felt_      = felt_at_ms;
  pending_intensity_ = intensity;
  pending_dur_       = dur_ms;
  has_pending_       = true;
  feed();
}

/* ---- duty limiter: max DUTY_MAX_PCT over a rolling DUTY_WINDOW_MS -------- */
bool EmdrMotor::dutyAllows_(uint32_t now, uint16_t dur_ms) {
  uint32_t on_ms = dur_ms;
  for (uint8_t i = 0; i < SEQ_MEMORY_DEPTH; i++) {
    if (duty_len_[i] == 0) continue;
    int32_t age = (int32_t)(now - duty_start_[i]);
    if (age < 0 || age > (int32_t)DUTY_WINDOW_MS) continue;   /* outside window */
    uint32_t inside = duty_len_[i];
    if ((uint32_t)age < inside) inside = (uint32_t)age;       /* still running */
    on_ms += inside;
  }
  return on_ms <= (DUTY_WINDOW_MS * DUTY_MAX_PCT) / 100u;
}

void EmdrMotor::dutyRecord_(uint32_t start, uint16_t dur_ms) {
  duty_start_[duty_head_] = start;
  duty_len_[duty_head_]   = dur_ms;
  duty_head_ = (uint8_t)((duty_head_ + 1) % SEQ_MEMORY_DEPTH);
}

void EmdrMotor::tick() {
  if (!ready_) return;
  const uint32_t now = millis();

  /* --- layer 1: the dead-man. First, before anything can start a motor. --- */
  if (!deadman_tripped_ && reached(now, deadman_deadline_)) {
    hardOff_();
    deadman_tripped_ = true;
  }
  if (deadman_tripped_) {
    if (motor_on_) hardOff_();
    return;                       /* nothing else may run while tripped */
  }

  /* --- end an active pulse --------------------------------------------- */
  if (motor_on_) {
    if (reached(now, pulse_end_)) {
      setPwm_(0);
      motor_on_ = false;
      overdriving_ = false;
    } else if (overdriving_ && reached(now, overdrive_end_)) {
      setPwm_(target_duty_);      /* drop from the 255 kick to the commanded level */
      overdriving_ = false;
    }
  }

  /* --- fire the pending tap -------------------------------------------- */
  if (has_pending_ && !motor_on_) {
    /* the firmware owns the ERM's 20-50 ms mechanical rise, so no client
     * anywhere has to model it (D.1) */
    uint32_t fire_at = pending_felt_ - ERM_LEAD_MS;
    if (reached(now, fire_at)) {
      uint16_t dur   = pending_dur_;
      uint8_t  inten = pending_intensity_;
      has_pending_ = false;

      if (!dutyAllows_(now, dur)) {
        /* refused, not truncated - D.5. The person simply misses one tap. */
        duty_limited_ = true;
        return;
      }
      duty_limited_ = false;

      /* The end time is written BEFORE the PWM starts. If anything at all
       * goes wrong after this line, the pulse still has an end. */
      pulse_end_     = now + dur;
      uint16_t over  = OVERDRIVE_MS;
      if (over > dur / 3) over = dur / 3;
      overdrive_end_ = now + over;
      overdriving_   = over > 0;
      target_duty_   = inten;
      last_intensity_ = inten;
      motor_on_      = true;
      dutyRecord_(now, dur);

      setPwm_(overdriving_ ? 255 : inten);
    }
  }
}
