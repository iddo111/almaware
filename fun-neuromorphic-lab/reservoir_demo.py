"""Compact echo-state network forecasting a nonlinear time series."""

from __future__ import annotations

import numpy as np


def make_signal(length: int) -> np.ndarray:
    signal = np.zeros(length)
    signal[:20] = 0.3
    for index in range(20, length - 1):
        delayed = signal[index - 17]
        signal[index + 1] = 0.82 * signal[index] + 0.2 * delayed / (1 + delayed**10) - 0.08
    return signal


def main() -> None:
    rng = np.random.default_rng(161803)
    reservoir_size = 180
    signal = make_signal(1800)
    recurrent = rng.normal(0, 1, size=(reservoir_size, reservoir_size))
    radius = np.max(np.abs(np.linalg.eigvals(recurrent)))
    recurrent *= 0.88 / radius
    input_weights = rng.uniform(-0.55, 0.55, size=reservoir_size)

    states = np.zeros((len(signal) - 1, reservoir_size))
    state = np.zeros(reservoir_size)
    for index, value in enumerate(signal[:-1]):
        state = np.tanh(input_weights * value + recurrent @ state)
        states[index] = state

    warmup, train_end = 100, 1250
    design = np.column_stack([np.ones(train_end - warmup), states[warmup:train_end]])
    target = signal[warmup + 1 : train_end + 1]
    ridge = 1e-5
    readout = np.linalg.solve(design.T @ design + ridge * np.eye(design.shape[1]), design.T @ target)

    test_design = np.column_stack([np.ones(len(states) - train_end), states[train_end:]])
    prediction = test_design @ readout
    truth = signal[train_end + 1 :]
    rmse = float(np.sqrt(np.mean((prediction - truth) ** 2)))

    print("ECHO-STATE RESERVOIR")
    print(f"Reservoir neurons={reservoir_size}, test RMSE={rmse:.6f}")
    print("truth      predicted")
    for expected, predicted in zip(truth[:10], prediction[:10]):
        print(f"{expected: .6f}  {predicted: .6f}")


if __name__ == "__main__":
    main()

