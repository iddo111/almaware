# ear-v3 Phase 1: determinism of patched-JAX CARFAC NAP.
# python determinism_check.py save     -> runs twice in-process (bit compare) + saves NAP
# python determinism_check.py compare  -> runs once, bit-compares against the saved NAP
import sys
import wave

import numpy as np

FS = 16000
WAV = "/home/eran2/eran-cortex/data/t06/ah_t06_1.wav"
NPY = "/home/eran2/ear-v3/det_run_nap.npy"

with wave.open(WAV, "rb") as w:
    audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0

import jax
import jax.numpy as jnp
from carfac.jax import carfac as cjax


def run_once():
    params = cjax.CarfacDesignParameters(fs=FS)
    hypers, weights, state0 = cjax.design_and_init_carfac(params)
    inp = jnp.asarray(audio[:, np.newaxis], dtype=jnp.float32)
    out = cjax.run_segment_jit(inp, hypers, weights, state0)
    return np.asarray(jax.device_get(out.naps))


mode = sys.argv[1]
nap = run_once()
if mode == "save":
    nap2 = run_once()
    identical = nap.tobytes() == nap2.tobytes()
    print(f"in_process_twice_bit_identical: {identical}")
    if not identical:
        print(f"in_process_max_abs_diff: {float(np.max(np.abs(nap - nap2))):.3e}")
    np.save(NPY, nap)
    print(f"saved: {NPY}")
elif mode == "compare":
    ref = np.load(NPY)
    identical = nap.tobytes() == ref.tobytes()
    print(f"cross_process_bit_identical: {identical}")
    if not identical:
        print(f"cross_process_max_abs_diff: {float(np.max(np.abs(nap - ref))):.3e}")
else:
    raise SystemExit("mode must be save|compare")
