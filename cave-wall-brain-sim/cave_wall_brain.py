#!/usr/bin/env python3
"""
Cave Wall Brain — LED/fiber-optic neural-net wall SIMULATOR
============================================================
Software model of project_cave_wall_brain: a live neural network whose
synaptic weights are broadcast as LED color/brightness on a physical wall
(the role Zack Akil's RGB Neural Net plays over WiFi -> Arduino -> LEDs).

This is the *control-software* half of that installation, runnable today
with zero dependencies (pure Python stdlib). It:
  1. Builds + trains a tiny 2-layer net (XOR) with plain-Python backprop.
  2. Maps every synaptic weight to an RGB "LED" (sign -> hue, |w| -> brightness).
  3. Renders the wall live in the terminal (24-bit ANSI) each epoch.
  4. Emits the same frame as a "broadcast packet" (JSON) — exactly what the
     Raspberry Pi would push to the Arduino LED driver — and an HTML snapshot.

Run:  python cave_wall_brain.py            (live animated training)
      python cave_wall_brain.py --html     (also write wall.html snapshot)
"""
import math, random, json, sys, time, os

random.seed(7)

# ---------------------------------------------------------------- net
# Architecture: 2 inputs -> 4 hidden -> 1 output  (XOR)
DATA = [([0,0],0),([0,1],1),([1,0],1),([1,1],0)]

def rnd(): return random.uniform(-1,1)

W1 = [[rnd() for _ in range(2)] for _ in range(4)]   # hidden[4] x in[2]
B1 = [rnd() for _ in range(4)]
W2 = [rnd() for _ in range(4)]                        # out x hidden[4]
B2 = rnd()

def sig(x): return 1/(1+math.exp(-max(-30,min(30,x))))

def forward(x):
    h = [sig(sum(W1[j][k]*x[k] for k in range(2))+B1[j]) for j in range(4)]
    o = sig(sum(W2[j]*h[j] for j in range(4))+B2)
    return h,o

def train_step(lr=0.5):
    global B2
    for x,y in DATA:
        h,o = forward(x)
        do = (o-y)*o*(1-o)
        dh = [W2[j]*do*h[j]*(1-h[j]) for j in range(4)]
        for j in range(4):
            W2[j] -= lr*do*h[j]
        B2 -= lr*do
        for j in range(4):
            for k in range(2):
                W1[j][k] -= lr*dh[j]*x[k]
            B1[j] -= lr*dh[j]

def loss():
    return sum((forward(x)[1]-y)**2 for x,y in DATA)/len(DATA)

# ---------------------------------------------------------------- LED mapping
def led(w):
    """Map a synaptic weight -> (r,g,b) LED. sign=hue, |w|=brightness."""
    mag = min(1.0, abs(w)/3.0)           # saturate near |w|~3
    b = int(40 + 215*mag)                # brightness floor so 'off' still glows
    if w >= 0:   # excitatory -> warm amber (Edison-bulb look)
        return (b, int(b*0.55), int(b*0.15))
    else:        # inhibitory -> cool cyan
        return (int(b*0.15), int(b*0.7), b)

def all_leds():
    """Flat list of ('label', weight, rgb) — the wall's LED array."""
    out=[]
    for j in range(4):
        for k in range(2):
            out.append((f"H{j}<-I{k}", W1[j][k], led(W1[j][k])))
    for j in range(4):
        out.append((f"O<-H{j}", W2[j], led(W2[j])))
    return out

# ---------------------------------------------------------------- terminal render
def cell(rgb):
    r,g,b = rgb
    return f"\x1b[48;2;{r};{g};{b}m  \x1b[0m"

def render(epoch):
    l = loss()
    lines=[]
    lines.append(f"\x1b[1m CAVE WALL BRAIN  \x1b[0m epoch {epoch:4d}   loss {l:.4f}")
    lines.append("")
    # input layer (2), hidden (4), output (1) laid out as a wall
    leds = all_leds()
    # hidden synapses grid: 4 rows x 2 cols
    lines.append("  input->hidden synapses            hidden->output")
    idx=0
    for j in range(4):
        row = "   "
        for k in range(2):
            row += cell(leds[idx][2]); idx+=1
        row += "     H"+str(j)+"   "
        row += cell(leds[8+j][2])
        lines.append(row)
    lines.append("")
    # predictions
    preds=" ".join(f"{x}->{forward(x)[1]:.2f}" for x,_ in DATA)
    lines.append("  "+preds)
    lines.append("  amber=excitatory(+)   cyan=inhibitory(-)   brightness=|weight|")
    return "\n".join(lines)

def broadcast_packet(epoch):
    """The WiFi packet the Pi would send to the Arduino LED driver."""
    return {"epoch":epoch,"loss":round(loss(),5),
            "leds":[{"id":lbl,"w":round(w,4),"rgb":rgb} for lbl,w,rgb in all_leds()]}

# ---------------------------------------------------------------- html snapshot
def write_html(path):
    leds = all_leds()
    dots=""
    for lbl,w,rgb in leds:
        dots+=(f'<div class="led" style="background:rgb{rgb};'
               f'box-shadow:0 0 14px rgb{rgb}" title="{lbl} w={w:.3f}">'
               f'<span>{lbl}</span></div>')
    html=f"""<!doctype html><meta charset=utf-8><title>Cave Wall Brain</title>
<style>body{{background:#0d0b08;color:#c9a34e;font-family:Georgia,serif;
text-align:center;padding:30px}}h1{{letter-spacing:3px}}
.wall{{display:flex;flex-wrap:wrap;gap:22px;justify-content:center;
max-width:620px;margin:30px auto;padding:30px;border:3px solid #6b4f2a;
border-radius:10px;background:#151009}}
.led{{width:72px;height:72px;border-radius:50%;display:flex;align-items:center;
justify-content:center;border:2px solid #3a2c14}}
.led span{{font-size:10px;color:#000a;font-family:monospace}}
p{{color:#8a7040}}</style>
<h1>CAVE WALL BRAIN</h1>
<p>live synaptic weights as light &middot; loss {loss():.4f}</p>
<div class="wall">{dots}</div>
<p>amber = excitatory (+) &nbsp; cyan = inhibitory (&minus;) &nbsp; brightness = |weight|<br>
&ldquo;That brain of mine is something more than merely mortal.&rdquo; &mdash; Ada Lovelace, 1843</p>"""
    with open(path,"w",encoding="utf-8") as f: f.write(html)

# ---------------------------------------------------------------- main
def main():
    want_html = "--html" in sys.argv
    EPOCHS=3000
    for e in range(EPOCHS+1):
        train_step(lr=0.7)
        if e % 50 == 0:
            os.system("")  # enable ANSI on Windows terminals
            sys.stdout.write("\x1b[2J\x1b[H")
            print(render(e))
            time.sleep(0.02)
    print()
    print("Final broadcast packet (Pi -> Arduino LED driver):")
    print(json.dumps(broadcast_packet(EPOCHS), indent=2))
    if want_html:
        p=os.path.join(os.path.dirname(os.path.abspath(__file__)),"wall.html")
        write_html(p)
        print("\nHTML snapshot written:",p)

if __name__=="__main__":
    main()
