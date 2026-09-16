"""Leaky integrate-and-fire network with an ASCII raster."""

from __future__ import annotations

import numpy as np


def main() -> None:
    rng = np.random.default_rng(271828)
    neurons, steps = 16, 120
    leak, threshold, reset = 0.92, 1.0, 0.0
    membrane = np.zeros(neurons)
    spike_history = np.zeros((steps, neurons), dtype=bool)

    rates = np.linspace(0.03, 0.24, neurons)
    weights = np.linspace(0.25, 0.75, neurons)
    for step in range(steps):
        poisson_spikes = rng.random(neurons) < rates
        membrane = leak * membrane + poisson_spikes * weights + 0.06
        fired = membrane >= threshold
        spike_history[step] = fired
        membrane[fired] = reset

    print("LEAKY INTEGRATE-AND-FIRE NETWORK")
    print("Each row is one neuron; # is a spike. Time flows left to right.")
    compressed = spike_history.reshape(40, 3, neurons).any(axis=1).T
    for neuron, row in enumerate(compressed):
        raster = "".join("#" if value else "." for value in row)
        print(f"N{neuron:02d} {raster}  spikes={spike_history[:, neuron].sum():2d}")


if __name__ == "__main__":
    main()

