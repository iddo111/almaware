# -*- coding: utf-8 -*-
"""
MIKDASH — the future Temple of Yechezkel 40-43, built from the text's own numbers.

Every measurement in M below carries the verse it comes from. Nothing is invented
silently: a measurement is one of

    GIVEN    the text states this number outright
    DERIVED  the text states a total and all the other parts, so this follows by
             arithmetic (and is cross-checked against a second verse where possible)
    INFERRED the text does NOT give this. It is named here, it is listed in
             SOURCES.md, and in the viewer it can be lit up in a separate colour
             by pressing I. Do not mistake it for scripture.

Units are cubits throughout. The conversion to metres is a single constant.
Numpy only, no torch, no GPU  (D:\\CLAUDE\\CLAUDE.md).
"""
from __future__ import annotations

# ----------------------------------------------------------------------------
# THE CUBIT
# ----------------------------------------------------------------------------
# Yechezkel 40:5 defines the measuring reed as "six cubits, by the cubit and a
# handbreadth" (shesh amot ba-amah va-tefach), and 43:13 repeats the same standard
# for the altar. So Yechezkel's cubit is the LONG cubit of 7 handbreadths, not the
# ordinary 6. The physical size of a handbreadth is disputed and always has been:
#     R' Chaim Naeh    tefach ~= 8.0 cm  ->  long cubit 0.560 m
#     Chazon Ish       tefach ~= 9.6 cm  ->  long cubit 0.672 m
# We pick R' Chaim Naeh, visibly, and put it in one constant so it can be flipped.
TEFACH_M = 0.08
CUBIT_TEFACHIM = 7                      # 40:5, 43:13 — "the cubit and a handbreadth"
CUBIT_M = TEFACH_M * CUBIT_TEFACHIM     # 0.56 m
REED_CUBITS = 6                         # 40:5 — "a measuring reed of six cubits"

# A person, for scale. 1.80 m expressed in Yechezkel's cubits.
PERSON_M = 1.80
PERSON_CUBITS = PERSON_M / CUBIT_M      # ~3.21 cubits
EYE_M = 1.65                            # walker's eye height


def _m(value, kind, src, note=""):
    return {"v": value, "kind": kind, "src": src, "note": note}


