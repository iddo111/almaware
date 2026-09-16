"""GAZE — the three torch spells, frozen forwards only, eran3/4 only.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

The honest sentence about torch, kept here where the torch is: torch remains in
exactly three frozen forward passes inside taught spells — `propose` (the
painter's talent, trained by backprop elsewhere in winston-forever on eran3,
consumed frozen), `behold` (the frozen eye, and the zivug eye-head when its
checkpoint is given), `hear_back` (ear centroids from ear-human.npz) — plus
`render_big` for the 4K path. The organ itself never backprops: its learning is
strand drift and one-scalar wiggles, and the canvas lives in host memory
because sparks are scalars.

Everything is imported READ-ONLY and DIRECTLY from the originals — no vendored
copies:

    alma-draughtsman/winston/winston.py   decode / render_big / floors
                                          (import-safe: __main__ guard verified)
    eran-brain/eye/eye.py                 Encoder.gist (192-d, L2-normalised)
    eran-brain/holobrain/ear-human.npz    V (396,192), y, syllables

Guarded lazy import: this module can be IMPORTED anywhere (the PC included) —
it only reaches for torch inside `teach_gaze`, and refuses plainly if torch or
a checkpoint is missing. No PC test path imports it.

Binding honesty (the standing rule): the 192-d gist cannot flow through the
weave — sparks are scalars, the tensor door stays shut. `behold` is the organ
boundary, ear-style: the full point is saved host-side to state/gist-*.npz and
ONE resemblance scalar is answered. No retrieval accuracy is CLAIMED for any
of these numbers until they ship with the zivug controls (shuffle-pairing
floor, random-point floor, scramble, holdouts, seed 1933) and one
murphy.watch() per claim; until then the gist/ear fringes are recorded
observations.
"""
from __future__ import annotations

import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
WINSTON_DIR = "D:/CLAUDE/alma-draughtsman/winston"
EYE_DIR = "D:/CLAUDE/eran-brain/eye"
HOLO_DIR = "D:/CLAUDE/eran-brain/holobrain"

# On eran3/4 the mirror lives under ~/eran-holobrain; run_eran4.sh exports
# WINSTON_SRC / EYE_SRC / EAR_NPZ so the same file runs there unchanged.
WINSTON_DIR = os.environ.get("WINSTON_SRC", WINSTON_DIR)
EYE_DIR = os.environ.get("EYE_SRC", EYE_DIR)
EAR_NPZ = os.environ.get("EAR_NPZ", os.path.join(HOLO_DIR, "ear-human.npz"))


