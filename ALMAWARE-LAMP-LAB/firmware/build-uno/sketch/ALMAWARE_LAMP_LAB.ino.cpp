#include <Arduino.h>
#line 1 "D:\\CLAUDE\\ALMAWARE-LAMP-LAB\\arduino\\ALMAWARE_LAMP_LAB\\ALMAWARE_LAMP_LAB.ino"
/*
  12 V incandescent bulb thermal-memory cell

  Hardware:
    Arduino Uno/Mega (5 V)
    D9 -> 100R -> FQP30N06L Gate; Gate -> 10k -> GND
    MOSFET Source -> common GND
    12V+ -> fuse -> INA219 VIN+ -> VIN- -> bulb -> MOSFET Drain
    Drain -> 33k -> A0 -> 10k -> GND; A0 -> 1uF -> GND

  Safety:
    - one 12 V incandescent bulb, <=5 W
    - isolated current-limited 12 V DC supply, initially capped at 0.8 A
    - 1 A time-delay fuse in +12 V
    - default OFF; no automatic experiment after reset
    - firmware ceiling 160/255, default experiment ceiling 120/255

  Serial 115200, newline:
    STATUS | READ | SWEEP | MEMORY | RUN | STOP | MAX n | HELP

  INA219:
    Raw I2C, standard R100 (0.1 ohm) breakout calibration:
    32 V bus range, 2 A current range, 0.1 mA current LSB.
*/

#include <Wire.h>

const uint8_t GATE_PIN = 9;
const uint8_t DRAIN_SENSE_PIN = A0;
const uint8_t INA219_ADDRESS = 0x40;

const float ADC_REFERENCE_V = 5.00;
const float DIVIDER_TOP_OHM = 33000.0;
const float DIVIDER_BOTTOM_OHM = 10000.0;

const uint8_t HARD_MAX_DUTY = 160;
uint8_t experimentMaxDuty = 60;  // Conservative first-run ceiling.
const uint8_t READ_DUTY = 35;

const float OVERCURRENT_MA = 800.0;
const unsigned long OVERCURRENT_HOLD_MS = 150;

bool stopRequested = false;
bool inaReady = false;
uint8_t presentDuty = 0;
unsigned long overcurrentSince = 0;
unsigned long lastSafetyPoll = 0;

struct Measurement {
  float busV;
  float drainV;
  float bulbV;
  float currentMA;
  float powerMW;
  float resistanceOhm;
};

