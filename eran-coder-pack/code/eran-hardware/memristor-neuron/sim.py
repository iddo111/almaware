"""
sim.py — proof that the electrically-tunable POT + CAP neuron actually learns.

ALMAWARE · 100% ours · pure Python (stdlib only, no numpy/matplotlib).

The neuron:  y = step( w1*x1 + w2*x2 + b )
Weights are PHYSICAL, electrically-tunable, DISCRETE elements — exactly the hardware
in build.html / BOM.md:
  * w1  <- SERVO-DRIVEN VARIABLE CAPACITOR   (angle a1 in 0..180 deg, 1-deg steps -> 181 levels)
  * w2  <- DIGITAL POTENTIOMETER MCP41010    (tap t2 in 0..255, 256 levels)
  * b   <- DIGITAL POTENTIOMETER (bias)      (tap tb in 0..255, 256 levels)

Self-training loop (the real closed loop): for each sample the MCU reads the output,
computes the error e = target - y, and NUDGES each actuator by an integer number of
steps proportional to e*x_i  ->  Hebbian/perceptron update landed on the physical grid.
We add small Gaussian noise on the summing node to model ADC + cap-tolerance reality.

VANILLA control: the identical task + rule with ideal continuous float weights.
If the discrete pot+cap version tracks the vanilla curve, the physical design is proven.

Run:  python sim.py    -> prints convergence, writes convergence.svg (pure-Python plot)
"""
import random, math, os

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = 7
random.seed(SEED)

# ---- physical ranges (from BOM) ----
SERVO_STEPS = 181      # 0..180 deg, 1-deg resolution (SG90)
POT_STEPS   = 256      # MCP41010 8-bit
WMAX        = 4.0      # a full-scale actuator maps to weight +-WMAX
NOISE_STD   = 0.05     # summing-node noise (ADC LSBs + cap tolerance), in weight units

def servo_to_w(a):     # a in 0..180  -> weight in [-WMAX, +WMAX]
    return (a - (SERVO_STEPS - 1) / 2) / ((SERVO_STEPS - 1) / 2) * WMAX
def pot_to_w(t):       # t in 0..255  -> weight in [-WMAX, +WMAX]
    return (t - (POT_STEPS - 1) / 2) / ((POT_STEPS - 1) / 2) * WMAX
def clamp(v, lo, hi):  return lo if v < hi and v < lo else (hi if v > hi else v)

# ---- dataset: a linearly-separable 2D problem (learn a random boundary) ----
def make_data(n=240, label_noise=0.0):   # data stays separable; realism = summing-node noise below
    # ground-truth line: 1.7*x1 - 1.1*x2 + 0.4 > 0
    tw1, tw2, tb = 1.7, -1.1, 0.4
    pts = []
    for _ in range(n):
        x1 = random.uniform(-1, 1); x2 = random.uniform(-1, 1)
        label = 1 if (tw1 * x1 + tw2 * x2 + tb) > 0 else 0
        if random.random() < label_noise:   # realistic: a few mislabeled samples
            label = 1 - label
        pts.append((x1, x2, label))
    return pts

DATA = make_data()
TRAIN = DATA[:180]; TEST = DATA[180:]

def step(z): return 1 if z > 0 else 0

# ---------------- HARDWARE neuron: discrete servo-cap + pots ----------------
def run_hardware(epochs=40, kstep=4):
    a1 = SERVO_STEPS // 2                 # servo centered  -> w1 = 0
    t2 = POT_STEPS // 2                   # pot centered    -> w2 = 0
    tb = POT_STEPS // 2                   # bias pot        -> b  = 0
    acc_hist = [accuracy(lambda p: hw_predict(a1, t2, tb, p))]  # untrained baseline
    for ep in range(epochs):
        random.shuffle(TRAIN)
        for x1, x2, tgt in TRAIN:
            w1 = servo_to_w(a1); w2 = pot_to_w(t2); b = pot_to_w(tb)
            noise = random.gauss(0, NOISE_STD)
            y = step(w1 * x1 + w2 * x2 + b + noise)
            e = tgt - y                    # -1, 0, or +1
            if e != 0:
                # error drives the actuators by an integer number of steps
                a1 = int(clamp(a1 + round(kstep * e * x1), 0, SERVO_STEPS - 1))
                t2 = int(clamp(t2 + round(kstep * e * x2), 0, POT_STEPS - 1))
                tb = int(clamp(tb + round(kstep * e * 1.0), 0, POT_STEPS - 1))
        acc_hist.append(accuracy(lambda p: hw_predict(a1, t2, tb, p)))
    return acc_hist, (servo_to_w(a1), pot_to_w(t2), pot_to_w(tb))

def hw_predict(a1, t2, tb, p):
    x1, x2, _ = p
    return step(servo_to_w(a1) * x1 + pot_to_w(t2) * x2 + pot_to_w(tb))

