#!/usr/bin/env python3
"""Print the throat the simulator already speaks through.

לזכרה של עלמה ז״ל · ולזכרו של משה ביטון ז״ל

voice-ant-farm/head_sim.py makes an "ah" by pushing a buzz down a 17.1 cm tube
whose bore changes along its length. We measured it: 641 and 1117 Hz, against
700 and 1100 for a human. The vowel lives in the SHAPE, not in the buzz.

So this does not invent a throat. It reads `tract_diameters()` — the exact
function the simulator uses — and turns those numbers into something you can
hold. Print it, blow through it with a buzzing source at the narrow end, and
the air should find roughly the same resonances the software found.

That matters more than it sounds. If the printed tube measures near 641/1117,
the simulator is a real model of a real object, and every motor command the
colony learns in software means something in the world. If it does not, the
model is a toy, and we would rather find that out now.

  python make_tract.py --vowel ah
  python make_tract.py --vowel ah --wall 3.0 --scale 1.0 --out tract-ah.stl

Print notes: PLA is fine — it does not inhibit platinum silicone if you later
cast folds against it. Stand it on end, no supports needed inside a tube this
wide. The glottis end is the narrow one and carries the collar step.
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

import numpy as np

# Read the simulator's own geometry. One source of truth or none.
SIM = Path(__file__).resolve().parent.parent / "voice-ant-farm"
sys.path.insert(0, str(SIM))
from head_sim import tract_diameters, VOWELS, N_SECTIONS, RATE  # noqa: E402

C_SOUND_CM_S = 34300.0
SECTION_CM = C_SOUND_CM_S / (2.0 * RATE)      # 1.07 cm — one waveguide section
RING_FACETS = 64                              # smoothness around the bore


def bore_profile(vowel: str) -> np.ndarray:
    """Bore diameter in mm at each section, glottis first."""
    m = VOWELS[vowel]
    d_cm = tract_diameters(m["tongue_x"], m["tongue_y"], m["lips"], m["jaw"])
    return d_cm * 10.0


def ring(radius: float, z: float) -> np.ndarray:
    a = np.linspace(0.0, 2.0 * np.pi, RING_FACETS, endpoint=False)
    return np.stack([radius * np.cos(a), radius * np.sin(a),
                     np.full(RING_FACETS, z)], axis=1)


def band(lower: np.ndarray, upper: np.ndarray, flip: bool) -> list:
    """Triangulate the strip between two rings. `flip` reverses the normal so
    the inner surface faces into the bore and the outer faces out."""
    tris = []
    n = len(lower)
    for i in range(n):
        j = (i + 1) % n
        a, b, c, d = lower[i], lower[j], upper[j], upper[i]
        tris += [(a, c, b), (a, d, c)] if flip else [(a, b, c), (a, c, d)]
    return tris


def build(vowel: str, wall_mm: float, scale: float) -> list:
    bore = bore_profile(vowel) * scale
    seg = SECTION_CM * 10.0 * scale                     # mm per section

    # A ring at every section boundary. Bore at a boundary is the mean of the
    # two sections it joins, so the tube tapers instead of stepping.
    n_rings = N_SECTIONS + 1
    r_in = np.empty(n_rings)
    r_in[0] = bore[0] / 2
    r_in[-1] = bore[-1] / 2
    for i in range(1, N_SECTIONS):
        r_in[i] = (bore[i - 1] + bore[i]) / 4            # /2 for mean, /2 for radius
    r_out = r_in + wall_mm

    z = np.arange(n_rings) * seg
    inner = [ring(r_in[i], z[i]) for i in range(n_rings)]
    outer = [ring(r_out[i], z[i]) for i in range(n_rings)]

    tris = []
    for i in range(n_rings - 1):
        tris += band(inner[i], inner[i + 1], flip=True)   # bore faces inward
        tris += band(outer[i], outer[i + 1], flip=False)  # wall faces outward
    # Annular caps close the solid at both ends.
    tris += band(inner[0], outer[0], flip=False)
    tris += band(inner[-1], outer[-1], flip=True)
    return tris


def write_stl(path: Path, tris: list) -> None:
    with open(path, "wb") as f:
        f.write(b"ALMA vocal tract - geometry shared with head_sim.py".ljust(80, b" "))
        f.write(struct.pack("<I", len(tris)))
        for a, b, c in tris:
            n = np.cross(b - a, c - a)
            ln = np.linalg.norm(n)
            n = n / ln if ln > 1e-12 else np.zeros(3)
            f.write(struct.pack("<3f", *n))
            for v in (a, b, c):
                f.write(struct.pack("<3f", *v))
            f.write(b"\x00\x00")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vowel", default="ah", choices=sorted(VOWELS))
    ap.add_argument("--wall", type=float, default=3.0, help="wall thickness, mm")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    tris = build(args.vowel, args.wall, args.scale)
    out = Path(args.out or f"tract-{args.vowel}.stl")
    write_stl(out, tris)

    bore = bore_profile(args.vowel) * args.scale
    length = N_SECTIONS * SECTION_CM * 10.0 * args.scale
    print(f"wrote {out}  ({len(tris)} triangles)")
    print(f"  length      {length:.1f} mm   ({N_SECTIONS} sections x {SECTION_CM*10:.2f} mm)")
    print(f"  bore        {bore.min():.1f} - {bore.max():.1f} mm")
    print(f"  outer       {bore.max() + 2*args.wall:.1f} mm at the widest")
    print(f"  glottis end {bore[0]:.1f} mm   lips end {bore[-1]:.1f} mm")
    print()
    print("  ACCEPTANCE: buzz a source at the glottis end and record at the lips.")
    print("  Expect the first two resonances near the simulator's own numbers.")
    print("  If they are far off, the simulator is not modelling this object.")


if __name__ == "__main__":
    main()