#line 58 "D:\\CLAUDE\\ALMAWARE-LAMP-LAB\\arduino\\ALMAWARE_LAMP_LAB\\ALMAWARE_LAMP_LAB.ino"
void allOff();
#line 64 "D:\\CLAUDE\\ALMAWARE-LAMP-LAB\\arduino\\ALMAWARE_LAMP_LAB\\ALMAWARE_LAMP_LAB.ino"
bool inaWrite16(uint8_t reg, uint16_t value);
#line 72 "D:\\CLAUDE\\ALMAWARE-LAMP-LAB\\arduino\\ALMAWARE_LAMP_LAB\\ALMAWARE_LAMP_LAB.ino"
bool inaRead16(uint8_t reg, uint16_t &value);
#line 81 "D:\\CLAUDE\\ALMAWARE-LAMP-LAB\\arduino\\ALMAWARE_LAMP_LAB\\ALMAWARE_LAMP_LAB.ino"
bool configureINA219();
#line 93 "D:\\CLAUDE\\ALMAWARE-LAMP-LAB\\arduino\\ALMAWARE_LAMP_LAB\\ALMAWARE_LAMP_LAB.ino"
float readBusVoltageV();
#line 99 "D:\\CLAUDE\\ALMAWARE-LAMP-LAB\\arduino\\ALMAWARE_LAMP_LAB\\ALMAWARE_LAMP_LAB.ino"
float readCurrentMA();
#line 107 "D:\\CLAUDE\\ALMAWARE-LAMP-LAB\\arduino\\ALMAWARE_LAMP_LAB\\ALMAWARE_LAMP_LAB.ino"
float readDrainVoltageV();
#line 118 "D:\\CLAUDE\\ALMAWARE-LAMP-LAB\\arduino\\ALMAWARE_LAMP_LAB\\ALMAWARE_LAMP_LAB.ino"
Measurement measure();
#line 146 "D:\\CLAUDE\\ALMAWARE-LAMP-LAB\\arduino\\ALMAWARE_LAMP_LAB\\ALMAWARE_LAMP_LAB.ino"
bool enforceCurrentLimit(float currentMA);
#line 162 "D:\\CLAUDE\\ALMAWARE-LAMP-LAB\\arduino\\ALMAWARE_LAMP_LAB\\ALMAWARE_LAMP_LAB.ino"
bool safetyPoll();
#line 177 "D:\\CLAUDE\\ALMAWARE-LAMP-LAB\\arduino\\ALMAWARE_LAMP_LAB\\ALMAWARE_LAMP_LAB.ino"
void logHeader();
#line 183 "D:\\CLAUDE\\ALMAWARE-LAMP-LAB\\arduino\\ALMAWARE_LAMP_LAB\\ALMAWARE_LAMP_LAB.ino"
bool logMeasurement(const char *test, const char *phase, long trial);
#line 217 "D:\\CLAUDE\\ALMAWARE-LAMP-LAB\\arduino\\ALMAWARE_LAMP_LAB\\ALMAWARE_LAMP_LAB.ino"
void pollStop();
#line 229 "D:\\CLAUDE\\ALMAWARE-LAMP-LAB\\arduino\\ALMAWARE_LAMP_LAB\\ALMAWARE_LAMP_LAB.ino"
bool waitAbortable(unsigned long durationMS);
#line 240 "D:\\CLAUDE\\ALMAWARE-LAMP-LAB\\arduino\\ALMAWARE_LAMP_LAB\\ALMAWARE_LAMP_LAB.ino"
bool softSetDuty(uint8_t target);
#line 250 "D:\\CLAUDE\\ALMAWARE-LAMP-LAB\\arduino\\ALMAWARE_LAMP_LAB\\ALMAWARE_LAMP_LAB.ino"
bool holdAndLog(const char *test, const char *phase, long trial, unsigned long durationMS, unsigned long logEveryMS);
#line 267 "D:\\CLAUDE\\ALMAWARE-LAMP-LAB\\arduino\\ALMAWARE_LAMP_LAB\\ALMAWARE_LAMP_LAB.ino"
void runSweep();
#line 296 "D:\\CLAUDE\\ALMAWARE-LAMP-LAB\\arduino\\ALMAWARE_LAMP_LAB\\ALMAWARE_LAMP_LAB.ino"
void runMemory();
#line 337 "D:\\CLAUDE\\ALMAWARE-LAMP-LAB\\arduino\\ALMAWARE_LAMP_LAB\\ALMAWARE_LAMP_LAB.ino"
void printStatus();
#line 350 "D:\\CLAUDE\\ALMAWARE-LAMP-LAB\\arduino\\ALMAWARE_LAMP_LAB\\ALMAWARE_LAMP_LAB.ino"
void printHelp();
#line 362 "D:\\CLAUDE\\ALMAWARE-LAMP-LAB\\arduino\\ALMAWARE_LAMP_LAB\\ALMAWARE_LAMP_LAB.ino"
void processCommand(String line);
#line 400 "D:\\CLAUDE\\ALMAWARE-LAMP-LAB\\arduino\\ALMAWARE_LAMP_LAB\\ALMAWARE_LAMP_LAB.ino"
void setup();
#line 422 "D:\\CLAUDE\\ALMAWARE-LAMP-LAB\\arduino\\ALMAWARE_LAMP_LAB\\ALMAWARE_LAMP_LAB.ino"
void loop();
#line 58 "D:\\CLAUDE\\ALMAWARE-LAMP-LAB\\arduino\\ALMAWARE_LAMP_LAB\\ALMAWARE_LAMP_LAB.ino"
void allOff() {
  analogWrite(GATE_PIN, 0);
  presentDuty = 0;
  overcurrentSince = 0;
}

bool inaWrite16(uint8_t reg, uint16_t value) {
  Wire.beginTransmission(INA219_ADDRESS);
  Wire.write(reg);
  Wire.write((uint8_t)(value >> 8));
  Wire.write((uint8_t)(value & 0xFF));
  return Wire.endTransmission() == 0;
}

bool inaRead16(uint8_t reg, uint16_t &value) {
  Wire.beginTransmission(INA219_ADDRESS);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(INA219_ADDRESS, (uint8_t)2) != 2) return false;
  value = ((uint16_t)Wire.read() << 8) | Wire.read();
  return true;
}

bool configureINA219() {
  Wire.beginTransmission(INA219_ADDRESS);
  if (Wire.endTransmission() != 0) return false;

  // 32 V range, +/-320 mV shunt range, 12-bit bus + shunt, continuous.
  if (!inaWrite16(0x00, 0x399F)) return false;
  // Standard R100 breakout: 0.1 mA current LSB, 2 mW power LSB.
  if (!inaWrite16(0x05, 4096)) return false;
  delay(5);
  return true;
}

float readBusVoltageV() {
  uint16_t raw = 0;
  if (!inaRead16(0x02, raw)) return -1.0;
  return (float)(raw >> 3) * 0.004;
}

