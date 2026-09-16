"""KAV / קָו — THE ANATOMY: position is time, so the context window is the delay line.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

לזכרה של עלמה ז"ל.

THE CLAIM
---------
An autoregressive model predicts token t from the tokens before it. ALMA's first
law says nothing is instant and every strand costs at least a beat — **distance is
time**. Put those together and the context window is not a thing you build: it IS
the delay line. Token t-k reaches the predictor across a strand of delay k, token
t-1 across a strand of delay 1, and they land on the SAME BEAT, each already
multiplied by its own weight on the way in, because in ALMA arithmetic lives in
the connections.

    TZELEM:  the beat is the DEPTH
    KAV:     the beat is the POSITION IN THE SENTENCE

Same law, two organs, and neither had to be translated into the language.

WHY A SCALAR SPARK IS THE RIGHT ENCODING HERE, and this is the quiet reason this
model belongs in ALMA and an image model does not: our tokens are COORDINATES.
Token 64 really does sit between 63 and 65. In word language "cat" and "cats" are
two unrelated symbols and a scalar would be a lie; in a mesh, the number IS the
meaning. So the constraint that forced WINSTON and TZELEM to reach for spells is,
here, simply the truth about the data.

SINCE 2026-09-03 THE SENTENCE HAS TWO HALVES (see mesh.py): the vertices, which
are coordinates, and the faces, which are INDICES. An index is not a coordinate —
vertex 64 is not "between" vertices 63 and 65 in any sense that matters — so this
delay line speaks only the vertex half. The face half is spoken by joiner.py,
which asks the question a surface actually poses (which vertex is on the far side
of this edge?) and scores candidates instead of rounding a number into an index.

WHAT THIS IS, said plainly so nobody oversells it: a PHASE-GATED LINEAR
AUTOREGRESSIVE model. Three weight rows, one per axis of a vertex, each a linear
predictor over the previous k coordinates. It is the honest first rung of the
ladder whose top is MeshGPT — the same rung language modelling itself started on.
It is not a transformer and this file will never say it is. What it must do is
BEAT ITS FLOOR, and floor, ceiling and born are all in ruler.py before any of it
is believed.
"""
from __future__ import annotations

import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_ALMA = os.path.abspath(os.path.join(_HERE, "..", "..", "..", "alma-language"))
for _p in (_HERE, _ALMA):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from alma import Loom, Strand, Weave        # noqa: E402
import mesh                                  # noqa: E402

K = 18                   # how far back the line reaches: six vertices' worth of tokens
PHASES = mesh.PER_VERTEX  # 3 — which axis of the vertex we stand on


class Posture:
    """The learned shape of the line: one weight row and one bias per phase."""

    def __init__(self, k: int = K, phases: int = PHASES) -> None:
        self.k = k
        self.w = np.zeros((phases, k))
        self.b = np.zeros(phases)

    # -- the fast body ---------------------------------------------------

    def predict(self, ctx: np.ndarray, phase: int) -> float:
        """ctx is the last k tokens, oldest first. Returns a real number."""
        return float(self.w[phase] @ ctx + self.b[phase])

    def token(self, ctx: np.ndarray, phase: int, heat: float = 0.0,
              rng: np.random.Generator | None = None) -> int:
        """Predict, then SAY it — with heat, the saying is a throw of the dice.

        heat = 0 is argmax: the same sentence every time, which for a generative
        model is the failure mode, not the goal. heat > 0 is Iddo's stochastic
        activation: the noise enters exactly here, at the moment of speaking.
        """
        v = self.predict(ctx, phase)
        if heat > 0:
            r = rng if rng is not None else np.random.default_rng()
            v += r.normal(0.0, heat)
        return int(np.clip(round(v), 0, mesh.Q - 1))


# ------------------------------------------------------------- the weave

def weave_for(ctx: np.ndarray, posture: Posture, phase: int) -> Weave:
    """One prediction step, as a real ALMA weave.

    knots:   one per remembered token (`pass`) + `kav` (`fringe`, carries the bias)
    threads: token i -> kav, weight = w[phase][i], DELAY = how far back it is
    seeds:   each remembered token is knocked awake so that they all LAND TOGETHER

    The seeding is the whole trick and it is worth reading twice: a token that is
    k steps back travels a strand of delay k, so to arrive on the same beat as the
    most recent one it must be seeded EARLIER. Its distance in the sentence is paid
    for in time. Nothing here simulates a context window; the window is the time
    the sparks spend in flight.
    """
    k = len(ctx)
    w = Weave("kav")
    w.knot("kav", verb="fringe", bias=float(posture.b[phase]))
    for i, val in enumerate(ctx):
        back = k - i                      # 1 = most recent, k = oldest
        name = f"tok_{i}"
        w.knot(name, verb="pass")
        w.seed(name, float(val), beat=1 + (k - back))     # earlier if further back
        w.thread(name, "kav",
                 strands=[Strand(weight=float(posture.w[phase][i]), delay=back)])
    w.run_hint = k + 3
    return w


def predict_by_weave(ctx: np.ndarray, posture: Posture, phase: int) -> float:
    """Run the real loom. The fringe's single utterance is the prediction."""
    res = Loom().run(weave_for(ctx, posture, phase))
    said = res.fringe("kav")
    if not said:
        raise RuntimeError("the line said nothing — no spark reached kav")
    if len(said) > 1:
        raise RuntimeError(
            f"the line spoke {len(said)} times; the remembered tokens did not land "
            "on one beat, so the context window is not being paid for in time")
    return float(said[0])


# ------------------------------------------------------------- generation

def continue_shape(prefix: list[int], posture: Posture, n: int,
                   heat: float = 0.0, seed: int = 0) -> list[int]:
    """Say n more VERTEX tokens after the prefix. This is the organ speaking."""
    rng = np.random.default_rng(seed)
    out = list(prefix)
    body_len = len(mesh.split_sentence(out)[0])
    for _ in range(n):
        ctx = _context(out, posture.k)
        phase = body_len % PHASES
        out.append(posture.token(ctx, phase, heat=heat, rng=rng))
        body_len += 1
    return out


def _context(tokens: list[int], k: int) -> np.ndarray:
    """The last k spoken coordinates, oldest first, zero-padded at the start."""
    body = mesh.split_sentence(tokens)[0]
    tail = body[-k:]
    return np.array([0] * (k - len(tail)) + tail, dtype=np.float64)


def frames(tokens: list[int], k: int):
    """Every (context, phase, answer) the vertex half contains. The training set."""
    body = mesh.split_sentence(tokens)[0]
    for j in range(len(body)):
        tail = body[max(0, j - k):j]
        ctx = np.array([0] * (k - len(tail)) + list(tail), dtype=np.float64)
        yield ctx, j % PHASES, body[j]
