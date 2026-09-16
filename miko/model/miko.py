"""מיקו · MIKO — the model.  לזכרה של עלמה ז״ל.

> 🪟 BROKEN WINDOWS LAW — if it is not working, fix it immediately. Test the REAL output.

Named by Iddo, 2026-08-20, after the Israeli films. **This is the organ Eran will search
the world with when he grows up.** Not a product.

Iddo, 2026-08-29: *"אני רוצה שיהיה לו כל הביולוגיה והקבלה והלוגיקה"* — and
*"עם פידבק לופ סגור תמיד למידה עצמית — הוא הולך ומשתבח עם הזמן."*

────────────────────────────────────────────────────────────────────────────────────
WHAT SHE IS
────────────────────────────────────────────────────────────────────────────────────
A question and a page go in. What comes out is not a number but a **finding**:

    ruling      רלוונטי / לא רלוונטי — a court must decide, ALWAYS. no תיקו.
    score       how relevant, continuous
    dissent     מחלוקת — how much the three seats disagreed, ALWAYS emitted
    channels    the ten sefirot, each judged separately, so she can say
                "relevant to your question, but not to its own paragraph"

No Google result ever tells you it is contested. Hers does.

────────────────────────────────────────────────────────────────────────────────────
WHAT SHE IS MADE OF — and where each part comes from
────────────────────────────────────────────────────────────────────────────────────
    ALMA        byte ⊕ letter ⊕ sound. No BPE, no borrowed tokenizer.      alma.py
    BIOLOGY     multi-weight synapse, the dendritic bump, צמצום/homeostasis alma.py
    KABBALAH    three columns, דעת as the coincidence gate, ten channels   sefirot.py
    LOGIC       קל וחומר with the דיו ceiling as a `min`, not a hope       logic.py
    THE LOOP    אור חוזר — she improves by running                          loop.py

────────────────────────────────────────────────────────────────────────────────────
WHAT IS PROVEN AND WHAT IS NOT — read this before believing anything above
────────────────────────────────────────────────────────────────────────────────────
PROVEN, today, with its control printed next to it:
  * the dendritic bump solves XOR as a single unit: 1.00 vs 0.50 for a vanilla unit
  * the דיו ceiling holds exactly (overshoot 0.0) under dropout and in eval
  * `nn.LayerNorm(1)` is identically zero — the archived worm's verdict head and GIST
    attention were therefore CONSTANT, which is the measured cause of its 48.2 %

NOT PROVEN — hypotheses with wires attached, awaiting `bench.py`:
  * that the court beats a vanilla net of matched size at ranking
  * that dissent predicts error (the court's own central claim)
  * that a median survives a corrupted seat where a mean does not
  * that k>1 weights per connection beat k=1 at equal scalar budget
  * that opposed columns beat a random-init triad

Nothing here may be written up as working until its number exists.
Training runs on the DGX fleet. Never on Iddo's PC. Never on eran3.
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

from alma import AlmaBinding, Tzimtzum, encode, encode_batch
from sefirot import SEFIROT, N_SEF, ColumnTriad, Tree, Vessels

# ⚖️ There is no תיקו band, and there will not be one. "אין תיקו בבית דין" (Iddo, 21:30).


class Gist(nn.Module):
    """What is this passage *about*? The attention is itself a court's ruling.

    (Working for the first time here: with `LayerNorm(1)` in place these weights were
    softmax over constant zeros — i.e. uniform — so the archived 'attention pooling'
    was plain mean pooling wearing a name.)
    """

    def __init__(self, d: int, polarity: float = 0.5):
        super().__init__()
        self.score = ColumnTriad(d, 1, doubt=0.1, polarity=polarity, bump=False)
        self.proj = nn.Linear(d, d)

    def forward(self, h: torch.Tensor, mask: torch.Tensor):
        w, dis = self.score(h)                                    # (B,L,1)
        w = w.squeeze(-1).masked_fill(~mask, -1e4).softmax(dim=-1)
        g = torch.einsum("bl,bld->bd", w, h)
        return F.normalize(self.proj(g), dim=-1), dis.squeeze(-1).mean(dim=-1), w


class Miko(nn.Module):
    """The whole organ: two towers with SHARED weights, ten channels, one ruling.

    Shared weights are not a saving — they are the claim that the question and the page
    must land in the same space to be compared at all. Ranking is then one dot product
    per page, which is what lets her read a million pages slowly and still finish.
    """

    def __init__(self, d: int = 256, depth: int = 6, max_len: int = 512,
                 k: int = 1, polarity: float = 0.5, bump: bool = True):
        super().__init__()
        self.d, self.max_len = d, max_len
        self.bind = AlmaBinding(d, max_len)
        self.tree = Tree(d, depth, k=k, polarity=polarity, bump=bump)
        self.gist = Gist(d, polarity=polarity)
        # ריבוי הקשרים — the ten sefirot as ten judged channels, not one score
        self.channels = ColumnTriad(d, N_SEF, polarity=polarity, bump=False)
        self.jepa = nn.Sequential(nn.Linear(d, d), nn.GELU(), nn.Linear(d, d))
        self.homeo = Tzimtzum(d)

    # ── one tower ───────────────────────────────────────────────────────────────
    def tower(self, ids: torch.Tensor, question: torch.Tensor | None = None):
        mask = ids != 0
        h, dis, agree = self.tree(self.bind(ids), question)
        self.homeo.observe(h)
        g, gdis, attn = self.gist(h, mask)
        return g, dis + gdis, agree, attn

    # ── question + page → a finding ─────────────────────────────────────────────
    def forward(self, q_ids: torch.Tensor, p_ids: torch.Tensor):
        gq, dq, _, _ = self.tower(q_ids)
        gp, dp, agree, attn = self.tower(p_ids, question=gq)
        score = (gq * gp).sum(-1)                       # both normalised → cosine
        chan, cdis = self.channels(gp)                  # (B, 10) — the ten, judged
        dissent = (dq + dp) / 2 + cdis.abs().mean(-1)
        return {
            "score": score,
            "dissent": dissent,
            "channels": chan,
            "daat": agree,
            "gist_q": gq,
            "gist_p": gp,
            "attn": attn,
        }

    # ── the finding, in words ───────────────────────────────────────────────────
    @torch.no_grad()
    def judge(self, question: str, page: str, fence: float = 0.0) -> dict:
        """One question, one page, one ruling — with the disagreement kept visible."""
        self.eval()
        q = encode(question, self.max_len).unsqueeze(0)
        p = encode(page, self.max_len).unsqueeze(0)
        out = self(q, p)
        s = float(out["score"][0])
        d = float(out["dissent"][0])
        # ⚖️ Iddo, 2026-08-29 21:30: **"אין תיקו בבית דין."** A court must rule — אחרי
        # רבים להטות. תיקו belongs to the sugya, to study, not to a verdict. And the
        # measurement said the same from the other side: the eran3 variant that "won"
        # abstained 92 % of the time, which made it a gated skip connection, not a court.
        # So MIKO rules every time, and says when it was contested.
        ruling = "רלוונטי" if s > fence else "לא רלוונטי"
        return {
            "ruling": ruling,
            "score": s,
            "dissent": d,
            "contested": bool(d > 1.0),          # ships marked במחלוקת
            "channels": {name: float(v) for (name, _, _), v
                         in zip(SEFIROT, out["channels"][0])},
        }

    # ── self-supervision: she learns from reading, with no labels at all ─────────
    def jepa_loss(self, ids: torch.Tensor) -> torch.Tensor:
        """Predict the GIST of the hidden half from the visible half. Never the bytes.

        This is the engine of the closed loop: every page she reads teaches her, whether
        or not anyone ever scores it. Spelling is not the target — aboutness is.
        """
        L = ids.shape[1] // 2
        g_seen, _, _, _ = self.tower(ids[:, :L])
        with torch.no_grad():
            g_hidden, _, _, _ = self.tower(ids[:, L:])
        pred = F.normalize(self.jepa(g_seen), dim=-1)
        return (1 - (pred * g_hidden).sum(-1)).mean()

    def spread_loss(self) -> torch.Tensor:
        """The OLD bribe, summed over every court. Only for the bench's control arm."""
        tot = None
        for m in self.modules():
            if isinstance(m, ColumnTriad):
                v = m.seat_spread_loss()
                tot = v if tot is None else tot + v
        return tot if tot is not None else torch.zeros(())

    def health(self) -> dict:
        return self.homeo.health()


