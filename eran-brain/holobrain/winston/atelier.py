"""THE BODY — WINSTON's canvas and stroke table, in numpy, zero torch.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

לזכרה של עלמה ז"ל. The organ that paints in her language must not lie about
what it is: this file is a SECOND BODY for the painter's mathematics — the same
decode, the same segment ink, the same alpha-over compositing, the same loss and
the same floors as `alma-draughtsman/winston/winston.py` — rewritten in numpy so
the weave can run on a machine that is not allowed to carry torch (the PC; see
feedback_no_training_on_pc). A second decoder is a drift risk and the risk is
named, not hidden: the eran4 equality test (tests/test_eran4_pin.py,
test_one_decoder) locks every number here to the torch original, so a silent
divergence screams instead of painting quietly wrong for a month.

What is honest here and measured, not assumed:

  * decode is winston.decode verbatim: anchor tanh*0.95, reach tanh*MAX_REACH
    (0.16) cumsum'd, clamp to +/-0.99; width (0.012 + 0.10*sigmoid)*wmul with
    wmul = linspace(2.6, 0.55, n_total) — coarse-to-fine lives in the INDEX;
    colour = sigmoid. A stroke is a mark, not a beam.
  * ink is distance-to-SEGMENT, never sampled dots. The dot-cloud trick scored
    86% on 2026-08-30 drawing constellations no person would call a letter;
    pen_check() measures for it on every sheet rather than assuming it away.
  * compositing is sequential alpha-over onto white paper in FIRE ORDER, which
    is stroke-index order — later strokes lie on top, exactly the closed form
    winston.composite computes in chunks. Same mathematics, not an approximation.
  * the loss is winston's training loss: mse + detail_w * busy-weighted error
    + colour hinge charged only on UNDER-saturation, scaled by n_alive/n_total
    (the demand for colour arrives as the strokes that can afford it do).
  * floors() computes BLANK and BLUR the way winston.floors does. BLANK must be
    beaten or nothing happened. The BUSY tenth is measured because on 08-31 a
    run said PASSES while the walking people were gone.

Placement craft, declared: a fresh stroke's colour raw-params are seeded from
the subject's colour under its own anchor (a painter dips the brush before
touching canvas). The loss still judges every trial; nothing is scored by this.

PIL, not cv2 — cv2.imread cannot open a Hebrew path on Windows and every
photograph in this workspace lives under a Hebrew folder name. Seeded RNG 1933.
"""
from __future__ import annotations

import os

import numpy as np

SIZE = 32                 # proof-of-life default; the easel may ask for more
POINTS = 6                # control points per stroke — a stroke is a curve
PARAMS = POINTS * 2 + 1 + 3          # xy per point, width, rgb  -> 16
MAX_REACH = 0.16          # how far one step of a stroke may travel, in [-1,1]
SEED = 1933
WIGGLE_SCALE = 0.35       # perturbation sigma per unit of arriving spark


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


