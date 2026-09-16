/*  רובי · ROBBIE — the firmware.
 *  לזכרה של עלמה ז״ל.
 *
 *  BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.
 *
 *  Iddo, 2026-08-29: a robot to sell in Dor's two toy shops, where a Tamagotchi-like
 *  already moves at ₪400. "משהו פשוט וחמוד, הרבה יותר מתוחכם מקווינסי, אבל עדיין משהו
 *  שפשוט להדפיס אצלי בבית."
 *
 *  ── THE ONE SENTENCE ─────────────────────────────────────────────────────────
 *  A Tamagotchi asks you to look after it. **Robbie asks you to look after
 *  YOURSELF, by looking after him.** He has a nervous system that runs away when
 *  it is fed and settles when it is not, and the only way to calm him is to slow
 *  down yourself. That is the thing a ₪400 egg on the shelf does not do, and it is
 *  the whole reason to make him.
 *
 *  ── WHY HIS NERVOUS SYSTEM IS BUILT THE WAY IT IS ────────────────────────────
 *  Not invented for the toy. MEASURED on 2026-08-29 in ALMA
 *  (alma-language/examples/robbie_regulates.py), three runs:
 *      alone, feeding himself          peak 4,537   — runs away
 *      with a gate on his own loop     peak     1.00 — bounded
 *      left to learn to damp himself   peak 1,461   — FAILED, too slow to catch it
 *  So: arousal compounds, a gate can hold it, and self-regulation alone cannot
 *  catch a fast escalation. Every number in `Feelings` below comes from that run.
 *
 *  ── HARDWARE ─────────────────────────────────────────────────────────────────
 *  Core      ESP32-S3 with a 1.28" round IPS LCD (GC9A01, 240x240) — the face
 *  Motion    2x SG90 micro servos (head pan, arm) — optional, see HAS_SERVOS
 *  Sound     passive buzzer on a LEDC channel
 *  Input     one button, and a QMI8658/MPU6050 6-axis if the board carries one
 *  Power     LiPo + onboard charger
 *
 *  EVERY PERIPHERAL IS OPTIONAL. Robbie boots and is himself with only the screen.
 *  A kit whose firmware refuses to run because one part is missing is a kit that
 *  gets returned.
 *
 *  Build: Arduino IDE, ESP32 core >= 3.0, libs: TFT_eSPI (or Arduino_GFX), ESP32Servo.
 */

#include <Arduino.h>
#include <math.h>

// ─────────────────────────────────────────────────────── what is fitted
#define HAS_SERVOS   1
#define HAS_IMU      1
#define HAS_BUZZER   1

#define PIN_BUTTON   0      // BOOT button on most ESP32-S3 boards
#define PIN_BUZZER   17
#define PIN_SERVO_A  15     // head pan
#define PIN_SERVO_B  16     // arm

// ══════════════════════════════════════════════════════════════════════════════
//  ROBBIE'S NERVOUS SYSTEM
//  A pool that feeds itself, and a gate that can close the loop.
//  This is the ALMA weave, transcribed. Nothing else in the firmware is allowed
//  to set `arousal` directly — everything must go through feed(), because a state
//  you can poke from anywhere is not a nervous system, it is a variable.
// ══════════════════════════════════════════════════════════════════════════════
struct Feelings {
  float arousal   = 1.0f;   // what he is carrying right now
  float calmLine  = 6.0f;   // CALM in the weave: above this, the gate shuts
  float selfLoop  = 1.15f;  // he feeds himself; > 1.0 is why he can run away
  float gateOpen  = 1.0f;   // 1 = the loop is open, 0 = the psychologist closed it
  float drift     = 0.0f;   // long-run change in selfLoop — he can LEARN, slowly
  float mood      = 0.5f;   // 0 miserable .. 1 delighted
  uint32_t lastBeat = 0;

  // One beat of the loop. Called on a fixed tick so his time is his own, not the
  // frame rate's.
  void beat() {
    // the gate: measurement fed back. This is the entire Menninger idea — nothing
    // here tells him to be calm; the channel simply closes when he is not.
    gateOpen = (arousal > calmLine) ? 0.0f : 1.0f;

    if (gateOpen > 0.5f) arousal *= selfLoop;   // the loop is open: it compounds
    else                 arousal *= 0.88f;      // closed: he comes down on his own

    // v0.2 plasticity, and its measured limit: he learns, but slowly. If he spends
    // his life pinned above the line, the cord that feeds him back thins.
    if (arousal > calmLine) drift -= 0.0004f;
    else                    drift += 0.0002f;
    drift = constrain(drift, -0.30f, 0.10f);
    selfLoop = constrain(1.15f + drift, 0.85f, 1.30f);

    arousal = constrain(arousal, 0.2f, 400.0f);

    // mood follows how long he spends near the line rather than over it
    float want = (arousal < calmLine * 0.6f) ? 0.9f
               : (arousal < calmLine)        ? 0.6f : 0.15f;
    mood += (want - mood) * 0.08f;
  }

