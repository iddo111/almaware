/*
 * firmware.ino — self-training controller for the POT + CAP neuron.
 * ALMAWARE · 100% ours. Arduino Nano / RP2040.
 *
 * This is the REAL closed loop that sim.py proves in software:
 *   1. read inputs x1,x2 (ADC)
 *   2. the ANALOG neuron (op-amps U1/U2 sum, U3 comparator) computes y in hardware;
 *      we read y from the comparator output pin.
 *   3. e = target - y
 *   4. nudge each electrically-tunable weight by an integer #steps proportional to e*x_i:
 *        w1  -> SERVO angle  (variable capacitor Cw1)      0..180 deg
 *        w2  -> MCP41010 tap (digital pot Rw2)             0..255
 *        b   -> MCP41010 tap (bias pot)                    0..255
 * Same update rule and grids as sim.py, so the bench matches the simulation.
 */
#include <Servo.h>
#include <SPI.h>

// ---- pins ----
const int PIN_X1   = A0;    // input 1  (analog, 0..1023 -> -1..+1)
const int PIN_X2   = A1;    // input 2
const int PIN_Y    = 2;     // comparator U3 output (digital: neuron fired?)
const int PIN_TGT  = 3;     // desired label switch during training (0/1)
const int PIN_SERVO= 9;     // SG90 signal -> rotates the variable capacitor Cw1
const int CS_W2    = 10;    // MCP41010 chip-select: weight-2 pot
const int CS_B     = 8;     // MCP41010 chip-select: bias pot

// ---- learning (mirror sim.py) ----
const int   KSTEP     = 4;      // integer step gain (== sim.py kstep)
const int   SERVO_MIN = 0, SERVO_MAX = 180;
const int   POT_MIN   = 0, POT_MAX   = 255;
const float LR_HOLD_MS = 20;    // one update every 20 ms (== sim loop cadence)

// ---- weight state (start centered = zero weight) ----
int a1 = 90;    // servo angle  -> w1 = 0
int t2 = 128;   // pot tap      -> w2 = 0
int tb = 128;   // bias tap     -> b  = 0

Servo capServo;

int clampi(int v, int lo, int hi){ return v<lo?lo:(v>hi?hi:v); }

// write an 8-bit wiper value to an MCP41010 over SPI
void setPot(int cs, int val){
  digitalWrite(cs, LOW);
  SPI.transfer(0x11);            // command: write to potentiometer 0
  SPI.transfer(clampi(val,0,255));
  digitalWrite(cs, HIGH);
}

void applyWeights(){
  capServo.write(clampi(a1, SERVO_MIN, SERVO_MAX)); // Cw1 via servo
  setPot(CS_W2, t2);                                // Rw2
  setPot(CS_B,  tb);                                // bias
}

void setup(){
  pinMode(PIN_Y, INPUT);
  pinMode(PIN_TGT, INPUT_PULLUP);
  pinMode(CS_W2, OUTPUT); pinMode(CS_B, OUTPUT);
  digitalWrite(CS_W2, HIGH); digitalWrite(CS_B, HIGH);
  SPI.begin();
  capServo.attach(PIN_SERVO);
  applyWeights();
  Serial.begin(115200);
  Serial.println("POT+CAP neuron — self-training online. (open switch=infer, hold=train)");
}

void loop(){
  // read inputs, map ADC 0..1023 -> -1..+1  (x for the update sign)
  float x1 = (analogRead(PIN_X1) - 511.5f) / 511.5f;
  float x2 = (analogRead(PIN_X2) - 511.5f) / 511.5f;

  // the ANALOG circuit already computed the weighted sum + activation:
  int y = digitalRead(PIN_Y);          // 1 if neuron fired, else 0

  bool training = (digitalRead(PIN_TGT) == LOW); // held = supply a target & learn
  if (training){
    int target = 1;                    // wire PIN_TGT source to the desired label
    int e = target - y;                // -1, 0, +1
    if (e != 0){
      a1 = clampi(a1 + (int)round(KSTEP * e * x1), SERVO_MIN, SERVO_MAX); // Cw1
      t2 = clampi(t2 + (int)round(KSTEP * e * x2), POT_MIN,  POT_MAX);    // Rw2
      tb = clampi(tb + (int)round(KSTEP * e * 1.0f), POT_MIN, POT_MAX);   // bias
      applyWeights();
    }
  }

  Serial.print("x1="); Serial.print(x1,2);
  Serial.print(" x2="); Serial.print(x2,2);
  Serial.print(" y=");  Serial.print(y);
  Serial.print(" | a1="); Serial.print(a1);
  Serial.print(" t2=");   Serial.print(t2);
  Serial.print(" tb=");   Serial.println(tb);

  delay(LR_HOLD_MS);
}
