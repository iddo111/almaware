// Compile-only bring-up sketch for the Seeed XIAO RP2350.
// This sketch is intentionally hardware-neutral: it performs no GPIO writes.

void setup() {
  Serial.begin(115200);
}

void loop() {
  static unsigned long last_report_ms = 0;
  const unsigned long now_ms = millis();
  if (now_ms - last_report_ms >= 1000) {
    last_report_ms = now_ms;
    Serial.println("XIAO_RP2350_READY");
  }
}