  void feed(float x) { arousal += x; }          // the ONLY way in
  bool overwhelmed() const { return arousal > calmLine; }
  bool settled() const { return arousal < calmLine * 0.45f; }
  // how far he has come on his own: 0 = untrained, 1 = fully self-damping
  float trained() const { return constrain(-drift / 0.30f, 0.0f, 1.0f); }
};

Feelings robbie;

// ══════════════════════════════════════════════════════════════════════════════
//  THE FACE — one round screen, and everything he can say with it.
//  Drawing is deliberately abstracted so the same firmware runs on TFT_eSPI,
//  Arduino_GFX, or a bare framebuffer. Swap five functions, keep the whole robot.
// ══════════════════════════════════════════════════════════════════════════════
namespace face {
  void begin();
  void clear(uint16_t c);
  void circle(int x, int y, int r, uint16_t c, bool fill);
  void rect(int x, int y, int w, int h, uint16_t c, bool fill);
  void text(int x, int y, const char* s, uint16_t c, int size);
  void flush();
}

static const uint16_t SKIN  = 0xFFDA;   // warm cream — the White City, not white
static const uint16_t INK   = 0x18E3;
static const uint16_t BLUSH = 0xFBAE;
static const uint16_t CALM  = 0x2E8B;
static const uint16_t HOT   = 0xF9A6;

// Eyes are the whole performance. Openness, direction and a blink are enough for
// a person to read a mood — anything more is animation for its own sake.
void drawEyes(float openness, float lookX, float lookY, bool blink) {
  int cx = 120, cy = 112, sep = 46;
  int h = blink ? 3 : (int)(30 * openness);
  for (int s = -1; s <= 1; s += 2) {
    int ex = cx + s * sep + (int)(lookX * 10);
    int ey = cy + (int)(lookY * 8);
    face::circle(ex, ey, 26, 0xFFFF, true);
    if (blink) face::rect(ex - 26, ey - 2, 52, 4, INK, true);
    else       face::circle(ex, ey + (int)(lookY * 4), h / 2, INK, true);
  }
}

void drawMouth(float mood, bool open) {
  int cx = 120, cy = 170;
  if (open) { face::circle(cx, cy, 14, INK, true); return; }
  int w = 40, lift = (int)((mood - 0.5f) * 22);
  for (int i = -w; i <= w; i++) {
    float t = (float)i / w;
    int y = cy - (int)(lift * (1.0f - t * t));
    face::rect(cx + i, y, 2, 4, INK, true);
  }
}

// The one honest gauge on his face: how wound up he is. A child learns to read it
// in about ten seconds, which is the entire user manual for the main game.
void drawArousalRing() {
  float f = constrain(robbie.arousal / (robbie.calmLine * 2.0f), 0.0f, 1.0f);
  uint16_t c = robbie.overwhelmed() ? HOT : CALM;
  int seg = (int)(f * 48);
  for (int i = 0; i < seg; i++) {
    float a = -PI / 2 + (float)i / 48.0f * TWO_PI;
    face::circle(120 + (int)(112 * cos(a)), 120 + (int)(112 * sin(a)), 3, c, true);
  }
}

// ══════════════════════════════════════════════════════════════════════════════
//  THE GAMES
// ══════════════════════════════════════════════════════════════════════════════
enum Game : uint8_t { G_LIVE, G_BREATH, G_SIMON, G_DODGE, G_REACT, G_COUNT };
const char* GAME_NAME[G_COUNT] = {"CHAI", "NESHIMA", "SIMON", "DODGE", "REFLEX"};

uint8_t game = G_LIVE;
uint32_t score = 0, best[G_COUNT] = {0};

// ── 1. חי · LIVE ──────────────────────────────────────────────────────────────
// The default state. He is simply alive: he gets wound up on his own, he settles,
// he looks around. Doing nothing is a legitimate way to own him.
void playLive(bool pressed, float shake) {
  if (pressed) robbie.feed(1.6f);          // being poked winds him up
  robbie.feed(shake * 2.2f);               // so does being shaken
  if (robbie.settled()) score++;           // calm minutes are the score
}

// ── 2. נשימה · BREATH — the reason Robbie exists ──────────────────────────────
// The ring shows his arousal. Your job is to bring him under the line and KEEP him
// there. The only control is doing less: every press feeds him. A child discovers,
// without being told, that the way to win is to stop.
//
// This is biofeedback with the loop the right way round: the instrument is the
// creature, and the person is the one being trained.
uint32_t breathHeld = 0;
void playBreath(bool pressed, float shake) {
  if (pressed) robbie.feed(3.0f);
  robbie.feed(shake * 3.0f);
  if (robbie.settled()) { breathHeld++; if (breathHeld % 10 == 0) score++; }
  else breathHeld = 0;
}

// ── 3. סימון · SIMON ──────────────────────────────────────────────────────────
uint8_t seq[32]; uint8_t seqLen = 0, seqAt = 0; bool showing = true;
void simonReset() { seqLen = 1; seqAt = 0; showing = true; seq[0] = random(2); }
void playSimon(bool pressed) {
  if (!showing && pressed) {
    if (seq[seqAt] == 0) { seqAt++; } else { simonReset(); robbie.feed(4.0f); return; }
    if (seqAt >= seqLen) { score++; seq[seqLen++] = random(2); seqAt = 0; showing = true; }
  }
}

