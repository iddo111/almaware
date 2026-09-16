# tel_aviv_1933.gd -- THE CITY. Procedural 1933 Tel Aviv, built at load, walkable in VR.
#
# BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.
#
# Iddo, 2026-08-29: the game is 1930s Tel Aviv -- Irgun, Lehi, Palmach, the Haganah,
# the Arlosoroff killing. And: "Real-time rendering in 3D in VR."
#
# So this is a GENERATOR, not a diorama. The city is described as data -- a street
# plan and a facade grammar -- and built as real geometry every run. That is what
# makes it an engine: change the plan, get a different city; change the grammar, get
# a different decade. Nothing here is hand-placed.
#
# WHY GEOMETRY AND NOT DIFFUSION: a diffusion model cannot render a stereo pair at
# 90 Hz on any hardware in this building, and a VR frame that arrives late is not a
# picture, it is nausea. So the division of labour is fixed and honest:
#     this script   -> structure, in real time, in VR
#     Flux on eran4 -> the surfaces, baked ahead of time into textures
# The beauty comes from the second; the presence comes from the first.
#
# THE PERIOD, held to honestly:
#   1933. The White City is going up -- Bauhaus emigres are three years off the boat,
#   the International Style built cheap and fast in Mediterranean sun: flat roofs,
#   horizontal ribbon windows, deep balconies for shade, blocks lifted on pilotis so
#   the sea breeze passes underneath. Not Berlin's white boxes: Berlin's ideas cooked
#   in Levantine light and sand.
#   Rothschild Boulevard already has its planted median. Herzl Street runs down to the
#   Herzliya Gymnasium. Allenby carries the traffic and the cafes.
#   On 16 June 1933 Chaim Arlosoroff was shot on the beach north of the city. That
#   murder was never solved -- and it stays UNSOLVED here. This world may let a player
#   walk that sand; it must never hand them a culprit that history never proved.
extends Node3D

const BLOCK := 44.0          # metres, city block including street
const STREET := 14.0         # carriageway + walks
const STOREY := 3.2          # 1930s floor-to-floor, low by modern habit

# The plan. x = east/west (the sea is WEST, -x), z = north/south.
const STREETS := [
	{"name": "HaYarkon",       "axis": "ns", "at": -3, "w": 1.0, "boulevard": false},
	{"name": "Allenby",        "axis": "ns", "at": -1, "w": 1.5, "boulevard": false},
	{"name": "Rothschild",     "axis": "ns", "at":  1, "w": 2.2, "boulevard": true},
	{"name": "Herzl",          "axis": "ns", "at":  3, "w": 1.2, "boulevard": false},
	{"name": "Montefiore",     "axis": "ew", "at": -2, "w": 1.0, "boulevard": false},
	{"name": "Nachalat Binyamin","axis": "ew","at":  0, "w": 1.3, "boulevard": false},
	{"name": "Balfour",        "axis": "ew", "at":  2, "w": 1.0, "boulevard": false},
]

@export var blocks_x := 7
@export var blocks_z := 7
@export var seed_value := 1933

var _rng := RandomNumberGenerator.new()
var _mat_render: StandardMaterial3D     # the cream stucco
var _mat_shade: StandardMaterial3D      # balcony undersides, shadowed returns
var _mat_glass: StandardMaterial3D
var _mat_road: StandardMaterial3D
var _mat_walk: StandardMaterial3D
var _mat_sand: StandardMaterial3D
var _mat_sea: StandardMaterial3D
var _mat_tree: StandardMaterial3D
var _mat_leaf: StandardMaterial3D
var _mat_bench: StandardMaterial3D
var _mat_iron: StandardMaterial3D
var _mat_hedge: StandardMaterial3D


func _ready() -> void:
	_rng.seed = seed_value
	_build_materials()
	_build_light()
	_build_ground()
	_build_sea()
	_build_streets()
	_build_blocks()
	_build_boulevard_trees()
	print("[tel-aviv-1933] city built: %d x %d blocks, seed %d"
		% [blocks_x, blocks_z, seed_value])


