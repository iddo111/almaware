# EAR v3 — CARFAC vendoring record (Phase 1.0, 2026-08-26)

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

## Vendor pin

- Repo: `https://github.com/google/carfac` cloned `--depth 50` to eran2 `~/ear-v3/vendor/carfac`
- **HEAD SHA: `4cdb95eefd2161bc0c64566d2ee3f05637a00d51`**
- Commit date: 2026-08-11 20:09:57 -0700 — "Fix Python package build with hatchling >=1.32: use python/README.md (#35)"
- License: Apache-2.0

## Two-cap IHC in C++ — honest verdict

**The C++ code has A two-capacitor IHC, but it is the OLD (v1-era) two-cap, NOT the v2 model that is the Python/MATLAB default.**

Evidence:
- `cpp/ihc.h` (struct `IHCParams`): `one_capacitor = true;` is the **default**; taus are
  `tau1_out = 0.0005; tau1_in = 0.010; tau2_out = 0.0025; tau2_in = 0.005;`
- `cpp/ear.cc` (`Ear::IHCStep`, ~lines 149–164) implements both branches — the two-cap branch exists and runs when `one_capacitor == false`.
- Python v2 two-cap (`python/src/carfac/np/carfac.py`, `IhcTwoCapParams`, lines 404–411) uses **different taus**: `tau1_out=0.0005, tau1_in=0.0002, tau2_out=0.001, tau2_in=0.010` — and interprets cap1 voltage as a receptor potential. There is no C++ counterpart of this.
- `matlab/RELEASE_NOTES.md` §4 says v2 **removed** the old two-cap "and replaced it by a new one that allows interpreting one of the capacitor voltages as a receptor potential. This new two-cap version is the default."
- Python additionally has `'two_cap_with_syn'` (v3 model) — also absent from C++.

**Conclusion:** the current (v2) two-cap IHC exists only in MATLAB / NumPy / JAX. `cpp/` carries the deprecated v1 two-cap with the old taus and defaults to one-cap. C++ = contingency only, as the plan assumed.

## eran2 venv (pin: `~/ear-v3/requirements.lock` on eran2)

- python3 venv at `~/ear-v3/venv` (aarch64, Ubuntu)
- `numpy==2.5.2`, `scipy==1.18.1`, `jax==0.11.1`, `jaxlib==0.11.1` — **jax[cpu] installed cleanly on aarch64, no error**
- `carfac==0.0.1` installed via `pip install "carfac[jax] @ file:///home/eran2/ear-v3/vendor/carfac#subdirectory=python"` — no sys.path fallback needed (pulls in matplotlib etc. as deps)

## First NAP — smoke test (`~/ear-v3/smoke_nap.py`, results `~/ear-v3/SMOKE-20260826.txt`)

Clip: `~/eran-cortex/data/t06/ah_t06_1.wav` — 11409 samples, 0.713 s, 16 kHz, rms 0.234.

| backend | n_ch | NAP shape | min | max | mean | wall |
|---|---|---|---|---|---|---|
| NumPy (`design_carfac(fs=16000)`, ihc `two_cap`) | 65 | (11409, 65, 1) | −0.8116 | 5.2085 | 0.4456 | 0.343 s |
| JAX (`run_segment_jit`, float32) 1st call | 65 | (11409, 65, 1) | −0.8116 | 5.3956 | 0.6478 | 0.234 s (incl JIT) |
| JAX 2nd call (warm) | | | | | | **0.036 s** (~25 ms / 0.5 s clip) |

NumPy is ~0.48 s per s of audio single-core — far from the plan's ≤25 ms/0.5 s gate. Warm JAX sits right at the gate.

## ⚠️ FINDING: JAX ≠ NumPy at 16 kHz (the corpus rate)

On the real clip at fs=16000: **max_abs_diff 5.50, correlation 0.41** — not float noise.

Bisect (all on eran2, JAX_ENABLE_X64 tried — precision is NOT the cause):
- open_loop=True: matches at both rates (~1.1e-4).
- closed loop: matches at fs=22050 (~1.3e-4), **diverges at fs=16000** (2.89 max on 200 random samples).
- All designed coefficients (CAR/IHC/AGC) match to float32 eps at fs=16000.

