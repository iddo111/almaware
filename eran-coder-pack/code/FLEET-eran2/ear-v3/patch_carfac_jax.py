# Apply the ERAN ear3 5-tap AGC spatial FIR patch to the vendored JAX carfac.
# Exact-string replacement; fails loudly if the anchors are not found.
import sys

PATH = "/home/eran2/ear-v3/vendor/carfac/python/src/carfac/jax/carfac.py"
src = open(PATH, encoding="utf-8").read()

# --- 1. add _shift_right_two / _shift_left_two after _shift_left_one ---
anchor_helpers = '''  return jnp.concat((s[1:, ...], s[-1, jnp.newaxis, ...]))


def spatial_smooth_jit('''
assert src.count(anchor_helpers) == 1, "helper anchor not found"

new_helpers = '''  return jnp.concat((s[1:, ...], s[-1, jnp.newaxis, ...]))


# ERAN ear3 patch 2026-08-26: 5-tap AGC spatial FIR (upstream silently used
# 3-tap). Helpers mirror np/carfac.py shift_right_two / shift_left_two exactly.
def _shift_right_two(s: jax.Array) -> jax.Array:
  """Shifts a vector to the right by two.

  WARNING: The two blank elements at the start of the vector are filled in with
  a copy of the first TWO elements, matching the behavior of the non-`new_way`
  MATLAB implementation of spatial smoothing.
  For example, [1, 2, 3, 4, 5] becomes [1, 2, 1, 2, 3].

  Args:
    s: The vector to shift.

  Returns:
    The shifted vector.
  """
  return jnp.concat(
      (s[0, jnp.newaxis, ...], s[1, jnp.newaxis, ...], s[:-2, ...])
  )


def _shift_left_two(s: jax.Array) -> jax.Array:
  """Shifts a vector to the left by two.

  WARNING: The two blank elements at the end of the vector are filled in with
  a copy of the last TWO elements in reverse order, matching the behavior of
  the non-`new_way` MATLAB implementation of spatial smoothing.
  For example, [1, 2, 3, 4, 5] becomes [3, 4, 5, 5, 4].

  Args:
    s: The vector to shift.

  Returns:
    The shifted vector.
  """
  return jnp.concat(
      (s[2:, ...], s[-1, jnp.newaxis, ...], s[-2, jnp.newaxis, ...])
  )


def spatial_smooth_jit('''
src = src.replace(anchor_helpers, new_helpers)

# --- 2. fix the stale docstring claim ---
anchor_doc = '''  This also does not support a 5-tap filter in the non-`new_way` branch, despite
  the code in `design_and_init_agc` and `design_fir_coeffs` to support it.
'''
assert src.count(anchor_doc) == 1, "docstring anchor not found"
new_doc = '''  ERAN ear3 patch 2026-08-26: 5-tap AGC spatial FIR (upstream silently used
  3-tap). Upstream applied the 3-tap formula even when the design selected
  5 taps (e.g. at fs=16000); this version dispatches on
  `agc_hypers.agc_spatial_n_taps` and matches np/carfac.py `spatial_smooth`.
'''
src = src.replace(anchor_doc, new_doc)

# --- 3. dispatch on n_taps in spatial_smooth_jit ---
anchor_body = '''  # Always do the default case to unblock the work on agc_step.
  # TODO(honglinyu): add the other cases back.
  n_iterations = agc_hypers.agc_spatial_iterations
  fir_coeffs = weights.agc_spatial_fir
  return jax.lax.fori_loop(
      0,
      n_iterations,
      lambda _, stage_state: (  # pylint: disable=g-long-lambda
          fir_coeffs[0] * _shift_right_one(stage_state)  # pyrefly: ignore[unsupported-operation]
          + fir_coeffs[1] * stage_state  # pyrefly: ignore[unsupported-operation]
          + fir_coeffs[2] * _shift_left_one(stage_state)  # pyrefly: ignore[unsupported-operation]
      ),
      stage_state,
  )'''
assert src.count(anchor_body) == 1, "body anchor not found"

new_body = '''  n_iterations = agc_hypers.agc_spatial_iterations
  fir_coeffs = weights.agc_spatial_fir
  # ERAN ear3 patch 2026-08-26: 5-tap AGC spatial FIR (upstream silently used
  # 3-tap). `agc_spatial_n_taps` lives on AgcHypers, which is static under
  # `jax.jit`, so this Python branch resolves at trace time. The 5-tap body
  # matches np/carfac.py `spatial_smooth`: the design stores 3 coefficients
  # and the outer ones are implicitly duplicated to make the 5-point FIR.
  if agc_hypers.agc_spatial_n_taps == 5:
    return jax.lax.fori_loop(
        0,
        n_iterations,
        lambda _, stage_state: (  # pylint: disable=g-long-lambda
            fir_coeffs[0]  # pyrefly: ignore[unsupported-operation]
            * (_shift_right_two(stage_state) + _shift_right_one(stage_state))
            + fir_coeffs[1] * stage_state  # pyrefly: ignore[unsupported-operation]
            + fir_coeffs[2]  # pyrefly: ignore[unsupported-operation]
            * (_shift_left_one(stage_state) + _shift_left_two(stage_state))
        ),
        stage_state,
    )
  return jax.lax.fori_loop(
      0,
      n_iterations,
      lambda _, stage_state: (  # pylint: disable=g-long-lambda
          fir_coeffs[0] * _shift_right_one(stage_state)  # pyrefly: ignore[unsupported-operation]
          + fir_coeffs[1] * stage_state  # pyrefly: ignore[unsupported-operation]
          + fir_coeffs[2] * _shift_left_one(stage_state)  # pyrefly: ignore[unsupported-operation]
      ),
      stage_state,
  )'''
src = src.replace(anchor_body, new_body)

open(PATH, "w", encoding="utf-8").write(src)
print("patched OK:", PATH)
