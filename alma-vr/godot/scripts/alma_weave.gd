# alma_weave.gd — the heart of the ALMA<->Godot bridge.
#
# Loads a weave JSON at runtime (alma-language's alma/godot.py exports it —
# the canonical ALMA text format, SPEC.md §8, plus an additive "scene"
# block for layout and an additive "trace" block for playback) and builds
# the sculpture SPEC.md §10 promises:
#
#   knot     -> a solid whose SHAPE is its verb (sphere=pass/sum,
#               box=pool, torus=gate, cone=prod, hemisphere=fringe)
#   trigger  -> a collar around the knot's equator (open ring=any,
#               notched ring=count N, wide band=rise T)
#   thread   -> one cord PER STRAND (a 3-strand thread is 3 visible cords)
#   weight   -> the cord's thickness (negative = cool colour, not warm)
#   delay    -> the cord's path: straight for delay 1, a visible bow/arc
#               for delay > 1 (distance is time — SPEC.md law #1)
#
# If the JSON carries a "trace", the weave can be PLAYED: a small emissive
# spark travels each cord from source to destination over exactly `delay`
# beats, arriving when the loom says it arrives, and a knot pulses when it
# fires. beats_per_second, play(), pause(), restep() let you watch a weave
# think, slowly. Everything below is a pure function of one float
# (_beat_pos), so scrubbing/restepping needs no separate rewind logic.
#
# Self-contained, procedural, no external assets — matches neuron_forest.gd.
extends Node3D

@export_file("*.json") var weave_path: String = "res://weaves/fib.json"
@export var beats_per_second: float = 0.6
@export var autoplay: bool = true

const KNOT_LABEL_OFFSET := Vector3(0, 1.3, 0)
const BIAS_LABEL_OFFSET := Vector3(0, -1.0, 0)
const PULSE_WINDOW := 0.6              # beats either side of a fire that glow
const PULSE_BOOST := 3.0
const SPARK_RADIUS := 0.16
const CORD_MIN_RADIUS := 0.03
const CORD_MAX_RADIUS := 0.4

var _weave: Dictionary = {}
var _positions: Dictionary = {}        # knot name -> Vector3
var _knot_mats: Dictionary = {}        # knot name -> StandardMaterial3D
var _knot_base_energy: Dictionary = {}
var _fires: Array = []                 # [{beat, knot, spoke}]
var _sparks: Array = []                # [{from,to,port,weight,delay,depart,arrival,value,path,node}]
var _min_beat := 0.0
var _max_beat := 1.0
var _beat_pos := 0.0
var _playing := true


func _ready() -> void:
	_playing = autoplay
	_ambient()
	_load_weave()
	_build_knots()
	_build_threads()
	_build_sparks()
	_compute_beat_range()
	_beat_pos = _min_beat
	_update_visuals()


func _process(delta: float) -> void:
	if _playing:
		_beat_pos = clampf(_beat_pos + delta * beats_per_second, _min_beat, _max_beat)
		_update_visuals()

# -------------------------------------------------------- playback control

func play() -> void:
	_playing = true


func pause() -> void:
	_playing = false


func restep(beats: float) -> void:
	_beat_pos = clampf(_beat_pos + beats, _min_beat, _max_beat)
	_update_visuals()

# ------------------------------------------------------------- ambient world

func _ambient() -> void:
	var env := WorldEnvironment.new()
	var e := Environment.new()
	e.background_mode = Environment.BG_COLOR
	e.background_color = Color(0.01, 0.01, 0.035)
	e.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	e.ambient_light_color = Color(0.2, 0.22, 0.32)
	e.ambient_light_energy = 0.6
	e.glow_enabled = true
	e.glow_intensity = 1.0
	e.fog_enabled = true
	e.fog_light_color = Color(0.05, 0.08, 0.2)
	e.fog_density = 0.008
	env.environment = e
	add_child(env)

	var sun := DirectionalLight3D.new()
	sun.light_energy = 0.7
	sun.rotation_degrees = Vector3(-50, -30, 0)
	add_child(sun)

# ------------------------------------------------------------------ loading

