"""The eran4 pins — tests 15 and 16. Marked; SKIPPED on the PC, on purpose.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Test 15 is the license for the numpy atelier's existence: a second decoder is
a drift risk, and this is the pin that makes any numeric divergence from
winston.py SCREAM instead of painting quietly wrong. Test 16 checks behold
answers one honest scalar, with a control run BEFORE any binding sentence.

Run on a torch machine only:

    WINSTON_ERAN4=1 PYTHONIOENCODING=utf-8 python -m pytest tests/test_eran4_pin.py -v

with optional env: WINSTON_SRC (winston.py dir), WINSTON_PAINTER (painter.pt),
ERAN_EYE (eye checkpoint), ZIVUG_HEAD (zivug eye-head checkpoint), EAR_NPZ.
"""
from __future__ import annotations

import os

import numpy as np
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("WINSTON_ERAN4") != "1",
    reason="eran4 pin tests: set WINSTON_ERAN4=1 on a torch machine "
           "(the PC organ is numpy-only by law)")


# ---------------------------------------------------------------- 15

def test_one_decoder(tmp_path):
    import torch
    import atelier as A
    import gaze
    import record
    W = gaze.import_winston_py()

    n, size = 24, 32
    rng = np.random.default_rng(1933)
    p = rng.normal(0, 1.5, (n, A.PARAMS))
    pt = torch.as_tensor(p[None], dtype=torch.float64)

    xy_t, w_t, c_t = W.decode(pt, n_total=n)
    xy_n, w_n, c_n = A.decode(p, n, np.arange(n))
    assert abs(xy_t[0].numpy() - xy_n).max() < 1e-5
    assert abs(w_t[0].numpy() - w_n).max() < 1e-5
    assert abs(c_t[0].numpy() - c_n).max() < 1e-5

    x = rng.random((size, size, 3))
    bl_t, br_t, side_t = W.floors(torch.as_tensor(x[None]), strokes=n,
                                  size=size)
    bl_n, br_n, side_n = A.floors(x, n, size)
    assert side_t == side_n
    assert abs(bl_t - bl_n) < 1e-9 and abs(br_t - br_n) < 1e-9

    # the record's replay at 256px equals the imported render_big of the SAME
    # strokes (full table alive, so global index == position and every stroke
    # keeps its own brush)
    at = A.Atelier(x, n, seed=1933)
    at.set_table(p)
    for i in range(n):
        at.trial(i, 1.0)
        at.commit(i)
    rec = str(tmp_path / "pin-record.json")
    record.paint_record(at, rec, bands=(n // 3, n // 3, n - 2 * (n // 3)))
    got = record.replay(rec, size=256)
    with torch.no_grad():
        want = W.render_big(pt, 256, chunk=8)[0].numpy()
    assert abs(got - want).max() < 1e-5, \
        "the numpy body has DRIFTED from winston.py — fix it before trusting a single painting"


# ---------------------------------------------------------------- 16

def test_behold_scalar(tmp_path):
    import torch
    import gaze
    import atelier as A
    painter_pt = os.environ.get("WINSTON_PAINTER", "")
    eye_pt = os.environ.get("ERAN_EYE", "")
    if not (os.path.isfile(painter_pt) and os.path.isfile(eye_pt)):
        pytest.skip("needs WINSTON_PAINTER and ERAN_EYE checkpoint paths")

    rng = np.random.default_rng(1933)
    x = rng.random((64, 64, 3))
    at = A.Atelier(x, 16, seed=1933)
    book = gaze.teach_gaze(at, painter_pt, eye_pt,
                           zivug_head_pt=os.environ.get("ZIVUG_HEAD"),
                           state_dir=str(tmp_path))
    # CONTROL FIRST, before any binding sentence: the untouched white canvas
    # should not resemble the subject more than the subject resembles itself.
    c = book["behold"](())
    assert isinstance(c, float) and -1.0 <= c <= 1.0
    z = np.load(tmp_path / "gist-latest.npz")
    assert abs(np.linalg.norm(z["subject"]) - 1.0) < 1e-5
    assert abs(np.linalg.norm(z["painting"]) - 1.0) < 1e-5
    # paint the subject exactly (host-side cheat, for the ruler only): the
    # canvas that IS the subject must score higher than the white canvas did
    at._canvas = x.reshape(-1, 3).copy()
    c_perfect = book["behold"](())
    assert c_perfect > c, (c_perfect, c)
    # shuffled-subject control: the painting should resemble ITS subject more
    # than a scrambled copy of it
    dev = book["_dev"]
    enc = book["_enc"]
    with torch.no_grad():
        gp = torch.as_tensor(z["painting"][None], device=dev)
        xs = x.copy().reshape(-1, 3)
        np.random.default_rng(7).shuffle(xs)
        gs2 = enc.gist(torch.as_tensor(
            xs.reshape(1, 64, 64, 3), dtype=torch.float32, device=dev))
    # (raw-gist comparison when no zivug head was given; said in gaze.py)
    cos_scrambled = float((gs2[0].cpu().numpy() * z["painting"]).sum())
    assert c_perfect > cos_scrambled

    if os.environ.get("ZIVUG_HEAD"):
        import hashlib
        h = hashlib.sha256(
            open(os.environ["ZIVUG_HEAD"], "rb").read()).hexdigest()
        print("zivug head sha256:", h)                 # the identity pin
