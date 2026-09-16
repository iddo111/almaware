/*
 * pemf_driver.ino — decimal-frequency PEMF coil driver
 * לזכרה של עלמה ז״ל — iddoperez.ai
 *
 * Toggles a logic-level MOSFET that switches a 5 V PEMF coil, at a PRECISE
 * decimal frequency (e.g. 7.83 Hz Schumann) set over serial. micros()-based
 * timing => true fractional Hz, not integer-only.
 *
 * ------------------------------------------------------------------ WIRING ---
 *   Arduino D9 ──[100 Ω]──┬── MOSFET GATE        (logic-level N-ch: IRLZ44N,
 *                         └──[10 kΩ]── GND         IRLB8721, or a gate-driver)
 *   MOSFET SOURCE ── GND (common with Arduino GND and the 5 V supply GND)
 *   MOSFET DRAIN  ── coil(−)
 *   coil(+) ── +5 V supply
 *
 *   ***FLYBACK DIODE (MANDATORY)***  put a fast diode across the COIL:
 *        diode cathode (band) → coil(+) / +5V ,  anode → coil(−)/DRAIN.
 *        Use 1N4007 (ok at low Hz) or UF4007 / 1N5819 Schottky (faster, better).
 *        Without it the coil's collapsing field spikes the MOSFET and kills it.
 *   Optional: 100 nF across the supply; don't exceed the coil's safe current
 *   (I = 5V / coil_resistance) — add a series resistor if it runs hot.
 *
 * ------------------------------------------------------------- SERIAL @115200 -
 *   F7.83     set frequency to 7.83 Hz (any decimal 0.05–2000 Hz)
 *   D25       set duty cycle to 25 %  (1–99)
 *   ON / OFF  start / stop pulsing (OFF drives the gate LOW = coil off)
 *   P<name>   preset: schumann, theta, alpha, delta, beta, s2,s3,s4,s5
 *   ?         print current status
 *   Anything else prints the help. Echoes every change so a host/GUI can sync.
 *
 * NOT a medical device. PEMF here is a maker/biofeedback experiment, not
 * treatment or diagnosis. Keep power low. Do NOT use near a pacemaker / implanted
 * electronics, and avoid use in pregnancy — consult a clinician if unsure.
 */

const uint8_t PIN_GATE = 9;     // -> gate resistor -> MOSFET gate
const uint8_t PIN_LED  = 13;    // mirrors the pulse (visual)

float        freqHz   = 7.83;   // default: Schumann fundamental
uint8_t      dutyPct  = 50;     // % on-time
bool         running  = false;

unsigned long onUs    = 0;      // computed on-time  (microseconds)
unsigned long offUs   = 0;      // computed off-time (microseconds)
unsigned long edgeUs  = 0;      // micros() of the last edge
bool          pulseHigh = false;

const float FREQ_MIN = 0.05f;
const float FREQ_MAX = 2000.0f; // micros() resolution (~4us) keeps this honest

void recompute() {
  float f = freqHz;
  if (f < FREQ_MIN) f = FREQ_MIN;
  if (f > FREQ_MAX) f = FREQ_MAX;
  float periodUs = 1000000.0f / f;
  onUs  = (unsigned long)(periodUs * (dutyPct / 100.0f));
  offUs = (unsigned long)(periodUs - (float)onUs);
  if (onUs  < 1) onUs  = 1;
  if (offUs < 1) offUs = 1;
}

void setGate(bool high) {
  pulseHigh = high;
  digitalWrite(PIN_GATE, high ? HIGH : LOW);
  digitalWrite(PIN_LED,  high ? HIGH : LOW);
}

void printStatus() {
  Serial.print(F("PEMF  freq="));
  Serial.print(freqHz, 2);
  Serial.print(F(" Hz  duty="));
  Serial.print(dutyPct);
  Serial.print(F("%  state="));
  Serial.print(running ? F("ON") : F("OFF"));
  Serial.print(F("  (on="));
  Serial.print(onUs);
  Serial.print(F("us off="));
  Serial.print(offUs);
  Serial.println(F("us)"));
}

void printHelp() {
  Serial.println(F("cmds: F<hz> D<pct> ON OFF P<preset> ?"));
  Serial.println(F("presets: schumann(7.83) s2(14.3) s3(20.8) s4(27.3) s5(33.8)"));
  Serial.println(F("         delta(2) theta(6) alpha(10) beta(20)"));
}

void applyPreset(String name) {
  name.toLowerCase();
  if      (name == "schumann") freqHz = 7.83f;
  else if (name == "s2")       freqHz = 14.3f;
  else if (name == "s3")       freqHz = 20.8f;
  else if (name == "s4")       freqHz = 27.3f;
  else if (name == "s5")       freqHz = 33.8f;
  else if (name == "delta")    freqHz = 2.0f;
  else if (name == "theta")    freqHz = 6.0f;
  else if (name == "alpha")    freqHz = 10.0f;
  else if (name == "beta")     freqHz = 20.0f;
  else { Serial.println(F("unknown preset")); return; }
  recompute();
  printStatus();
}

void handleLine(String line) {
  line.trim();
  if (line.length() == 0) return;
  char c = toupper(line.charAt(0));
  String arg = line.substring(1);
  switch (c) {
    case 'F': {
      float f = arg.toFloat();
      if (f >= FREQ_MIN && f <= FREQ_MAX) { freqHz = f; recompute(); printStatus(); }
      else Serial.println(F("freq out of range 0.05-2000"));
      break;
    }
    case 'D': {
      int d = arg.toInt();
      if (d >= 1 && d <= 99) { dutyPct = (uint8_t)d; recompute(); printStatus(); }
      else Serial.println(F("duty 1-99"));
      break;
    }
    case 'P': applyPreset(arg); break;
    case '?': printStatus(); break;
    default:
      if (line.equalsIgnoreCase("ON"))  { running = true;  edgeUs = micros(); setGate(true);  printStatus(); }
      else if (line.equalsIgnoreCase("OFF")) { running = false; setGate(false); printStatus(); }
      else printHelp();
      break;
  }
}

void setup() {
  pinMode(PIN_GATE, OUTPUT);
  pinMode(PIN_LED,  OUTPUT);
  setGate(false);
  Serial.begin(115200);
  recompute();
  Serial.println(F("PEMF driver ready. Coil OFF. Send ON to start."));
  printHelp();
  printStatus();
}

void loop() {
  // Non-blocking serial line assembly.
  static String buf;
  while (Serial.available()) {
    char ch = (char)Serial.read();
    if (ch == '\n' || ch == '\r') { if (buf.length()) { handleLine(buf); buf = ""; } }
    else if (buf.length() < 48)   { buf += ch; }
  }

  // Precise micros()-paced square wave (decimal Hz).
  if (running) {
    unsigned long now = micros();
    unsigned long want = pulseHigh ? onUs : offUs;
    if ((unsigned long)(now - edgeUs) >= want) {
      edgeUs += want;                 // advance by the exact interval (no drift)
      setGate(!pulseHigh);
    }
  }
}