func _load_weave() -> void:
	var f := FileAccess.open(weave_path, FileAccess.READ)
	if f == null:
		push_error("alma_weave: cannot open " + weave_path)
		return
	var parsed: Variant = JSON.parse_string(f.get_as_text())
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("alma_weave: bad JSON in " + weave_path)
		return
	_weave = parsed

	var scene: Dictionary = _weave.get("scene", {})
	var positions: Dictionary = scene.get("positions", {})
	for name in positions.keys():
		var p: Array = positions[name]
		_positions[name] = Vector3(float(p[0]), float(p[1]), float(p[2]))

	var trace: Dictionary = _weave.get("trace", {})
	_fires = trace.get("fires", [])
	for s in trace.get("sparks", []):
		_sparks.append({
			"from": s.get("from", ""),
			"to": s.get("to", ""),
			"port": s.get("port", "in"),
			"weight": float(s.get("weight", 1.0)),
			"delay": int(s.get("delay", 1)),
			"depart": float(s.get("depart_beat", 0)),
			"arrival": float(s.get("arrival_beat", 0)),
			"value": float(s.get("value", 0.0)),
		})


func _compute_beat_range() -> void:
	_min_beat = 0.0
	_max_beat = 1.0
	for f in _fires:
		_max_beat = maxf(_max_beat, float(f.get("beat", 0)) + 1.0)
	for sp in _sparks:
		_max_beat = maxf(_max_beat, float(sp["arrival"]) + 1.0)

# -------------------------------------------------------------- knot shapes

func _verb_mesh(verb: String) -> Mesh:
	match verb:
		"pool":
			var m := BoxMesh.new()
			m.size = Vector3(1.15, 1.15, 1.15)
			return m
		"gate":
			var m := TorusMesh.new()
			m.inner_radius = 0.45
			m.outer_radius = 0.78
			return m
		"prod":
			var m := CylinderMesh.new()
			m.top_radius = 0.0
			m.bottom_radius = 0.72
			m.height = 1.3
			return m
		"fringe":
			var m := SphereMesh.new()
			m.radius = 0.65
			m.height = 1.3
			m.is_hemisphere = true
			return m
		"spell":                        # a solid with an inside: it computes
			var m := PrismMesh.new()
			m.size = Vector3(1.15, 1.25, 1.15)
			return m
		_:                              # pass / sum
			var m := SphereMesh.new()
			m.radius = 0.6
			m.height = 1.2
			return m


func _verb_hue(verb: String) -> float:
	match verb:
		"pool": return 0.09             # warm orange — the stateful one
		"gate": return 0.83             # magenta/violet — the decider
		"prod": return 0.30             # yellow-green
		"fringe": return 0.0            # red-white — the hem, facing out
		"spell": return 0.70            # indigo — the knot that computes
		_: return 0.55                  # cyan — pass/sum


func _add_collar(parent: Node3D, trigger: String) -> void:
	var parts := trigger.split(" ")
	var kind := parts[0] if parts.size() > 0 else "any"
	var mat := StandardMaterial3D.new()
	mat.emission_enabled = true
	mat.emission = Color(0.92, 0.92, 1.0)
	mat.emission_energy_multiplier = 1.3
	mat.albedo_color = Color(0.1, 0.1, 0.15)

	var ring := TorusMesh.new()
	var mi := MeshInstance3D.new()
	if kind == "rise":
		ring.inner_radius = 0.76        # a wide band: evidence gathers slowly
		ring.outer_radius = 1.08
	elif kind == "count":
		ring.inner_radius = 0.85        # a thin ring, notched below
		ring.outer_radius = 0.98
	else:                                # "any": a plain open ring
		ring.inner_radius = 0.9
		ring.outer_radius = 0.97
	mi.mesh = ring
	mi.material_override = mat
	mi.rotation.x = PI / 2.0
	parent.add_child(mi)

	if kind == "count":
		var n := int(float(parts[1])) if parts.size() > 1 else 2
		n = maxi(n, 1)
		for i in n:
			var ang := TAU * float(i) / float(n)
			var notch := BoxMesh.new()
			notch.size = Vector3(0.16, 0.32, 0.16)
			var nm := MeshInstance3D.new()
			nm.mesh = notch
			nm.material_override = mat
			nm.position = Vector3(cos(ang) * 0.92, 0.0, sin(ang) * 0.92)
			mi.add_child(nm)

