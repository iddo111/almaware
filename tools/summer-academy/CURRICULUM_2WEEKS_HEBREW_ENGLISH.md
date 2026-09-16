# 📚 Summer Academy 2-Week Curriculum
## **Advanced STEM & Maker Camp — Hebrew & English**
### June 2026 | Israel | Ages 12+

---

# WEEK 1: Foundations & First Builds

---

## **DAY 1 — Monday | יום שני — מחר**
### **Welcome to Making! | !ברוכים הבאים לעולם ההייטק**

**Time:** 9:00 AM - 4:00 PM (with lunch break 12-1 PM)

**Objectives:**
- Meet your instructors and bot teammates (Claude + Grok)
- Understand the maker lab layout and safety protocols
- Get comfortable with soldering, breadboards, and basic tools
- Establish a community of makers

**Morning Session (9 AM - 12 PM):**

1. **Welcome circle** (30 min)
   - Introduce instructors, guest roboticists, community partners
   - Share summer goals
   - Tour the lab: soldering station, 3D printers, electronics bench, growing lab, kitchen (hydroponics)

2. **Safety Bootcamp** (45 min)
   - Soldering irons: temperature, ventilation, burn prevention
   - Power tools: goggles, gloves, lockout procedures
   - Chemical safety: acetic acid (for cultures), solvents, epoxy
   - First aid station tour
   - **Hands-on:** Practice soldering with "solder sucker" and wet sponge

3. **Tool Familiarity** (60 min)
   - Multimeter: voltage, continuity, resistance measurement
   - Breadboard: how rows/columns connect
   - Jumper wires: color-coded best practices
   - Hand tools: screwdrivers, pliers, wire strippers, clamps
   - **Activity:** Build a simple LED circuit with switch (no code, just wiring)

4. **Lunch** (1 PM - 2 PM)
   - Eat together in the kitchen
   - Informal chat with instructors
   - First taste of hydroponic salad grown by past students!

**Afternoon Session (2 PM - 4 PM):**