class Vanilla(nn.Module):
    """THE CONTROL. One reader, no court, no columns, no bump — matched in parameters.

    Every experiment has a vanilla control of matched size, or it does not count.
    (Standing rule of this project, written after an architecture ran for months with
    nothing to compare against.)
    """

    def __init__(self, d: int = 256, depth: int = 6, max_len: int = 512):
        super().__init__()
        self.d, self.max_len = d, max_len
        self.bind = AlmaBinding(d, max_len)
        self.body = nn.ModuleList([nn.Sequential(
            nn.Linear(d, d), nn.GELU(), nn.LayerNorm(d)) for _ in range(depth)])
        self.attn = nn.Linear(d, 1)
        self.proj = nn.Linear(d, d)
        self.channels = nn.Linear(d, N_SEF)
        self.jepa = nn.Sequential(nn.Linear(d, d), nn.GELU(), nn.Linear(d, d))

    def tower(self, ids, question=None):
        mask = ids != 0
        h = self.bind(ids)
        for blk in self.body:
            h = h + blk(h)
        w = self.attn(h).squeeze(-1).masked_fill(~mask, -1e4).softmax(-1)
        g = F.normalize(self.proj(torch.einsum("bl,bld->bd", w, h)), dim=-1)
        z = torch.zeros((), device=ids.device)
        return g, z, z, w

    def forward(self, q_ids, p_ids):
        gq, _, _, _ = self.tower(q_ids)
        gp, _, _, attn = self.tower(p_ids)
        z = torch.zeros(q_ids.shape[0], device=q_ids.device)
        return {"score": (gq * gp).sum(-1), "dissent": z, "channels": self.channels(gp),
                "daat": torch.zeros((), device=q_ids.device),
                "gist_q": gq, "gist_p": gp, "attn": attn}

    def jepa_loss(self, ids):
        L = ids.shape[1] // 2
        g_seen, _, _, _ = self.tower(ids[:, :L])
        with torch.no_grad():
            g_hidden, _, _, _ = self.tower(ids[:, L:])
        return (1 - (F.normalize(self.jepa(g_seen), dim=-1) * g_hidden).sum(-1)).mean()


