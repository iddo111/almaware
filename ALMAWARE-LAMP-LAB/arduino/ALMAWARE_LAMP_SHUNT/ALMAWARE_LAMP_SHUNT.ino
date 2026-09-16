/*
  ALMAWARE 12 V incandescent-lamp thermal hysteresis — no INA219.

  Current is measured with a low-side power shunt:
    D9 -> 100R -> MOSFET gate; gate -> 10k -> source
    MOSFET source -> shunt -> common GND; A1 -> source/shunt top
    12V+ -> fuse -> bulb -> MOSFET drain
    drain -> 33k -> A0 -> 10k -> GND; A0 -> 1uF -> GND
    12V+ -> 33k -> A2 -> 10k -> GND; A2 -> 1uF -> GND

  Default shunt: 1.000 ohm, >=1 W.  Serial command RSHUNT changes the
  calculation only; it cannot make an under-rated physical resistor safe.
*/

const uint8_t GATE_PIN = 9;
const uint8_t DRAIN_SENSE_PIN = A0;
const uint8_t SHUNT_SENSE_PIN = A1;
const uint8_t SUPPLY_SENSE_PIN = A2;

const float ADC_REFERENCE_V = 5.00;  // Measure Arduino 5V for calibration.
const float DIVIDER_TOP_OHM = 33000.0;
const float DIVIDER_BOTTOM_OHM = 10000.0;
const float DIVIDER_RATIO =
    (DIVIDER_TOP_OHM + DIVIDER_BOTTOM_OHM) / DIVIDER_BOTTOM_OHM;

float shuntOhm = 1.000;
const uint8_t HARD_MAX_DUTY = 100;
uint8_t experimentMaxDuty = 60;
const uint8_t READ_DUTY = 30;
const float OVERCURRENT_MA = 650.0;
const unsigned long OVERCURRENT_HOLD_MS = 120;

bool stopRequested = false;
uint8_t presentDuty = 0;
unsigned long overcurrentSince = 0;
unsigned long lastSafetyPoll = 0;

struct Measurement {
  float supplyV;
  float drainV;
  float bulbV;
  float shuntV;
  float currentMA;
  float powerMW;
  float resistanceOhm;
};

void allOff() {
  analogWrite(GATE_PIN, 0);
  presentDuty = 0;
  overcurrentSince = 0;
}

float readAveragePinV(uint8_t pin, uint8_t samples) {
  analogRead(pin);  // Discard after channel change.
  unsigned long sum = 0;
  for (uint8_t i = 0; i < samples; i++) {
    sum += analogRead(pin);
    delayMicroseconds(220);
  }
  return ((float)sum / samples) * ADC_REFERENCE_V / 1023.0;
}

float readCurrentMA(uint8_t samples = 64) {
  float shuntV = readAveragePinV(SHUNT_SENSE_PIN, samples);
  return shuntV * 1000.0 / shuntOhm;
}

Measurement measure() {
  Measurement m;
  // Each average spans several 490 Hz PWM periods.
  m.shuntV = readAveragePinV(SHUNT_SENSE_PIN, 96);
  m.drainV = readAveragePinV(DRAIN_SENSE_PIN, 64) * DIVIDER_RATIO;
  m.supplyV = readAveragePinV(SUPPLY_SENSE_PIN, 64) * DIVIDER_RATIO;
  m.currentMA = m.shuntV * 1000.0 / shuntOhm;
  m.bulbV = max(0.0, m.supplyV - m.drainV);
  m.powerMW = m.bulbV * m.currentMA;
  m.resistanceOhm =
      m.currentMA > 2.0 ? m.bulbV / (m.currentMA / 1000.0) : -1.0;
  return m;
}

