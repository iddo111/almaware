# ear-v3 Phase 1.0 smoke test: first NAP from a real Iddo clip through vendored CARFAC.
# Runs the NumPy CARFAC and (if available) the JAX CARFAC at fs=16000.
import time
import wave

import numpy as np

WAV = "/home/eran2/eran-cortex/data/t06/ah_t06_1.wav"
FS = 16000

with wave.open(WAV, "rb") as w:
    assert w.getframerate() == FS, f"unexpected fs {w.getframerate()}"
    assert w.getnchannels() == 1, f"unexpected channels {w.getnchannels()}"
    assert w.getsampwidth() == 2, f"unexpected sampwidth {w.getsampwidth()}"
    n = w.getnframes()
    audio = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768.0

print(f"wav: {WAV}")
print(f"samples: {n}  dur_s: {n / FS:.3f}  rms: {float(np.sqrt(np.mean(audio ** 2))):.5f}")

# ---------- NumPy CARFAC ----------
from carfac.np import carfac as cnp

cfp = cnp.design_carfac(fs=FS)  # default ihc_style='two_cap'
cfp = cnp.carfac_init(cfp)
t0 = time.perf_counter()
naps, cfp, bm, seg_ohc, seg_agc = cnp.run_segment(cfp, audio[:, np.newaxis])
t_np = time.perf_counter() - t0
nap2 = naps[..., 0] if naps.ndim == 3 else naps
print(f"numpy_n_ch: {getattr(cfp, 'n_ch', nap2.shape[1])}")
print(f"numpy_nap_shape: {naps.shape}")
print(f"numpy_nap_min: {float(nap2.min()):.6f}  max: {float(nap2.max()):.6f}  mean: {float(nap2.mean()):.6f}")
print(f"numpy_wall_s: {t_np:.3f}")

# ---------- JAX CARFAC ----------
try:
    import jax
    import jax.numpy as jnp
    from carfac.jax import carfac as cjax

    params = cjax.CarfacDesignParameters(fs=FS)
    hypers, weights, state0 = cjax.design_and_init_carfac(params)
    inp = jnp.asarray(audio[:, np.newaxis], dtype=jnp.float32)

    t0 = time.perf_counter()
    out1 = cjax.run_segment_jit(inp, hypers, weights, state0)
    jax.block_until_ready(out1.naps)
    t_jax1 = time.perf_counter() - t0  # includes JIT compile

    t0 = time.perf_counter()
    out2 = cjax.run_segment_jit(inp, hypers, weights, state0)
    jax.block_until_ready(out2.naps)
    t_jax2 = time.perf_counter() - t0  # warm

    napsj = np.asarray(out2.naps)
    napj2 = napsj[..., 0] if napsj.ndim == 3 else napsj
    print(f"jax_nap_shape: {napsj.shape}")
    print(f"jax_nap_min: {float(napj2.min()):.6f}  max: {float(napj2.max()):.6f}  mean: {float(napj2.mean()):.6f}")
    print(f"jax_wall_s_first_call_incl_jit: {t_jax1:.3f}")
    print(f"jax_wall_s_second_call: {t_jax2:.3f}")
except Exception as e:  # noqa: BLE001 - smoke test records the failure honestly
    print(f"jax_path_FAILED: {type(e).__name__}: {e}")