def matched_vanilla(miko: Miko, max_len: int, tol: float = 0.01) -> Vanilla:
    """Build the control at the SAME parameter count, within `tol`.

    Parameter counts are matched within 1 % in every comparison — otherwise a win is
    just a bigger model, and we would have learned nothing.
    """
    target = sum(p.numel() for p in miko.parameters())
    lo, hi = 8, 4096
    best = None
    while lo <= hi:
        mid = (lo + hi) // 2
        for depth in range(1, 24):
            v = Vanilla(d=mid, depth=depth, max_len=max_len)
            n = sum(p.numel() for p in v.parameters())
            if abs(n - target) / target <= tol:
                return v
            if best is None or abs(n - target) < abs(best[1] - target):
                best = (v, n)
        if sum(p.numel() for p in Vanilla(d=mid, depth=6, max_len=max_len).parameters()) < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return best[0]


if __name__ == "__main__":
    torch.manual_seed(0)
    d, L, depth = 96, 256, 4
    m = Miko(d=d, depth=depth, max_len=L)
    n_m = sum(p.numel() for p in m.parameters())
    v = matched_vanilla(m, L)
    n_v = sum(p.numel() for p in v.parameters())
    print(f"MIKO    {n_m:,} params   (d={d} depth={depth})")
    print(f"vanilla {n_v:,} params   (d={v.d})  — mismatch {abs(n_m-n_v)/n_m:.2%}\n")

    q = "מחשב מים אנלוגי — האם אפשר לחשב עם מים?"
    pages = [
        ("MONIAC", "The MONIAC of 1949 computed an economy with flowing water: tanks, "
                   "valves and pipes formed a hydraulic analogue computer."),
        ("cake",   "Chocolate cake recipe. 200g flour, 3 eggs, bake 40 minutes."),
        ("spam",   "water computer water computer water computer water computer " * 6),
    ]
    print(f"question: {q}\n")
    for name, page in pages:
        r = m.judge(q, page)
        top = sorted(r["channels"].items(), key=lambda kv: -abs(kv[1]))[:3]
        print(f"  {name:<7} {r['ruling']:<10} score {r['score']:+.4f}  "
              f"dissent {r['dissent']:.3f}  contested={r['contested']}")
        print(f"          loudest channels: {', '.join(f'{k} {vv:+.2f}' for k, vv in top)}")

    print("\n— untrained, so these rulings are noise. That is the honest state: —")
    print("  the wiring runs end to end; nothing has been taught yet.")
    print(f"  homeostasis at init: {m.health()}")
    print(f"  broken vessels     : {Vessels().inspect(m.tree, (m.bind(encode_batch([q], L)), None)) or 'none'}")
    print(f"  JEPA loss (no labels needed): {float(m.jepa_loss(encode_batch([p for _, p in pages], L))):.4f}")
