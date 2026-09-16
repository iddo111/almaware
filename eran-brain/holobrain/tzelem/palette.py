"""TZELEM / צלם — THE PALETTE: where colour lives, OUTSIDE the weave.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

לזכרה של עלמה ז"ל.

THE HONEST LIMIT THIS FILE TURNS INTO A DESIGN
----------------------------------------------
A spark in ALMA v0.3 is a SCALAR. So a brushstroke's spark can carry exactly one
number, and in `anatomy.weave_for` that number is the stroke's INDEX (`i + 1`).
Smuggling an RGB triple into a spark would be a lie about the language, and the
lab has a law against that kind of lie.

So colour is a LOOKUP, not a signal:

    the weave   says  WHICH stroke owns this patch of canvas   (an index)
    the palette says  WHAT COLOUR stroke i is                  (a table)

The table is sampled once, at planting time, from the SHADED truth at each
stroke's anchor — the Lambert that `Stage.shade` already computes. A painter
paints what he SEES, not what the wall is made of; that was bug #2 of gate 1 and
it stays fixed here.

Because the palette is only ever read AFTER ownership is decided, changing every
colour in it cannot move a single edge. `tests/test_gate2.py::
test_palette_lookup_does_not_change_occlusion` is that sentence, executed.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

BACKGROUND = (0.82, 0.87, 0.94)          # the sky the stage shades with


@dataclass
class Palette:
    """table[i] = the RGB of stroke i. Index in, colour out. Nothing else."""

    table: np.ndarray

    def __post_init__(self) -> None:
        self.table = np.asarray(self.table, dtype=np.float64)
        if self.table.ndim != 2 or self.table.shape[1] != 3:
            raise ValueError(f"a palette is (N,3), got {self.table.shape}")

    def __len__(self) -> int:
        return int(self.table.shape[0])

    # ---------------------------------------------------------------- build

    @classmethod
    def of(cls, strokes) -> "Palette":
        """The palette a set of strokes was planted with.

        `anatomy.scatter` samples `Stage.shade(gbuffer)` at each anchor pixel and
        stores it on the Strokes. That array IS the palette table — this just
        gives it its real name and its own type.
        """
        return cls(strokes.rgb)

    @classmethod
    def shuffled(cls, strokes, seed: int = 0) -> "Palette":
        """A deliberately wrong palette, for the test that colour cannot occlude."""
        rng = np.random.default_rng(seed)
        return cls(rng.random((len(strokes), 3)))

    # --------------------------------------------------------------- lookup

    def lookup(self, owner: np.ndarray,
               background=BACKGROUND) -> np.ndarray:
        """(H,W) int ownership map -> (H,W,3) picture. -1 means nobody arrived."""
        bg = np.asarray(background, dtype=np.float64)
        out = np.empty(owner.shape + (3,), dtype=np.float64)
        hit = owner >= 0
        out[~hit] = bg
        if hit.any():
            out[hit] = self.table[owner[hit]]
        return out
