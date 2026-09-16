from __future__ import annotations

from typing import Dict, List


EXAMPLES: List[Dict[str, object]] = [
    {
        "id": "axis-check-1mm",
        "name": "1 mm axis check",
        "file_name": "xe-pro-axis-check-1mm.nc",
        "summary": "Moves X, Y, and Z out and back by 1 mm at commissioning speed.",
        "size": "1 x 1 x 1 mm",
        "feed_mm_min": 100,
        "tag": "FIRST TEST",
        "source": """(XE-PRO built-in example: 1 mm axis check)
G21
G91
G1 X1 F100
G1 X-1 F100
G1 Y1 F100
G1 Y-1 F100
G1 Z1 F100
G1 Z-1 F100
M5
""",
    },
    {
        "id": "square-20mm",
        "name": "20 mm square",
        "file_name": "xe-pro-square-20mm.nc",
        "summary": "Traces a small square and returns to the starting point.",
        "size": "20 x 20 mm",
        "feed_mm_min": 300,
        "tag": "GEOMETRY",
        "source": """(XE-PRO built-in example: 20 mm square)
G21
G91
G1 X20 F300
G1 Y20 F300
G1 X-20 F300
G1 Y-20 F300
M5
""",
    },
    {
        "id": "diamond-30mm",
        "name": "30 mm diamond",
        "file_name": "xe-pro-diamond-30mm.nc",
        "summary": "Checks coordinated X/Y motion with four diagonal moves.",
        "size": "30 x 30 mm",
        "feed_mm_min": 300,
        "tag": "XY SYNC",
        "source": """(XE-PRO built-in example: 30 mm diamond)
G21
G91
G1 X15 Y15 F300
G1 X-15 Y15 F300
G1 X-15 Y-15 F300
G1 X15 Y-15 F300
M5
""",
    },
    {
        "id": "raster-40x20",
        "name": "40 x 20 mm raster",
        "file_name": "xe-pro-raster-40x20.nc",
        "summary": "Runs a five-line serpentine pattern to expose Y1/Y2 tracking errors.",
        "size": "40 x 20 mm",
        "feed_mm_min": 400,
        "tag": "GANTRY CHECK",
        "source": """(XE-PRO built-in example: 40 x 20 mm raster)
G21
G91
G1 X40 F400
G1 Y5 F200
G1 X-40 F400
G1 Y5 F200
G1 X40 F400
G1 Y5 F200
G1 X-40 F400
G1 Y5 F200
G1 X40 F400
G1 X-40 F400
G1 Y-20 F200
M5
""",
    },
]


def public_examples() -> List[Dict[str, object]]:
    return [dict(item) for item in EXAMPLES]