**Root cause:** at fs=16000 the AGC design picks a **5-tap** spatial FIR (`agc_spatial_n_taps=5`; it's 3 at 22050). NumPy `spatial_smooth` implements the 5-tap case; JAX `spatial_smooth_jit` implements **only the 3-tap formula** and silently applies it to the 5-tap coefficients. This limitation is documented in the vendor source itself — `python/src/carfac/jax/carfac.py` ~line 1757:

> "This also does not support a 5-tap filter in the non-`new_way` branch, despite the code in `design_and_init_agc` and `design_fir_coeffs` to support it."

Upstream's np-vs-jax equivalence test (`jax/carfac_test.py::test_equal_forward_pass`) runs only at the default fs=22050, so it never hits the 5-tap path.

**Implication for Phase 1 (decision needed, not taken here):** the plan named JAX-CPU as the ear backend with NumPy as cross-check. At our 16 kHz corpus the two are different ears. Options: (a) NumPy as the reference judge (self-consistent, runs the smoother its design specifies) with JAX only after a local patch to `spatial_smooth_jit`; (b) patch JAX and prove equivalence at 16 kHz; (c) force a 3-tap design at 16 kHz in both. Not chosen in Phase 1.0.

## Deviations from the assigned steps

- None in substance. jax[cpu] needed no fallback; the package install needed no sys.path fallback. Extra work beyond the letter of the steps: the np-vs-jax divergence chase above (Broken Windows — the cross-check failing at the corpus rate is a fact Phase 1 must know).

## ✅ PATCH 0001 (Phase 1.1, 2026-08-26): JAX 5-tap AGC spatial FIR — option (b) taken, JAX == NumPy at 16 kHz now

**Patch file:** `patches/0001-jax-5tap-agc.patch` (here, next to this file) — same file on eran2 at `~/ear-v3/patches/0001-jax-5tap-agc.patch`. Applied to the vendored clone (`git diff` vs `4cdb95ee`, only `python/src/carfac/jax/carfac.py`, +62/−4) and force-reinstalled into the venv (`pip install --force-reinstall --no-deps "carfac @ file://...#subdirectory=python"` — the venv imports a *copy* in site-packages, so reinstall after any vendor edit).

What it does, marked in-source with `ERAN ear3 patch 2026-08-26: 5-tap AGC spatial FIR (upstream silently used 3-tap)`:

1. Adds `_shift_right_two` / `_shift_left_two` to `jax/carfac.py`, exact mirrors of the NumPy `shift_right_two` / `shift_left_two` including the odd MATLAB-compatible edge fills (`[1,2,3,4,5]` → right-two `[1,2,1,2,3]`, left-two `[3,4,5,5,4]`).
2. `spatial_smooth_jit` now dispatches on `agc_hypers.agc_spatial_n_taps` — a **static** field under `jax.jit` (AgcHypers is a hashed static argument), so the Python `if` resolves at trace time, no `lax.cond` needed. The 5-tap body is the NumPy formula verbatim: `fir[0]*(right_two+right_one) + fir[1]*state + fir[2]*(left_one+left_two)`, `agc_spatial_iterations` times via `fori_loop` (the design stores 3 coefficients; the outer ones are implicitly duplicated to make 5 taps). The 3-tap path is untouched.

**Equivalence at fs=16000, closed loop, NAP outputs (`~/ear-v3/test_backend_equiv.py`; NumPy = reference):**

| clip | before max_abs_diff / corr | after max_abs_diff / corr |
|---|---|---|
| ah_t06_1.wav (11409 smp) | 5.500 / 0.410 | **3.585e-4 / 1.000000** |
| abba_t06_1.wav (6217 smp) | 5.619 / 0.659 | **1.500e-4 / 1.000000** |
| ma_t06_1.wav (6786 smp) | 5.311 / 0.609 | **1.182e-4 / 1.000000** |

Gates in the test: closed-loop `max_abs_diff < 1e-3`, `corr > 0.999` — pass with margin, no float32 relaxation needed. Open-loop path still matches: 5.760e-4 full-clip max on ah_t06_1 (the earlier "1.1e-4" was measured on 200 sampled points, not the full-clip max; gate set at 1e-3 with that note in the test). All 4 checks PASS.

**Timing, patched JAX, 0.5 s clip (8000 smp), eran2 (20-core GB10, CPU jaxlib):**

| condition | 1st call (incl JIT) | steady per call | 25 ms gate |
|---|---|---|---|
| pinned 1 core (`taskset -c 0`, `OMP_NUM_THREADS=1`) | 0.994 s | median 42.3 ms (min 41.7) | **FAIL** |
| unpinned (default XLA threading) | 0.233 s | median 20.9 ms (min 20.1) | **PASS** |

Honest read: the ear makes the ≤25 ms/0.5 s gate only with XLA's default multi-threading, not on a single pinned core. (Pre-patch "0.036 s per 0.713 s clip ≈ 25 ms/0.5 s" in the table above was also unpinned.) If the gate is meant per-core, the ear is ~1.7× over it.

**Determinism (ah_t06_1 through patched JAX):** same process twice → bit-identical NAP; two separate process invocations → bit-identical NAP (byte compare vs saved `.npy`).

eran2 `~/ear-v3/SMOKE-20260826.txt` carries the same numbers in a "post-patch" section.