# ----------------------------------------------------------------- materials
# Cream, not white. The White City was never white -- it was sand-coloured render
# that the sun bleached and the hamsin dirtied. Pure white reads as modern and wrong.
func _build_materials() -> void:
	_mat_render = StandardMaterial3D.new()
	_mat_render.albedo_color = Color(0.906, 0.878, 0.816)
	_mat_render.roughness = 0.92

	_mat_shade = StandardMaterial3D.new()
	_mat_shade.albedo_color = Color(0.741, 0.706, 0.643)
	_mat_shade.roughness = 0.95

	_mat_glass = StandardMaterial3D.new()
	# Dark and slightly warm: 1930s glass over an unlit room, not a mirror.
	_mat_glass.albedo_color = Color(0.106, 0.118, 0.129)
	_mat_glass.metallic = 0.15
	_mat_glass.roughness = 0.35

	_mat_road = StandardMaterial3D.new()
	_mat_road.albedo_color = Color(0.243, 0.235, 0.227)
	_mat_road.roughness = 0.98

	_mat_walk = StandardMaterial3D.new()
	_mat_walk.albedo_color = Color(0.647, 0.624, 0.580)
	_mat_walk.roughness = 0.96

	_mat_sand = StandardMaterial3D.new()
	_mat_sand.albedo_color = Color(0.847, 0.784, 0.639)
	_mat_sand.roughness = 1.0

	_mat_sea = StandardMaterial3D.new()
	_mat_sea.albedo_color = Color(0.118, 0.325, 0.404)
	_mat_sea.roughness = 0.18
	_mat_sea.metallic = 0.30

	_mat_tree = StandardMaterial3D.new()
	_mat_tree.albedo_color = Color(0.302, 0.243, 0.180)
	_mat_tree.roughness = 1.0

	_mat_bench = StandardMaterial3D.new()
	_mat_bench.albedo_color = Color(0.318, 0.184, 0.129)   # dark stained slats
	_mat_bench.roughness = 0.9

	_mat_iron = StandardMaterial3D.new()
	_mat_iron.albedo_color = Color(0.09, 0.09, 0.10)       # black iron ends
	_mat_iron.roughness = 0.7

	_mat_hedge = StandardMaterial3D.new()
	_mat_hedge.albedo_color = Color(0.204, 0.310, 0.161)   # clipped box, darker than canopy
	_mat_hedge.roughness = 1.0

	_mat_leaf = StandardMaterial3D.new()
	# Ficus: the boulevard tree. Dusty green, never emerald.
	_mat_leaf.albedo_color = Color(0.286, 0.376, 0.239)
	_mat_leaf.roughness = 1.0


# Mediterranean light: high, hard, slightly yellow. The shadows ARE the architecture
# here -- these buildings were designed around them.
func _build_light() -> void:
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-62, 38, 0)
	sun.light_color = Color(1.0, 0.957, 0.878)
	sun.light_energy = 1.35
	sun.shadow_enabled = true
	add_child(sun)

	var env := WorldEnvironment.new()
	var e := Environment.new()
	e.background_mode = Environment.BG_SKY
	var sky := Sky.new()
	var pm := ProceduralSkyMaterial.new()
	pm.sky_top_color = Color(0.325, 0.529, 0.749)
	pm.sky_horizon_color = Color(0.827, 0.831, 0.788)
	pm.ground_bottom_color = Color(0.706, 0.667, 0.588)
	pm.ground_horizon_color = Color(0.827, 0.831, 0.788)
	sky.sky_material = pm
	e.sky = sky
	e.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	e.ambient_light_energy = 0.55
	e.fog_enabled = true
	e.fog_light_color = Color(0.878, 0.851, 0.780)   # sea haze plus dust
	e.fog_density = 0.0022
	env.environment = e
	add_child(env)


func _add_box(parent: Node3D, size: Vector3, pos: Vector3, mat: Material) -> MeshInstance3D:
	var m := MeshInstance3D.new()
	var b := BoxMesh.new()
	b.size = size
	m.mesh = b
	m.position = pos
	m.material_override = mat
	parent.add_child(m)
	return m


func _add_body(parent: Node3D, size: Vector3, pos: Vector3, mat: Material) -> void:
	# Static geometry the player collides with. Without this the city is a painting.
	var body := StaticBody3D.new()
	body.position = pos
	var col := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = size
	col.shape = shape
	body.add_child(col)
	var m := MeshInstance3D.new()
	var b := BoxMesh.new()
	b.size = size
	m.mesh = b
	m.material_override = mat
	body.add_child(m)
	parent.add_child(body)


func _build_ground() -> void:
	var w := blocks_x * BLOCK + 400.0
	var d := blocks_z * BLOCK + 400.0
	_add_body(self, Vector3(w, 1.0, d), Vector3(0, -0.5, 0), _mat_walk)


func _build_sea() -> void:
	# West of the city: the beach, then the Mediterranean out to the horizon.
	var west := -(blocks_x * BLOCK) / 2.0 - 60.0
	var d := blocks_z * BLOCK + 400.0
	_add_box(self, Vector3(120.0, 0.6, d), Vector3(west - 60.0, -0.2, 0), _mat_sand)
	_add_box(self, Vector3(1200.0, 0.4, d), Vector3(west - 720.0, -0.6, 0), _mat_sea)


