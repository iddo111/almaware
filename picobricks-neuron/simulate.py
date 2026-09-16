"""Deterministic, dependency-free host simulation of the PicoBricks neuron."""

from lif_core import AdaptiveLDR, LeakyIntegrateAndFire


DT_S = 0.01


def run_segment(normalizer, neuron, raw, seconds, start_s):
    spikes = []
    steps = int(round(seconds / DT_S))
    for index in range(steps):
        now_s = start_s + index * DT_S
        stimulus = normalizer.update(raw, DT_S)
        if neuron.step(stimulus, DT_S):
            spikes.append(now_s)
    return spikes, start_s + steps * DT_S


def main():
    normalizer = AdaptiveLDR(active_high=True)
    neuron = LeakyIntegrateAndFire()
    now_s = 0.0

    ambient, now_s = run_segment(normalizer, neuron, 9000, 3.0, now_s)
    bright, now_s = run_segment(normalizer, neuron, 52000, 5.0, now_s)
    recovery, now_s = run_segment(normalizer, neuron, 9000, 3.0, now_s)

    intervals = [
        bright[index + 1] - bright[index]
        for index in range(len(bright) - 1)
    ]
    minimum_isi = min(intervals) if intervals else 999.0
    passed = (
        len(ambient) == 0
        and len(bright) >= 3
        and len(recovery) == 0
        and minimum_isi >= neuron.refractory_s
    )

    print("PicoBricks LDR sensory-neuron deterministic simulation")
    print("ambient spikes :", len(ambient))
    print("bright spikes  :", len(bright))
    print("recovery spikes:", len(recovery))
    print("minimum ISI    : {:.3f} s".format(minimum_isi))
    print("VERDICT        :", "PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

