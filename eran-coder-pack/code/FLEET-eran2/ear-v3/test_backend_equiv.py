# ear-v3 Phase 1: NumPy-vs-JAX backend equivalence on real Iddo clips at fs=16000.
# NumPy is the reference (it runs the smoother its own design asked for).
# Run: python test_backend_equiv.py   -> prints per-clip numbers, asserts at the end.
import sys
import wave

import numpy as np

FS = 16000
CLIPS = [
    "/home/eran2/eran-cortex/data/t06/ah_t06_1.wav",
    "/home/eran2/eran-cortex/data/t06/abba_t06_1.wav",
    "/home/eran2/eran-cortex/data/t06/ma_t06_1.wav",
]

# Closed-loop gate. Both backends compute in float32 (JAX by default; the NumPy
# design/state arrays are float64 but the open-loop float32-noise floor measured
# here is ~1e-4), so 1e-3 on a NAP with values up to ~5.4 is achievable once the
# 5-tap AGC smoother matches. If it were not, this constant is where the honest
# bound goes.
MAX_ABS_TOL = 1e-3
CORR_MIN = 0.999
# Open loop skips the AGC entirely, so it measures the pure float32-vs-float64
# noise floor between the backends: 5.76e-4 full-clip max on ah_t06_1.wav
# (the earlier 1.1e-4 record was on 200 sampled points, not the full-clip max).
OPEN_LOOP_TOL = 1e-3


def load(path):
    with wave.open(path, "rb") as w:
        assert w.getframerate() == FS, f"{path}: fs {w.getframerate()}"
        assert w.getnchannels() == 1 and w.getsampwidth() == 2
        n = w.getnframes()
        return np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768.0


def run_np(audio, open_loop=False):
    from carfac.np import carfac as cnp

    cfp = cnp.design_carfac(fs=FS)
    cfp = cnp.carfac_init(cfp)
    naps, _, _, _, _ = cnp.run_segment(cfp, audio[:, np.newaxis], open_loop=open_loop)
    return np.asarray(naps)[..., 0] if naps.ndim == 3 else np.asarray(naps)


def run_jax(audio, open_loop=False):
    import jax
    import jax.numpy as jnp
    from carfac.jax import carfac as cjax

    params = cjax.CarfacDesignParameters(fs=FS)
    hypers, weights, state0 = cjax.design_and_init_carfac(params)
    inp = jnp.asarray(audio[:, np.newaxis], dtype=jnp.float32)
    out = cjax.run_segment_jit(inp, hypers, weights, state0, open_loop)
    naps = np.asarray(jax.device_get(out.naps if hasattr(out, "naps") else out[0]))
    return naps[..., 0] if naps.ndim == 3 else naps


def compare(a, b):
    assert a.shape == b.shape, f"shape mismatch {a.shape} vs {b.shape}"
    d = float(np.max(np.abs(a.astype(np.float64) - b.astype(np.float64))))
    corr = float(np.corrcoef(a.ravel().astype(np.float64), b.ravel().astype(np.float64))[0, 1])
    return d, corr


def main():
    failures = []
    print(f"fs={FS}  closed-loop gate: max_abs_diff < {MAX_ABS_TOL}  corr > {CORR_MIN}")
    for path in CLIPS:
        audio = load(path)
        name = path.rsplit("/", 1)[-1]
        nap_np = run_np(audio)
        nap_jx = run_jax(audio)
        d, corr = compare(nap_np, nap_jx)
        ok = d < MAX_ABS_TOL and corr > CORR_MIN
        print(f"closed  {name:20s} n={len(audio):6d} max_abs_diff={d:.3e} corr={corr:.6f} {'PASS' if ok else 'FAIL'}")
        if not ok:
            failures.append(f"closed {name}: max_abs_diff={d:.3e} corr={corr:.6f}")

    # Open-loop path (AGC feedback off) must keep matching as before (~1e-4).
    audio = load(CLIPS[0])
    d, corr = compare(run_np(audio, open_loop=True), run_jax(audio, open_loop=True))
    ok = d < OPEN_LOOP_TOL
    print(f"open    {CLIPS[0].rsplit('/', 1)[-1]:20s} n={len(audio):6d} max_abs_diff={d:.3e} corr={corr:.6f} {'PASS' if ok else 'FAIL'}")
    if not ok:
        failures.append(f"open-loop: max_abs_diff={d:.3e}")

    if failures:
        print("EQUIVALENCE: FAIL")
        for f in failures:
            print("  " + f)
        sys.exit(1)
    print("EQUIVALENCE: PASS (numpy == patched jax within gates)")


if __name__ == "__main__":
    main()
