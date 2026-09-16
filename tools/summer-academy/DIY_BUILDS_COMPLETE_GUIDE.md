# 🔧 DIY Builds Guide — Complete Course
## Fungal Neural Networks, Optical Computers, Abacus, Turing Machines
**For Makers, Students, Educators — All Ages. All Open-Source.**

---

# Table of Contents
1. Fungal Neural Network (Physarum polycephalum bio-computer)
2. Optical Logic Gates (light-based computing)
3. Wooden Abacus Computer (mechanical analog)
4. Turing Machine Simulator (3D-printed, Arduino-driven)
5. Appendix: Code, Schematics, Shopping Lists

---

---

# Part 1: Fungal Neural Network — The Living Computer

## 1.1 What is Physarum Polycephalum?

Physarum polycephalum ("many-headed slime mold") is a single-celled organism that behaves like a distributed network. It:
- Grows through branching tubes (plasmodium)
- Solves optimization problems (shortest path, maze solving)
- Communicates chemically across its body
- Dies and regrows in response to stimuli
- Trains neural-like networks

**Why it's brilliant for DIY AI:** You can literally watch intelligence emerge from a living system. It's a hands-on proof that intelligence doesn't require a brain.

---

## 1.2 Materials Needed

### Culturing Supplies
- Physarum polycephalum culture kit (~$25 online or local bio lab)
- **Or:** Obtain from Carolina Biological Supply or grow from oat spores
- Petri dishes (100mm, 10 pack) — $8
- Agar powder (mycological grade) — $12
- Oatmeal (organic, rolled) — $5 (kitchen staple)
- Distilled water — $3/gallon
- Plastic wrap, parafilm — $5
- Incubator (or use a warm closet, 20-24°C) — $0 (optional)

### Sensing & Computing
- Arduino Uno or Nano — $15
- 4× gold-plated electrodes (0.5mm diameter) — DIY: use gold-plated sewing pins + epoxy
- Jumper wires (40-pack) — $3
- Breadboard — $2
- 10kΩ resistors (10-pack) — $1
- Capacitors (assorted) — $5
- 3.3V relay module — $2
- USB cable — $2
- Laptop with Arduino IDE (free)

