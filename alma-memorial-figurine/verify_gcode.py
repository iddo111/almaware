import hashlib
import json
import math
import os
import re
import sys


MOVE_RE = re.compile(r"^G([0123])(?:\s|$)", re.I)
AXIS_RE = re.compile(r"(?:^|\s)([XYZ])(-?(?:\d+(?:\.\d*)?|\.\d+))", re.I)


def verify(path):
    absolute = True
    pos = {"X": 0.0, "Y": 0.0, "Z": 0.0}
    mins = {"X": math.inf, "Y": math.inf, "Z": math.inf}
    maxs = {"X": -math.inf, "Y": -math.inf, "Z": -math.inf}
    motion_lines = 0
    layer_markers = 0
    support_lines = 0
    metadata = {}
    config_started = False

    sha = hashlib.sha256()
    with open(path, "rb") as raw:
        for block in iter(lambda: raw.read(1024 * 1024), b""):
            sha.update(block)

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            text = line.strip()
            low = text.lower()
            if low.startswith("; config_block_start"):
                config_started = True
            if not config_started:
                if text == "G90":
                    absolute = True
                elif text == "G91":
                    absolute = False
                if text.startswith(";LAYER_CHANGE"):
                    layer_markers += 1
                if "; support material" in low:
                    support_lines += 1
                if MOVE_RE.match(text):
                    axes = {m.group(1).upper(): float(m.group(2)) for m in AXIS_RE.finditer(text)}
                    for axis, value in axes.items():
                        pos[axis] = value if absolute else pos[axis] + value
                        mins[axis] = min(mins[axis], pos[axis])
                        maxs[axis] = max(maxs[axis], pos[axis])
                    motion_lines += 1

            if not config_started:
                for key, marker in [
                    ("layers_header", "; total layer number:"),
                    ("filament_mm", "; filament used [mm] ="),
                    ("filament_cm3", "; filament used [cm3] ="),
                    ("filament_g", "; filament used [g] ="),
                    ("estimated_time", "; estimated printing time (normal mode) ="),
                    ("max_z_header", "; max_z_height:"),
                ]:
                    if marker in low and key not in metadata:
                        metadata[key] = text.split("=", 1)[-1].strip() if "=" in text else text.split(":", 1)[-1].strip()

    finite = all(math.isfinite(v) for v in [*mins.values(), *maxs.values()])
    within_k2 = (
        finite
        and mins["X"] >= -0.001
        and mins["Y"] >= -0.001
        and mins["Z"] >= -0.001
        and maxs["X"] <= 350.001
        and maxs["Y"] <= 350.001
        and maxs["Z"] <= 350.001
    )
    return {
        "file": os.path.abspath(path),
        "bytes": os.path.getsize(path),
        "sha256": sha.hexdigest(),
        "motion_lines": motion_lines,
        "layer_markers": layer_markers,
        "support_motion_lines": support_lines,
        "motion_bounds_mm": {"min": mins, "max": maxs},
        "within_k2_plus_350mm_motion_bounds": within_k2,
        "metadata": metadata,
        "pass": within_k2 and layer_markers > 2000 and support_lines > 0,
    }


if __name__ == "__main__":
    result = verify(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["pass"] else 2)
