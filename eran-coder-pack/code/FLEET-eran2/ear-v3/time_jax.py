# ear-v3 Phase 1: patched-JAX CARFAC timing on a 0.5 s clip, single core.
# Run under: taskset -c 0, OMP_NUM_THREADS=1.
import time
import wave

import numpy as np

FS = 16000
N = 8000  # 0.5 s
WAV = "/home/eran2/eran-cortex/data/t06/ah_t06_1.wav"

with wave.open(WAV, "rb") as w:
    audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
audio = audio[:N]

import jax
import jax.numpy as jnp
from carfac.jax import carfac as cjax

params = cjax.CarfacDesignParameters(fs=FS)
hypers, weights, state0 = cjax.design_and_init_carfac(params)
inp = jnp.asarray(audio[:, np.newaxis], dtype=jnp.float32)

t0 = time.perf_counter()
out = cjax.run_segment_jit(inp, hypers, weights, state0)
jax.block_until_ready(out.naps)
first = time.perf_counter() - t0

times = []
for _ in range(30):
    t0 = time.perf_counter()
    out = cjax.run_segment_jit(inp, hypers, weights, state0)
    jax.block_until_ready(out.naps)
    times.append(time.perf_counter() - t0)
times.sort()

print(f"clip: {N} samples = {N / FS:.2f} s, single core")
print(f"first_call_incl_jit_s: {first:.3f}")
print(f"steady_state_per_call_ms: median {times[len(times) // 2] * 1e3:.1f}  min {times[0] * 1e3:.1f}  max {times[-1] * 1e3:.1f}")
print(f"gate_25ms: {'PASS' if times[len(times) // 2] * 1e3 <= 25.0 else 'FAIL'}")
