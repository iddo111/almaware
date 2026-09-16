"""Small differential memristor-crossbar inference experiment."""

from __future__ import annotations

import numpy as np


def quantize(values: np.ndarray, bits: int, limit: float) -> np.ndarray:
    levels = (1 << bits) - 1
    clipped = np.clip(values, -limit, limit)
    return np.round((clipped + limit) * levels / (2 * limit)) * (2 * limit) / levels - limit


def main() -> None:
    rng = np.random.default_rng(314159)
    n_features, n_classes, n_samples = 24, 4, 1200
    weights = rng.normal(0, 0.45, size=(n_features, n_classes))
    inputs = rng.uniform(0, 1, size=(n_samples, n_features))
    labels = np.argmax(inputs @ weights, axis=1)

    max_weight = float(np.max(np.abs(weights)))
    g_plus = np.clip(weights, 0, None) / max_weight
    g_minus = np.clip(-weights, 0, None) / max_weight

    # Programming error and conductance drift emulate imperfect devices.
    programming_sigma = 0.05
    drift_factor = 0.96
    noisy_plus = np.clip(g_plus * drift_factor + rng.normal(0, programming_sigma, g_plus.shape), 0, 1)
    noisy_minus = np.clip(g_minus * drift_factor + rng.normal(0, programming_sigma, g_minus.shape), 0, 1)
    analog_logits = inputs @ (noisy_plus - noisy_minus) * max_weight
    limit = float(np.max(np.abs(analog_logits)))

    ideal_accuracy = np.mean(np.argmax(inputs @ weights, axis=1) == labels)
    print("MEMRISTOR DIFFERENTIAL CROSSBAR")
    print(f"Samples={n_samples}, inputs={n_features}, outputs={n_classes}")
    print(f"Ideal digital accuracy: {ideal_accuracy:.3f}")
    print("ADC bits | noisy analog accuracy")
    for bits in (3, 4, 6, 8):
        converted = quantize(analog_logits, bits, limit)
        accuracy = np.mean(np.argmax(converted, axis=1) == labels)
        print(f"{bits:8d} | {accuracy:.3f}")


if __name__ == "__main__":
    main()

