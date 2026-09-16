"""KAV-07 proof — the coordinate half gives every SHAPE one vote, not every frame

Run: python proofs/proof_KAV-07.py old   -> must FAIL (exit 1)
     python proofs/proof_KAV-07.py new   -> must PASS (exit 0)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness


def check(organ):

    import numpy as np
    import mesh, learn
    from anatomy import PHASES, frames
    big = ("drum12", mesh.prism(mesh.regular(12, 0.6), mesh.regular(12, 0.6), 0, 2.0))
    small = ("cube", mesh.box([0, 0, 0], [1, 1, 1]))
    corpus = [big, small]
    k, lam, ph = 18, 1e-3, 0
    rows, share = [], []
    for _, tris in corpus:
        toks, _, _ = mesh.speak(tris)
        got = list(frames(toks, k))
        for ctx, phase, ans in got:
            if phase == ph:
                rows.append((ctx, ans))
                share.append(1.0 / len(got))
    nb = sum(1 for (_, t) in [big] for _ in frames(mesh.speak(t)[0], k))
    nsm = sum(1 for (_, t) in [small] for _ in frames(mesh.speak(t)[0], k))
    print(f"    frames: drum12 {nb}, cube {nsm}  ({nb / nsm:.1f}x)")
    X = np.array([c for c, _ in rows])
    y = np.array([a for _, a in rows], dtype=np.float64)
    X1 = np.hstack([X, np.ones((len(X), 1))])

    def solve(w):
        Xw = X1 * w[:, None]
        A = Xw.T @ X1 + lam * np.eye(X1.shape[1])
        A[-1, -1] -= lam
        return np.linalg.solve(A, Xw.T @ y)

    flat = solve(np.ones(len(rows)))
    wv = np.array(share)
    wv = wv * (len(wv) / wv.sum())
    voted = solve(wv)
    got = learn.fit(corpus, k, lam)
    mine = np.concatenate([got.w[ph], [got.b[ph]]])
    d_flat = float(np.linalg.norm(mine - flat))
    d_voted = float(np.linalg.norm(mine - voted))
    print(f"    ||fit - frame-pooled|| = {d_flat:.3e}   ||fit - shape-voted|| = {d_voted:.3e}")
    assert d_voted < 1e-9, ("learn.fit does NOT reproduce the one-shape-one-vote ridge: "
                            "it still pools every frame equally, so the grid-decimated "
                            "STL parts (79.9%% of the training frames) drown the clean "
                            "solids the gates are about -- the same disease joiner.py "
                            "was cured of on 2026-09-05, one half of the organ left sick")
    assert d_flat > 1e-9, "the two solutions are identical — the test cannot tell them apart"


_harness.run(check)