# ----------------------------------------------------------------- building

func _build_knots() -> void:
	for kd in _weave.get("knots", []):
		var name: String = kd.get("name", "")
		var verb: String = kd.get("verb", "pass")
		var trigger: String = kd.get("trigger", "any")
		var bias: float = float(kd.get("bias", 0.0))
		var pos: Vector3 = _positions.get(name, Vector3.ZERO)

		var holder := Node3D.new()
		holder.name = "Knot_" + name
		holder.position = pos
		add_child(holder)

		var mi := MeshInstance3D.new()
		mi.mesh = _verb_mesh(verb)
		var mat := StandardMaterial3D.new()
		mat.emission_enabled = true
		mat.emission = Color.from_hsv(_verb_hue(verb), 0.75, 1.0)
		mat.emission_energy_multiplier = 1.1
		mat.albedo_color = Color(0.05, 0.05, 0.08)
		mi.material_override = mat
		holder.add_child(mi)

		_add_collar(holder, trigger)

		var label := Label3D.new()
		label.text = name
		label.font_size = 96
		label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		label.position = KNOT_LABEL_OFFSET
		holder.add_child(label)

		if bias != 0.0:                 # bias: "a small tile ... engraved"
			var tile := Label3D.new()
			tile.text = "bias %.3g" % bias
			tile.font_size = 56
			tile.modulate = Color(1.0, 0.85, 0.4)
			tile.billboard = BaseMaterial3D.BILLBOARD_ENABLED
			tile.position = BIAS_LABEL_OFFSET
			holder.add_child(tile)

		_knot_mats[name] = mat
		_knot_base_energy[name] = 1.1


func _bow_path(a: Vector3, b: Vector3, delay: int) -> PackedVector3Array:
	# delay 1 -> straight line. delay > 1 -> a visible bow, bulging
	# perpendicular to the a->b axis. Self-threads (a == b) still get a
	# small visible loop instead of collapsing to a point.
	var segs := maxi(delay, 1) * 2
	var pts := PackedVector3Array()
	var d := b - a
	var length := d.length()
	var dir := d / length if length > 0.0001 else Vector3.FORWARD
	var up := Vector3.UP if absf(dir.dot(Vector3.UP)) < 0.99 else Vector3.RIGHT
	var perp := dir.cross(up).normalized()

	var bulge := 0.0
	if delay > 1:
		bulge = 0.4 * float(delay - 1) * maxf(length * 0.12, 0.5)
	if length < 0.0001:
		bulge = maxf(bulge, 0.6)         # self-loop: always visible

	for i in range(segs + 1):
		var t := float(i) / float(segs)
		var p := a.lerp(b, t)
		p += perp * (sin(t * PI) * bulge)
		pts.append(p)
	return pts


func _stretch_transform(a: Vector3, b: Vector3) -> Transform3D:
	var d := b - a
	var length := d.length()
	if length < 0.0001:
		return Transform3D(Basis.IDENTITY, a)
	var y := d / length
	var reference := Vector3.RIGHT if absf(y.dot(Vector3.UP)) > 0.99 else Vector3.UP
	var x := reference.cross(y).normalized()
	var z := y.cross(x).normalized()
	return Transform3D(Basis(x, y, z), (a + b) * 0.5)


func _add_cylinder_segment(parent: Node3D, a: Vector3, b: Vector3,
		radius: float, mat: Material) -> void:
	var length := a.distance_to(b)
	if length < 0.0001:
		return
	var mesh := CylinderMesh.new()
	mesh.top_radius = radius
	mesh.bottom_radius = radius
	mesh.height = length
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	mi.material_override = mat
	mi.transform = _stretch_transform(a, b)
	parent.add_child(mi)


