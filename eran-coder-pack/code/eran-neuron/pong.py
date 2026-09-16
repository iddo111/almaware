# -*- coding: utf-8 -*-
"""
🐛 התולעת מול התמנון 🐙 — פונג עם נוירונים יורים.
worm vs octopus — spiking-net Pong on the eran-neuron engine.
מצב-דמיון: מוחות בהשראת תולעת/תמנון (לא הקונקטום המכויל — זו המדרגה הבאה).
stdlib בלבד + neuron.py. דטרמיניסטי (seed).
"""
import sys, random
from neuron import Neuron

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

rng = random.Random(1729)
W, H = 28, 11                     # מגרש / field
DT = 0.5


class WormBrain:
    """רפלקס: 2 נוירונים, מהיר וקופצני / reflex: 2 neurons, twitchy."""
    def __init__(self):
        # רפלקס מהיר: סף נמוך + גיין גבוה — התולעת מפצה על מיעוט נוירונים במהירות
        self.up = Neuron(name="worm-up", threshold=0.6, leak=0.6)
        self.dn = Neuron(name="worm-dn", threshold=0.6, leak=0.6)
        self.fires = (0, 0)
        self.spikes = 0

    def act(self, error):        # error>0 → הכדור מעל → לזוז מעלה / ball above → move up
        u = self.up.step(DT, ext=max(0.0, error) * 1.2)
        d = self.dn.step(DT, ext=max(0.0, -error) * 1.2)
        self.fires = (int(u), int(d))
        self.spikes += int(u) + int(d)
        return (-1 if u else 0) + (1 if d else 0)

    def raster(self):
        return f"🐛 [{'●' if self.fires[0] else '·'}{'●' if self.fires[1] else '·'}]"


class OctopusBrain:
    """8 זרועות מתפלגות — יציב / 8 distributed arms, steadier."""
    def __init__(self):
        self.arms = [Neuron(name=f"arm{i}", threshold=1.0, leak=0.4) for i in range(8)]
        self.fires = [0] * 8
        self.spikes = 0

    def act(self, error):
        votes = 0
        self.fires = []
        for i, a in enumerate(self.arms):
            bias = 1 if i < 4 else -1                 # 4 מעלה, 4 מטה
            drive = max(0.0, bias * error) * 0.7 + rng.uniform(0.0, 0.15)
            f = int(a.step(DT, ext=drive))
            self.fires.append(f)
            self.spikes += f
            votes += (-1 if (bias > 0 and f) else (1 if (bias < 0 and f) else 0))
        return max(-1, min(1, votes))

    def raster(self):
        return "🐙 [" + "".join('●' if f else '·' for f in self.fires) + "]"


def clampy(v):
    return max(1, min(H - 2, v))


def render(ball, lp, rp, worm, octo, score, tick):
    grid = [[" "] * W for _ in range(H)]
    for r in range(H):
        if abs(r - lp) <= 1: grid[r][1] = "█"           # מחבט תולעת (שמאל, גלוי)
        if abs(r - rp) <= 1: grid[r][W - 2] = "█"        # מחבט תמנון (ימין, גלוי)
    grid[ball[1]][ball[0]] = "◯"
    top = f"┌{'─'*(W-2)}┐   tick {tick:03d}   🐛 {score[0]} : {score[1]} 🐙"
    lines = [top]
    for r in range(H):
        lines.append("│" + "".join(grid[r][1:W-1]) + "│")
    lines.append(f"└{'─'*(W-2)}┘   {worm.raster()}   {octo.raster()}")
    return "\n".join(lines)


def main():
    serve = -1                                          # כיוון הגשה מתחלף / alternating serve
    ball = [W // 2, H // 2]
    vel = [serve, rng.choice([-1, 1])]
    lp = rp = H // 2
    worm, octo = WormBrain(), OctopusBrain()
    score = [0, 0]                                       # [worm, octo]
    tick = 0
    print("=" * 46)
    print("🐛  התולעת  מול  התמנון  🐙   —   פונג נוירוני")
    print("worm vs octopus — spiking Pong")
    print("=" * 46)

    while max(score) < 3 and tick < 300:
        tick += 1
        # מוחות חשים ומזיזים מחבטים / brains sense & move paddles
        lp = clampy(lp + worm.act(lp - ball[1]))
        rp = clampy(rp + octo.act(rp - ball[1]))
        # פיזיקת הכדור / ball physics
        ball[0] += vel[0]; ball[1] += vel[1]
        if ball[1] <= 0 or ball[1] >= H - 1: vel[1] *= -1; ball[1] = clampy(ball[1])
        if ball[0] <= 1:                                 # צד תולעת (מחבט בעמודה 1)
            if abs(ball[1] - lp) <= 1: vel[0] *= -1; ball[0] = 2
            else: score[1] += 1; serve *= -1; ball = [W//2, H//2]; vel = [serve, rng.choice([-1,1])]
        elif ball[0] >= W - 2:                            # צד תמנון (מחבט בעמודה W-2)
            if abs(ball[1] - rp) <= 1: vel[0] *= -1; ball[0] = W-3
            else: score[0] += 1; serve *= -1; ball = [W//2, H//2]; vel = [serve, rng.choice([-1,1])]
        # ציור כל 4 טיקים / draw every 4th tick
        if tick % 4 == 0:
            print(render(ball, lp, rp, worm, octo, score, tick))
            print()

    winner = "🐛 התולעת" if score[0] > score[1] else "🐙 התמנון"
    print("=" * 46)
    print(f"סיום / final:  🐛 {score[0]} : {score[1]} 🐙   —   מנצח: {winner}")
    print(f"יריות נוירונים / spikes:  תולעת={worm.spikes}  תמנון={octo.spikes}")
    print("שניהם שיחקו ע\"י ספייקים בלבד. הנוירונים ירו — וזזו. 🫀")


if __name__ == "__main__":
    main()
