"""brain_to_weave.py — export the whole cortex as an ALMA weave you can walk.

Iddo asked for the brain in 3D, inside the VR world. This writes the canonical
ALMA JSON (D:\\CLAUDE\\alma-language, alma/text.py to_dict + alma/godot.py's
additive "scene" block) so D:\\CLAUDE\\alma-vr\\godot loads it like any other
weave:

    knot    one per prototype, named L<layer>p<index>
    thread  what is actually connected:
              * cross-layer — a layer-k unit IS an ordered sequence of
                layer-(k-1) prototypes, so each of its LAYER_SLOTS slots
                becomes a thread from the layer-(k-1) prototype that slot most
                resembles, into the layer-k knot. The slot's ORDER IN TIME is
                carried by the strand delay (slot 0 -> delay 1, slot 1 ->
                delay 2, ...), which is exactly what a delay means in ALMA, so
                walking the weave replays the sequence the unit is about.
              * within-layer — each prototype threads to its single most
                similar neighbour above WITHIN_LAYER_MIN_SIM, so a plane reads
                as a map and not as scattered dust.
    seed    the heaviest layer-0 prototypes, so the weave actually runs.
    scene   the REAL 3D positions the cortex grew (body/cortex.py), not a
            re-layout. That is the point: you are walking his map, not a
            graph-drawing of it.

Pure stdlib + numpy on purpose: this file ships with the organism to eran1,
where alma-language is not installed. It writes the format rather than
importing the package. proof/test_organism.py closes that loop from the PC
side by round-tripping the output through the real ``alma.text.from_dict``.

    python3 proof/brain_to_weave.py
    python3 proof/brain_to_weave.py --out somewhere.json --label
"""
import argparse
import json
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(ROOT, "body"))
sys.path.insert(0, _HERE)

import genome                                     # noqa: E402
from cortex import Cortex                         # noqa: E402

# D:\CLAUDE\alma-vr\godot\weaves\eran-brain.json — alma-vr is eran-brain's
# sibling, so this resolves without hard-coding a drive letter (and on eran1,
# where there is no alma-vr, --out names somewhere that exists).
DEFAULT_OUT = os.path.join(os.path.dirname(ROOT), "alma-vr", "godot",
                           "weaves", "eran-brain.json")

WITHIN_LAYER_MIN_SIM = 0.30       # below this they are not neighbours at all
SEED_KNOTS = 3                    # heaviest layer-0 prototypes get a spark


def knot_name(layer, idx):
    return f"L{layer}p{idx:04d}"


def _within_layer_threads(brain, layer):
    """Each prototype -> its single most similar neighbour. Bounded, legible."""
    out = []
    n = len(brain.protos)
    if n < 2:
        return out
    m = np.stack([p["vec"] for p in brain.protos])
    sims = m @ m.T
    np.fill_diagonal(sims, -2.0)
    for i in range(n):
        j = int(np.argmax(sims[i]))
        s = float(sims[i, j])
        if s < WITHIN_LAYER_MIN_SIM:
            continue
        out.append({"from": knot_name(layer, i), "to": knot_name(layer, j),
                    "port": "near",
                    "strands": [{"weight": round(s, 4), "delay": 1}]})
    return out


def _cross_layer_threads(cortex, k):
    """Decompose each layer-k unit into the layer-(k-1) prototypes it is made
    of, one thread per slot, the slot order carried by the strand delay."""
    below, above = cortex.layers[k - 1], cortex.layers[k]
    out = []
    if not below.protos or not above.protos:
        return out
    m = np.stack([p["vec"] for p in below.protos])
    width = below.dim
    for i, p in enumerate(above.protos):
        v = np.asarray(p["vec"], dtype=np.float64)
        for slot in range(genome.LAYER_SLOTS):
            sub = v[slot * width:(slot + 1) * width]
            n = float(np.linalg.norm(sub))
            if n <= 0:
                continue
            sims = m @ (sub / n)
            j = int(np.argmax(sims))
            out.append({
                "from": knot_name(k - 1, j), "to": knot_name(k, i),
                "port": f"slot{slot}",
                "strands": [{"weight": round(float(sims[j]), 4),
                             "delay": slot + 1}]})
    return out


def weave_dict(cortex, proto_label=None, name="eran-brain"):
    """The canonical ALMA weave dict + the additive scene and eran blocks."""
    knots, threads, positions, meta = [], [], {}, {}
    for k, brain in enumerate(cortex.layers):
        for i, p in enumerate(brain.protos):
            nm = knot_name(k, i)
            knots.append({"name": nm})
            pos = p.get("pos") or [0.0, 0.0, k * genome.POS_Z_SPACING]
            positions[nm] = [round(float(x), 4) for x in pos]
            meta[nm] = {"layer": k, "index": i,
                        "mass": round(float(p["mass"]), 3),
                        "scar": round(float(p["scar"]), 4),
                        "birth_step": int(p["birth_step"]),
                        "n_absorbed": int(p.get("n_abs", 0))}
            if k == 0 and proto_label and i in proto_label:
                # EXAMINER-SIDE INFO, export only — the same rule sleep.py's
                # dream hints follow. It never flows back into the organism.
                meta[nm]["examiner_label"] = proto_label[i]
        threads.extend(_within_layer_threads(brain, k))
    for k in range(1, len(cortex.layers)):
        threads.extend(_cross_layer_threads(cortex, k))

    seeds = []
    for i in cortex.layers[0].top_protos(SEED_KNOTS):
        seeds.append({"to": knot_name(0, i), "value": 1.0, "beat": 1})

    return {
        "alma": "0.1",
        "weave": name,
        "knots": knots,
        "threads": threads,
        "seeds": seeds,
        "run": 16,
        "scene": {
            "seed": genome.SEED,
            "layout": "eran-cortex-grown",
            "positions": positions,
        },
        "eran": {
            "source": "eran-brain/state (body/cortex.py)",
            "beat": int(cortex.beat),
            "layers": cortex.n_layers(),
            "layer_protos": cortex.counts(),
            "z_spacing": genome.POS_Z_SPACING,
            "note": ("positions are the ones the brain GREW, not a layout "
                     "algorithm's. Their topographic quality is measured in "
                     "proof/measure_depth.py, not asserted here."),
            "knots": meta,
        },
    }


def export(cortex, out=None, proto_label=None, log=print):
    out = out or DEFAULT_OUT
    d = weave_dict(cortex, proto_label=proto_label)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)
    os.replace(tmp, out)
    log(f"[weave] {len(d['knots'])} knots, {len(d['threads'])} threads -> {out}")
    return d


def main(argv=None):
    ap = argparse.ArgumentParser(description="export the cortex as a weave")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--state", default=None,
                    help="a state dir to read instead of the genome's")
    ap.add_argument("--label", action="store_true",
                    help="attach examiner-side class labels to layer-0 knots")
    args = ap.parse_args(argv)
    if args.state:
        genome.use_state_dir(args.state)
    from ears import Ears
    ears = Ears(exam=True)
    cortex = Cortex.load(ears.dim, log=print)
    proto_label = None
    if args.label:
        import measure
        proto_label = measure.fit_proto_labels(
            cortex.layers[0], ears, measure.wavs_in(genome.FOOD_TRAIN))
    export(cortex, args.out, proto_label=proto_label)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