def load(path: str, size: int) -> np.ndarray:
    """Read an image to (size,size,3) float64 in [0,1]. PIL only (Hebrew paths)."""
    from PIL import Image
    im = Image.open(path).convert("RGB")
    s = min(im.size)
    im = im.crop(((im.width - s) // 2, (im.height - s) // 2,
                  (im.width + s) // 2, (im.height + s) // 2)).resize(
        (size, size), Image.LANCZOS)
    return np.asarray(im, np.float64) / 255.0


# ------------------------------------------------------------------ decode

def decode(p: np.ndarray, n_total: int, idx: np.ndarray):
    """Stroke parameters -> geometry. The numpy mirror of winston.decode.

    p: (m, PARAMS) raw params; idx: (m,) GLOBAL stroke indices (a stroke keeps
    its own brush: wmul is indexed by where the stroke sits in the FULL budget,
    exactly as winston passes n_total when rendering a truncated prefix).
    Returns xy (m,POINTS,2), w (m,), col (m,3).
    """
    p = np.asarray(p, np.float64).reshape(-1, PARAMS)
    idx = np.asarray(idx, int).reshape(-1)
    raw = p[:, :POINTS * 2].reshape(-1, POINTS, 2)
    anchor = np.tanh(raw[:, :1]) * 0.95
    reach = np.tanh(raw[:, 1:]) * MAX_REACH
    xy = np.concatenate([anchor, anchor + np.cumsum(reach, axis=1)],
                        axis=1).clip(-0.99, 0.99)
    wmul = np.linspace(2.6, 0.55, n_total)[idx]
    w = (0.012 + 0.10 * _sigmoid(p[:, POINTS * 2])) * wmul
    col = _sigmoid(p[:, POINTS * 2 + 1:])
    return xy, w, col


def grid(size: int) -> np.ndarray:
    """The pixel lattice in [-1,1], same ordering as winston's meshgrid."""
    g = np.linspace(-1.0, 1.0, size)
    gy, gx = np.meshgrid(g, g, indexing="ij")
    return np.stack([gx, gy], -1).reshape(-1, 2)


def stroke_alpha(xy: np.ndarray, w: float, px: np.ndarray,
                 soft: float = 1.0) -> np.ndarray:
    """One stroke's coverage: distance to the nearest SEGMENT, never to dots."""
    a0, a1 = xy[:-1], xy[1:]                          # (P-1, 2)
    d = a1 - a0
    dd = (d * d).sum(-1).clip(min=1e-6)
    v = px[None, :, :] - a0[:, None, :]               # (P-1, npx, 2)
    t = ((v * d[:, None, :]).sum(-1) / dd[:, None]).clip(0.0, 1.0)
    near = a0[:, None, :] + t[..., None] * d[:, None, :]
    d2 = ((px[None, :, :] - near) ** 2).sum(-1).min(axis=0)
    return np.exp(-d2 / (2.0 * w * w * soft))


def render_geometry(strokes, size: int, soft: float = 1.0) -> np.ndarray:
    """Sequential alpha-over of decoded strokes onto white, in index order.

    `strokes`: iterable of (index, xy (POINTS,2), w, col (3,)) sorted or not —
    they are painted in ascending index, which IS fire order, which IS the
    back-to-front z winston.composite computes. Returns (size,size,3).
    """
    px = grid(size)
    canvas = np.ones((px.shape[0], 3))
    for _, xy, w, col in sorted(strokes, key=lambda s: s[0]):
        a = stroke_alpha(np.asarray(xy, float), float(w), px, soft)[:, None]
        canvas = canvas * (1.0 - a) + np.asarray(col, float) * a
    return canvas.reshape(size, size, 3)


# ------------------------------------------------------------------ the ruler

def mse(y: np.ndarray, x: np.ndarray) -> float:
    return float(((y - x) ** 2).mean())


def _boxmean_replicate(e: np.ndarray, k: int) -> np.ndarray:
    """k x k box mean, stride 1, replicate padding — F.avg_pool2d after pad."""
    p = k // 2
    ep = np.pad(e, p, mode="edge")
    c = np.pad(ep, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    h, w = e.shape
    return (c[k:k + h, k:k + w] - c[0:h, k:k + w]
            - c[k:k + h, 0:w] + c[0:h, 0:w]) / (k * k)


def detail(x: np.ndarray, k: int = 5) -> np.ndarray:
    """Where the picture is BUSY: mean-1 weight map (H,W,1). winston.detail.

    Exists because plain MSE sold the girl for the wall (measured 2026-08-31):
    a face is 3% of the pixels, a wall is 40%.
    """
    g = x.mean(-1)
    dx = np.zeros_like(g)
    dx[:, :-1] = g[:, 1:] - g[:, :-1]
    dy = np.zeros_like(g)
    dy[:-1, :] = g[1:, :] - g[:-1, :]
    e = _boxmean_replicate(np.abs(dx) + np.abs(dy), k)
    return (e / max(e.mean(), 1e-6))[..., None]


def busy_error(y: np.ndarray, x: np.ndarray, dmap: np.ndarray) -> float:
    """Error in the busiest tenth — the number that catches a vanished person."""
    flat = dmap.ravel()
    cut = np.quantile(flat, 0.90)               # linear, same as torch.quantile
    m = (flat >= cut).astype(float).reshape(x.shape[0], x.shape[1], 1)
    return float((((y - x) ** 2) * m).sum() / max(m.sum() * 3.0, 1.0))


def colour_life(y: np.ndarray, x: np.ndarray, k: int = 8) -> float:
    """How much LESS alive the painting's colour is. Only under-saturation is
    charged — inventing colour stays expensive through the MSE. One
    subtraction, one hinge; winston.colour_life."""
    def sat(z):
        return z.max(-1) - z.min(-1)

    def pool(s):
        hk, wk = s.shape[0] // k, s.shape[1] // k
        if hk < 1 or wk < 1:                     # canvas smaller than a region
            return s.mean(keepdims=True).reshape(1, 1)
        return s[:hk * k, :wk * k].reshape(hk, k, wk, k).mean(axis=(1, 3))

    return float(np.maximum(pool(sat(x)) - pool(sat(y)), 0.0).mean())


def _adaptive_avg(x: np.ndarray, side: int) -> np.ndarray:
    """F.interpolate mode='area' == adaptive average pooling."""
    h, w = x.shape[:2]
    out = np.zeros((side, side, x.shape[2]))
    for i in range(side):
        y0, y1 = (i * h) // side, -(-((i + 1) * h) // side)
        for j in range(side):
            x0, x1 = (j * w) // side, -(-((j + 1) * w) // side)
            out[i, j] = x[y0:y1, x0:x1].mean(axis=(0, 1))
    return out


def _bilinear_up(s: np.ndarray, size: int) -> np.ndarray:
    """F.interpolate bilinear, align_corners=False, separable."""
    hs = s.shape[0]
    scale = hs / size
    coords = (np.arange(size) + 0.5) * scale - 0.5
    c0 = np.floor(coords).astype(int)
    frac = (coords - c0)[:, None]
    a = np.clip(c0, 0, hs - 1)
    b = np.clip(c0 + 1, 0, hs - 1)
    rows = s[a] * (1 - frac[:, :, None]) + s[b] * frac[:, :, None]
    return (rows[:, a] * (1 - frac)[None, :, 0, None]
            + rows[:, b] * frac[None, :, 0, None])


def floors(x: np.ndarray, strokes: int, size: int):
    """BLANK (must be beaten) and BLUR (the budget's own grid). winston.floors."""
    flat = x.mean(axis=(0, 1), keepdims=True)
    blank = mse(np.broadcast_to(flat, x.shape), x)
    side = max(2, int(round(strokes ** 0.5)))
    blur = _bilinear_up(_adaptive_avg(x, side), size)
    return blank, mse(blur, x), side


# ------------------------------------------------------------------ pen check

def _components(mask: np.ndarray) -> int:
    """4-connected components, plain flood fill (close_loop.py's own)."""
    h, wd = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    n = 0
    for sy in range(h):
        for sx in range(wd):
            if not mask[sy, sx] or seen[sy, sx]:
                continue
            n += 1
            stack = [(sy, sx)]
            seen[sy, sx] = True
            while stack:
                y, x = stack.pop()
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = y + dy, x + dx
                    if (0 <= ny < h and 0 <= nx < wd and mask[ny, nx]
                            and not seen[ny, nx]):
                        seen[ny, nx] = True
                        stack.append((ny, nx))
    return n


def pen_check(sheets: np.ndarray, thr: float = 0.35) -> dict:
    """Is it a LINE, or the dot-cloud trick again? Measured, never assumed.

    `sheets` is (B,H,W) darkness (1 = full ink). The 08-30 hand scored 86%
    drawing constellations; this is the standing witness against that."""
    a = sheets > thr
    pieces = [_components(a[i]) for i in range(len(a))]
    return {"pieces_mean": float(np.mean(pieces)),
            "pieces_max": int(np.max(pieces)),
            "one_or_two_pieces": float(np.mean([p <= 2 for p in pieces])),
            "cover_mean": float(a.mean())}


# ------------------------------------------------------------------ the body

class Atelier:
    """Canvas + stroke table + the trial/commit protocol the weave drives.

    All host state lives here, because ALMA sparks are scalars and pixels are
    never sparks. The weave decides; the atelier holds what was decided.

    Revert is the DEFAULT: every trial is a stage, and a stage dies unless the
    weave's settle knot commits it. The canvas only ever contains commits.
    """

    def __init__(self, subject, n_strokes: int, size: int | None = None,
                 seed: int = SEED, detail_w: float = 3.0,
                 colour_w: float = 1.5, soft: float = 1.0):
        if isinstance(subject, str):
            self.subject_path = subject
            self.size = size or SIZE
            self.x = load(subject, self.size)
        else:
            self.x = np.asarray(subject, np.float64)
            self.size = self.x.shape[0]
            self.subject_path = "array:%dx%d" % self.x.shape[:2]
        assert self.x.shape == (self.size, self.size, 3), self.x.shape
        self.n = int(n_strokes)
        self.seed = int(seed)
        self.detail_w = float(detail_w)
        self.colour_w = float(colour_w)
        self.soft = float(soft)
        self.px = grid(self.size)
        self.dmap = detail(self.x)
        self.blank, self.blur, self.blur_side = floors(self.x, self.n, self.size)
        flat = self.x.mean(axis=(0, 1), keepdims=True)
        self._blank_canvas = np.broadcast_to(flat, self.x.shape).copy()
        self.busy_blank = busy_error(self._blank_canvas, self.x, self.dmap)
        self.table = self._seed_table()          # (n, PARAMS) base proposals
        self.reset()

    # -- placement craft (declared in the module docstring)

    def _seed_table(self) -> np.ndarray:
        t = np.zeros((self.n, PARAMS))
        for i in range(self.n):
            rng = np.random.default_rng([self.seed, 5, i])
            t[i, :2] = rng.normal(0.0, 1.0, 2)               # anchor
            t[i, 2:POINTS * 2] = rng.normal(0.0, 0.5, POINTS * 2 - 2)
            t[i, POINTS * 2] = rng.normal(0.0, 1.0)          # width raw
            axy = np.tanh(t[i, :2]) * 0.95
            pj = int(round((axy[0] + 1) / 2 * (self.size - 1)))
            pi = int(round((axy[1] + 1) / 2 * (self.size - 1)))
            c = self.x[pi, pj].clip(1e-4, 1 - 1e-4)          # dip the brush
            t[i, POINTS * 2 + 1:] = (np.log(c / (1 - c))
                                     + rng.normal(0.0, 0.25, 3))
        return t

    def set_table(self, params: np.ndarray) -> int:
        """Replace the base proposals (gaze.propose / a test / a caller)."""
        p = np.asarray(params, np.float64).reshape(-1, PARAMS)
        m = min(len(p), self.n)
        self.table[:m] = p[:m]
        return m

    # -- run state

    def reset(self) -> None:
        """A fresh sitting: white canvas, nothing alive, nothing staged."""
        self.alive: dict[int, np.ndarray] = {}     # index -> committed params
        self.stage: dict[int, np.ndarray] = {}     # index -> staged params
        self.fire_count = np.zeros(self.n, int)
        self._alphas: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        self._canvas = np.ones((self.size * self.size, 3))
        self.err_white = self._loss(self._canvas, n_alive=0)
        self.err_now = self.err_white
        self.history: list[tuple[int, float]] = []  # (stroke, err after commit)

    # -- the ruler, winston's training loss

    def _loss(self, canvas_flat: np.ndarray, n_alive: int) -> float:
        y = canvas_flat.reshape(self.size, self.size, 3)
        return (mse(y, self.x)
                + self.detail_w * float((((y - self.x) ** 2) * self.dmap).mean())
                + self.colour_w * (n_alive / self.n) * colour_life(y, self.x))

    def _alpha_of(self, i: int, params: np.ndarray):
        xy, w, col = decode(params[None], self.n, np.array([i]))
        return stroke_alpha(xy[0], float(w[0]), self.px, self.soft)[:, None], col[0]

    def _fold(self, override: tuple[int, np.ndarray] | None = None) -> np.ndarray:
        """Alpha-over the committed strokes (plus one override) in index order."""
        keys = set(self.alive)
        if override is not None:
            keys.add(override[0])
        canvas = np.ones((self.size * self.size, 3))
        for i in sorted(keys):
            if override is not None and i == override[0]:
                a, col = self._alpha_of(i, override[1])
            else:
                a, col = self._alphas[i]
            canvas = canvas * (1.0 - a) + col * a
        return canvas

    # -- the trial/commit protocol (the weave's hands)

    def trial(self, i: int, spark: float) -> float:
        """One trial for stroke i. Fire 1 places; later fires wiggle.

        Returns the measured improvement d_err = err_now - err_with_trial
        (positive = the trial helps). The trial is STAGED, never committed —
        commit is the weave's explicit act through settle. An unsettled stage
        from a previous fire is discarded here: revert is the default.
        """
        i = int(i)
        self.stage.pop(i, None)                       # revert is the default
        self.fire_count[i] += 1
        fire_no = int(self.fire_count[i])
        base = self.alive.get(i, self.table[i])
        if fire_no == 1:
            cand = base.copy()
        else:
            rng = np.random.default_rng([self.seed, 7, i, fire_no])
            cand = base + rng.standard_normal(PARAMS) * WIGGLE_SCALE * abs(spark)
        self.stage[i] = cand
        n_alive = len(self.alive) + (0 if i in self.alive else 1)
        err_trial = self._loss(self._fold((i, cand)), n_alive)
        return float(self.err_now - err_trial)

    def commit(self, i: int) -> bool:
        """The weave said keep. Returns False if nothing was staged."""
        i = int(i)
        if i not in self.stage:
            return False
        params = self.stage.pop(i)
        self.alive[i] = params
        self._alphas[i] = self._alpha_of(i, params)
        self._canvas = self._fold()
        self.err_now = self._loss(self._canvas, len(self.alive))
        self.history.append((i, self.err_now))
        return True

    def discard(self, i: int) -> None:
        self.stage.pop(i, None)

    # -- what came out

    def canvas(self) -> np.ndarray:
        return self._canvas.reshape(self.size, self.size, 3).copy()

    def n_alive(self) -> int:
        return len(self.alive)

    def geometry(self):
        """Decoded strokes of everything alive: [(i, xy, w, col), ...]."""
        out = []
        for i in sorted(self.alive):
            xy, w, col = decode(self.alive[i][None], self.n, np.array([i]))
            out.append((i, xy[0], float(w[0]), col[0]))
        return out

    def verdicts(self) -> dict:
        """Every floor, computed fresh on the finished canvas. Honest floors:
        BLANK/BLUR are recomputed here, inside the organ, every time."""
        y = self.canvas()
        painter = mse(y, self.x)
        busy_p = busy_error(y, self.x, self.dmap)
        return {
            "blank": self.blank, "blur": self.blur, "painter": painter,
            "beats_blank": self.blank - painter,
            "blur_gap": self.blur - painter,
            "busy_painter": busy_p, "busy_blank": self.busy_blank,
            "busy_gap": self.busy_blank - busy_p,
            "chroma_deficit": colour_life(y, self.x),
            "n_alive": len(self.alive),
        }

    def save_png(self, path: str) -> str:
        from PIL import Image
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        Image.fromarray((self.canvas() * 255).astype(np.uint8)).save(path)
        return path