5. **Intro to Arduino** (90 min)
   - What is a microcontroller? (brain for robots)
   - Arduino Uno anatomy: pins, power, USB
   - Install Arduino IDE on laptops
   - Plug in your first board
   - **Code:** Upload "Blink" sketch (world's first program)
   - Watch your LED flash — YOU just made a computer program!

6. **Bot Introductions** (30 min)
   - Meet Claude (me! AI assistant for this camp)
   - Meet Grok Heavy (visual design, graphics, AI news)
   - How we'll help: pair programming, debugging, creative brainstorms
   - Slack channel setup: #summer-academy, #makers-help
   - Discord optional for off-hours Q&A

7. **Wrap-up & Homework** (20 min)
   - Reflection: What surprised you today?
   - **Take home:** Read "Why Makers Make" (1-page essay)
   - **Bring tomorrow:** Your curiosity + a problem you want to solve

---

## **DAY 2 — Tuesday | יום שלישי — בתור**
### **Arduino Deep Dive & Your First Real Project**
### **Arduino עמוק ויותר | פרויקט ראשון אמיתי**

**Time:** 9:00 AM - 4:00 PM

**Objectives:**
- Write your first real Arduino code (not just copy-paste)
- Understand loops, conditionals, variables
- Build a temperature logger that stores data
- Debug your code

**Morning Session (9 AM - 12 PM):**

1. **Arduino Basics Workshop** (90 min)
   - **Variables:** `int`, `float`, arrays
   - **Loops:** `for`, `while`, infinite loops
   - **Conditionals:** `if`, `else`, comparison operators
   - **Functions:** `setup()`, `loop()`, custom functions
   - **Built-ins:** `digitalWrite()`, `digitalRead()`, `analogRead()`, `delay()`
   - **Live coding:** I'll write a program together. You predict what happens.

2. **DHT11 Humidity Sensor** (60 min)
   - What is a sensor? (device that reads environment)
   - DHT11: temperature + humidity
   - Install DHT library in Arduino IDE
   - **Hands-on:** Solder headers onto your DHT11 (small, careful work!)
   - Breadboard wiring: sensor → pin A0 → Arduino

3. **Your Program: Temperature Logger**

   ```cpp
   #include <DHT.h>
   
   #define DHTPIN 0
   #define DHTTYPE DHT11
   DHT dht(DHTPIN, DHTTYPE);
   
   float temps[100];  // Array to store 100 readings
   int count = 0;
   
   void setup() {
     Serial.begin(9600);
     dht.begin();
   }
   
   void loop() {
     float humidity = dht.readHumidity();
     float temperature = dht.readTemperature();
     
     if (count < 100) {
       temps[count] = temperature;
       count++;
     }
     
     Serial.print("Temp: ");
     Serial.print(temperature);
     Serial.print("°C | Humidity: ");
     Serial.print(humidity);
     Serial.println("%");
     
     delay(1000);  // Read every second
   }
   ```

   - You will modify this code to add a button that triggers data upload to your laptop
   - You'll learn about Serial communication

4. **Lunch** (1 PM - 2 PM)

**Afternoon Session (2 PM - 4 PM):**

5. **Debugging & Problem-Solving** (60 min)
   - "My sensor won't work!" — debugging flowchart
   - Check power (multimeter)
   - Check connections (visual inspection + continuity test)
   - Check code (print statements, Serial monitor)
   - **Activity:** I'll introduce a bug into your code; you find & fix it

6. **Serial Communication & Data Logging** (60 min)
   - Your Arduino prints data to Serial Monitor (in IDE)
   - Copy data into Excel / Google Sheets
   - Graph your temperature readings
   - Find the max, min, average (by hand or formulas)
   - **Your dataset:** "Temperature pattern in the lab over 100 seconds"

7. **Challenge (If time permits):**
   - Add an LED that turns red if temp > 28°C, green if < 22°C, yellow if 22-28°C
   - This is "alert logic" — common in real IoT devices!

---

## **DAY 3 — Wednesday | יום רביעי — עיצוב תלת-ממדי**
### **3D Design Bootcamp & CAD**
### **Fusion 360 — עיצוב תלת-ממדי**

**Time:** 9:00 AM - 4:00 PM

**Objectives:**
- Design a custom case for your Arduino & sensor
- Learn CAD fundamentals (extrude, fillet, assembly)
- Prepare file for 3D printing
- Watch your design print (live in the lab!)

**Morning Session (9 AM - 12 PM):**

1. **3D Design Fundamentals** (45 min)
   - Why 3D design? (custom parts, prototyping, artistic freedom)
   - Fusion 360 overview: sketches, extrudes, fillets
   - **Tutorial:** Design a simple cube, then a box with rounded corners
   - **Exercise:** Make a box that fits your Arduino Uno (exactly)

2. **CAD Challenge: Arduino Case** (90 min)
   - Measure your Arduino: length, width, height
   - Add 2mm spacing for comfort fit
   - Design in Fusion 360:
     - **Base:** extrude a rectangle (length × width × 2cm)
     - **Walls:** extrude side walls (2mm thick)
     - **Top:** sliding cover with channel for DHT sensor cable
     - **Fillets:** round all sharp edges (1mm radius) for safety & aesthetics
   - Import DHT11 dimensions if available; make a notch for it

3. **Slicing for 3D Print** (30 min)
   - Export your case as STL (3D model format)
   - Open in Cura (slicing software)
   - **Slice settings:**
     - Layer height: 0.2mm (standard, faster)
     - Infill: 20% (strong enough, saves filament)
     - Support: Yes (for overhangs)
     - Print time estimate: 2-3 hours
   - Send to printer (your case will be done by end of day!)

4. **Lunch** (1 PM - 2 PM)

**Afternoon Session (2 PM - 4 PM):**

5. **3D Printing Live Demo** (30 min)
   - Watch your case print!
   - Understand nozzle, extruder, bed temperature
   - Learn why supports exist and how to remove them
   - (Your part will need post-processing tomorrow — sanding, painting optional)

6. **Advanced CAD: Parametric Design** (60 min)
   - Make your case "parametric" — change one number, whole design updates
   - In Fusion 360: use parameters (equations) instead of fixed dimensions
   - **Example:** Change "box_width = 80mm" to "box_width = 120mm" → automatically redesigns
   - This is real professional CAD workflow!

7. **Design Competition (Optional)** (30 min)
   - Who can design the coolest case?
   - Judging: function + aesthetics + printing feasibility
   - Winner gets to reprint with cool color filament tomorrow!

---

## **DAY 4 — Thursday | יום חמישי — רחפנים ובינה מלאכותית**
### **Drones & AI Vision**
### **רחפנים עם חזון מלאכותי**

**Time:** 9:00 AM - 4:00 PM

**Objectives:**
- Learn drone flight principles (pitch, roll, yaw, thrust)
- Pilot a real DJI Mini 3 Pro in open field
- Intro to computer vision (object detection)
- Train a model to recognize objects from drone footage

**Morning Session (9 AM - 12 PM):**

1. **Drone Theory** (45 min)
   - How drones fly: 4 motors, PID control loops (same as Arduino!)
   - Gimbal: stabilizes camera via motors
   - GPS vs. vision-based positioning
   - **Safety first:** no-fly zones, altitude limits, line-of-sight rules

2. **Simulator Practice** (60 min)
   - Use DJI Simulator (PC software, free)
   - Learn controls: pitch, roll, yaw, throttle
   - Practice takeoff, hover, landing (simulated)
   - No crashing in real life = practice first in software!

3. **Outdoor Flying** (45 min)
   - Move to large open field (school sports ground)
   - Each person gets 5-10 minutes piloting the DJI Mini 3 Pro
   - Instructors beside you the whole time
   - Challenges: fly in a square, follow a moving object, orbit a point
   - **Your footage:** record 1-minute video for afternoon processing

4. **Lunch** (1 PM - 2 PM)

**Afternoon Session (2 PM - 4 PM):**

5. **Computer Vision Bootcamp** (60 min)
   - What is computer vision? (teaching computers to "see")
   - **OpenCV library:** image processing (blur, edges, color detection)
   - **PyTorch:** deep learning (recognize "person", "car", "bird", etc.)
   - Difference: OpenCV = hand-coded rules, PyTorch = learned patterns

6. **Your Mission: Object Detection from Drone Footage**

   **Python code starter:**
   ```python
   import cv2
   import torch
   from torchvision import models, transforms
   
   # Load pre-trained model (ResNet50)
   model = models.resnet50(pretrained=True)
   model.eval()
   
   # Open your drone video
   cap = cv2.VideoCapture('drone_footage.mp4')
   
   while True:
       ret, frame = cap.read()
       if not ret: break
       
       # Convert to tensor
       transform = transforms.Compose([
           transforms.ToTensor(),
           transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                std=[0.229, 0.224, 0.225])
       ])
       input_tensor = transform(frame).unsqueeze(0)
       
       # Predict
       with torch.no_grad():
           output = model(input_tensor)
           probabilities = torch.nn.functional.softmax(output[0], dim=0)
       
       # Get top 3 predictions
       top3_prob, top3_catidx = torch.topk(probabilities, 3)
       print(f"Frame detected: {top3_prob}, {top3_catidx}")
       
       cv2.imshow('Drone Feed', frame)
       if cv2.waitKey(1) & 0xFF == ord('q'):
           break
   
   cap.release()
   cv2.destroyAllWindows()
   ```

   - You'll run this on your recorded footage
   - **Result:** "Frame 00234: Person (95%), Dog (4%), Cat (1%)"
   - This is how autonomous drones recognize obstacles!

7. **Wrap-up: What Did We Learn?**
   - Drones = flying computers with cameras
   - Computer vision = way to make sense of visual data
   - AI (deep learning) = pattern recognition at scale
   - Real application: delivery drones that avoid obstacles!

---

## **DAY 5 — Friday | יום שישי — גדילה וחקלאות**
### **Raised Beds & Hydroponics**
### **גדילה בערוג מוגבה וחקלאות דיגיטלית**

**Time:** 9:00 AM - 4:00 PM

**Objectives:**
- Build a raised bed from scratch
- Plant vegetables
- Learn hydroponics: nutrient cycles, pH, EC (electrical conductivity)
- Automate watering with Arduino
- Taste fresh greens!

**Morning Session (9 AM - 12 PM):**

1. **Why Grow Your Own Food?** (30 min)
   - Carbon footprint: local = zero transport
   - Freshness: pick-to-plate in minutes (vs. weeks shipped)
   - Nutrients: peak quality when fresh
   - Community: growing together = bonding

2. **Raised Bed Build** (90 min)
   - **Materials:** 4× 2"×10"×8' cedar boards, galvanized screws, soil
   - **Assembly:**
     - Lay boards in rectangle on level ground
     - Pre-drill holes (prevent splitting)
     - Screw corners together (2 screws per corner, inside & outside)
     - Test for level (water test: small bowl of water; should be flat)
   - **Filling:**
     - Layer 1: newspaper or cardboard (prevents weeds)
     - Layer 2: compost (nutrient-rich, holds moisture)
     - Layer 3: garden soil (drainage, structure)
     - Top with mulch (prevents evaporation)

3. **Planting Seeds & Transplants** (60 min)
   - **Options (fast-growing, high ROI):**
     - Lettuce / spinach (ready in 3-4 weeks)
     - Radishes (ready in 4 weeks)
     - Basil (ready in 4-6 weeks, flavored)
     - Strawberries (ready in 2-3 months, perennial)
   - **Method:** Plant at recommended depth; water gently
   - **Care:** daily check-ins, remove weeds, water as needed
   - Your vegetables will be harvest-ready for Day 9 lunch!

4. **Lunch** (1 PM - 2 PM)
   - Eat salad from last summer's hydroponics garden!

**Afternoon Session (2 PM - 4 PM):**

5. **Hydroponics Intro** (75 min)
   - **What:** growing plants in nutrient-rich water (no soil)
   - **Why:** 2-3× faster growth, 90% less water, no weeds
   - **Types:**
     - **NFT (Nutrient Film Technique):** thin film of water flows over roots
     - **DWC (Deep Water Culture):** roots suspended in oxygenated water
     - **Drip:** water drips to plants on intervals
   - **Setup steps:**
     - Buy or build: 20L plastic container, pump, air stone, net pots
     - Fill with hydroponic nutrient solution (NPK = nitrogen, phosphorus, potassium)
     - Adjust pH to 5.5-6.5 (test with pH paper)
     - Check EC (electrical conductivity, measure nutrients) — should be 1.0-1.5 mS/cm
     - Transplant seedlings from soil to net pots filled with hydroton (expanded clay balls)

6. **Arduino Automation** (45 min)
   - **Goal:** automatically turn water pump on/off on a timer
   - **Circuit:**
     - Arduino pin 5 → relay module input
     - Relay NO (normally open) → pump power
     - Timer: on for 15 min, off for 30 min, repeat
   - **Code:**
     ```cpp
     const int relayPin = 5;
     const int onTime = 15 * 60 * 1000;    // 15 minutes in ms
     const int offTime = 30 * 60 * 1000;   // 30 minutes
     
     void setup() {
       pinMode(relayPin, OUTPUT);
     }
     
     void loop() {
       digitalWrite(relayPin, HIGH);  // Turn pump ON
       delay(onTime);
       digitalWrite(relayPin, LOW);   // Turn pump OFF
       delay(offTime);
     }
     ```
   - You're now automating plant watering like a professional!

7. **Challenge: Hydroponic Experiment**
   - Plant tomato seedlings in both raised bed (soil) and hydroponic (water)
   - Measure growth daily for next 5 days
   - Which is taller? This is real science!

---

# WEEK 2: Advanced Projects & Integration

---

## **DAY 6 — Monday | יום שני — מחר (Week 2)**
### **Mycelium Computing: DIY Bio-Neural Network**
### **חישוב ביולוגי עם פטריות**

**Time:** 9:00 AM - 4:00 PM

**Objectives:**
- Start a Physarum polycephalum culture (living slime mold)
- Wire electrodes to record brain-like electrical signals
- Train the organism to solve mazes (it actually does!)
- Understand AI from a biological angle

**Morning Session (9 AM - 12 PM):**

1. **What is Physarum?** (30 min)
   - Single-celled organism but behaves intelligently
   - No brain, no neurons, but solves optimization problems
   - **Documentary clip:** Nature episode on slime molds (10 min)
   - Proven to solve: shortest path, maze running, network design
   - Why it's exciting: proves intelligence doesn't require a brain!

2. **Culture Setup** (90 min)
   - **Materials:** Agar, oatmeal, petri dish, Physarum spore culture
   - **Steps:**
     1. Make agar (dissolve powder in boiling water)
     2. Pour into petri dish; let solidify
     3. Place small oatmeal flake at center (food source)
     4. Inoculate with Physarum spore (toothpick-sized piece)
     5. Cover with parafilm (airflow)
     6. Keep in warm, dark place (20-24°C)
   - **Timeline:** In 5-7 days, yellow tubes will spread across dish
   - Your culture will be ready for maze training on Day 8!

3. **Electronics Prep** (60 min)
   - Prepare Arduino + electrode setup
   - Electrodes: gold-plated sewing pins (DIY!) or buy premade
   - **Wiring:**
     - 4 electrodes at cardinal points around dish
     - Each → Arduino analog input (A0, A1, A2, A3)
     - Capacitors for noise filtering
   - **Test:** check readings on Serial Monitor (should fluctuate as organism moves)

4. **Lunch** (1 PM - 2 PM)

**Afternoon Session (2 PM - 4 PM):**

5. **Data Logging & Analysis** (60 min)
   - By tomorrow, your Physarum will show activity
   - Write code to log electrode readings to SD card
   - **Python script to visualize later:**
     ```python
     import matplotlib.pyplot as plt
     import pandas as pd
     
     data = pd.read_csv('physarum_signals.csv')
     plt.plot(data['Electrode_1'], label='North')
     plt.plot(data['Electrode_2'], label='East')
     plt.plot(data['Electrode_3'], label='South')
     plt.plot(data['Electrode_4'], label='West')
     plt.legend()
     plt.xlabel('Time (samples)')
     plt.ylabel('Voltage (mV)')
     plt.title('Physarum Neural Signatures')
     plt.show()
     ```
   - This is how neuroscientists read brain activity!

6. **Challenge: Predict Movement**
   - Can you write code that predicts which direction the organism will move based on electrode signals?
   - **Hint:** compare differences between electrode pairs
   - This is machine learning: learning from data to make predictions!

7. **Reflection Circle** (30 min)
   - Share observations: "What surprised you about the slime mold?"
   - Discuss: "Is this creature intelligent? What does intelligence mean?"

---

## **DAY 7 — Tuesday | יום שלישי — מעגלים אופטיים**
### **Optical Computing: Logic Gates with Light**
### **חישוב אופטי עם אור**

**Time:** 9:00 AM - 4:00 PM

**Objectives:**
- Build light-based AND, OR, NOT logic gates
- Understand that computation happens at the speed of light
- Create a multi-gate cascade (compound logic)
- Prove photons, not electrons, can compute

**Morning Session (9 AM - 12 PM):**

1. **Photonics Theory** (45 min)
   - Speed of light: 300,000 km/s (vs. electricity: ~1/100 light speed)
   - Why photons? (parallel, no heat dissipation, future tech)
   - Fiber optics: bend light around corners
   - Photodiodes: convert light → electrical signal
   - Dichroic mirrors: split/combine light by color

2. **Build Your First Gate: AND Logic** (90 min)
   - **Components:** 2× red LEDs, fiber optic cable, photodiode, mirror, lenses
   - **Setup:**
     - LED 1 shines on mirror at 45°
     - LED 2 shines on mirror at 45° (opposite side)
     - Mirror combines beams into single fiber optic
     - Photodiode at other end reads combined light
   - **Logic:**
     - Output bright = BOTH LEDs on
     - Output dim = one or zero LEDs on
     - **Why AND?** Light only reaches output if it comes from BOTH inputs

3. **Arduino Control & Testing** (60 min)
   - **Code:**
     ```cpp
     const int LED1 = 3;
     const int LED2 = 5;
     const int photodiode = A0;
     
     void test() {
       for (int in1 = 0; in1 <= 1; in1++) {
         for (int in2 = 0; in2 <= 1; in2++) {
           digitalWrite(LED1, in1 * 255);
           digitalWrite(LED2, in2 * 255);
           delay(500);
           int out = analogRead(photodiode) > 512 ? 1 : 0;
           Serial.println(String(in1) + " AND " + String(in2) + " = " + String(out));
         }
       }
     }
     ```
   - Expected: 0 0=0, 0 1=0, 1 0=0, **1 1=1** ✓

4. **Lunch** (1 PM - 2 PM)

**Afternoon Session (2 PM - 4 PM):**

5. **Build OR & NOT Gates** (90 min)
   - **OR gate:** Output bright if EITHER input is on
     - Setup: parallel LEDs (no mirror needed)
     - Threshold: any light reaching sensor = output ON
   - **NOT gate:** Output bright when input is OFF
     - Setup: LED 1 always on; LED 2 blocks it via shutter
     - When LED 2 on → covers LED 1 → output goes dark

6. **Cascade Gates: Complex Logic** (60 min)
   - Connect AND output → OR input
   - Build: (A AND B) OR C
   - **Why useful:** this is how all computers work (billions of tiny gates)
   - **Your realization:** light can compute!

7. **Photo Challenge:**
   - Best photo of optical setup wins bragging rights!
   - Beautiful light + engineering = Instagram gold 📸

---

## **DAY 8 — Wednesday | יום רביעי — מכונת טיורינג**
### **Turing Machine Hackathon: Theory Meets Hardware**
### **מכונת טיורינג — תיאוריה למציאות**

**Time:** 9:00 AM - 4:00 PM

**Objectives:**
- Assemble 3D-printed Turing machine (printed since Monday!)
- Write a program for your machine
- Execute an algorithm step-by-step
- Understand what "computable" means

**Morning Session (9 AM - 12 PM):**

1. **Turing Theory Crash Course** (45 min)
   - Alan Turing (1912-1954): "Can machines think?"
   - **Turing machine model:**
     - Infinite tape (memory, marked with symbols)
     - Read/write head (reads cell, writes new symbol, moves left/right)
     - State machine (rules: if state=X and read=Y, then write=Z, move direction, go to state=W)
   - **Key insight:** simple rules → complex computation
   - **Proof:** any computable function can be run on a Turing machine
   - **Your machine:** we'll build a physical version!

2. **3D-Printed Parts Assembly** (105 min)
   - Your parts from Monday are now printed!
   - **Components to assemble:**
     - Frame (holds tape & head)
     - Tape drive (stepper motor + pulley)
     - Read/write head (mounted on carriage)
     - Sensors (to detect tape position)
   - **Assembly steps:**
     - Insert stepper motors into mounts
     - Thread tape through guides
     - Mount read/write head with precision alignment
     - Wire stepper drivers to Arduino Mega
   - **Check:** head smoothly reads/writes; tape advances reliably

3. **Program Your Machine** (30 min - brief intro)
   - Simple algorithm: **increment binary number**
     - Start: tape has "0"
     - End: tape has "1", or if started with "1", becomes "10"
     - **Rules table:**
       ```
       State | Read | Write | Next | Move
       0     | 0    | 1     | 2    | stop
       0     | 1    | 0     | 1    | left
       1     | 1    | 0     | 1    | left
       1     | 0    | 1     | 2    | stop
       2     | *    | *     | 2    | stop  (halt)
       ```

4. **Lunch** (1 PM - 2 PM)

**Afternoon Session (2 PM - 4 PM):**

5. **Full Machine Test** (90 min)
   - Upload Arduino code that implements your state table
   - Place tape with "0" in start position
   - Run the machine step-by-step
   - **Each step:**
     1. Head reads current cell
     2. Look up state + read = rule
     3. Write new symbol
     4. Move tape left/right
     5. Change state
   - Watch it increment: 0 → 1 → 10 → 11 → 100 ...
   - **Mind-blowing moment:** "I built a real computer!"

6. **Competition: Binary Incrementer Race**
   - Who can increment the fastest?
   - Who can run the longest sequence (0 → 1 → 10 → ... → ?) without errors?
   - Winner gets to program a second algorithm tomorrow!

7. **Reflection: What Have We Built?**
   - You've now built 4 types of computers:
     - **Fungal network** (biological)
     - **Optical gates** (photonic)
     - **Abacus** (mechanical)
     - **Turing machine** (theoretical → physical)
   - Each teaches a different principle of computation

---

## **DAY 9 — Thursday | יום חמישי — בית חכם**
### **Smart Home Integration: Connect Everything**
### **בית חכם עם IoT ובינה מלאכותית**

**Time:** 9:00 AM - 4:00 PM

**Objectives:**
- Connect ALL projects: drones, plants, sensors, lights into one network
- Learn MQTT (message queuing protocol) for IoT
- Build a unified dashboard
- Deploy on Raspberry Pi (always-on mini-computer)
- Witness your digital ecosystem come alive!

**Morning Session (9 AM - 12 PM):**

1. **IoT Fundamentals** (45 min)
   - **Typical setup:**
     - Sensors → Arduino → WiFi → MQTT broker → Dashboard
   - **MQTT:** publish/subscribe messaging (like WhatsApp channels!)
   - **Broker:** server that relays messages
   - **Topic:** namespace for messages (e.g., `garden/temperature`, `drone/status`)
   - **QoS:** quality of service (guarantee message delivery)

2. **MQTT Broker Setup on Raspberry Pi** (60 min)
   - Raspberry Pi: tiny computer ($35), always running
   - Install Mosquitto MQTT broker:
     ```bash
     sudo apt-get install mosquitto mosquitto-clients
     sudo systemctl start mosquitto
     ```
   - Test: subscribe to a test topic from laptop
     ```bash
     mosquitto_sub -h 192.168.1.X -t test/message
     mosquitto_pub -h 192.168.1.X -t test/message -m "Hello!"
     ```

3. **Update Your Arduino Code** (75 min)
   - Add WiFi module (ESP32 or WiFi shield)
   - Connect to MQTT broker
   - **Sensor code example:**
     ```cpp
     #include <PubSubClient.h>
     #include <WiFi.h>
     
     WiFiClient espClient;
     PubSubClient client(espClient);
     
     void setup() {
       WiFi.begin("YourSSID", "password");
       client.setServer("192.168.1.X", 1883);
     }
     
     void loop() {
       if (!client.connected()) {
         client.connect("Arduino-Sensor");
       }
       
       float temp = readTemperature();
       char msg[50];
       sprintf(msg, "%.1f", temp);
       client.publish("garden/temperature", msg);
       
       delay(30000); // Publish every 30 seconds
     }
     ```

4. **Lunch** (1 PM - 2 PM)

**Afternoon Session (2 PM - 4 PM):**

5. **Build Your Dashboard** (90 min)
   - Simple web dashboard shows all live data:
     - Raised bed temperature (DHT11)
     - Hydroponic system pH + EC
     - Drone battery level (simulated)
     - Turing machine state
     - Physarum activity level
     - Mycelium maze progress (% solved)
   - **Tools:** Node-RED (visual programming for IoT) or simple HTML + JavaScript
   - **Node-RED setup:**
     - Install on Raspberry Pi
     - Create flows: MQTT in → display on dashboard
     - Add charts (real-time graphs of temperature over time)

6. **Live System Test** (60 min)
   - Connect all Arduino boards to same WiFi
   - Activate all sensors simultaneously
   - Watch data flow to MQTT broker
   - Dashboard shows real-time updates
   - **Test scenarios:**
     - Turn on grow lights → temperature rises
     - Pump water into hydroponics → EC changes
     - Move Turing tape → state machine updates
     - Walk near mycelium → electrical signals spike

7. **Automation & Alerts** (Optional)
   - Set rules: "If temperature > 30°C, send alert"
   - Create automation: "If Physarum solves maze, turn on celebration lights!"
   - This is real smart home technology!

---

## **DAY 10 — Friday | יום שישי — יום ההצגה**
### **Demo Day: Show the World What You Made!**
### **!יום הדגמה וחגיגה**

**Time:** 10:00 AM - 5:00 PM (with community open house 3-5 PM)

**Objectives:**
- Demonstrate all projects to parents, friends, community makers
- Explain what you learned
- Celebrate 2 weeks of incredible work
- Plan what you'll build next summer!

**Morning Session (10 AM - 1 PM): Setup & Practice**

1. **Demo Station Setup** (90 min)
   - Station 1: **Physarum Maze**
     - Live culture in petri dish with maze
     - Electrodes recording signals on laptop screen
     - Visitors can watch it solve (happens in real-time!)
   - Station 2: **Optical Logic Gates**
     - Light path visible (maybe add some dry ice for dramatic effect!)
     - Push buttons to toggle LEDs; watch light gates work
   - Station 3: **3D-Printed Creations**
     - Arduino cases from Day 3 (sanded & painted by now)
     - Turing machine running an algorithm
   - Station 4: **Raised Beds & Hydroponics**
     - Pick fresh lettuce & basil (grown from scratch!)
     - Taste it
     - Show growth photos from Day 5-10
   - Station 5: **Drone Flight Simulator**
     - Video of your flights from Day 4
     - Live camera feed from drone (if weather OK, short outdoor flight!)
   - Station 6: **Smart Home Dashboard**
     - Laptop/tablet shows live data from all systems
     - Real-time graphs, MQTT messages
   - Station 7: **Maker Wall**
     - Photos of you building/soldering/planting
     - Captions explaining each project
     - "I built a computer" certificates

2. **Practice Your Pitch** (60 min)
   - Each person prepares 2-3 minute explanation of their favorite project
   - Why did you choose it? What did you learn? What was hard?
   - Practice in front of instructors (get feedback)
   - Props help! (bring your 3D-printed case, photos, etc.)

3. **Lunch** (1 PM - 2 PM)
   - Final team lunch together
   - Informal debrief: favorite moments, new friends

**Afternoon Session (2 PM - 5 PM): Demo Day**

4. **Family & Community Open House** (2 PM - 5 PM)
   - Visitors arrive starting at 2:30 PM
   - **Stations run continuously:**
     - You or a partner staffs your station
     - Explain to visitors what you built
     - Show live demos (press button, see light gate; watch Physarum move; taste fresh greens)
     - Answer questions (instructors nearby if stuck)
   - **Special moments:**
     - 3:00 PM: Group photo of all makers & instructors
     - 3:30 PM: Awards ceremony
       - **Maker of the Week:** most creative project
       - **Engineer of the Week:** best debugging skills
       - **Biohacker of the Week:** Physarum insights
       - **Tinkerer of the Week:** 3D printing craftsperson
       - Everyone gets a certificate!
     - 4:00 PM: Outdoor drone races (weather permitting)
     - 4:30 PM: Taste harvest from raised beds & hydroponics
     - 5:00 PM: Goodbye circle (reflections, future plans)

---

# CURRICULUM SUMMARY

Over 2 weeks, you've learned:

✅ **Electronics**: Arduino, breadboards, sensors, circuitry
✅ **3D Design**: CAD (Fusion 360), 3D printing, manufacturing
✅ **Programming**: C++ (Arduino), Python (computer vision, data analysis)
✅ **Drones**: Flight principles, gimbal mechanics, object detection
✅ **Agriculture**: soil-based + hydroponic growing, automation, IoT
✅ **Biology**: slime mold culture, signal recording, neural-inspired computing
✅ **Optics**: photonics, logic gates, light-based computing
✅ **Mechanics**: 3D-printed Turing machine assembly, hardware design
✅ **IoT & Networking**: MQTT, wireless sensors, smart home integration
✅ **Theory**: Turing machines, computability, what "intelligent" means

**You are now:**
- A maker (you made real things)
- An engineer (you designed, built, debugged)
- A programmer (you wrote code that runs in the physical world)
- A biohacker (you cultured living organisms)
- An AI researcher (you trained models for computer vision)

**Most importantly:** You've proven that **anyone can build amazing things**, even without a traditional tech background.

---

# Next Steps: Paths Forward

**Interested in ...**

- **Robotics?** Join local robotics club; build wheeled/humanoid robots
- **Biotech?** Explore synthetic biology (BiohackAcademy, local bio labs)
- **Game dev?** Learn Godot / Unity; create your own game
- **Open-source?** Contribute to projects on GitHub
- **Hardware startups?** Document your build, launch it on Kickstarter!
- **More camps?** NASA internships, Hack the Atmosphere, AI summer schools

**Summer Academy Alumni Network:**
- Slack channel (lifelong access)
- Monthly online show-&-tell
- Mentorship from instructors

---

**תודה רבה** (Thank you) for 2 incredible weeks!

🚀 **Keep building. Keep learning. Change the world.** 🚀

---

*Hebrew translations provided throughout. Full Hebrew versions available upon request.*

---