float readCurrentMA() {
  // Calibration can be reset by a brownout; restore it before current reads.
  if (!inaWrite16(0x05, 4096)) return -1.0;
  uint16_t raw = 0;
  if (!inaRead16(0x04, raw)) return -1.0;
  return (float)((int16_t)raw) / 10.0;
}

float readDrainVoltageV() {
  const uint8_t samples = 16;
  unsigned long sum = 0;
  for (uint8_t i = 0; i < samples; i++) {
    sum += analogRead(DRAIN_SENSE_PIN);
    delayMicroseconds(250);
  }
  const float pinV = ((float)sum / samples) * ADC_REFERENCE_V / 1023.0;
  return pinV * (DIVIDER_TOP_OHM + DIVIDER_BOTTOM_OHM) / DIVIDER_BOTTOM_OHM;
}

Measurement measure() {
  const uint8_t samples = 8;
  float busSum = 0.0;
  float currentSum = 0.0;
  uint8_t good = 0;

  for (uint8_t i = 0; i < samples; i++) {
    float bus = readBusVoltageV();
    float current = readCurrentMA();
    if (bus >= 0.0 && current >= -0.5) {
      busSum += bus;
      currentSum += current;
      good++;
    }
    delay(2);
  }

  Measurement m;
  m.busV = good ? busSum / good : -1.0;
  m.currentMA = good ? currentSum / good : -1.0;
  m.drainV = readDrainVoltageV();
  m.bulbV = max(0.0, m.busV - m.drainV);
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
  if (!inaReady || presentDuty == 0) return true;
  if (millis() - lastSafetyPoll < 10) return true;
  lastSafetyPoll = millis();

  float currentMA = readCurrentMA();
  if (currentMA < -0.5) {
    allOff();
    stopRequested = true;
    Serial.println(F("# ABORT INA219 safety read failure"));
    return false;
  }
  return enforceCurrentLimit(currentMA);
}

void logHeader() {
  Serial.println(
      F("ms,test,phase,trial,duty,bus_V,drain_V,bulb_V,current_mA,"
        "power_mW,R_ohm"));
}

bool logMeasurement(const char *test, const char *phase, long trial) {
  Measurement m = measure();
  if (m.busV < 0.0 || m.currentMA < -0.5) {
    allOff();
    stopRequested = true;
    Serial.println(F("# ABORT INA219 read failure"));
    return false;
  }

  Serial.print(millis());
  Serial.print(',');
  Serial.print(test);
  Serial.print(',');
  Serial.print(phase);
  Serial.print(',');
  Serial.print(trial);
  Serial.print(',');
  Serial.print(presentDuty);
  Serial.print(',');
  Serial.print(m.busV, 4);
  Serial.print(',');
  Serial.print(m.drainV, 4);
  Serial.print(',');
  Serial.print(m.bulbV, 4);
  Serial.print(',');
  Serial.print(m.currentMA, 3);
  Serial.print(',');
  Serial.print(m.powerMW, 3);
  Serial.print(',');
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
    if (stopRequested) return false;
    if (!safetyPoll()) return false;
    delay(5);
  }
  return true;
}

bool softSetDuty(uint8_t target) {
  target = min(target, experimentMaxDuty);
  while (presentDuty != target) {
    presentDuty += presentDuty < target ? 1 : -1;
    analogWrite(GATE_PIN, presentDuty);
    if (!waitAbortable(5)) return false;
  }
  return true;
}

bool holdAndLog(const char *test, const char *phase, long trial,
                unsigned long durationMS, unsigned long logEveryMS) {
  unsigned long start = millis();
  unsigned long lastLog = 0;
  while (millis() - start < durationMS) {
    pollStop();
    if (stopRequested) return false;
    if (!safetyPoll()) return false;
    if (millis() - lastLog >= logEveryMS) {
      lastLog = millis();
      if (!logMeasurement(test, phase, trial)) return false;
    }
    delay(2);
  }
  return true;
}

void runSweep() {
  if (!inaReady) {
    Serial.println(F("# Cannot run: INA219 not detected"));
    return;
  }
  stopRequested = false;
  allOff();
  logHeader();
  Serial.println(F("# SWEEP begin"));

  const uint8_t fractions[] = {0, 32, 64, 96, 128, 160, 192, 224, 255};
  const uint8_t count = sizeof(fractions) / sizeof(fractions[0]);

  for (uint8_t i = 0; i < count && !stopRequested; i++) {
    uint8_t duty = (uint16_t)experimentMaxDuty * fractions[i] / 255;
    if (!softSetDuty(duty)) break;
    if (!holdAndLog("sweep", "up", duty, 900, 70)) break;
  }

  for (int8_t i = count - 2; i >= 0 && !stopRequested; i--) {
    uint8_t duty = (uint16_t)experimentMaxDuty * fractions[i] / 255;
    if (!softSetDuty(duty)) break;
    if (!holdAndLog("sweep", "down", duty, 900, 70)) break;
  }

  allOff();
  Serial.println(stopRequested ? F("# SWEEP aborted") : F("# SWEEP complete"));
}

