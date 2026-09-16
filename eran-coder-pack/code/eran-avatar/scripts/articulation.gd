## articulation.gd -- loads data/articulation.json (written by tools/export_articulation.py).
## Every number in it except `jaw_open01_derived` is the physics that rendered the wav:
## a 23-section area function (cm^2) of ERAN's adult tract at 60 fps, plus velum/voicing/tenseness.
class_name Articulation
extends RefCounted

var meta: Dictionary = {}
var syllables: Dictionary = {}
var fps: float = 60.0
var n_sections: int = 23
var section_cm: float = 0.7292
var ladder_cm: float = 16.771
var nasal_junction: int = 9
var lip_open_cm2: float = 3.813
var seal_cm2: float = 0.01
var velum_open: float = 0.05
var no_noise_cm2: float = 0.49
var ok: bool = false


static func load_from(path: String) -> Articulation:
	var a := Articulation.new()
	var data: Variant = null
	if FileAccess.file_exists(path):
		data = JSON.parse_string(FileAccess.get_file_as_string(path))
	else:
		var res: Variant = load(path)            # exported build: .json imported as a JSON resource
		if res is JSON:
			data = res.data
	if data == null or not (data is Dictionary):
		push_error("[ERAN-AVATAR] articulation.json missing or unparsable at " + path)
		return a
	a._from_dict(data)
	return a


func _from_dict(d: Dictionary) -> void:
	meta = d
	syllables = d.get("syllables", {})
	fps = float(d.get("fps", 60))
	var t: Dictionary = d.get("tract", {})
	n_sections = int(t.get("n_sections", 23))
	section_cm = float(t.get("section_cm", 0.7292))
	ladder_cm = float(t.get("ladder_cm", 16.771))
	nasal_junction = int(t.get("nasal_junction_section", 9))
	lip_open_cm2 = float(d.get("lip_area_open_cm2", 3.813))
	seal_cm2 = float(d.get("seal_cm2", 0.01))
	velum_open = float(d.get("velum_open_threshold", 0.05))
	no_noise_cm2 = float(d.get("no_noise_cm2", 0.49))
	ok = syllables.size() > 0


func has(name: String) -> bool:
	return syllables.has(name)


func syllable(name: String) -> Dictionary:
	return syllables.get(name, {})


## Frame index for time t (seconds from syllable start), clamped to the syllable.
func frame_index(syl: Dictionary, t: float) -> int:
	var frames: Array = syl.get("frames", [])
	if frames.is_empty():
		return 0
	return clampi(int(floor(t * fps)), 0, frames.size() - 1)


func frame_at(syl: Dictionary, t: float) -> Dictionary:
	var frames: Array = syl.get("frames", [])
	if frames.is_empty():
		return {}
	return frames[frame_index(syl, t)]


## --- the mapping formulas of the brief, section 2.2 (all constants measured over the 21) ---
func lip_open01(f: Dictionary) -> float:
	return sqrt(clampf(float(f.get("lip_area", 0.0)) / lip_open_cm2, 0.0, 1.0))


func tightness01(f: Dictionary) -> float:
	return 1.0 - clampf(float(f.get("min_area", 1.0)) / (no_noise_cm2 + 0.01), 0.0, 1.0)


func nasal_open(f: Dictionary) -> bool:
	return float(f.get("velum", 0.0)) > velum_open


func sealed(f: Dictionary) -> bool:
	return float(f.get("min_area", 1.0)) < seal_cm2
