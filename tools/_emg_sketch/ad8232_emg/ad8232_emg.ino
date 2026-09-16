/*
 * ad8232_emg.ino  --  AD8232 single-lead bio-amp -> Arduino Uno -> serial EMG/ECG
 *
 * Streams one ADC reading per line at 115200 baud so emg_pong.py --serial and
 * emg_gui.py can parse it (plain Serial.println of an integer). When a lead is
 * off the skin, it sends the sentinel -1 so the GUI can show "electrode loose".
 *
 * ------------------------------------------------------------------ WIRING ---
 *   AD8232 board   ->   Arduino Uno
 *   ------------        ------------
 *   OUTPUT         ->   A0          (analog bio-signal, 0..1023)
 *   LO+            ->   D11         (leads-off detect, + electrode)
 *   LO-            ->   D10         (leads-off detect, - electrode)
 *   3.3V           ->   3.3V        (DO NOT use 5V -- AD8232 is a 3.3V part)
 *   GND            ->   GND
 *   SDN            ->   (leave unconnected, or tie to 3.3V to keep enabled)
 *
 * The AD8232 ADC reading sits around mid-scale (~512) and swings with the
 * muscle/heart signal. analogRead() uses the 5V reference by default; the
 * AD8232 output is 0..3.3V so readings top out near ~675 -- that is fine, the
 * envelope detector in the Python side is ratiometric and auto-calibrates the
 * resting baseline.
 *
 * --------------------------------------------------------- ELECTRODE PLACEMENT
 *   EMG (muscle, e.g. forearm flexor):
 *     RA (+, red)   -> on the muscle belly
 *     LA (-, yellow)-> ~2-3 cm along the same muscle, in line with the fibers
 *     RL (ref,green)-> a bony, electrically-quiet spot (wrist bone / elbow)
 *
 *   ECG (heart, classic Einthoven-ish):
 *     RA -> right upper chest / below right collarbone
 *     LA -> left upper chest  / below left collarbone
 *     RL -> lower right abdomen (reference)
 *
 *   Use fresh gel electrodes, press firmly, keep cables still. If the trace is
 *   flat-lining at -1 the leads-off detector says an electrode isn't making
 *   skin contact -- re-stick it.
 * -----------------------------------------------------------------------------
 */

const int PIN_EMG   = A0;   // AD8232 OUTPUT
const int PIN_LO_P  = 11;   // AD8232 LO+  (leads-off, + side)
const int PIN_LO_M  = 10;   // AD8232 LO-  (leads-off, - side)

const long SERIAL_BAUD = 115200;

// Target sample period. ~333 Hz (3 ms) sits comfortably in the 200-500 Hz
// window the task asks for and is plenty for surface EMG (most power < 150 Hz)
// and ECG. Lower SAMPLE_INTERVAL_US -> faster sampling.
const unsigned long SAMPLE_INTERVAL_US = 3000UL;   // 3 ms -> ~333 samples/sec

unsigned long lastSampleUs = 0;

void setup() {
  Serial.begin(SERIAL_BAUD);
  // The AD8232 drives LO+/LO- HIGH when its electrode is off the body.
  pinMode(PIN_LO_P, INPUT);
  pinMode(PIN_LO_M, INPUT);
  // A0 is analog input by default; no pinMode needed.
}

void loop() {
  unsigned long now = micros();
  // Fixed-rate, non-blocking sampling (micros() wraps cleanly with unsigned math).
  if ((unsigned long)(now - lastSampleUs) < SAMPLE_INTERVAL_US) {
    return;
  }
  lastSampleUs = now;

  // Leads-off detection: if either electrode is lifted, emit the sentinel.
  if (digitalRead(PIN_LO_P) == HIGH || digitalRead(PIN_LO_M) == HIGH) {
    Serial.println(-1);
    return;
  }

  int value = analogRead(PIN_EMG);   // 0..1023
  Serial.println(value);
}