func _build_streets() -> void:
	var half_x := blocks_x * BLOCK / 2.0
	var half_z := blocks_z * BLOCK / 2.0
	for s in STREETS:
		var width: float = STREET * float(s["w"])
		if s["axis"] == "ns":
			var x := float(s["at"]) * BLOCK
			_add_box(self, Vector3(width, 0.12, half_z * 2.0),
					Vector3(x, 0.06, 0), _mat_road)
			if s["boulevard"]:
				# Rothschild's planted median -- the reason a boulevard reads as a
				# boulevard and not merely as a wide road.
				_add_box(self, Vector3(width * 0.42, 0.30, half_z * 2.0),
						Vector3(x, 0.15, 0), _mat_walk)
		else:
			var z := float(s["at"]) * BLOCK
			_add_box(self, Vector3(half_x * 2.0, 0.12, width),
					Vector3(0, 0.06, z), _mat_road)


func _street_at(axis: String, idx: int) -> bool:
	for s in STREETS:
		if s["axis"] == axis and int(s["at"]) == idx:
			return true
	return false


func _build_blocks() -> void:
	var ox := -(blocks_x - 1) * BLOCK / 2.0
	var oz := -(blocks_z - 1) * BLOCK / 2.0
	for ix in range(blocks_x):
		for iz in range(blocks_z):
			var gx := ix - blocks_x / 2
			var gz := iz - blocks_z / 2
			if _street_at("ns", gx) or _street_at("ew", gz):
				continue
			_build_bauhaus(ox + ix * BLOCK, oz + iz * BLOCK)


# One International-Style apartment block, 1933 Tel Aviv vintage.
#
# The five things that make it read as Bauhaus-on-the-sand and not a white box:
#   pilotis        -- the ground floor is columns, so the sea breeze crosses the plot
#   ribbon windows -- horizontal bands, not punched holes
#   deep balconies -- here shade is structure, not decoration
#   flat roof      -- and a used one: laundry, and sleeping out in summer
#   thermometer    -- the vertical glazed stair tower, the one upright gesture
func _build_bauhaus(cx: float, cz: float) -> void:
	var storeys := _rng.randi_range(3, 4)
	var w := _rng.randf_range(20.0, 27.0)
	var d := _rng.randf_range(14.0, 19.0)
	var h := storeys * STOREY
	var piloti_h := 2.9

	var blk := Node3D.new()
	blk.position = Vector3(cx, 0, cz)
	add_child(blk)

	# --- pilotis: the block stands on columns
	var cols := 4
	for i in range(cols):
		for j in range(2):
			var px := -w / 2.0 + w * float(i) / float(cols - 1)
			var pz := -d / 2.0 + d * float(j)
			_add_box(blk, Vector3(0.55, piloti_h, 0.55),
					Vector3(px * 0.86, piloti_h / 2.0, pz * 0.86), _mat_shade)

	# --- the mass, lifted clear of the ground
	_add_body(blk, Vector3(w, h, d), Vector3(0, piloti_h + h / 2.0, 0), _mat_render)

	# --- ribbon windows: one continuous horizontal band per storey, both long faces
	for s in range(storeys):
		var y := piloti_h + s * STOREY + STOREY * 0.62
		for face in [-1.0, 1.0]:
			_add_box(blk, Vector3(w * 0.82, STOREY * 0.42, 0.16),
					Vector3(0, y, face * (d / 2.0 + 0.02)), _mat_glass)

	# --- balconies: deep, shading the window band beneath them
	for s in range(storeys):
		var y := piloti_h + s * STOREY + STOREY * 0.06
		var bw := w * (0.50 if _rng.randf() < 0.5 else 0.66)
		_add_box(blk, Vector3(bw, 0.22, 2.3),
				Vector3(0, y, -(d / 2.0 + 1.15)), _mat_render)
		_add_box(blk, Vector3(bw, 0.95, 0.14),
				Vector3(0, y + 0.55, -(d / 2.0 + 2.25)), _mat_shade)

	# --- the stair tower (the "thermometer"): the vertical the facade needs
	var tx := w / 2.0 * _rng.randf_range(-0.30, 0.30)
	_add_box(blk, Vector3(3.4, h + 0.9, 1.0),
			Vector3(tx, piloti_h + (h + 0.9) / 2.0, d / 2.0 + 0.35), _mat_render)
	for s in range(storeys):
		_add_box(blk, Vector3(2.2, STOREY * 0.60, 0.14),
				Vector3(tx, piloti_h + s * STOREY + STOREY * 0.5, d / 2.0 + 0.88),
				_mat_glass)

	# --- roof: a parapet, plus the tanks that make a roof inhabited
	_add_box(blk, Vector3(w, 0.75, d), Vector3(0, piloti_h + h + 0.37, 0), _mat_render)
	for i in range(_rng.randi_range(1, 3)):
		_add_box(blk, Vector3(1.1, 1.1, 1.1),
				Vector3(_rng.randf_range(-w * 0.3, w * 0.3), piloti_h + h + 1.2,
						_rng.randf_range(-d * 0.3, d * 0.3)), _mat_shade)


