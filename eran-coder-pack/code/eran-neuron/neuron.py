# -*- coding: utf-8 -*-
"""
ERAN NEURON — נוירון בהשראה ביולוגית / biology-inspired neuron
==============================================================
עברית + English. ללא תלויות חיצוניות (stdlib בלבד) — נועד לרוץ ולא להישבר.
No external deps (stdlib only) — meant to run, not to break.

עקרונות מהשיחה / principles from our talk:
  * מספר פתוח של כניסות ויציאות   — OPEN number of inputs and outputs
  * חיבור = צרור ערוצים, לא סקלר   — a connection is a BUNDLE of channels, not a scalar
  * מצב פנימי + פאזה + זמן + ירי    — internal state, phase, time, spiking
  * למידה משנה יחסים, לא רק מספר    — learning changes RELATIONSHIPS, not just a number
  * עדכון א-סינכרוני = ביולוגי       — asynchronous update = biological, "less rigid order"
"""
import math


# ── קשר / Connection ────────────────────────────────────────────────────
class Connection:
    """
    קשר רב-ערוצי — לא משקל בודד אלא צרור יחסים.
    Multi-channel connection — not one weight but a bundle of relationships.
      amp   — משרעת / amplitude   (real, ±)
      phase — פאזה  / phase (rad) : יישור-פאזה = התאבכות (interference-like alignment)
      gate  — שער   / gate (0..1) : יחס בוליאני-רך (soft boolean relation)
      trace — עקבה  / eligibility trace  (מצב פנימי ללמידה / internal state for learning)
    """
    def __init__(self, amp=0.5, phase=0.0, gate=1.0):
        self.amp = amp
        self.phase = phase
        self.gate = gate
        self.trace = 0.0

    def transmit(self, signal, ctx_phase):
        # הערך הנמסר תלוי ביישור-פאזה ובשער — לא רק במשרעת
        # delivered value depends on phase-alignment and gate — not amplitude alone
        align = math.cos(self.phase - ctx_phase)      # -1..1  (interference term)
        return self.amp * align * self.gate * signal

    def decay_trace(self, rho=0.9):
        self.trace *= rho


# ── נוירון / Neuron ─────────────────────────────────────────────────────
class Neuron:
    """
    יחידה דינמית עם מספר פתוח של כניסות ויציאות.
    Dynamical unit with an OPEN number of inputs and outputs.
    מצב / state: v (פוטנציאל), phase (מתנד פנימי), a (אדפטציה).
    """
    _next_id = 0

    def __init__(self, name=None, threshold=1.0, leak=0.2, freq=1.0, adapt=0.3):
        self.id = Neuron._next_id
        Neuron._next_id += 1
        self.name = name or f"n{self.id}"
        self.v = 0.0            # פוטנציאל קרום / membrane potential
        self.phase = 0.0        # פאזה עצמית / own oscillatory phase
        self.freq = freq        # תדר מתנד / oscillator frequency
        self.a = 0.0            # אדפטציה / adaptation
        self.threshold = threshold
        self.leak = leak
        self.adapt = adapt
        self.inputs = []        # [(source|None, Connection)]  כניסות פתוחות / open inputs
        self.outputs = []       # [(target,      Connection)]  יציאות פתוחות / open outputs
        self.spiked = False

    # הטופולוגיה פתוחה — אפשר להוסיף כמה שרוצים / topology is open — add as many as you like
    def add_input(self, source, conn=None):
        conn = conn or Connection()
        self.inputs.append((source, conn))
        return conn

    def add_output(self, target, conn=None):
        conn = conn or Connection()
        self.outputs.append((target, conn))
        return conn

    def step(self, dt, ext=0.0, neuromod=1.0):
        # 1) קדם מתנד פנימי / advance internal oscillator
        self.phase = (self.phase + 2 * math.pi * self.freq * dt) % (2 * math.pi)
        # 2) אינטגרציה של כל הכניסות דרך החיבורים הרב-ערוציים
        drive = ext
        for src, conn in self.inputs:
            sig = 1.0 if (src is not None and src.spiked) else 0.0
            drive += conn.transmit(sig, self.phase)
            if sig > 0:
                conn.trace += sig                     # coincidence eligibility / עקבת צירוף
        # 3) דליפה + אינטגרציה - אדפטציה / leak + integrate - adaptation
        self.v += dt * (-self.leak * self.v + drive - self.a)
        # 4) סף וירי / threshold & spike
        self.spiked = self.v >= self.threshold
        if self.spiked:
            self.v = 0.0
            self.a += self.adapt                      # מתעייף אחרי ירי / fatigue after firing
            self._learn(neuromod)
        # 5) דעיכה / decay
        self.a *= 0.9
        for _, conn in self.inputs:
            conn.decay_trace()
        return self.spiked

    def _learn(self, neuromod):
        # למידה מקומית משנה *יחסים* (משרעת+פאזה), מגודרת בנוירומודולטור (כלל תלת-גורמי)
        # local learning changes *relationships* (amp+phase), gated by neuromodulator (3-factor)
        for _, conn in self.inputs:
            if conn.trace > 0:
                conn.amp += 0.05 * neuromod * conn.trace                       # Hebbian-ish
                conn.phase += 0.10 * neuromod * math.sin(self.phase - conn.phase)  # קרב לסנכרון

    def reset(self):
        # אתחול מצב (לא הטופולוגיה/הלמידה) / reset state (not topology/learning)
        self.v = 0.0
        self.phase = 0.0
        self.a = 0.0
        self.spiked = False

    def fan_in(self):
        return len(self.inputs)

    def fan_out(self):
        return len(self.outputs)