### Maze & Stimulus Setup
- Clear acrylic sheet (9×12") — $5
- Fabric paint (yellow, non-toxic) — $3 (marks the maze)
- LED strip (RGB optional) — $8
- Hot glue gun + glue sticks — $3

**Total starter cost: ~$100 (culture kit rental) or $150 (own kit)**

---

## 1.3 Step 1: Culturing Physarum

### Week 1: Prepare the Culture Medium

1. **Make the agar:**
   - Boil 500mL distilled water
   - Add 5g agar powder
   - Stir until fully dissolved (~5 min)
   - Cool to 50°C (lukewarm)

2. **Pour into petri dishes:**
   - Pour ~15mL agar per dish
   - Let cool to room temperature (solidifies in ~30 min)
   - Cover with lids; store in cool, dark place (4°C fridge OK)

3. **Add food source:**
   - Sprinkle a small pinch of dry oatmeal (~5mm cube) on center of agar
   - This is the "seed"

### Week 1-2: Inoculate

1. **Obtain Physarum:**
   - If using kit: follow kit instructions (usually a vial of plasmodium)
   - If growing from spores: collect brown sclerotia (resting bodies) from damp leaf litter, place on oatmeal
   
2. **Place culture on agar:**
   - Transfer a tiny piece (toothpick-sized) of plasmodium onto oatmeal
   - Cover with parafilm (leaves small gaps for gas exchange)
   - Place in warm, dark spot (drawer, box, 20-24°C)

### Week 2-3: Growth Phase

- **Days 3-5:** Plasmodium emerges from spore, explores agar
- **Days 5-10:** Yellow tubes spread outward, branching network forms
- **Day 10-14:** Full network established (~10cm diameter)

**Feeding:** Place fresh oatmeal flakes at new sites; plasmodium migrates toward food.

**Troubleshooting:**
- Too wet → mold contamination (use parafilm, not full seal)
- Too dry → desiccation (keep humidity ~60%)
- Wrong temp → slow growth (<15°C) or death (>28°C)

---

## 1.4 Step 2: Training the Network (Maze Solving)

### Build the Maze

1. **Design maze on acrylic:**
   - Draw a simple maze (5×5 grid, 1cm paths) in pencil on clear acrylic
   - Paint pathways with non-toxic yellow or white fabric paint
   - Mark start (S) and food destination (F)
   - Let dry 24 hours

2. **Setup:**
   - Place agar layer on the acrylic (use thin clear silicone or double-sided tape)
   - Seal edges with parafilm (keep 1cm gap for air)

3. **Inoculate at start:**
   - Place plasmodium at S
   - Place fresh oatmeal at F
   - Incubate in the dark

### Observation & Training

- **Day 1:** Plasmodium explores randomly
- **Day 2-3:** Network converges toward food
- **Day 4-7:** Plasmodium retracts unnecessary branches → optimal path emerges
- **Day 7+:** Repeatable solution; plasmodium "solves" the maze

**Quantify:**
- Measure efficiency: `(optimal path length) / (actual path length)` 
- Early: ~1.5-2.0 (wastes energy)
- Late: ~1.0-1.1 (near-optimal)

---

## 1.5 Step 3: Electrophysiology — The Living Neural Network

### Wire the Electrodes

**Goal:** Record electrical signals as plasmodium explores. These mimic neural spikes.

1. **Electrode placement:**
   - Insert 4 gold-plated electrodes into agar at cardinal points (N, E, S, W) of the network
   - Push until they just touch the plasmodium (visible yellow tube)
   - Space 2cm apart

2. **Wiring to Arduino:**
   ```
   Electrode 1 (N)  → Arduino A0
   Electrode 2 (E)  → Arduino A1
   Electrode 3 (S)  → Arduino A2
   Electrode 4 (W)  → Arduino A3
   Ground (GND)     → Arduino GND
   Reference (Ref)  → Arduino 3.3V via 10kΩ resistor
   ```

3. **Breadboard setup:**
   - Arrange in a 4-channel analog input configuration
   - Add capacitors (0.1µF) across analog inputs for noise filtering

---

## 1.6 Arduino Code: Read Signals

```cpp
// Physarum Neural Signal Monitor
// Reads electrical activity from 4 electrodes in a petri dish

const int electrode1 = A0;
const int electrode2 = A1;
const int electrode3 = A2;
const int electrode4 = A3;

void setup() {
  Serial.begin(9600);
  pinMode(electrode1, INPUT);
  pinMode(electrode2, INPUT);
  pinMode(electrode3, INPUT);
  pinMode(electrode4, INPUT);
}

void loop() {
  int val1 = analogRead(electrode1);
  int val2 = analogRead(electrode2);
  int val3 = analogRead(electrode3);
  int val4 = analogRead(electrode4);
  
  // Print as CSV for plotting
  Serial.print(val1); Serial.print(",");
  Serial.print(val2); Serial.print(",");
  Serial.print(val3); Serial.print(",");
  Serial.println(val4);
  
  delay(100); // 10Hz sampling
}
```

**Analysis (Python):**
```python
import serial
import matplotlib.pyplot as plt
import numpy as np

ser = serial.Serial('/dev/ttyUSB0', 9600)
data = [[], [], [], []]

for i in range(1000):
    line = ser.readline().decode().strip()
    vals = list(map(int, line.split(',')))
    for j in range(4):
        data[j].append(vals[j])

# Plot
for i, ch in enumerate(data):
    plt.plot(ch, label=f'Electrode {i+1}')
plt.legend()
plt.xlabel('Time (10Hz samples)')
plt.ylabel('Voltage (mV)')
plt.title('Physarum Neural Activity')
plt.show()
```

---

## 1.7 Step 4: Training a Classifier

**Goal:** Teach Arduino to recognize patterns in plasmodium signals.

### Collect Training Data

1. **Stimulate plasmodium:**
   - Place light source on one side
   - Place food on another side
   - Record electrode signals during exploration

2. **Label data:**
   - "Moving toward light" (positive)
   - "Moving toward food" (positive)
   - "Random movement" (neutral)

3. **Use TinyML (TensorFlow Lite for microcontrollers):**

```cpp
// Simplified pattern matcher (binary: responding or not)
int detectResponse(int vals[4]) {
  int diff_horizontal = abs(vals[1] - vals[3]); // E - W
  int diff_vertical = abs(vals[0] - vals[2]);   // N - S
  int avg_activity = (vals[0] + vals[1] + vals[2] + vals[3]) / 4;
  
  // Heuristic: high activity + directional bias = response
  if (avg_activity > 400 && (diff_horizontal > 100 || diff_vertical > 100)) {
    return 1; // Responding
  }
  return 0; // Random
}
```

---

## 1.8 Project Outcomes

By the end of this module, you have:
- ✅ A living, growing organism
- ✅ Proof of maze-solving intelligence
- ✅ Real-time electrical signals from a bio-network
- ✅ Data logging & analysis pipeline
- ✅ A classifier that recognizes behavior

**Photos & videos:** Document growth, maze solving, and signals. Share with the group!

---

---

# Part 2: Optical Logic Gates — Computing with Light

## 2.1 Intro: Why Optical Computing?

- **Speed:** Light travels 300,000 km/s (vs. electrons at ~1/100 light speed)
- **Energy:** Photons don't dissipate heat like electricity
- **Parallelism:** Light beams can cross without interfering
- **Physical beauty:** You *see* computation happening

**Goal:** Build AND, OR, NOT gates using LEDs, fiber optics, and photodiodes.

---

## 2.2 Materials

### Optical Hardware
- **Fiber optic cable** (multimode, 50µm core, 1m) — $10
- **LEDs** (red 5mm, 2×) — $1
- **Photodiodes** (BPW34 or similar, 2×) — $5
- **Prism or dichroic mirror** (beam splitter) — $12 (or DIY with glass at 45°)
- **Lens kit** (focal lengths 25mm, 50mm, 100mm) — $15
- **Fiber optic connectors** (SMA or FC, 2 pairs) — $10
- **Mounting hardware** (rails, brackets, clamps) — $20
- **3D-printed stands** — $5 (filament)

### Electronics
- Arduino Uno — $15
- Photodiode amplifier circuit (op-amp based) — $5
- 555 Timer IC — $1
- Resistors & capacitors (assorted) — $10
- Breadboard + wires — $5
- LED driver module (for high-brightness LEDs) — $3

**Total: ~$120**

---

## 2.3 Part A: Build a Basic Optical AND Gate

### Setup

```
INPUT 1 (Red LED) ──┐
                    ├─→ Beam Splitter ──→ Fiber Optic ──→ Photodiode → OUTPUT
INPUT 2 (Red LED) ──┘
```

**Logic:** Output is HIGH only if BOTH inputs are HIGH.

### Assembly

1. **Mount LEDs:**
   - Place LED 1 and LED 2 on opposite sides of a beam splitter (prism or dichroic mirror at 45°)
   - Align optics so both beams converge into a single fiber optic cable
   - Use 3D-printed brackets for precise alignment

2. **Fiber Coupling:**
   - Insert fiber optic cable into the convergence point
   - Use a focusing lens (50mm) to direct light into fiber
   - Secure with set screws

3. **Output Photodiode:**
   - Place photodiode at fiber exit
   - Attach lens (25mm) to focus light onto photodiode
   - Secure in place

### Wiring (Arduino)

```
LED 1  → Arduino Pin 3 (PWM)
LED 2  → Arduino Pin 5 (PWM)
Photodiode → Arduino A0

GND → Common ground
```

### Arduino Code: AND Gate

```cpp
const int LED1 = 3;
const int LED2 = 5;
const int photodiode = A0;

void setup() {
  pinMode(LED1, OUTPUT);
  pinMode(LED2, OUTPUT);
  Serial.begin(9600);
}

void loop() {
  // Test all 4 combinations
  for (int input1 = 0; input1 <= 1; input1++) {
    for (int input2 = 0; input2 <= 1; input2++) {
      digitalWrite(LED1, input1 * 255);  // Full on if 1, off if 0
      digitalWrite(LED2, input2 * 255);
      
      delay(500);
      
      int output = analogRead(photodiode) > 512 ? 1 : 0;
      Serial.print("Input: ");
      Serial.print(input1); Serial.print(" ");
      Serial.print(input2); Serial.print(" → Output: ");
      Serial.println(output);
      
      delay(500);
    }
  }
  delay(2000);
}
```

**Expected result:**
```
0 0 → 0
0 1 → 0
1 0 → 0
1 1 → 1  ✓ AND logic
```

---

## 2.4 Part B: OR Gate & Cascading

**OR Gate Setup:**
- Same fiber optic but measure output when **either** input is HIGH

**Code Modification:**
```cpp
// Threshold = 30% of max (sensitive; fires if ANY light present)
int output = analogRead(photodiode) > 300 ? 1 : 0;
```

**Cascade multiple gates:**
- Output of AND gate → Input to next optical gate
- Build complex logic (e.g., (A AND B) OR C)

---

## 2.5 Photodiode Amplifier Circuit

Raw photodiode output is weak (~pA). Amplify with op-amp:

```
Photodiode (cathode) ──┬──────┬───[10MΩ]───┬─────→ Output
                       │      │             │
                      GND    [Op-Amp]      │
                              │            │
                              └────[1MΩ]───┘
                              (feedback)
```

**Gain = -(Rf / Ri) = -(1M / 10M) = -0.1V/nA**

---

## 2.6 Project Outcomes

By the end:
- ✅ Working optical AND gate (light-based computation)
- ✅ Cascadable logic system
- ✅ Understanding of photon-based computing
- ✅ Hands-on experience with optics & precision alignment

---

---

# Part 3: Wooden Abacus Computer — Analog Arithmetic

## 3.1 What is an Abacus?

An abacus is humanity's oldest calculator — a mechanical device for arithmetic using position of beads on rods.

**DIY angle:** Craft a programmable wooden abacus that stores and performs calculations. It's a tangible, beautiful introduction to analog computing.

---

## 3.2 Materials

### Wood & Hardware
- **Wooden dowels** (0.5" diameter, 2 feet length, 10×) — $8
- **Wood frame** (3/4" plywood, 2×1 feet) — $10
- **Wood glue** — $5
- **Sandpaper** (assorted grits) — $3
- **Stain or paint** (optional) — $5
- **Beads** (0.75" wooden beads, 100 pack) — $5
- **Screws & nails** — $3

### Assembly Tools
- Drill with bits
- Saw (hand or power)
- Ruler, pencil, square

**Total: ~$40**

---

## 3.3 Step 1: Design the Frame

**Standard abacus: 10 rods, 10 beads per rod = 100 total beads**

### Dimensions
- Frame width: 12 inches
- Frame height: 8 inches
- Rod length: 10 inches
- Rod spacing: 1 inch

### Sketch (top view)
```
┌─────────────────────────┐
│ O O O  O O O  O O O  O  │ Rod 1 (Units)
│ O O O  O O O  O O O  O  │ Rod 2 (Tens)
│ O O O  O O O  O O O  O  │ Rod 3 (Hundreds)
│ O O O  O O O  O O O  O  │ Rod 4 (Thousands)
│ O O O  O O O  O O O  O  │ Rod 5 (Tens of thousands)
│                         │
│ O O O  O O O  O O O  O  │ Rod 6-10 (for other operations)
└─────────────────────────┘
```

---

## 3.4 Step 2: Build the Frame

1. **Cut plywood:**
   - Two sides (12" × 8")
   - Top and bottom rails (10" × 3")
   - Back support (10" × 8")

2. **Assemble:**
   - Glue & screw sides to rails
   - Attach back support for stability
   - Sand all edges smooth

3. **Drill rod holes:**
   - Mark 10 holes, 1" apart, horizontally
   - Drill 0.5" holes through both sides
   - Ensure perfect alignment (use drill press if available)

---

## 3.5 Step 3: Insert Rods & Beads

1. **Prepare rods:**
   - Cut dowels to 10" length
   - Sand smooth
   - Paint or stain (optional, for aesthetics)

2. **String beads:**
   - Insert rod through first hole
   - Slide 10 beads onto rod
   - Continue through all 10 rods

3. **Secure rods:**
   - Glue each rod into place (use removable glue if you want to adjust)
   - Verify all beads slide freely

---

## 3.6 Step 4: Programming Logic — Addition

### How to Use for Addition

**Example: 24 + 35 = 59**

1. **Setup (represent 24):**
   - Rod 1 (units): Move 4 beads up
   - Rod 2 (tens): Move 2 beads up
   - Result: 24

2. **Add 35:**
   - Rod 1: Add 5 more (move up) → total 9 beads up
   - Rod 2: Add 3 more (move up) → total 5 beads up
   - Result: 59 ✓

**For subtraction:** Start with the minuend, move beads down.

---

## 3.7 Mechanical Improvements: Gears & Wheels

**Advanced version:** Add mechanical gears to automate carry operations.

```
Rod 1 (Units)
    ↓
[Gear A: 10 teeth]
    ↓ (meshes with)
[Gear B: 1 tooth] → Rod 2 (Tens) — automatic carry
```

When a rod reaches 10 beads, gear system triggers a bead on the next rod.

**DIY gear wheels:**
- 3D print or laser-cut from plywood
- Use involute gear profiles (Google "DIY gear generator")
- Attach with brass rods & bearings

---

## 3.8 Project Outcomes

By the end:
- ✅ A working mechanical calculator
- ✅ Hands-on understanding of positional arithmetic
- ✅ Beautiful wooden artifact
- ✅ Proof that computation existed for 4,000 years without electricity

---

---

# Part 4: Turing Machine Simulator — 3D-Printed + Arduino

## 4.1 What is a Turing Machine?

Alan Turing's 1936 theoretical model of computation:
- **Infinite tape** (memory) with cells containing symbols
- **Read/write head** that moves left/right
- **State machine** that executes rules based on current state & symbol
- **Proves** the concept of algorithm & computability

**DIY goal:** Build a working mechanical Turing machine that can run simple programs.

---

## 4.2 Materials

### 3D Printing
- **PLA filament** (500g, ~$10)
- **3D printer access** (Makerspace, school lab, or home printer ~$200)
- **Print files** (open-source, provided below)

### Electronics
- **Arduino Mega** (larger I/O than Uno) — $20
- **Stepper motors** (4×, NEMA 17) — $40
- **Motor drivers** (2× DRV8825) — $8
- **Limit switches** (4×) — $3
- **Power supply** (12V 5A) — $15
- **Breadboard, wires, resistors** — $10

### Mechanical
- **Threaded rods** (M8, 2 meters) — $5
- **Bearings** (608 skateboard bearing, 4×) — $4
- **Tape** (thermal paper roll, 10m) — $5
- **Markers** (dry-erase, for tape symbols) — $3

**Total: ~$130 (without printer)**

---

## 4.3 Step 1: Print the Structure

### Files (download from Thingiverse or Printables)

1. **Frame components:**
   - `turing-frame-left.stl` (support bracket)
   - `turing-frame-right.stl` (mirror)
   - `tape-roller-pulley.stl` (2×, drives tape)
   - `head-carriage.stl` (holds read/write mechanism)

2. **Tape movement:**
   - `stepper-bracket.stl` (mounts motor to pulley)
   - `tape-guide.stl` (keeps tape straight)

3. **Read/Write head:**
   - `pen-holder.stl` (dry-erase marker clamp)
   - `sensor-mount.stl` (IR sensor for reading)

### Print Settings
- Layer height: 0.2mm (standard)
- Infill: 20% (strong enough, saves filament)
- Support: Yes (generate automatically in Cura/PrusaSlicer)
- Material: PLA (easier than PETG for beginners)
- Estimated print time: 24-48 hours total

---

## 4.4 Step 2: Assemble the Mechanics

### Tape System

1. **Tape path:**
   ```
   [Spool A] ──→ [Tape] ──→ [Carriage] ──→ [Spool B]
                              ↑
                        Read/Write Head
   ```

2. **Mount tape spools:**
   - Attach stepper motors to pulleys via 3D-printed couplings
   - Spools wind/unwind tape as motors turn

3. **Carriage movement (optional):**
   - Alternative: Keep tape still, move read/write head left/right
   - Simpler mechanically; use a third stepper for head position

---

## 4.5 Arduino Code: Turing Machine Core

```cpp
#include <Stepper.h>

// Motor definitions
#define STEPS_PER_REV 200
Stepper tapeMotor(STEPS_PER_REV, 8, 9, 10, 11);   // Tape movement
Stepper headMotor(STEPS_PER_REV, 12, 13, 14, 15); // Head left/right

// State machine
int currentState = 0;
int tapePosition = 0;
char tapeCell[100]; // Tape cells

// Turing machine state table (simple example: binary counter)
struct Rule {
  int state;
  char read;
  char write;
  int newState;
  int moveDirection; // -1 (left), 0 (stop), 1 (right)
};

Rule rules[] = {
  // State 0: Start
  {0, '_', '0', 1, 1},
  {0, '0', '1', 0, 0},
  {0, '1', '0', 1, 1},
  
  // State 1: Increment
  {1, '0', '1', 2, 0},
  {1, '1', '0', 1, -1},
  
  // State 2: Halt
  {2, '_', '_', 2, 0},
};

const int numRules = sizeof(rules) / sizeof(rules[0]);

void setup() {
  Serial.begin(9600);
  tapeMotor.setSpeed(60);  // RPM
  headMotor.setSpeed(60);
  
  // Initialize tape with blanks
  for (int i = 0; i < 100; i++) {
    tapeCell[i] = '_';
  }
  tapeCell[50] = '0'; // Start with 0 at center
  
  printTape();
}

void loop() {
  // Step 1: Read current cell
  char currentCell = tapeCell[tapePosition];
  Serial.print("State: "); Serial.print(currentState);
  Serial.print(" | Read: "); Serial.print(currentCell);
  Serial.print(" | Position: "); Serial.println(tapePosition);
  
  // Step 2: Find applicable rule
  boolean foundRule = false;
  for (int i = 0; i < numRules; i++) {
    if (rules[i].state == currentState && rules[i].read == currentCell) {
      // Execute rule
      tapeCell[tapePosition] = rules[i].write;
      currentState = rules[i].newState;
      
      // Move head/tape
      if (rules[i].moveDirection == 1) {
        tapePosition++;
        tapeMotor.step(10); // Move right
      } else if (rules[i].moveDirection == -1) {
        tapePosition--;
        tapeMotor.step(-10); // Move left
      }
      
      foundRule = true;
      break;
    }
  }
  
  // Step 3: Halt if no rule found (implicit accept)
  if (!foundRule || currentState == 2) {
    Serial.println("HALT");
    printTape();
    while (1); // Stop
  }
  
  delay(1000); // Pause between steps
  printTape();
}

void printTape() {
  Serial.print("Tape: ");
  for (int i = 40; i < 60; i++) {
    Serial.print(tapeCell[i]);
  }
  Serial.println();
}
```

---

## 4.6 Sample Programs

### Program 1: Binary Increment
**Starts with "0", converts to "1", "10", "11", "100", ...**

```
State | Read | Write | Next | Move
------+------+-------+------+------
  0   | '_'  |  '0'  |  1   | →
  0   | '0'  |  '1'  |  0   | ·
  0   | '1'  |  '0'  |  1   | →
  1   | '0'  |  '1'  |  2   | ·
  1   | '1'  |  '0'  |  1   | ←
  2   | '_'  |  '_'  |  2   | ·
```

---

### Program 2: Palindrome Checker
**Checks if tape matches its reverse**

(More complex; requires 5-7 states)

---

## 4.7 Project Outcomes

By the end:
- ✅ Working mechanical Turing machine
- ✅ Executable programs stored as state tables
- ✅ Real-time understanding of computability
- ✅ Proof that Turing's theoretical model is physically realizable

---

---

# Appendix A: Shopping List (Complete)

| Item | Qty | Cost | Source |
|------|-----|------|--------|
| **Fungal Neural Network** |
| Physarum polycephalum culture | 1 | $25 | Carolina Bio |
| Petri dishes (100mm) | 10 | $8 | AmazonBasics |
| Agar powder | 1 | $12 | Bio-supply |
| Arduino Uno | 1 | $15 | Arduino.cc |
| Gold electrodes | 4 | $15 | DIY (sewing pins + epoxy) |
| Sensors & breadboard | 1 | $10 | Adafruit |
| **Optical Computer** |
| Fiber optic cable (multimode) | 1m | $10 | Amazon |
| Red LEDs (5mm) | 10 | $3 | Local electronics |
| Photodiodes (BPW34) | 2 | $5 | DigiKey |
| Optical lenses kit | 1 | $15 | Thorlabs (or aliexpress knockoff) |
| Dichroic mirror / beam splitter | 1 | $12 | Amazon |
| 3D filament (PLA) | 500g | $10 | MatterHackers |
| **Wooden Abacus** |
| Wooden dowels | 10 | $8 | Home Depot |
| Plywood sheet | 1 | $10 | Home Depot |
| Wooden beads | 100 | $5 | Craft store |
| Wood glue, nails, screws | 1 | $10 | Hardware store |
| **Turing Machine** |
| PLA filament | 1kg | $20 | MatterHackers |
| Arduino Mega | 1 | $20 | Arduino.cc |
| Stepper motors (NEMA 17) | 4 | $40 | AmazonBasics |
| Motor drivers (DRV8825) | 2 | $8 | AliExpress |
| Power supply (12V 5A) | 1 | $15 | Amazon |
| Threaded rods, bearings | 1 | $10 | Home Depot |
| **Common Tools & Supplies** |
| Breadboards, wires, resistors | 1 | $30 | Adafruit kit |
| Soldering kit | 1 | $20 | Amazon |
| Safety goggles, gloves | 1 | $10 | Hardware store |

**Grand Total: ~$400-500 (with 3D printer access; ~$700 if buying printer)**

---

---

# Appendix B: Additional Resources

### Recommended Reading
- **"Gödel, Escher, Bach"** by Douglas Hofstadter (philosophy of mind & self-reference)
- **"The Turing Omnibus"** by A.K. Dewdney (100 short essays on computation)
- **"Life's a Glitch"** — online documentation of DIY bio-computing projects

### Open-Source Projects
- **Physarum solver:** github.com/adrianveres/physarum
- **Optical computing:** github.com/openoptics/diy-gates
- **Turing machine simulator:** github.com/smarr/turing-machine-3d

### Communities
- r/DIYbiology (Reddit)
- BiohackAcademy (Berlin-based, open curriculum)
- Local makerspaces (find via hackerspaces.org)

---

# Appendix C: Safety Notes

1. **Fungal culture:** Keep sealed to prevent mold cross-contamination. Wash hands after handling.
2. **High-power LEDs:** Can cause eye damage. Wear safety glasses during optical work.
3. **Soldering:** Use ventilation; lead-free solder preferred.
4. **3D printing:** Heated beds/nozzles; long-print jobs may emit fumes. Work in ventilated area.
5. **Arduino:** 5V circuits are safe; always use proper grounding.

---

# End of DIY Builds Guide

**Congratulations!** You now have 4 complete DIY projects spanning biology, photonics, mechanics, and computation theory.

Each project teaches a different computational paradigm:
- **Fungal networks:** Distributed, emergent intelligence
- **Optical gates:** Physical speed of light computation
- **Abacus:** Historical analog arithmetic
- **Turing machine:** Theoretical computer science in hardware

**Share your builds with us!** Tag #SummerAcademy2026 on social media.

---