func _build_threads() -> void:
	for td in _weave.get("threads", []):
		var src: String = td.get("from", "")
		var dst: String = td.get("to", "")
		var port: String = td.get("port", "in")
		var strands: Array = td.get("strands", [{}])
		if not _positions.has(src) or not _positions.has(dst):
			continue
		var a: Vector3 = _positions[src]
		var b: Vector3 = _positions[dst]

		var labeled_port := false
		for sd in strands:
			var weight: float = float(sd.get("weight", 1.0))
			var delay: int = int(sd.get("delay", 1))
			var path := _bow_path(a, b, delay)

			var mat := StandardMaterial3D.new()
			mat.emission_enabled = true
			mat.emission = (Color(1.0, 0.55, 0.2) if weight >= 0.0
					else Color(0.25, 0.6, 1.0))            # cool = negative
			mat.emission_energy_multiplier = 1.0 + minf(absf(weight), 3.0)
			var radius := clampf(0.03 + absf(weight) * 0.05,
					CORD_MIN_RADIUS, CORD_MAX_RADIUS)

			var cord := Node3D.new()
			cord.name = "Cord_%s_%s" % [src, dst]
			add_child(cord)
			for i in range(path.size() - 1):
				_add_cylinder_segment(cord, path[i], path[i + 1], radius, mat)

			if port != "in" and not labeled_port:
				var lbl := Label3D.new()
				lbl.text = port
				lbl.font_size = 64
				lbl.modulate = Color(0.8, 0.95, 1.0)
				lbl.billboard = BaseMaterial3D.BILLBOARD_ENABLED
				lbl.position = (a + b) * 0.5 + Vector3(0, 0.5, 0)
				add_child(lbl)
				labeled_port = true

# ------------------------------------------------------------- spark replay

func _build_sparks() -> void:
	for sp in _sparks:
		if not _positions.has(sp["from"]) or not _positions.has(sp["to"]):
			continue
		var mesh := SphereMesh.new()
		mesh.radius = SPARK_RADIUS
		mesh.height = SPARK_RADIUS * 2.0
		var mi := MeshInstance3D.new()
		mi.mesh = mesh
		var mat := StandardMaterial3D.new()
		mat.emission_enabled = true
		mat.emission = Color(1.0, 1.0, 0.7)
		mat.emission_energy_multiplier = 4.0
		mi.material_override = mat
		mi.visible = false
		add_child(mi)
		sp["path"] = _bow_path(_positions[sp["from"]], _positions[sp["to"]],
				maxi(int(sp["delay"]), 1))
		sp["node"] = mi


func _update_visuals() -> void:
	# Knot pulses: a stateless function of _beat_pos, so restepping
	# (including backwards) needs no separate rewind bookkeeping.
	var boost: Dictionary = {}
	for f in _fires:
		var name: String = f.get("knot", "")
		var beat: float = float(f.get("beat", 0))
		var dist := absf(_beat_pos - beat)
		if dist < PULSE_WINDOW:
			var amount := 1.0 - dist / PULSE_WINDOW
			boost[name] = maxf(boost.get(name, 0.0), amount)
	for name in _knot_mats.keys():
		var mat: StandardMaterial3D = _knot_mats[name]
		var base: float = _knot_base_energy.get(name, 1.0)
		mat.emission_energy_multiplier = base + boost.get(name, 0.0) * PULSE_BOOST

	# Sparks: also a pure function of _beat_pos and each spark's own
	# [depart, arrival] window — "arriving exactly when the loom says".
	for sp in _sparks:
		var node: MeshInstance3D = sp.get("node")
		if node == null:
			continue
		var depart: float = sp["depart"]
		var arrival: float = sp["arrival"]
		if _beat_pos < depart or _beat_pos > arrival:
			node.visible = false
			continue
		node.visible = true
		var span := maxf(arrival - depart, 0.0001)
		var t := clampf((_beat_pos - depart) / span, 0.0, 1.0)
		var path: PackedVector3Array = sp["path"]
		var idx := t * float(path.size() - 1)
		var i0 := int(floor(idx))
		var i1 := mini(i0 + 1, path.size() - 1)
		var frac := idx - float(i0)
		node.position = path[i0].lerp(path[i1], frac)