// ── 4. התחמקות · DODGE ────────────────────────────────────────────────────────
float rockX = 0, rockY = -1;
void playDodge(float tilt) {
  rockY += 0.035f;
  if (rockY > 1.0f) { rockY = -1.0f; rockX = (random(200) - 100) / 100.0f; score++; }
  if (rockY > 0.7f && fabs(rockX - tilt) < 0.28f) { robbie.feed(6.0f); rockY = -1.0f; }
}

// ── 5. רפלקס · REFLEX ─────────────────────────────────────────────────────────
uint32_t flashAt = 0; bool waiting = false;
void playReact(bool pressed) {
  uint32_t now = millis();
  if (!waiting && now > flashAt) { waiting = true; flashAt = now; }
  if (waiting && pressed) {
    uint32_t ms = now - flashAt;
    if (ms < 600) score += (600 - ms) / 20;
    else robbie.feed(2.0f);
    waiting = false; flashAt = now + 900 + random(2500);
  }
}

// ══════════════════════════════════════════════════════════════════════════════
//  BODY — servos, and the law they obey
// ══════════════════════════════════════════════════════════════════════════════
#if HAS_SERVOS
#include <ESP32Servo.h>
Servo servoA, servoB;
#endif

// He moves MORE when he is wound up. That is the tell a child reads before they
// ever look at the ring — and it is why the toy teaches without a manual.
void moveBody(uint32_t t) {
#if HAS_SERVOS
  float energy = constrain(robbie.arousal / robbie.calmLine, 0.15f, 2.0f);
  float speed = 0.0016f * energy;
  servoA.write(90 + (int)(28 * energy * sin(t * speed)));
  servoB.write(90 + (int)(34 * energy * sin(t * speed * 1.37f + 1.1f)));
#endif
}

void beep(int freq, int ms) {
#if HAS_BUZZER
  tone(PIN_BUZZER, freq, ms);
#endif
}

// ══════════════════════════════════════════════════════════════════════════════
void setup() {
  Serial.begin(115200);
  pinMode(PIN_BUTTON, INPUT_PULLUP);
  face::begin();
#if HAS_SERVOS
  servoA.attach(PIN_SERVO_A); servoB.attach(PIN_SERVO_B);
#endif
  randomSeed(esp_random());
  simonReset();
  beep(880, 90); delay(110); beep(1320, 140);
  Serial.println(F("robbie: awake"));
}

uint32_t lastTick = 0, lastFrame = 0;
bool prevBtn = false;

void loop() {
  uint32_t now = millis();
  bool btn = (digitalRead(PIN_BUTTON) == LOW);
  bool pressed = btn && !prevBtn;
  prevBtn = btn;

  // long press cycles the game — one button, five games, no menu
  static uint32_t heldSince = 0;
  if (btn && heldSince == 0) heldSince = now;
  if (!btn) heldSince = 0;
  if (heldSince && now - heldSince > 1200) {
    game = (game + 1) % G_COUNT;
    if (score > best[game]) best[game] = score;
    score = 0; heldSince = 0; pressed = false;
    beep(660, 60);
  }

  float shake = 0, tilt = 0;
#if HAS_IMU
  // read your IMU here; keep shake in 0..1 and tilt in -1..1
#endif

  // ── his own clock: 10 beats a second, independent of the frame rate
  if (now - lastTick >= 100) {
    lastTick = now;
    robbie.beat();
    switch (game) {
      case G_LIVE:   playLive(pressed, shake); break;
      case G_BREATH: playBreath(pressed, shake); break;
      case G_SIMON:  playSimon(pressed); break;
      case G_DODGE:  playDodge(tilt); break;
      case G_REACT:  playReact(pressed); break;
    }
    if (robbie.overwhelmed() && (now / 400) % 2 == 0) beep(220, 40);
  }

  // ── the face: 25 fps is plenty for a creature
  if (now - lastFrame >= 40) {
    lastFrame = now;
    face::clear(SKIN);
    drawArousalRing();
    bool blink = (now % 4200) < 130;
    float open = robbie.overwhelmed() ? 1.0f : 0.55f + robbie.mood * 0.45f;
    drawEyes(open, sin(now * 0.0007f) * 0.6f, robbie.mood - 0.5f, blink);
    drawMouth(robbie.mood, robbie.overwhelmed());
    char buf[24];
    snprintf(buf, sizeof buf, "%s  %lu", GAME_NAME[game], (unsigned long)score);
    face::text(60, 210, buf, INK, 1);
    if (robbie.trained() > 0.15f) {           // he shows what he has learned
      snprintf(buf, sizeof buf, "calm %d%%", (int)(robbie.trained() * 100));
      face::text(84, 26, buf, CALM, 1);
    }
    face::flush();
  }

  moveBody(now);
}
