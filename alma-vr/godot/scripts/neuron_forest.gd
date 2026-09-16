# neuron_forest.gd — THE NETWORK, from the inside. M0.
#
# Generates a field of glowing neurons connected by axon lines, a sweeping
# attention beam the player must hide from (stillness = low activation), and
# one NPC portal (E to talk — the words come from Iddo's real DGX fleet).
extends Node3D

const NEURONS := 220
const FIELD := 90.0
const SWEEP_PERIOD := 14.0

var _neurons: Array[MeshInstance3D] = []
var _sweep: SpotLight3D
var _t := 0.0

func _ready() -> void:
	_grow_forest()
	_raise_sweep()
	_ambient()

func _grow_forest() -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = 20260818
	var sphere := SphereMesh.new()
	sphere.radius = 0.6
	sphere.height = 1.2
	for i in NEURONS:
		var n := MeshInstance3D.new()
		n.mesh = sphere
		var m := StandardMaterial3D.new()
		var hue := rng.randf_range(0.45, 0.62)          # cyan→violet
		m.emission_enabled = true
		m.emission = Color.from_hsv(hue, 0.8, 1.0)
		m.emission_energy_multiplier = rng.randf_range(0.6, 2.4)
		m.albedo_color = Color(0.05, 0.05, 0.1)
		n.material_override = m
		n.position = Vector3(rng.randf_range(-FIELD, FIELD),
							 rng.randf_range(1.0, 22.0),
							 rng.randf_range(-FIELD, FIELD))
		add_child(n)
		_neurons.append(n)
	# axons: each neuron links to its nearest 2 — light travels later (M1)
	var im := ImmediateMesh.new()
	var axons := MeshInstance3D.new()
	axons.mesh = im
	var am := StandardMaterial3D.new()
	am.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	am.albedo_color = Color(0.2, 0.6, 1.0, 0.25)
	am.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	axons.material_override = am
	im.surface_begin(Mesh.PRIMITIVE_LINES)
	for n in _neurons:
		for other in _nearest(n, 2):
			im.surface_add_vertex(n.position)
			im.surface_add_vertex(other.position)
	im.surface_end()
	add_child(axons)

func _nearest(node: MeshInstance3D, k: int) -> Array[MeshInstance3D]:
	var sorted := _neurons.filter(func(o): return o != node)
	sorted.sort_custom(func(a, b):
		return a.position.distance_to(node.position) < b.position.distance_to(node.position))
	return sorted.slice(0, k)

func _raise_sweep() -> void:
	# ATTENTION: the network looking for you. M0: one beam, slow orbit.
	_sweep = SpotLight3D.new()
	_sweep.light_color = Color(1.0, 0.25, 0.2)
	_sweep.light_energy = 14.0
	_sweep.spot_range = 140.0
	_sweep.spot_angle = 9.0
	_sweep.position = Vector3(0, 60, 0)
	add_child(_sweep)

func _ambient() -> void:
	var env := WorldEnvironment.new()
	var e := Environment.new()
	e.background_mode = Environment.BG_COLOR
	e.background_color = Color(0.008, 0.008, 0.03)
	e.glow_enabled = true
	e.glow_intensity = 1.1
	e.fog_enabled = true
	e.fog_light_color = Color(0.05, 0.08, 0.2)
	e.fog_density = 0.012
	env.environment = e
	add_child(env)

func _process(delta: float) -> void:
	_t += delta
	# neurons breathe
	for i in range(0, _neurons.size(), 3):
		var n := _neurons[i]
		var m := n.material_override as StandardMaterial3D
		m.emission_energy_multiplier = 1.2 + sin(_t * 1.7 + i) * 0.8
	# the sweep orbits, hunting
	var ang := _t * TAU / SWEEP_PERIOD
	_sweep.position = Vector3(cos(ang) * 45.0, 55.0, sin(ang) * 45.0)
	_sweep.look_at(Vector3(cos(ang + 0.9) * 30.0, 0, sin(ang + 0.9) * 30.0))