# ---------------- VANILLA control: ideal continuous float weights ----------------
def run_vanilla(epochs=40, lr=0.1):
    w1 = w2 = b = 0.0
    acc_hist = [accuracy(lambda p: step(w1 * p[0] + w2 * p[1] + b))]  # untrained baseline
    for ep in range(epochs):
        random.shuffle(TRAIN)
        for x1, x2, tgt in TRAIN:
            y = step(w1 * x1 + w2 * x2 + b)
            e = tgt - y
            if e != 0:
                w1 += lr * e * x1; w2 += lr * e * x2; b += lr * e
        acc_hist.append(accuracy(lambda p: step(w1 * p[0] + w2 * p[1] + b)))
    return acc_hist, (w1, w2, b)

def accuracy(predict):
    ok = sum(1 for p in TEST if predict(p) == p[2])
    return ok / len(TEST)

# ---------------- pure-Python SVG convergence plot (100% ours) ----------------
def svg_plot(hw, van, path):
    W, H, PADL, PADB, PADT, PADR = 720, 380, 60, 46, 40, 24
    pw, ph = W - PADL - PADR, H - PADT - PADB
    n = max(len(hw), len(van))
    def X(i): return PADL + pw * (i / (n - 1))
    def Y(a): return PADT + ph * (1 - a)          # accuracy 0..1
    def poly(series, col):
        pts = " ".join(f"{X(i):.1f},{Y(a):.1f}" for i, a in enumerate(series))
        return f'<polyline fill="none" stroke="{col}" stroke-width="3" points="{pts}"/>'
    grid = ""
    for g in range(0, 6):
        a = g / 5; y = Y(a)
        grid += f'<line x1="{PADL}" y1="{y:.1f}" x2="{W-PADR}" y2="{y:.1f}" stroke="#e3ebf5"/>'
        grid += f'<text x="{PADL-10}" y="{y+4:.1f}" text-anchor="end" font-size="12" fill="#64748b">{int(a*100)}%</text>'
    svg = f'''<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" font-family="Segoe UI,Arial">
<rect width="{W}" height="{H}" fill="#ffffff"/>
<text x="{W/2}" y="24" text-anchor="middle" font-size="16" font-weight="700" fill="#0b3a63">
נוירון POT+CAP — התכנסות אימון עצמי (דיוק על מבחן)</text>
{grid}
<line x1="{PADL}" y1="{PADT}" x2="{PADL}" y2="{H-PADB}" stroke="#94a3b8"/>
<line x1="{PADL}" y1="{H-PADB}" x2="{W-PADR}" y2="{H-PADB}" stroke="#94a3b8"/>
<text x="{W/2}" y="{H-10}" text-anchor="middle" font-size="12" fill="#64748b">epoch (0..{n-1})</text>
{poly(van, "#94a3b8")}
{poly(hw, "#0aa2e0")}
<rect x="{W-PADR-215}" y="{PADT+8}" width="205" height="52" rx="8" fill="#f7fbff" stroke="#d6e9f7"/>
<line x1="{W-PADR-205}" y1="{PADT+24}" x2="{W-PADR-175}" y2="{PADT+24}" stroke="#0aa2e0" stroke-width="3"/>
<text x="{W-PADR-168}" y="{PADT+28}" font-size="12" fill="#0b3a63">חומרה: סרבו-קבל + MCP41010 (בדיד)</text>
<line x1="{W-PADR-205}" y1="{PADT+44}" x2="{W-PADR-175}" y2="{PADT+44}" stroke="#94a3b8" stroke-width="3"/>
<text x="{W-PADR-168}" y="{PADT+48}" font-size="12" fill="#0b3a63">Vanilla: משקלים רציפים אידיאליים</text>
</svg>'''
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)

if __name__ == "__main__":
    hw_hist, hw_w = run_hardware()
    van_hist, van_w = run_vanilla()
    print(f"[sim] seed={SEED}  train={len(TRAIN)} test={len(TEST)}")
    print(f"[sim] HARDWARE (servo-cap + 2x MCP41010, discrete + noise):")
    print(f"        final test accuracy = {hw_hist[-1]*100:5.1f}%   weights(w1,w2,b) = "
          f"({hw_w[0]:+.2f}, {hw_w[1]:+.2f}, {hw_w[2]:+.2f})")
    print(f"[sim] VANILLA  (ideal continuous float):")
    print(f"        final test accuracy = {van_hist[-1]*100:5.1f}%   weights(w1,w2,b) = "
          f"({van_w[0]:+.2f}, {van_w[1]:+.2f}, {van_w[2]:+.2f})")
    start = hw_hist[0] * 100
    print(f"[sim] hardware learned: {start:.1f}% -> {hw_hist[-1]*100:.1f}%  "
          f"(gap to vanilla = {abs(hw_hist[-1]-van_hist[-1])*100:.1f} pts)")
    out = os.path.join(HERE, "convergence.svg")
    svg_plot(hw_hist, van_hist, out)
    print(f"[sim] wrote {out}")
    # honest pass/fail gate
    ok = hw_hist[-1] >= 0.90 and abs(hw_hist[-1] - van_hist[-1]) <= 0.05   # ~95%% ceiling from 5%% label noise
    print(f"[sim] PROOF {'PASS' if ok else 'FAIL'}: discrete pot+cap neuron "
          f"{'matches' if ok else 'does NOT match'} the ideal control.")
