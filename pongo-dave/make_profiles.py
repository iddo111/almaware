# Build the PONGO/Dave PETG print profiles from the stock K2 Plus ones.
# Overrides come from PLAN-dave-uclip.md (Iddo/Dave, 2026-09-01).
import json, os, sys

SYS = r"C:/Program Files/OrcaSlicer/resources/profiles/Creality"
OUT = r"D:/CLAUDE/pongo-dave/print"

PROC_SRC = SYS + "/process/0.20mm Strength @Creality K2 Plus 0.4 nozzle.json"
FIL_SRC  = SYS + "/filament/CR-PETG @K2 Plus-all.json"

SPEED = "40"          # plan: 40 mm/s
proc_over = {
    "name": "PONGO clip PETG 0.20 @K2 Plus",
    "wall_loops": "4",                 # plan: 4 perimeters
    "sparse_infill_density": "40%",    # plan: 40 % infill
    "brim_type": "outer_only",         # 70 mm tall part on a small footprint
    "brim_width": "5",
    "enable_support": "0",             # orientation needs none
    "outer_wall_speed": SPEED,
    "inner_wall_speed": SPEED,
    "sparse_infill_speed": SPEED,
    "internal_solid_infill_speed": SPEED,
    "top_surface_speed": SPEED,
    "gap_infill_speed": SPEED,
    "initial_layer_speed": "25",
    "initial_layer_infill_speed": "25",
    "default_acceleration": "3000",    # tall thin tower - keep the jerk off it
    "outer_wall_acceleration": "2000",
    "inner_wall_acceleration": "2000",
    "initial_layer_acceleration": "1000",
}
fil_over = {
    "name": "PONGO PETG @K2 Plus",
    "nozzle_temperature": "240",               # plan
    "nozzle_temperature_initial_layer": "245",
    "hot_plate_temp": "80",                    # plan
    "hot_plate_temp_initial_layer": "80",
    "textured_plate_temp": "80",
    "textured_plate_temp_initial_layer": "80",
    "cool_plate_temp": "80",
    "cool_plate_temp_initial_layer": "80",
    "eng_plate_temp": "80",
    "eng_plate_temp_initial_layer": "80",
    "fan_max_speed": "30",                     # plan: 30 % fan
    "fan_min_speed": "30",
}

def apply(src, over, dst):
    d = json.load(open(src, encoding="utf-8"))
    changed, added = [], []
    for k, v in over.items():
        if k in d and isinstance(d[k], list):
            old = d[k]; d[k] = [v] * len(d[k])
        elif k in d:
            old = d[k]; d[k] = v
        else:
            if k in ("name",):
                old = d.get(k); d[k] = v
            else:
                # keep the same shape the sibling keys use
                old = None; d[k] = [v] if any(isinstance(x, list) for x in d.values()) and src == FIL_SRC else v
                added.append(k)
        if old is not None and old != d[k]:
            changed.append("%s: %s -> %s" % (k, old, d[k]))
    json.dump(d, open(dst, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("WROTE", dst)
    for c in changed: print("   ", c)
    if added: print("    added:", ", ".join(added))

os.makedirs(OUT, exist_ok=True)
apply(PROC_SRC, proc_over, OUT + "/PONGO-process.json")
apply(FIL_SRC,  fil_over,  OUT + "/PONGO-filament.json")
