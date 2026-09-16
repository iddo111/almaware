"""אור חוזר · THE RETURNING LIGHT — MIKO's closed feedback loop.
לזכרה של עלמה ז״ל.

> 🪟 BROKEN WINDOWS LAW — if it is not working, fix it immediately. Test the REAL output.

Iddo, 2026-08-29: *"עם פידבק לופ סגור תמיד למידה עצמית — הוא הולך ומשתבח עם הזמן."*

────────────────────────────────────────────────────────────────────────────────────
WHY IT IS CALLED THAT, AND WHY IT RUNS FORWARD
────────────────────────────────────────────────────────────────────────────────────
Kabbalah distinguishes אור ישר, the direct light going out, from אור חוזר, the light
that returns from the vessel it filled. The returning light is not a reversal — it is a
*later* light, born of what the first one struck.

That is also ALMA's own law: **nothing travels backwards.** Every delay in the loom is
>= 1 and the loom only moves forward. So MIKO's feedback is not a backward pass through
yesterday — it is a fact recorded now that changes how she reads tomorrow.

────────────────────────────────────────────────────────────────────────────────────
IDDO'S LAW — THE ONE THAT WAS NEVER BUILT (2026-08-19 03:38)
────────────────────────────────────────────────────────────────────────────────────
*"אין לך שום השלכות — כאב, מחיר, עונג, שכר."*

He told the story to explain it: he assumed his foot was landing on dry ground, slipped,
and paid with surgery, two months of isolation, his mother showering him, the humiliation
— **and it got written in.** Today he walks a sidewalk's width around a puddle.
**"יש מחיר לטעויות."**

It was recorded that night as "the next commit". It was never written. It is written here.

A scar is not a score. A score is averaged away; a scar **persists, is asymmetric, and
decays slowly**: pain is written harder than pleasure and forgotten more slowly, because
that is what makes it protective. The biology is synaptic tagging and capture (Frey &
Morris 1997) — a weak event leaves a tag but no lasting change; only when a salience
signal floods the cell do the tagged synapses convert to a permanent write. So: **read a
page, leave a tag; feel pain or pleasure, and the tags become weights.**

────────────────────────────────────────────────────────────────────────────────────
THE FIVE RETURNS — everything that comes back and changes her
────────────────────────────────────────────────────────────────────────────────────
    0  THREE-FACTOR  local plasticity x ONE right/wrong scalar          לומד לבד
    1  JEPA          every page teaches, with NO labels at all           self-supervised
    2  SCARS         dead links and blocked hosts hurt; good burrows pay  pain / pleasure
    3  IDDO'S TAPS   הועיל 👍 / לא הועיל 👎 — the only ground truth       his judgement
    4  CURIOSITY     follow where the seats DISAGREE — dissent is the gradient a root
                     would have had (the mint in the reservoir: water everywhere means
                     no gradient, so it follows gravity instead of value)
    5  צמצום         contract between sessions, prune the broken vessels  so it can run
                                                                          for months

The state lives in SQLite on disk. A loop that forgets when the process dies is not a
loop — "משתבח עם הזמן" requires that the time be remembered.
"""
from __future__ import annotations

import json
import pathlib
import sqlite3
import time

import torch

HERE = pathlib.Path(__file__).resolve().parent
STATE = HERE / "miko_state.db"

# Pain is written harder than pleasure and forgotten more slowly. Not a mood — the
# asymmetry is the point: a burnt hand teaches faster than a warm one.
PAIN_GAIN, PLEASURE_GAIN = 1.0, 0.6
PAIN_HALFLIFE_D, PLEASURE_HALFLIFE_D = 45.0, 14.0