# ----------------------------------------------------------------------------
# THE MEASUREMENTS
# ----------------------------------------------------------------------------
M = {
    # --- the outer wall and the sacred boundary -----------------------------
    "wall_thick":       _m(6,   "GIVEN",  "Yech 40:5",
                            "one reed: 'he measured the breadth of the building, one reed'"),
    "wall_height":      _m(6,   "GIVEN",  "Yech 40:5",
                            "one reed: 'and the height, one reed'"),
    "precinct":         _m(500, "GIVEN",  "Yech 42:15-20",
                            "500 x 500. Units disputed - see 'precinct_unit'"),
    "boundary_reeds":   _m(500, "GIVEN",  "Yech 42:16-20 (qere)",
                            "the separating wall, 500 REEDS = 3000 cubits, per the qere"),

    # --- the gates. All six are explicitly the same (40:21,24,28,32,35) -----
    "gate_depth":       _m(50,  "GIVEN",  "Yech 40:21,25,29,33,36", "'fifty cubits long'"),
    "gate_width":       _m(25,  "GIVEN",  "Yech 40:13",  "'breadth 25, door against door'"),
    "gate_threshold":   _m(6,   "GIVEN",  "Yech 40:6,7", "one reed; there are two thresholds"),
    "gate_cell":        _m(6,   "GIVEN",  "Yech 40:7,12", "the ta - one reed square; 40:12 'six cubits'"),
    "gate_pier":        _m(5,   "GIVEN",  "Yech 40:7",   "'between the guardrooms, five cubits'"),
    "gate_cells_side":  _m(3,   "GIVEN",  "Yech 40:10",  "'three on this side and three on that side'"),
    "gate_porch":       _m(8,   "GIVEN",  "Yech 40:9",   "'the porch of the gate, eight cubits'"),
    "gate_post":        _m(2,   "GIVEN",  "Yech 40:9",   "'and its posts, two cubits'"),
    "gate_opening":     _m(10,  "GIVEN",  "Yech 40:11",  "'the breadth of the entry of the gate, ten cubits'"),
    "gate_passage":     _m(13,  "GIVEN",  "Yech 40:11",  "'the length of the gate, thirteen cubits'"),
    "gate_border":      _m(1,   "GIVEN",  "Yech 40:12",  "'a border before the cells, one cubit'"),
    "steps_outer":      _m(7,   "GIVEN",  "Yech 40:22,26", "'by seven steps they went up to it'"),
    "steps_inner":      _m(8,   "GIVEN",  "Yech 40:31,34,37", "'and eight steps'"),

    # --- the courts ---------------------------------------------------------
    "court_gap":        _m(100, "GIVEN",  "Yech 40:19,23,27", "'from gate to gate, a hundred cubits'"),
    "inner_court":      _m(100, "GIVEN",  "Yech 40:47", "'the court, a hundred long and a hundred broad, foursquare'"),
    "outer_chambers":   _m(30,  "GIVEN",  "Yech 40:17", "'thirty chambers upon the pavement'"),

    # --- the House ----------------------------------------------------------
    "house_len":        _m(100, "GIVEN",  "Yech 41:13", "'he measured the house, a hundred cubits long'"),
    "house_front":      _m(100, "GIVEN",  "Yech 41:14", "'the breadth of the face of the house... a hundred cubits'"),
    "ulam_front_wall":  _m(6,   "DERIVED", "Yech 41:13 minus 41:1-9; confirmed by 41:5",
                            "Yechezkel never states it. 100 - (11+6+40+2+20+6+4+5) = 6, and 41:5 "
                            "independently gives the wall of the house as 6. Two routes agree. "
                            "Note Middot 4:7 gives 5 for the Second Temple's ulam wall."),
    "ulam_depth":       _m(11,  "GIVEN",  "Yech 40:49", "'the breadth eleven cubits' (Masoretic; LXX has twelve)"),
    "ulam_width":       _m(20,  "GIVEN",  "Yech 40:49", "'the length of the porch, twenty cubits'"),
    "ulam_pier":        _m(5,   "GIVEN",  "Yech 40:48", "'five cubits on this side and five cubits on that side'"),
    "ulam_jamb":        _m(3,   "GIVEN",  "Yech 40:48", "'the breadth of the gate, three cubits on either side'"),
    "heichal_len":      _m(40,  "GIVEN",  "Yech 41:2",  "'he measured its length, forty cubits'"),
    "heichal_width":    _m(20,  "GIVEN",  "Yech 41:2",  "'and the breadth, twenty cubits'"),
    "heichal_door":     _m(10,  "GIVEN",  "Yech 41:2",  "'the breadth of the door, ten cubits'"),
    "heichal_shoulder": _m(5,   "GIVEN",  "Yech 41:2",  "'the sides of the door, five cubits on either side'"),
    "house_wall":       _m(6,   "GIVEN",  "Yech 41:5",  "'he measured the wall of the house, six cubits'"),
    "partition":        _m(2,   "GIVEN",  "Yech 41:3",  "'he measured the post of the door, two cubits'"),
    "dvir_door":        _m(6,   "GIVEN",  "Yech 41:3",  "'and the door, six cubits'"),
    "dvir":             _m(20,  "GIVEN",  "Yech 41:4",  "'twenty cubits by twenty - this is the Holy of Holies'"),
    "tzela":            _m(4,   "GIVEN",  "Yech 41:5",  "'the breadth of every side chamber, four cubits'"),
    "tzela_outer_wall": _m(5,   "GIVEN",  "Yech 41:9",  "'the wall of the side chamber outward, five cubits'"),
    "tzela_tiers":      _m(3,   "GIVEN",  "Yech 41:6",  "'side chamber over side chamber, three'"),
    "free_strip":       _m(20,  "GIVEN",  "Yech 41:10", "'between the chambers, a breadth of twenty cubits'"),
    "gizrah_side":      _m(25,  "DERIVED", "Yech 41:14 minus the 50-cubit house block",
                            "(100 - 50) / 2 = 25 of open gizrah on the north and on the south"),

    # --- the western building (binyan) -------------------------------------
    "binyan_width":     _m(70,  "GIVEN",  "Yech 41:12", "'the breadth, seventy cubits'"),
    "binyan_len":       _m(90,  "GIVEN",  "Yech 41:12", "'and its length, ninety cubits'"),
    "binyan_wall":      _m(5,   "GIVEN",  "Yech 41:12", "'the wall of the building, five cubits thick'"),

    # --- the priests' chambers (ch. 42) ------------------------------------
    "lishkot_len":      _m(100, "GIVEN",  "Yech 42:2,8", "'the length a hundred cubits'"),
    "lishkot_width":    _m(50,  "GIVEN",  "Yech 42:2",   "'and the breadth fifty cubits'"),
    "lishkot_walk":     _m(10,  "GIVEN",  "Yech 42:4",   "'before the chambers a walk of ten cubits breadth'"),
    "lishkot_tiers":    _m(3,   "GIVEN",  "Yech 42:6",   "'for they were in three storeys'"),

    # --- the altar (43:13-17) ----------------------------------------------
    "altar_ariel":      _m(12,  "GIVEN",  "Yech 43:16", "'the ariel, twelve long by twelve broad, foursquare'"),
    "altar_azarah":     _m(14,  "GIVEN",  "Yech 43:17", "'the settle, fourteen long by fourteen broad'"),
    "altar_base_h":     _m(2,   "GIVEN",  "Yech 43:14", "'from the base upon the ground to the lower settle, two cubits'"),
    "altar_mid_h":      _m(4,   "GIVEN",  "Yech 43:14", "'from the lesser settle to the greater settle, four cubits'"),
    "altar_harel_h":    _m(4,   "GIVEN",  "Yech 43:15", "'and the harel, four cubits'"),
    "altar_setback":    _m(1,   "GIVEN",  "Yech 43:14", "'and the breadth one cubit' - each stage steps in by one"),
    "altar_chik":       _m(1,   "GIVEN",  "Yech 43:13", "'the base shall be a cubit, and the breadth a cubit'"),
    "altar_border":     _m(0.5, "GIVEN",  "Yech 43:13,17", "'the border by its edge round about, one span (zeret)'"),
    "altar_horns":      _m(4,   "GIVEN",  "Yech 43:15", "'and from the ariel upward, four horns'"),

    # --- heights the text simply does not give ------------------------------
    "h_court_wall":     _m(6,   "INFERRED", "no verse",
                            "by analogy with the outer wall of 40:5, which is one reed high"),
    "h_gate":           _m(12,  "INFERRED", "no verse",
                            "Yechezkel gives no gate height anywhere. Chosen to be walkable."),
    "h_gate_porch":     _m(14,  "INFERRED", "no verse", "as above; the porch is raised over the passage"),
    "h_house":          _m(30,  "INFERRED", "no verse",
                            "Yechezkel gives no height for the House. Middot 4:6 gives 100 cubits "
                            "for the SECOND Temple - a different building - so it is not used here."),
    "h_tzela_tier":     _m(6,   "INFERRED", "no verse", "one reed per tier, three tiers (41:6)"),
    "h_binyan":         _m(18,  "INFERRED", "no verse", ""),
    "h_lishkot_tier":   _m(6,   "INFERRED", "no verse", "three storeys (42:6)"),
    "step_rise":        _m(0.5, "INFERRED", "no verse",
                            "the step COUNTS are given (40:22,26,31,34,37); the rise is not"),
    "step_tread":       _m(1.0, "INFERRED", "no verse", ""),
    "steps_ulam":       _m(10,  "INFERRED", "LXX 40:49",
                            "the Masoretic text says only 'by steps'; the Septuagint says ten"),
    "altar_horn_size":  _m(1,   "INFERRED", "no verse", "43:15 gives four horns but no dimension"),
}


