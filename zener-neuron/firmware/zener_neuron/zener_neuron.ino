// ZENER NEURON - POC (2026-09-10)
// One zener, one op-amp, one ADC pin. The ESP32 only READS and REPORTS.
// All maths lives on the PC, so the raw stream is never hidden, never hashed.
//
// LM358 OUT -> R5 10k -> GPIO34 (ADC1_CH6, input-only pin)
// Onboard LED (GPIO2 on most dev boards) = the neuron firing, slowed to ~5 Hz so an eye can see it.

const int PIN_NOISE = 34;
const int PIN_LED   = 2;

void setup() {
  Serial.begin(921600);
  pinMode(PIN_LED, OUTPUT);
  analogReadResolution(12);                    // 0..4095
  analogSetPinAttenuation(PIN_NOISE, ADC_11db); // full 0..~3.1 V range
}

void loop() {
  int v = analogRead(PIN_NOISE);               // ~2000 when the amp is alive and biased at 1.65 V
  static int k = 0;
  if (++k >= 2000) { k = 0; digitalWrite(PIN_LED, v & 1); }   // LSB of every 2000th sample -> visible random blink
  Serial.println(v);                           // one integer per line, raw, always
}