def import_winston_py():
    """Import the ORIGINAL winston.py by explicit file path.

    Not `import winston`: this organ's own directory is named `winston` too,
    so a name-based import is one sys.path entry away from silently loading
    the organ instead of the painter (it happened on eran4 on day one). An
    explicit file path cannot be shadowed."""
    import importlib.util
    path = os.path.join(WINSTON_DIR, "winston.py")
    spec = importlib.util.spec_from_file_location("winston_torch", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["winston_torch"] = mod
    spec.loader.exec_module(mod)
    return mod


def _need_torch():
    try:
        import torch                                     # noqa: F401
        return torch
    except ImportError:
        raise RuntimeError(
            "gaze needs torch and runs on eran3/4 only. On the PC use "
            "stubs.stub_gaze() — the law is no torch in the PC organ "
            "(feedback_no_training_on_pc).") from None


def teach_gaze(atelier, painter_pt: str, eye_pt: str,
               zivug_head_pt: str | None = None,
               state_dir: str | None = None) -> dict:
    """Build the three real spells over one atelier. Returns the gaze book
    {"propose", "behold", "hear_back"} for Easel(gaze=...).

    Every checkpoint is loaded ONCE, frozen (`eval()`, no grad), and closed
    over. `zivug_head_pt` may be None — then behold compares raw gists and
    says so once, out loud, instead of pretending a head it does not have.
    """
    torch = _need_torch()
    if EYE_DIR not in sys.path:
        sys.path.insert(0, EYE_DIR)
    W = import_winston_py()
    from eye import Encoder                              # noqa: E402

    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    state_dir = state_dir or os.path.join(HERE, "state")
    os.makedirs(state_dir, exist_ok=True)

    ck = torch.load(painter_pt, map_location=dev, weights_only=False)
    painter = W.Painter(ck.get("strokes", atelier.n)).to(dev)
    painter.load_state_dict(ck["net"])
    painter.eval()

    eck = torch.load(eye_pt, map_location=dev, weights_only=False)
    enc = Encoder().to(dev)
    enc.load_state_dict(next((eck[k] for k in ("enc", "encoder") if k in eck),
                             eck))
    enc.eval()

    head = None
    if zivug_head_pt and os.path.isfile(zivug_head_pt):
        sys.path.insert(0, HOLO_DIR)
        from zivug import Head                           # noqa: E402
        hck = torch.load(zivug_head_pt, map_location=dev, weights_only=False)
        head = Head(192).to(dev)
        head.load_state_dict(hck["eye_h"] if "eye_h" in hck else hck)
        head.eval()
    else:
        print("gaze: no zivug head checkpoint — behold compares RAW gists "
              "(said once, not hidden)")

    ear = np.load(EAR_NPZ, allow_pickle=True)
    V, y = ear["V"], ear["y"]
    sylls = [str(s) for s in ear["syllables"]]
    cents = np.stack([V[y == c].mean(0) for c in range(len(sylls))])
    cents = cents / np.linalg.norm(cents, axis=1, keepdims=True)

    def _gist(img_np):
        with torch.no_grad():
            t = torch.as_tensor(img_np[None], dtype=torch.float32, device=dev)
            if t.shape[1] != 64:
                t = torch.nn.functional.interpolate(
                    t.permute(0, 3, 1, 2), size=(64, 64), mode="bilinear",
                    align_corners=False).permute(0, 2, 3, 1)
            g = enc.gist(t)
            if head is not None:
                g = torch.nn.functional.normalize(head(g), dim=-1)
        return g[0].cpu().numpy()

    def propose(vs):
        """The painter's talent, frozen: painter.pt looks at the subject and
        proposes the initial stroke table. Answers how many strokes landed."""
        with torch.no_grad():
            x = torch.as_tensor(atelier.x[None], dtype=torch.float32,
                                device=dev)
            p = painter(x)[0].cpu().numpy()
        return float(atelier.set_table(p))

    def behold(vs):
        """One cosine: does the painting LOOK like its subject, to the frozen
        eye? The 192-d points are saved host-side; the weave gets one scalar."""
        gp = _gist(atelier.canvas())
        gs = _gist(atelier.x)
        np.savez(os.path.join(state_dir, "gist-latest.npz"),
                 painting=gp, subject=gs)
        return float(np.dot(gp, gs))

    def hear_back(vs):
        """What this painting SOUNDS like: cosine to the nearest human-ear
        centroid. A recorded observation, not a claim (module docstring)."""
        g = _gist(atelier.canvas())
        cos = cents @ g
        k = int(cos.argmax())
        np.savez(os.path.join(state_dir, "hear-latest.npz"),
                 cos=cos, best=k, syllable=sylls[k])
        return float(cos[k])

    return {"propose": propose, "behold": behold, "hear_back": hear_back,
            "_painter": painter, "_enc": enc, "_dev": dev}


def render_big_png(atelier, size: int, out_path: str) -> str:
    """The 4K path: the SAME committed strokes on a finer lattice — no
    upscaler, nothing invented.

    When every stroke of the budget is alive, the params go through the
    imported winston.render_big verbatim (global index == position, so each
    stroke keeps its own brush). A PARTIAL set would get wrong brush widths
    from render_big (its coarse-to-fine ramp is positional), so it goes
    through the atelier's own decode+ink on the fine lattice instead —
    identical mathematics, exact for any subset, measured equal by the pin
    test."""
    idxs = sorted(atelier.alive)
    if len(idxs) == atelier.n:
        torch = _need_torch()
        W = import_winston_py()
        p = np.stack([atelier.alive[i] for i in idxs])
        with torch.no_grad():
            big = W.render_big(torch.as_tensor(p[None], dtype=torch.float32),
                               size, chunk=8)[0].cpu().numpy()
    else:
        import atelier as A                              # noqa: E402
        big = A.render_geometry(atelier.geometry(), size)
    from PIL import Image
    Image.fromarray((big * 255).astype(np.uint8)).save(out_path)
    return out_path