bool enforceCurrentLimit(float currentMA) {
  if (currentMA > OVERCURRENT_MA) {
    if (overcurrentSince == 0) overcurrentSince = millis();
    if (millis() - overcurrentSince >= OVERCURRENT_HOLD_MS) {
      allOff();
      stopRequested = true;
      Serial.print(F("# ABORT overcurrent_mA="));
      Serial.println(currentMA, 1);
      return false;
    }
  } else {
    overcurrentSince = 0;
  }
  return true;
}

bool safetyPoll() {
  if (presentDuty == 0) return true;
  if (millis() - lastSafetyPoll < 12) return true;
  lastSafetyPoll = millis();
  return enforceCurrentLimit(readCurrentMA(32));
}

void logHeader() {
  Serial.println(
      F("ms,test,phase,trial,duty,bus_V,drain_V,bulb_V,current_mA,"
        "power_mW,R_ohm"));
}

bool logMeasurement(const char *test, const char *phase, long trial) {
  Measurement m = measure();
  Serial.print(millis()); Serial.print(',');
  Serial.print(test); Serial.print(',');
  Serial.print(phase); Serial.print(',');
  Serial.print(trial); Serial.print(',');
  Serial.print(presentDuty); Serial.print(',');
  Serial.print(m.supplyV, 4); Serial.print(',');
  Serial.print(m.drainV, 4); Serial.print(',');
  Serial.print(m.bulbV, 4); Serial.print(',');
  Serial.print(m.currentMA, 3); Serial.print(',');
  Serial.print(m.powerMW, 3); Serial.print(',');
  Serial.println(m.resistanceOhm, 3);
  return enforceCurrentLimit(m.currentMA);
}

void pollStop() {
  if (!Serial.available()) return;
  String line = Serial.readStringUntil('\n');
  line.trim();
  line.toUpperCase();
  if (line == "STOP") {
    stopRequested = true;
    allOff();
    Serial.println(F("# STOP acknowledged"));
  }
}

bool waitAbortable(unsigned long durationMS) {
  unsigned long start = millis();
  while (millis() - start < durationMS) {
    pollStop();
    if (stopRequested || !safetyPoll()) return false;
    delay(4);
  }
  return true;
}

bool softSetDuty(uint8_t target) {
  target = min(target, experimentMaxDuty);
  while (presentDuty != target) {
    presentDuty += presentDuty < target ? 1 : -1;
    analogWrite(GATE_PIN, presentDuty);
    if (!waitAbortable(6)) return false;
  }
  return true;
}

bool holdAndLog(const char *test, const char *phase, long trial,
                unsigned long durationMS, unsigned long logEveryMS) {
  unsigned long start = millis();
  unsigned long lastLog = 0;
  while (millis() - start < durationMS) {
    pollStop();
    if (stopRequested || !safetyPoll()) return false;
    if (millis() - lastLog >= logEveryMS) {
      lastLog = millis();
      if (!logMeasurement(test, phase, trial)) return false;
    }
    delay(3);
  }
  return true;
}

void runSweep() {
  stopRequested = false;
  allOff();
  logHeader();
  Serial.println(F("# SWEEP begin"));
  const uint8_t fractions[] = {0, 32, 64, 96, 128, 160, 192, 224, 255};
  const uint8_t count = sizeof(fractions) / sizeof(fractions[0]);
  for (uint8_t i = 0; i < count && !stopRequested; i++) {
    uint8_t duty = (uint16_t)experimentMaxDuty * fractions[i] / 255;
    if (!softSetDuty(duty) || !holdAndLog("sweep", "up", duty, 900, 90)) break;
  }
  for (int8_t i = count - 2; i >= 0 && !stopRequested; i--) {
    uint8_t duty = (uint16_t)experimentMaxDuty * fractions[i] / 255;
    if (!softSetDuty(duty) || !holdAndLog("sweep", "down", duty, 900, 90)) break;
  }
  allOff();
  Serial.println(stopRequested ? F("# SWEEP aborted") : F("# SWEEP complete"));
}

