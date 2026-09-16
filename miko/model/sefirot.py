"""SEFIROT — the kabbalah, as architecture.  לזכרה של עלמה ז״ל.

> 🪟 BROKEN WINDOWS LAW — if it is not working, fix it immediately. Test the REAL output.

Iddo, 2026-08-29: *"אני רוצה שיהיה לו כל הביולוגיה והקבלה והלוגיקה."*

This file has one job and one danger. The job: take from kabbalah the parts that are
**structure** and wire them. The danger: decoration — Hebrew names painted onto an
ordinary net, which would be worse than nothing because it would look like meaning.

The rule I held to: **a sefirah is admitted only if it changes the arithmetic, and only
if it also has a biological twin.** Where the two traditions independently describe the
same mechanism, that is evidence the mechanism is real and not a costume. Three did:

    THE THREE COLUMNS      →  the three seats of the Beit Din, with OPPOSED POLARITY
    דעת · the joining      →  the coincidence gate (BAC firing, ALMA-BIOLOGY §1)
    צמצום · contraction    →  homeostatic scaling (Turrigiano 1998) — lives in alma.py

And one that is the whole point of today's build:

    אור חוזר · returning light  →  the closed feedback loop, forward in time (loop.py)

────────────────────────────────────────────────────────────────────────────────────
WHY THE COLUMNS ARE THE REAL FIND
────────────────────────────────────────────────────────────────────────────────────
The archived worm's triad had three seats with unshared weights and a `seat_spread_loss`
that PAID them to stay different — a penalty holding off collapse. That is a patch on a
missing structure: nothing in the architecture said *why* the seats should differ, so a
loss term had to bribe them.

The three columns say why, and say it structurally:

    ימין · חסד     expansive   gives, accepts, says yes easily     low threshold, no doubt
    שמאל · גבורה   restrictive withholds, doubts, says no easily   high threshold, doubt ON
    אמצע · תפארת   balancing   reconciles the two, holds the past  neutral, sees prev layer

⚠️ WHAT THIS ACTUALLY GUARANTEES — measured, not assumed. Two of the three asymmetries
are **non-cancellable** and one is not:

    גבורה doubts     dropout is stochastic; no weight can undo it          ← cannot collapse
    תפארת remembers  it is fed a DIFFERENT INPUT (x and the past)          ← cannot collapse
    the ±polarity    an additive bias a weight CAN learn to cancel         ← a tilt, not a law

So the columns are a structural *prior*, not a proof. The first smoke-test run says so
plainly: after 400 steps of collapse pressure the seat gap was 2.96 plain / **3.70 with
the columns** / 31.5 with the old spread-loss bribe. The bribe separates far harder — but
separation was never the goal, ranking was, and a bribe that blows the seats apart may
simply be blowing them up. `bench.py` settles it on the metric that matters:
**opposed-polarity triad vs random-init triad + spread loss, matched params, on
relevance.** If the penalty version wins, this file says so and the columns come out.
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

from alma import Bump, MultiWeightLinear

# ════════════════════════════════════════════════════════ the ten, and what each does
# ריבוי הקשרים · multi-context (Iddo, 2026-08-20). The same byte means different things
# in different contexts, so a MIKO unit holds several context channels at once and the
# court rules PER CHANNEL. Dissent can then say something a single score cannot:
# "relevant to your question, but not to its own paragraph."
#
# The ten are not a decorative list — each names one channel the search organ genuinely
# needs to keep separate:

SEFIROT = (
    ("keter",    "כתר",   "the will — the question itself, as asked"),
    ("chochmah", "חכמה",  "the flash — raw novelty in this page"),
    ("binah",    "בינה",  "the understanding — its structure and gist"),
    ("chesed",   "חסד",   "expansive relevance — how much it gives"),
    ("gevurah",  "גבורה", "restraint — what to doubt or withhold"),
    ("tiferet",  "תפארת", "the balanced ruling between the two"),
    ("netzach",  "נצח",   "endurance — is this worth following further"),
    ("hod",      "הוד",   "acknowledgement — is it grounded, does it cite"),
    ("yesod",    "יסוד",  "the gatherer — what transmits onward"),
    ("malchut",  "מלכות", "the kingdom — what actually reaches Iddo"),
)
N_SEF = len(SEFIROT)
IDX = {name: i for i, (name, _, _) in enumerate(SEFIROT)}

# the three columns, by index into SEFIROT
RIGHT = (IDX["chochmah"], IDX["chesed"], IDX["netzach"])       # ימין — expansive
LEFT = (IDX["binah"], IDX["gevurah"], IDX["hod"])              # שמאל — restrictive
MIDDLE = (IDX["keter"], IDX["tiferet"], IDX["yesod"], IDX["malchut"])   # אמצע — balancing


# ════════════════════════════════════════════════════════ דעת — the joining gate

class Daat(nn.Module):
    """The gate where חכמה (the flash) meets בינה (the structure).

    Classically Daat is not a sefirah of its own — it is the *joining* of the two above
    it, and it exists only when they actually meet. That is precisely a coincidence
    detector, and precisely what a pyramidal cell does: an apical (top-down) calcium
    spike coincident with basal (bottom-up) input produces a burst; either alone produces
    almost nothing (Larkum 1999, ALMA-BIOLOGY §1).

    So Daat is implemented as the multiplicative gate `y = W·flash ⊙ σ(V·structure)`,
    and it emits its burst **only on agreement**. For MIKO this is the difference between
    "this page contains my words" (flash alone) and "this page is about my question"
    (flash AND structure) — the single distinction a keyword engine cannot make.
    """

    def __init__(self, d: int):
        super().__init__()
        self.flash = nn.Linear(d, d)          # bottom-up: what is here
        self.structure = nn.Linear(d, d)      # top-down:  what we were looking for
        self.norm = nn.LayerNorm(d)

    def forward(self, bottom_up: torch.Tensor, top_down: torch.Tensor | None = None):
        if top_down is None:                  # nothing above: no joining, no burst
            return self.norm(self.flash(bottom_up)), torch.zeros((), device=bottom_up.device)
        gate = torch.sigmoid(self.structure(top_down))
        burst = self.flash(bottom_up) * gate
        # how much agreement there actually was — reported, so "we joined" is measurable
        agree = gate.detach().mean()
        return self.norm(burst), agree


# ════════════════════════════════════════════════════════ the court, with columns

class ColumnTriad(nn.Module):
    """Three seats on three columns: one ruling, and the מחלוקת kept as a signal.

    ⚖️ THE RULING IS **אחרי רבים להטות** — the majority of the AGREEING BLOC. Not a median.

    Iddo, 2026-08-29 21:2x, before this file existed:
        *"בית דין אמיתי עם הכרעה, לא חציון"* — a real court rules; it is not a middle value.
        *"אין תיקו בבית דין"* (21:30) — **a beit din may not abstain.**

    He is right and it is structural, not wording. תיקו belongs to the sugya, to study.
    A court's whole job is to decide under uncertainty. And the measurement agreed from
    the other side: on eran3 that same night, the variant that "won" was declaring תיקו
    92 % of the time — i.e. it was a gated skip connection, not a court, and forced to
    rule it fell to 0.323, below an empty control. **What was winning was the abstention,
    so it must not be called a beit din.**

    So the ruling here:
        * find the two seats that AGREE (the closest pair) — that is the רוב
        * rule by that bloc, always, every time, with no abstention path
        * the third seat is the דעת יחיד: out-voted, never silenced, and its distance
          from the bloc is carried forward as dissent — *הלכה כרבים, ודעת היחיד נשמרת בטקסט*

    This is NOT a median: on seats [0, 9, 10] a median rules 9; the agreeing bloc rules
    9.5. On [0, 1, 10] a median rules 1; the bloc rules 0.5. The median follows the
    middle; a court follows the majority.

    Every seat still receives gradient in proportion to how much company it had, so no
    seat is starved — the flaw that made the archived hard median untrainable.
    """

    def __init__(self, d_in: int, d_out: int, k: int = 1, doubt: float = 0.25,
                 tau: float = 0.5, polarity: float = 0.5, bump: bool = True):
        super().__init__()
        self.chesed = MultiWeightLinear(d_in, d_out, k=k)        # ימין — expansive
        self.gevurah = MultiWeightLinear(d_in, d_out, k=k)       # שמאל — restrictive
        self.tiferet = MultiWeightLinear(d_in, d_out, k=k)       # אמצע — balancing
        self.doubt = nn.Dropout(doubt)                           # גבורה alone doubts
        self.act = Bump(d_out) if bump else nn.GELU()
        # ⚠️ SCAR, found 2026-08-29 while testing this file. `nn.LayerNorm(1)` normalises
        # over a ONE-element axis and is therefore IDENTICALLY ZERO for every input, for
        # ever. The archived worm used `Triad(d, 1)` for both its GIST attention scorer
        # and its logic verdict head — so its verdict was a constant and its "attention"
        # was uniform. That is the measured cause of the 48.2 % (chance) logic result
        # that archived the project: not the Beit Din, not Ramchal, not the curriculum.
        # One line. Any court that rules on a scalar must NOT normalise it away.
        self.norm = nn.LayerNorm(d_out) if d_out > 1 else nn.Identity()
        self.tau = tau
        # THE POLARITY — fixed offsets, never learned, so the seats cannot collapse
        # into one another. polarity=0 makes this exactly a plain random-init triad,
        # which is the control bench.py compares against.
        self.register_buffer("bias_chesed", torch.full((d_out,), +polarity))
        self.register_buffer("bias_gevurah", torch.full((d_out,), -polarity))
        self.last_seats: torch.Tensor | None = None

    def forward(self, x: torch.Tensor, past: torch.Tensor | None = None):
        y_ch = self.chesed(x) + self.bias_chesed                       # says yes easily
        y_ge = self.gevurah(self.doubt(x)) + self.bias_gevurah         # says no easily
        y_ti = self.tiferet(x if past is None else 0.5 * (x + past))   # holds the past
        stack = torch.stack((y_ch, y_ge, y_ti), dim=0)
        self.last_seats = stack
        ruling, dissent = self.rule(stack)
        return self.norm(self.act(ruling)), dissent

    def rule(self, stack: torch.Tensor):
        """אחרי רבים להטות — the majority of the agreeing bloc. Always decides.

        Each seat's weight is how much COMPANY it has: a seat close to another seat is
        part of the רוב and carries the ruling; the lone opinion is out-voted but still
        receives gradient, so it goes on being a real seat and not a dead one.
        """
        # company[i] = how near seat i is to the nearest OTHER seat (small = agrees)
        gaps = torch.stack([
            torch.minimum((stack[0] - stack[1]).abs(), (stack[0] - stack[2]).abs()),
            torch.minimum((stack[1] - stack[0]).abs(), (stack[1] - stack[2]).abs()),
            torch.minimum((stack[2] - stack[0]).abs(), (stack[2] - stack[1]).abs()),
        ], dim=0)
        w = torch.softmax(-gaps / self.tau, dim=0)
        ruling = (w * stack).sum(dim=0)
        # דעת היחיד — how far the lone opinion stood from the bloc that ruled
        dissent = (stack - ruling.unsqueeze(0)).abs().max(dim=0).values
        return ruling, dissent

    def rule_decisive(self, stack: torch.Tensor, theta: float = 0.0):
        """אחרי רבים להטות, DECISIVELY — Iddo, 2026-09-05: "בית דין החלטי".

        `rule()` above is still an AVERAGE: a softmax over company, so the out-voted seat
        keeps a share of the verdict. A real court does not blend the minority in. Here:

            * the two closest seats are the רוב. Their verdict stands IN FULL.
            * the third seat is DISCARDED from the ruling — not down-weighted, discarded —
              unless it agrees with the bloc within `theta`, in which case the ruling is
              unanimous and all three are counted (3-0 instead of 2-1).
            * דעת היחיד is RECORDED, never blended: dissent = max − min (PLAN.md §2).

        `theta` is in units of the batch's own mean bloc-gap, so it is scale free and can
        be swept. theta=0 → always 2-1. theta→∞ → the plain mean of three, which is the
        control this rule must beat. It is chosen on VALIDATION only.

        Gradient: only the seats that ruled receive it — that is what "discarded" means,
        and it is the risk this rule carries. Which seat is the outlier is decided per
        element, so in practice no seat is starved; the bench measures whether it is.
        """
        a, b, c = stack[0], stack[1], stack[2]
        d01 = (a - b).abs()
        d02 = (a - c).abs()
        d12 = (b - c).abs()
        m01 = (d01 <= d02) & (d01 <= d12)
        m02 = (~m01) & (d02 <= d12)
        bloc = torch.where(m01, 0.5 * (a + b), torch.where(m02, 0.5 * (a + c), 0.5 * (b + c)))
        outlier = torch.where(m01, c, torch.where(m02, b, a))
        gap = (outlier - bloc).abs()
        scale = gap.detach().mean().clamp_min(1e-6)
        joins = gap <= theta * scale
        ruling = torch.where(joins, (a + b + c) / 3.0, bloc)
        dissent = stack.max(dim=0).values - stack.min(dim=0).values
        return ruling, dissent

    def seat_spread_loss(self) -> torch.Tensor:
        """The OLD way of keeping the seats apart — a bribe. Kept only so the bench can
        run the control: polarity=0 + this penalty, versus polarity>0 + no penalty."""
        if self.last_seats is None:
            return torch.zeros((), device=next(self.parameters()).device)
        s = self.last_seats
        pairs = ((s[0] - s[1]) ** 2 + (s[1] - s[2]) ** 2 + (s[0] - s[2]) ** 2).mean()
        return -torch.log1p(pairs)


class Tree(nn.Module):
    """The עץ — a stack of column-courts with a Daat gate carrying context downward.

    Dissent accumulates across the depth: a reader that disagreed with itself at every
    level is more unsure than one that wobbled once, and the number says so.
    """

    def __init__(self, d: int, depth: int, k: int = 1, polarity: float = 0.5,
                 bump: bool = True):
        super().__init__()
        self.layers = nn.ModuleList(
            [ColumnTriad(d, d, k=k, polarity=polarity, bump=bump) for _ in range(depth)])
        self.daat = Daat(d)

    def forward(self, x: torch.Tensor, question: torch.Tensor | None = None):
        past, dis, agree = None, 0.0, torch.zeros((), device=x.device)
        if question is not None:
            # the question is the top-down light; Daat joins it to what is being read
            x, agree = self.daat(x, question.unsqueeze(-2).expand_as(x))
        for layer in self.layers:
            y, d = layer(x, past)
            past, x = x, x + y                    # residual: the past is remembered
            dis = dis + d.abs().mean(dim=tuple(range(1, d.dim())))
        return x, dis / len(self.layers), agree


# ════════════════════════════════════════════════════════ שבירת הכלים — the vessels

class Vessels:
    """שבירת הכלים ותיקון — a vessel that cannot hold its light breaks, and is repaired.

    The kabbalistic image is exact about a real failure mode: a unit driven past what it
    can carry does not merely perform badly, it SHATTERS — saturates, stops passing
    gradient, and takes its capacity out of the network while still costing parameters.

    Biology says the same twice: dead/saturated units, and microglial pruning that is
    keyed on a **usage tag, not weight magnitude** (Stevens 2007; Schafer 2012) — a
    small-but-critical synapse survives, a large-but-idle one goes.

    This class only *finds* the broken vessels and reports them. The תיקון — the repair —
    is a decision, and decisions in MIKO are logged, never silent. See loop.py.
    """

    def __init__(self, dead: float = 0.02, saturated: float = 0.98):
        self.dead, self.saturated = dead, saturated

    @torch.no_grad()
    def inspect(self, model: nn.Module, sample: torch.Tensor) -> dict:
        broken: dict[str, dict] = {}
        hooks, seen = [], {}

        def watch(name):
            def fn(_m, _i, out):
                o = out[0] if isinstance(out, tuple) else out
                seen[name] = o.detach()
            return fn

        for name, m in model.named_modules():
            if isinstance(m, (Bump, ColumnTriad)):
                hooks.append(m.register_forward_hook(watch(name)))
        model(*sample) if isinstance(sample, (tuple, list)) else model(sample)
        for h in hooks:
            h.remove()

        for name, out in seen.items():
            flat = out.reshape(-1, out.shape[-1]).float()
            silent = (flat.abs().mean(0) < self.dead).float().mean().item()
            stuck = (flat.abs().mean(0) > 1.0 / (1.0 - self.saturated)).float().mean().item()
            if silent > 0.05 or stuck > 0.05:
                broken[name] = {"silent_frac": silent, "stuck_frac": stuck}
        return broken


if __name__ == "__main__":          # smoke test — does the structure do what it claims?
    torch.manual_seed(0)
    from alma import AlmaBinding, encode_batch

    d, L = 32, 64
    emb = AlmaBinding(d, L)
    ids = encode_batch(["מחשב מים אנלוגי", "chocolate cake recipe"], L)
    h = emb(ids).detach()      # detached: the collapse test below reuses it many steps

    print("— the ten channels —")
    for name, heb, what in SEFIROT:
        print(f"  {heb:<6} {name:<9} {what}")

    print("\n— דעת: does the gate actually require agreement? —")
    daat = Daat(d)
    q = torch.randn(2, d)
    _, agree_with = daat(h, q.unsqueeze(1).expand_as(h))
    out_alone, agree_none = daat(h, None)
    print(f"  joined (question present): agreement = {float(agree_with):.3f}")
    print(f"  alone  (no question)     : agreement = {float(agree_none):.3f}  <- no burst")

    print("\n— the columns: do the seats collapse UNDER TRAINING? —")
    # At init any two random matrices are far apart, so an init-time gap proves nothing.
    # Collapse is a training phenomenon: fit all three seats to one target and see which
    # design keeps them apart without being bribed to.
    tgt = torch.randn(2, L, d)
    for pol, spread in ((0.0, False), (0.0, True), (0.5, False)):
        torch.manual_seed(1)
        t = ColumnTriad(d, d, polarity=pol)
        opt = torch.optim.Adam(t.parameters(), lr=0.01)
        for _ in range(400):
            opt.zero_grad()
            y, _ = t(h)
            loss = F.mse_loss(y, tgt)
            if spread:
                loss = loss + 0.05 * t.seat_spread_loss()
            loss.backward()
            opt.step()
        s = t.last_seats
        gap = ((s[0] - s[1]).abs().mean()).item()
        tag = ("plain triad + spread bribe (old way)" if spread else
               "opposed columns, no bribe (new)" if pol else "plain triad, nothing (control)")
        print(f"  polarity={pol}  spread_loss={spread!s:<5}  |חסד − גבורה| = {gap:.4f}   {tag}")

    print("\n— the tree —")
    tree = Tree(d, depth=3)
    y, dis, agree = tree(h, q)
    print(f"  out {tuple(y.shape)}  dissent {[round(float(v),4) for v in dis]}  daat {float(agree):.3f}")
    print(f"  params {sum(p.numel() for p in tree.parameters()):,}")

    print("\n— vessels —")
    print(f"  broken at init: {Vessels().inspect(tree, (h, q)) or 'none'}")