# ── בית דין / BeitDin ───────────────────────────────────────────────────
class BeitDin:
    """
    שלושה נוירונים ששופטים יחד. Three neurons that judge together.
    פסק = רוב, 2 מתוך 3 (קוורום). Verdict = majority, 2 of 3 (quorum).
    זרע ל'מצפון כארכיטקטורה' — 3 → 71. Seed of conscience-as-architecture — 3 → 71.
    """
    def __init__(self, names=("דיין_א", "דיין_ב", "דיין_ג")):
        self.judges = [Neuron(name=nm, threshold=1.0, freq=1.0 + 0.13 * i)
                       for i, nm in enumerate(names)]
        # חיבור הדדי בין הדיינים / mutual cross-connections between judges
        for a in self.judges:
            for b in self.judges:
                if a is not b:
                    a.add_input(b, Connection(amp=0.25, phase=0.0, gate=1.0))

    def reset(self):
        for j in self.judges:
            j.reset()

    def deliberate(self, dt, evidence, steps=20, neuromod=1.0, min_spikes=2):
        # שיקול דעת לאורך זמן: כל דיין סופר יריות, מצביע אם ירה מספיק
        # deliberation over time: each judge counts spikes, votes YES if it fired enough
        self.reset()
        counts = [0, 0, 0]
        for _ in range(steps):
            for k, j in enumerate(self.judges):
                if j.step(dt, ext=evidence, neuromod=neuromod):
                    counts[k] += 1
        votes = [c >= min_spikes for c in counts]     # הצבעת כל דיין / each judge's vote
        verdict = sum(votes) >= 2                      # רוב / majority
        return votes, counts, verdict


# aliases בעברית / Hebrew aliases
נוירון = Neuron
קשר = Connection
בית_דין = BeitDin


# ── הדגמה / demo ────────────────────────────────────────────────────────
def _demo():
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")      # שלא יישבר על עברית / no unicode crash
    except Exception:
        pass

    print("=" * 62)
    print("הדגמה 1 — נוירון בודד עם כניסות ויציאות פתוחות")
    print("DEMO 1 — a single neuron with open inputs & outputs")
    print("=" * 62)

    # שלושה חיישנים מזינים נוירון-מטרה / three sensors feed one target neuron
    sensors = [Neuron(name=f"חיישן{i}") for i in range(3)]
    target = Neuron(name="מטרה", threshold=1.0, leak=0.2, freq=0.4)
    for i, s in enumerate(sensors):
        target.add_input(s, Connection(amp=0.8, phase=i * math.pi / 6, gate=1.0))  # פאזות שונות
    downstream = Neuron(name="במורד")
    target.add_output(downstream)                     # יציאה / an output

    print(f"למטרה יש {target.fan_in()} כניסות ו-{target.fan_out()} יציאות "
          f"(fan-in={target.fan_in()}, fan-out={target.fan_out()})\n")

    amps_before = [round(c.amp, 3) for _, c in target.inputs]
    pattern = [(1, 0, 1), (1, 1, 1), (0, 0, 0), (1, 1, 0), (1, 1, 1)]
    dt = 0.25
    spikes = 0
    for t, fire in enumerate(pattern * 3):
        for s, f in zip(sensors, fire):
            s.spiked = bool(f)
        spk = target.step(dt, ext=0.2, neuromod=1.5)
        spikes += spk
        bar = "▉" * int(max(0.0, target.v) * 18)
        print(f"t={t:02d}  in={fire}  v={target.v:5.2f} {bar}"
              + ("   ← ירי! SPIKE" if spk else ""))

    print(f"\nסה\"כ יריות / total spikes: {spikes}")
    print("משרעות לפני /before:", amps_before)
    print("משרעות אחרי  /after :", [round(c.amp, 3) for _, c in target.inputs],
          "  ← הלמידה שינתה יחסים / learning changed the relationships")

    print("\n" + "=" * 62)
    print("הדגמה 2 — בית דין של שלושה / DEMO 2 — a Beit Din of three")
    print("=" * 62)
    bd = BeitDin()
    print("ראיה חלשה → ראיה חזקה / weak evidence → strong evidence\n")
    for evidence in (0.15, 0.25, 0.45, 0.80):
        votes, counts, verdict = bd.deliberate(dt, evidence, steps=24)
        who = ", ".join(j.name for j, v in zip(bd.judges, votes) if v) or "—"
        rule = "אשם/כן  GUILTY/YES" if verdict else "זכאי/לא  NOT/NO"
        print(f"ראיה evidence={evidence:.2f}  יריות/spikes={counts}  "
              f"בעד/for=[{who:<18}] → פסק/verdict: {rule}")

    print("\nגמור. ערן הראשון פועם. / Done. the first Eran is pulsing. 🫀")


if __name__ == "__main__":
    _demo()