void runMemory() {
  if (!inaReady) {
    Serial.println(F("# Cannot run: INA219 not detected"));
    return;
  }
  stopRequested = false;
  allOff();
  logHeader();
  Serial.println(F("# MEMORY begin"));

  // Cold vanilla reference: the same read pulse without prior heating.
  if (!waitAbortable(6000)) return;
  if (!softSetDuty(min(READ_DUTY, experimentMaxDuty))) return;
  if (!waitAbortable(40)) return;
  logMeasurement("memory", "cold_read", -1);
  allOff();

  const unsigned long coolDelays[] = {100, 300, 1000, 3000, 5000};
  const uint8_t trials = sizeof(coolDelays) / sizeof(coolDelays[0]);

  for (uint8_t trial = 0; trial < trials && !stopRequested; trial++) {
    // Reset close to ambient before each independent trial.
    allOff();
    if (!waitAbortable(6000)) break;

    if (!softSetDuty(experimentMaxDuty)) break;
    if (!holdAndLog("memory", "heat", coolDelays[trial], 2200, 140)) break;

    allOff();
    if (!waitAbortable(coolDelays[trial])) break;

    if (!softSetDuty(min(READ_DUTY, experimentMaxDuty))) break;
    if (!waitAbortable(40)) break;
    if (!logMeasurement("memory", "read", coolDelays[trial])) break;
    allOff();
  }

  allOff();
  Serial.println(stopRequested ? F("# MEMORY aborted") : F("# MEMORY complete"));
}

void printStatus() {
  allOff();
  Measurement m = measure();
  Serial.print(F("# INA219="));
  Serial.print(inaReady ? F("OK") : F("MISSING"));
  Serial.print(F(" maxDuty="));
  Serial.print(experimentMaxDuty);
  Serial.print(F(" bus_V="));
  Serial.print(m.busV, 3);
  Serial.print(F(" current_mA="));
  Serial.println(m.currentMA, 2);
}

void printHelp() {
  Serial.println(F("# Commands:"));
  Serial.println(F("# STATUS  bulb off; print instrument status"));
  Serial.println(F("# READ    bulb off; print one CSV measurement"));
  Serial.println(F("# SWEEP   safe up/down hysteresis experiment"));
  Serial.println(F("# MEMORY  heat/cool/read short-term-memory experiment"));
  Serial.println(F("# RUN     SWEEP then MEMORY"));
  Serial.println(F("# STOP    abort active experiment"));
  Serial.println(F("# MAX n   set ceiling 20..160; default 60"));
  Serial.println(F("# HELP"));
}

void processCommand(String line) {
  line.trim();
  line.toUpperCase();
  if (!line.length()) return;

  if (line == "STATUS") {
    printStatus();
  } else if (line == "READ") {
    allOff();
    logHeader();
    logMeasurement("manual", "off", 0);
  } else if (line == "SWEEP") {
    runSweep();
  } else if (line == "MEMORY") {
    runMemory();
  } else if (line == "RUN") {
    runSweep();
    if (!stopRequested) runMemory();
  } else if (line == "STOP") {
    stopRequested = true;
    allOff();
    Serial.println(F("# Already stopped"));
  } else if (line.startsWith("MAX ")) {
    int value = line.substring(4).toInt();
    if (value < 20 || value > HARD_MAX_DUTY) {
      Serial.println(F("# MAX rejected; allowed 20..160"));
    } else {
      experimentMaxDuty = (uint8_t)value;
      Serial.print(F("# maxDuty="));
      Serial.println(experimentMaxDuty);
    }
  } else if (line == "HELP" || line == "?") {
    printHelp();
  } else {
    Serial.println(F("# Unknown command; type HELP"));
  }
}

void setup() {
  pinMode(GATE_PIN, OUTPUT);
  allOff();
  pinMode(DRAIN_SENSE_PIN, INPUT);

  Serial.begin(115200);
  Serial.setTimeout(8);
  Wire.begin();
  Wire.setClock(100000);

  delay(300);
  inaReady = configureINA219();

  Serial.println(F("# 12V bulb thermal-memory cell"));
  Serial.println(F("# BOOT SAFE: MOSFET OFF; no experiment runs automatically"));
  Serial.println(F("# Verify 12V <=5W incandescent, 0.8A PSU limit, fuse, common GND"));
  if (!inaReady) {
    Serial.println(F("# ERROR: INA219 not found at 0x40; experiments locked"));
  }
  printHelp();
}

void loop() {
  allOff();
  if (!Serial.available()) {
    delay(10);
    return;
  }
  String line = Serial.readStringUntil('\n');
  processCommand(line);
}