void runMemory() {
  stopRequested = false;
  allOff();
  logHeader();
  Serial.println(F("# MEMORY begin"));
  if (!waitAbortable(5000)) return;
  if (!softSetDuty(min(READ_DUTY, experimentMaxDuty))) return;
  if (!waitAbortable(60)) return;
  logMeasurement("memory", "cold_read", -1);
  allOff();

  const unsigned long coolDelays[] = {100, 300, 1000, 3000, 5000};
  for (uint8_t trial = 0; trial < 5 && !stopRequested; trial++) {
    allOff();
    if (!waitAbortable(5000)) break;
    if (!softSetDuty(experimentMaxDuty)) break;
    if (!holdAndLog("memory", "heat", coolDelays[trial], 1800, 160)) break;
    allOff();
    if (!waitAbortable(coolDelays[trial])) break;
    if (!softSetDuty(min(READ_DUTY, experimentMaxDuty))) break;
    if (!waitAbortable(60)) break;
    if (!logMeasurement("memory", "read", coolDelays[trial])) break;
    allOff();
  }
  allOff();
  Serial.println(stopRequested ? F("# MEMORY aborted") : F("# MEMORY complete"));
}

void printStatus() {
  allOff();
  Measurement m = measure();
  Serial.print(F("# SHUNT=OK shunt_ohm=")); Serial.print(shuntOhm, 4);
  Serial.print(F(" maxDuty=")); Serial.print(experimentMaxDuty);
  Serial.print(F(" supply_V=")); Serial.print(m.supplyV, 3);
  Serial.print(F(" current_mA=")); Serial.println(m.currentMA, 2);
}

void printHelp() {
  Serial.println(F("# STATUS | READ | SWEEP | MEMORY | RUN | STOP"));
  Serial.println(F("# MAX 20..100 | RSHUNT 0.20..10.0 | HELP"));
}

void processCommand(String line) {
  line.trim(); line.toUpperCase();
  if (!line.length()) return;
  if (line == "STATUS") printStatus();
  else if (line == "READ") {
    allOff(); logHeader(); logMeasurement("manual", "off", 0);
  } else if (line == "SWEEP") runSweep();
  else if (line == "MEMORY") runMemory();
  else if (line == "RUN") { runSweep(); if (!stopRequested) runMemory(); }
  else if (line == "STOP") { stopRequested = true; allOff(); Serial.println(F("# Already stopped")); }
  else if (line.startsWith("MAX ")) {
    int value = line.substring(4).toInt();
    if (value < 20 || value > HARD_MAX_DUTY) Serial.println(F("# MAX rejected; 20..100"));
    else { experimentMaxDuty = value; Serial.print(F("# maxDuty=")); Serial.println(value); }
  } else if (line.startsWith("RSHUNT ")) {
    float value = line.substring(7).toFloat();
    if (value < 0.20 || value > 10.0) Serial.println(F("# RSHUNT rejected; 0.20..10.0"));
    else { shuntOhm = value; Serial.print(F("# shuntOhm=")); Serial.println(shuntOhm, 4); }
  } else if (line == "HELP" || line == "?") printHelp();
  else Serial.println(F("# Unknown command; HELP"));
}

void setup() {
  pinMode(GATE_PIN, OUTPUT);
  allOff();
  pinMode(DRAIN_SENSE_PIN, INPUT);
  pinMode(SHUNT_SENSE_PIN, INPUT);
  pinMode(SUPPLY_SENSE_PIN, INPUT);
  Serial.begin(115200);
  Serial.setTimeout(10);
  delay(250);
  Serial.println(F("# ALMAWARE 12V lamp — low-side shunt edition"));
  Serial.println(F("# BOOT SAFE: MOSFET OFF; default MAX 60"));
  Serial.println(F("# Requires power-rated shunt and current-limited 12V supply"));
  printHelp();
}

void loop() {
  allOff();
  if (!Serial.available()) { delay(10); return; }
  processCommand(Serial.readStringUntil('\n'));
}