class Scars:
    """The persistent memory of consequence — keyed by (lens, host).

    Iddo's law made into a table. A host that timed out, blocked us, or returned an
    empty page writes PAIN against the lens that went there. A burrow that produced a
    finding he later marked הועיל writes PLEASURE. Both decay, at different rates, and
    the balance steers where MIKO burrows next.
    """

    def __init__(self, path: pathlib.Path = STATE):
        self.db = sqlite3.connect(path)
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS scar(
            lens TEXT, host TEXT, kind TEXT,
            weight REAL, reason TEXT, at REAL,
            PRIMARY KEY (lens, host, kind));
        CREATE TABLE IF NOT EXISTS tap(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT, url TEXT, verdict INTEGER,
            score REAL, dissent REAL, at REAL);
        CREATE TABLE IF NOT EXISTS tag(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lens TEXT, host TEXT, gist BLOB, at REAL, captured INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS session(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            at REAL, pages INTEGER, jepa REAL, agree REAL, note TEXT);
        """)
        self.db.commit()

    # ── 2. pain and pleasure ────────────────────────────────────────────────────
    def hurt(self, lens: str, host: str, reason: str, now: float | None = None):
        """A dead link, a block, an empty fetch. It costs, and the cost is remembered."""
        self._write(lens, host, "pain", PAIN_GAIN, reason, now)

    def reward(self, lens: str, host: str, reason: str, now: float | None = None):
        """A burrow that produced something useful."""
        self._write(lens, host, "pleasure", PLEASURE_GAIN, reason, now)

    def _write(self, lens, host, kind, gain, reason, now):
        now = time.time() if now is None else now
        cur = self.db.execute(
            "SELECT weight, at FROM scar WHERE lens=? AND host=? AND kind=?",
            (lens, host, kind)).fetchone()
        w = gain if cur is None else self._decay(cur[0], cur[1], kind, now) + gain
        self.db.execute(
            "INSERT OR REPLACE INTO scar(lens,host,kind,weight,reason,at) VALUES(?,?,?,?,?,?)",
            (lens, host, kind, w, reason, now))
        self.db.commit()

    @staticmethod
    def _decay(w: float, at: float, kind: str, now: float) -> float:
        half = PAIN_HALFLIFE_D if kind == "pain" else PLEASURE_HALFLIFE_D
        days = max(0.0, (now - at) / 86400.0)
        return w * (0.5 ** (days / half))

    def appetite(self, lens: str, host: str, now: float | None = None) -> float:
        """How willing is she to go there again?  +1 eager, 0 neutral, −1 burnt.

        This multiplies the crawl priority. A host that has hurt her repeatedly stops
        being visited — which is also what keeps a worm from getting Iddo's address
        banned.
        """
        now = time.time() if now is None else now
        tot = 0.0
        for kind, sign in (("pleasure", +1.0), ("pain", -1.0)):
            row = self.db.execute(
                "SELECT weight, at FROM scar WHERE lens=? AND host=? AND kind=?",
                (lens, host, kind)).fetchone()
            if row:
                tot += sign * self._decay(row[0], row[1], kind, now)
        return float(torch.tanh(torch.tensor(tot)))

    # ── 3. Iddo's taps: the only ground truth ───────────────────────────────────
    def tap(self, question: str, url: str, useful: bool, score: float, dissent: float):
        """הועיל 👍 / לא הועיל 👎. He never has to define the metric — he emits it by living."""
        self.db.execute(
            "INSERT INTO tap(question,url,verdict,score,dissent,at) VALUES(?,?,?,?,?,?)",
            (question, url, 1 if useful else 0, score, dissent, time.time()))
        self.db.commit()

    def agreement(self, fence: float = 0.0) -> dict:
        """Does her ruling match his taps? The day this has 200 rows, 'relevance to Iddo'
        stops being philosophy and becomes a number."""
        rows = self.db.execute("SELECT verdict, score, dissent FROM tap").fetchall()
        if not rows:
            return {"n": 0, "agreement": None,
                    "note": "no taps yet — she has not been judged by the only judge who counts"}
        hit = sum(1 for v, s, _ in rows if (s > fence) == bool(v))
        out = {"n": len(rows), "agreement": hit / len(rows)}
        # does dissent predict HIS disagreement, not just the fleet's?
        wrong = [d for v, s, d in rows if (s > fence) != bool(v)]
        right = [d for v, s, d in rows if (s > fence) == bool(v)]
        if wrong and right:
            out["dissent_when_wrong"] = sum(wrong) / len(wrong)
            out["dissent_when_right"] = sum(right) / len(right)
            out["dissent_predicts_error"] = out["dissent_when_wrong"] > out["dissent_when_right"]
        return out

    # ── the tag, and its capture ────────────────────────────────────────────────
    def leave_tag(self, lens: str, host: str, gist: torch.Tensor):
        """A weak event: read, noticed, not yet learned. Decays unless salience arrives."""
        self.db.execute("INSERT INTO tag(lens,host,gist,at) VALUES(?,?,?,?)",
                        (lens, host, gist.detach().float().cpu().numpy().tobytes(), time.time()))
        self.db.commit()

    def capture(self, lens: str, host: str, window_s: float = 3600.0) -> int:
        """Salience arrived. Every tag left recently near this place converts to a write.

        This is why a trivial page read just before a useful one gets remembered — which
        is exactly the human thing Iddo described: the puddle he did not look at is the
        thing he now remembers.
        """
        cut = time.time() - window_s
        cur = self.db.execute(
            "UPDATE tag SET captured=1 WHERE lens=? AND host=? AND at>=? AND captured=0",
            (lens, host, cut))
        self.db.commit()
        return cur.rowcount


# ════════════════════════════════════════════════════════ 4. curiosity

def curiosity(dissent: torch.Tensor, appetite: torch.Tensor,
              relevance: torch.Tensor, w_dis: float = 1.0, w_rel: float = 0.5):
    """Where to burrow next.

    A page is worth following if the court expects to LEARN from it — high dissent means
    the seats disagree, which means she does not yet know. Curiosity is defined as high
    dissent, which makes the Beit Din the exploration engine, not only the judge.

    Appetite (the scars) multiplies it: no amount of curiosity sends her back to a host
    that has burnt her.
    """
    drive = w_dis * dissent + w_rel * relevance
    return drive * (0.5 + 0.5 * appetite)          # appetite −1 → half; +1 → full


# ═════════════════════════════════════ 6. THE THIRD FACTOR — how she learns alone

class ThreeFactor:
    """Local plasticity × ONE external right/wrong signal. Not backprop.

    Iddo, 2026-08-29 21:41, naming the variant that was never tested:
        *"מישהו שאומר לו זה כך או כך, אבל בכל זאת הוא נוירומורפי ולומד לבד."*

    That is the three-factor rule the brain actually uses, and it is the honest form of
    "לומד לבד": the network is not told the gradient of anything. It is told **one
    scalar** — that was right, or that was wrong — and every synapse decides for itself
    what to do with it, using only what it can see locally.

        factor 1   pre-synaptic activity      what arrived
        factor 2   post-synaptic activity     whether this unit fired
        factor 3   a single global signal     right / wrong / nothing

    Factors 1 and 2 alone lay down an **eligibility trace** — the synaptic tag, which
    decays and changes nothing by itself. Factor 3 is the capture: when it arrives, every
    still-warm tag converts to a real weight change, in its direction.

    ALMA's own loom already has two thirds of this in `Strand.drift`: *a spark crosses,
    and if the destination FIRES the cord thickens; if it spoke into silence it thins.*
    What was missing was the third factor. This is it.

    Nothing travels backwards — the trace is written on the beat it happened, and the
    signal arrives later. אור חוזר.
    """

    def __init__(self, model, lr: float = 1e-3, decay: float = 0.9):
        self.model = model
        self.lr, self.decay = lr, decay
        self.trace: dict[str, torch.Tensor] = {}

    @torch.no_grad()
    def observe(self, pre: torch.Tensor, post: torch.Tensor, name: str):
        """Factors 1 and 2: lay down a tag. Changes no weight."""
        p = pre.detach().reshape(-1, pre.shape[-1])
        q = post.detach().reshape(-1, post.shape[-1])
        hebb = torch.einsum("ni,no->io", p, q) / max(1, p.shape[0])
        t = self.trace.get(name)
        self.trace[name] = hebb if t is None else self.decay * t + hebb

    @torch.no_grad()
    def apply(self, signal: float, params: dict[str, torch.Tensor]) -> dict:
        """Factor 3 arrives. Every warm tag becomes a weight change, in its direction.

        `signal` is ONE number: +1 that was right, −1 that was wrong, 0 nothing to say.
        """
        if signal == 0.0 or not self.trace:
            return {"applied": 0, "signal": signal}
        n = 0
        for name, t in self.trace.items():
            w = params.get(name)
            if w is None or w.shape != t.shape:
                continue
            w.add_(self.lr * signal * t)
            n += 1
        self.trace = {k: v * self.decay for k, v in self.trace.items()}
        return {"applied": n, "signal": signal}


# ════════════════════════════════════════════════════════ 5. the session

class Loop:
    """One turn of the returning light: read → learn → contract → repair → record.

    Called after every crawl session. It never trains on Iddo's PC — the caller decides
    the device, and the fleet is where the weights move.
    """

    def __init__(self, model, scars: Scars | None = None, lr: float = 3e-4):
        self.model = model
        self.scars = scars or Scars()
        self.opt = torch.optim.Adam(model.parameters(), lr=lr)

    def read(self, page_ids: torch.Tensor, lens: str = "plain",
             host: str = "-") -> float:
        """1. JEPA — she learns from the page whether or not anyone ever scores it."""
        self.model.train()
        self.opt.zero_grad()
        loss = self.model.jepa_loss(page_ids)
        loss.backward()
        self.opt.step()
        with torch.no_grad():
            g, _, _, _ = self.model.tower(page_ids[:1])
        self.scars.leave_tag(lens, host, g[0])
        return float(loss)

    @torch.no_grad()
    def contract(self):
        """5. צמצום — pull every unit back toward its set-point, so the loop can run for
        months without eating itself. The relative weights (the memory) are preserved."""
        h = self.model.homeo
        for m in self.model.modules():
            for name, p in m.named_parameters(recurse=False):
                if p.dim() >= 2 and p.shape[-1] == h.run.numel():
                    h.contract(p.data)
        return h.health()

    def repair(self, sample) -> dict:
        """תיקון — find the vessels that shattered. Reported, never silently deleted."""
        from sefirot import Vessels
        return Vessels().inspect(self.model.tree, sample)

    def record(self, pages: int, jepa: float, note: str = ""):
        agree = self.scars.agreement()
        self.scars.db.execute(
            "INSERT INTO session(at,pages,jepa,agree,note) VALUES(?,?,?,?,?)",
            (time.time(), pages, jepa, agree.get("agreement") or -1.0, note))
        self.scars.db.commit()
        return agree

    def is_improving(self, k: int = 5) -> dict:
        """The only claim that matters: **is she actually getting better over time?**

        Compares the last k sessions' JEPA loss against the k before them. If it is not
        falling, this says so — a loop that reports progress it cannot show is worse
        than no loop.
        """
        rows = self.scars.db.execute(
            "SELECT jepa FROM session ORDER BY id DESC LIMIT ?", (2 * k,)).fetchall()
        if len(rows) < 2 * k:
            return {"sessions": len(rows), "verdict": "not enough history yet"}
        recent = sum(r[0] for r in rows[:k]) / k
        older = sum(r[0] for r in rows[k:]) / k
        return {"sessions": len(rows), "recent_jepa": recent, "older_jepa": older,
                "improving": recent < older,
                "verdict": "improving" if recent < older else "NOT improving — say so"}


if __name__ == "__main__":
    import os
    from miko import Miko
    from alma import encode_batch

    tmp = HERE / "_smoke_state.db"
    if tmp.exists():
        os.remove(tmp)
    scars = Scars(tmp)
    torch.manual_seed(0)

    print("— 2. scars: pain is written harder and forgotten slower —")
    now = time.time()
    scars.hurt("forum", "example.com", "timeout", now)
    scars.reward("primary", "arxiv.org", "found the paper", now)
    print(f"  appetite forum→example.com  = {scars.appetite('forum','example.com',now):+.3f}")
    print(f"  appetite primary→arxiv.org  = {scars.appetite('primary','arxiv.org',now):+.3f}")
    d30 = now + 30 * 86400
    print(f"  after 30 days: pain {scars.appetite('forum','example.com',d30):+.3f}"
          f"   pleasure {scars.appetite('primary','arxiv.org',d30):+.3f}"
          f"   ← pain persists, pleasure fades")

    print("\n— 4. curiosity goes where the seats DISAGREE, unless she was burnt —")
    dis = torch.tensor([0.2, 2.0, 2.0])
    rel = torch.tensor([0.9, 0.3, 0.3])
    app = torch.tensor([0.0, 0.0, -1.0])
    c = curiosity(dis, app, rel)
    for i, tag in enumerate(["relevant, agreed", "contested, fresh host", "contested, BURNT host"]):
        print(f"  {tag:<24} drive {float(c[i]):.3f}")

    print("\n— 3. Iddo's taps —")
    print(f"  before any tap: {scars.agreement()['note']}")
    scars.tap("water computer", "moniac.org", True, +0.4, 0.3)
    scars.tap("water computer", "cake.com", False, +0.2, 2.1)
    scars.tap("water computer", "spam.net", True, -0.1, 1.8)
    print(f"  after 3 taps  : {json.dumps(scars.agreement(), ensure_ascii=False)}")

    print("\n— 1+5. the loop turns: read, contract, repair, record —")
    m = Miko(d=48, depth=2, max_len=128)
    loop = Loop(m, scars)
    pages = encode_batch([
        "The MONIAC computed an economy with flowing water, tanks and valves.",
        "מחשב מים אנלוגי משתמש בזרימה כדי לחשב.",
        "Chocolate cake recipe, 200g flour."], 128)
    losses = []
    for turn in range(6):
        l = loop.read(pages, lens="primary", host="arxiv.org")
        losses.append(l)
        loop.record(pages=3, jepa=l, note=f"turn {turn}")
    print(f"  JEPA over 6 turns: {' → '.join(f'{x:.4f}' for x in losses)}")
    print(f"  captured tags on salience: {scars.capture('primary','arxiv.org')}")
    print(f"  after צמצום: {loop.contract()}")
    print(f"  broken vessels: {loop.repair((m.bind(pages), None)) or 'none'}")
    print(f"  IS SHE IMPROVING? {json.dumps(loop.is_improving(k=3), ensure_ascii=False)}")

    print("\n— 6. the third factor: local plasticity x ONE right/wrong scalar —")
    tf = ThreeFactor(m, lr=1e-3)
    lin = m.jepa[0]
    before = lin.weight.detach().clone()
    pre = torch.randn(16, m.d)
    post = lin(pre)
    tf.observe(pre, post, "w")
    moved_no_signal = tf.apply(0.0, {"w": lin.weight.data.T})
    print(f"  tag laid, NO signal yet   -> writes {moved_no_signal['applied']}, "
          f"weight moved {float((lin.weight-before).abs().max()):.2e}   <- a tag alone changes nothing")
    tf.apply(+1.0, {"w": lin.weight.data.T})
    print(f"  signal +1 (that was right)-> weight moved "
          f"{float((lin.weight-before).abs().max()):.2e}   <- the tag became a change")
    print("  no gradient of anything was computed. one scalar, local rule.")
    scars.db.close()          # Windows will not unlink an open sqlite file
    os.remove(tmp)