# Ficus down the Rothschild median. The boulevard is the one place in this city
# where a person in 1933 stood in shade for free.
func _build_boulevard_trees() -> void:
	for s in STREETS:
		if not s["boulevard"]:
			continue
		var x := float(s["at"]) * BLOCK
		var half_z := blocks_z * BLOCK / 2.0
		var z := -half_z
		while z < half_z:
			var t := Node3D.new()
			t.position = Vector3(x + _rng.randf_range(-1.2, 1.2), 0.3, z)
			add_child(t)
			_boulevard_tree(t)
			_median_furniture(t, x, z)
			z += _rng.randf_range(9.0, 12.0)


# 2026-08-30. Iddo walked out to a boulevard and photographed it -- his own pictures,
# in reference/iddo/. The old tree here was ONE upright post and ONE flat green slab,
# and next to his photographs it was obviously wrong. What the real trees do:
#   * the trunk is THICK and SHORT and it LEANS -- one in his set lies almost flat
#   * heavy limbs leave the trunk low, around 1.5-2.5 m, and travel sideways far
#   * the crown is not a slab, it is several overlapping clumps at different heights
# The third point is the one that matters, because a slab casts a slab of shade and
# what the place actually looks like is HARD DAPPLED LIGHT. The shade is the subject.
func _boulevard_tree(t: Node3D) -> void:
	var lean := Vector3(_rng.randf_range(-0.30, 0.30), 0, _rng.randf_range(-0.30, 0.30))
	var girth := _rng.randf_range(0.62, 1.05)
	var trunk_h := _rng.randf_range(2.1, 3.2)
	var trunk := _add_box(t, Vector3(girth, trunk_h, girth),
			Vector3(0, trunk_h * 0.5, 0), _mat_tree)
	trunk.rotation = Vector3(lean.z, 0, -lean.x)

	var top := Vector3(lean.x * trunk_h, trunk_h, lean.z * trunk_h)
	var limbs := _rng.randi_range(2, 4)
	for i in limbs:
		var a := _rng.randf_range(0.0, TAU)
		var reach := _rng.randf_range(1.8, 3.6)
		var rise := _rng.randf_range(0.3, 1.4)
		var lw := girth * _rng.randf_range(0.42, 0.68)
		var mid := top + Vector3(cos(a) * reach * 0.5, rise * 0.5, sin(a) * reach * 0.5)
		var limb := _add_box(t, Vector3(reach, lw, lw), mid, _mat_tree)
		limb.rotation = Vector3(0, -a, atan2(rise, reach))
		# a clump of leaf at the end of each limb, not a lid over the whole tree
		var tip := top + Vector3(cos(a) * reach, rise, sin(a) * reach)
		var cr := _rng.randf_range(1.5, 2.6)
		_add_box(t, Vector3(cr, cr * _rng.randf_range(0.5, 0.8), cr),
				tip + Vector3(0, cr * 0.35, 0), _mat_leaf)
	# and two loose clumps riding above the middle, so the canopy is never one plane
	for i in 2:
		var cr2 := _rng.randf_range(1.9, 3.0)
		_add_box(t, Vector3(cr2, cr2 * 0.55, cr2),
				top + Vector3(_rng.randf_range(-1.4, 1.4),
						_rng.randf_range(0.9, 2.0),
						_rng.randf_range(-1.4, 1.4)), _mat_leaf)


# Benches on black iron, and the clipped hedge that lines the walk. Both are in every
# one of his photographs and neither existed here. They are what makes a median a place
# somebody sits, instead of a strip of planting between two carriageways.
func _median_furniture(t: Node3D, x: float, z: float) -> void:
	if _rng.randf() < 0.55:
		var side := 1.0 if _rng.randf() < 0.5 else -1.0
		var b := Node3D.new()
		b.position = Vector3(side * _rng.randf_range(2.2, 3.4), 0, _rng.randf_range(-2.0, 2.0))
		b.rotation.y = _rng.randf_range(-0.25, 0.25) + (0.0 if side > 0.0 else PI)
		t.add_child(b)
		_add_box(b, Vector3(1.75, 0.09, 0.46), Vector3(0, 0.44, 0), _mat_bench)
		_add_box(b, Vector3(1.75, 0.52, 0.08), Vector3(0, 0.70, -0.21), _mat_bench)
		_add_box(b, Vector3(0.07, 0.44, 0.44), Vector3(-0.82, 0.22, 0), _mat_iron)
		_add_box(b, Vector3(0.07, 0.44, 0.44), Vector3(0.82, 0.22, 0), _mat_iron)
	for sgn in [-1.0, 1.0]:
		_add_box(t, Vector3(0.85, 0.62, 6.0),
				Vector3(sgn * _rng.randf_range(4.6, 5.4), 0.31, 0), _mat_hedge)