def val(key):
    return M[key]["v"]


# ----------------------------------------------------------------------------
# LEVELS — the floor heights, from the step counts
# ----------------------------------------------------------------------------
GROUND = 0.0
Y_OUTER = val("steps_outer") * val("step_rise")            # 7 steps  -> 3.5
Y_INNER = Y_OUTER + val("steps_inner") * val("step_rise")  # +8 steps -> 7.5
Y_HOUSE = Y_INNER + val("steps_ulam") * val("step_rise")   # +10      -> 12.5


# ----------------------------------------------------------------------------
# THE ARITHMETIC THE TEXT ITSELF ASSERTS — checked, not assumed
# ----------------------------------------------------------------------------
def checks():
    """Each entry: (name, computed, stated, verse). All must match."""
    v = val
    out = []

    gate = [v("gate_threshold"),
            v("gate_cell"), v("gate_pier"), v("gate_cell"), v("gate_pier"), v("gate_cell"),
            v("gate_threshold"), v("gate_porch"), v("gate_post")]
    out.append(("gate depth", sum(gate), v("gate_depth"), "Yech 40:21", " + ".join(map(str, gate))))

    gw = [v("gate_cell"), v("gate_passage"), v("gate_cell")]
    out.append(("gate width", sum(gw), v("gate_width"), "Yech 40:13", " + ".join(map(str, gw))))

    house = [v("ulam_front_wall"), v("ulam_depth"), v("house_wall"), v("heichal_len"),
             v("partition"), v("dvir"), v("house_wall"), v("tzela"), v("tzela_outer_wall")]
    out.append(("house east-west", sum(house), v("house_len"), "Yech 41:13", " + ".join(map(str, house))))

    block = [v("tzela_outer_wall"), v("tzela"), v("house_wall"), v("heichal_width"),
             v("house_wall"), v("tzela"), v("tzela_outer_wall")]
    out.append(("house north-south block", sum(block), 50, "itemised 41:2,5,9", " + ".join(map(str, block))))

    front = sum(block) + 2 * v("gizrah_side")
    out.append(("house front + gizrah", front, v("house_front"), "Yech 41:14",
                f"{sum(block)} + {v('gizrah_side')} + {v('gizrah_side')}"))

    east = [v("inner_court") / 2, v("gate_depth"), v("court_gap"), v("gate_depth")]
    west = [v("inner_court") / 2, v("house_len"), v("house_len")]
    out.append(("whole precinct east-west", int(sum(east) + sum(west)), v("precinct"),
                "Yech 42:20 (in cubits, per Rashi)",
                " + ".join(str(int(x)) for x in east + west)))

    binyan = v("binyan_len") + 2 * v("binyan_wall")
    out.append(("binyan with its walls", binyan, v("house_len"), "Yech 41:13",
                f"{v('binyan_len')} + {v('binyan_wall')} + {v('binyan_wall')}"))

    altar = [v("altar_ariel"), 2 * v("altar_setback")]
    out.append(("altar: ariel + two setbacks", sum(altar), v("altar_azarah"), "Yech 43:16-17",
                f"{v('altar_ariel')} + {v('altar_setback')} + {v('altar_setback')}"))

    return out


def report():
    ok = True
    lines = []
    for name, got, want, ref, work in checks():
        good = abs(got - want) < 1e-9
        ok = ok and good
        lines.append(("MATCH   " if good else "MISMATCH") +
                     f" {name:26s} {work:>34s} = {got:<5g} text says {want:<5g} [{ref}]")
    return ok, lines


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    good, lines = report()
    print("\n".join(lines))
    print()
    print(f"cubit = {CUBIT_M:.3f} m ({CUBIT_TEFACHIM} tefachim x {TEFACH_M*100:.1f} cm, R' Chaim Naeh)")
    print(f"reed  = {REED_CUBITS * CUBIT_M:.3f} m")
    print(f"levels: outside {GROUND}, outer court {Y_OUTER}, inner court {Y_INNER}, house {Y_HOUSE} cubits")
    n_given = sum(1 for k in M if M[k]["kind"] == "GIVEN")
    n_der = sum(1 for k in M if M[k]["kind"] == "DERIVED")
    n_inf = sum(1 for k in M if M[k]["kind"] == "INFERRED")
    print(f"measurements: {n_given} GIVEN, {n_der} DERIVED, {n_inf} INFERRED  (total {len(M)})")
    sys.exit(0 if good else 1)
