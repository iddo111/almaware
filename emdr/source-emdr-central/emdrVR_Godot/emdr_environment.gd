## emdr_environment.gd
## Attach to WorldEnvironment node.
## Creates a calm, dark-blue therapeutic environment with a subtle
## starfield and gently glowing horizon — no distracting elements.
## Everything is procedural; no external asset files needed.

extends WorldEnvironment

@export var sky_top_color    : Color = Color(0.02, 0.04, 0.10)
@export var sky_horizon_color: Color = Color(0.06, 0.12, 0.25)
@export var ground_color     : Color = Color(0.02, 0.03, 0.07)
@export var star_count       : int   = 200
@export var enable_breathing : bool  = true  # very subtle ambient pulsing

var _stars     : Array[MeshInstance3D] = []
var _star_base : float                 = 0.0
var _breathe_t : float                 = 0.0

func _ready() -> void:
	_setup_environment()
	_build_ground()
	_build_stars()

# ── Environment settings ──────────────────────────────────────────────────────
func _setup_environment() -> void:
	var env = Environment.new()

	# Sky gradient
	var sky_mat              = ProceduralSkyMaterial.new()
	sky_mat.sky_top_color    = sky_top_color
	sky_mat.sky_horizon_color= sky_horizon_color
	sky_mat.ground_bottom_color = ground_color
	sky_mat.ground_horizon_color= sky_horizon_color.darkened(0.3)
	sky_mat.sky_energy_multiplier = 0.3

	var sky         = Sky.new()
	sky.sky_material = sky_mat
	env.background_mode  = Environment.BG_SKY
	env.sky              = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_energy = 0.2

	# Gentle glow for the orb and UI
	env.glow_enabled     = true
	env.glow_normalized  = true
	env.glow_intensity   = 0.8
	env.glow_bloom       = 0.2
	env.glow_blend_mode  = Environment.GLOW_BLEND_MODE_SOFTLIGHT

	# Subtle tone mapping — keeps dark areas dark (important for VR comfort)
	env.tonemap_mode     = Environment.TONE_MAPPER_FILMIC
	env.tonemap_exposure = 0.9

	self.environment     = env

# ── Ground plane ─────────────────────────────────────────────────────────────
func _build_ground() -> void:
	var ground     = MeshInstance3D.new()
	var plane      = PlaneMesh.new()
	plane.size     = Vector2(30, 30)
	ground.mesh    = plane
	ground.position= Vector3(0, 0, 0)

	var mat        = StandardMaterial3D.new()
	mat.albedo_color = Color(0.03, 0.04, 0.09)
	mat.roughness    = 0.95
	mat.metallic     = 0.1
	# Subtle grid gives spatial reference without distraction
	mat.uv1_scale   = Vector3(10, 10, 10)
	ground.material_override = mat
	add_child(ground)

# ── Procedural starfield ──────────────────────────────────────────────────────
func _build_stars() -> void:
	var rng = RandomNumberGenerator.new()
	rng.randomize()

	for i in range(star_count):
		var star     = MeshInstance3D.new()
		var sphere   = SphereMesh.new()
		var size     = rng.randf_range(0.005, 0.025)
		sphere.radius = size; sphere.height = size * 2
		sphere.radial_segments = 4; sphere.rings = 2
		star.mesh    = sphere

		# Random position on a hemisphere above the user
		var theta    = rng.randf() * TAU
		var phi      = rng.randf_range(0.1, PI * 0.45)
		var radius   = rng.randf_range(12.0, 20.0)
		star.position = Vector3(
			radius * sin(phi) * cos(theta),
			radius * cos(phi),
			radius * sin(phi) * sin(theta)
		)

		var star_mat = StandardMaterial3D.new()
		var bright   = rng.randf_range(0.4, 1.0)
		var col      = Color(bright * 0.8, bright * 0.88, bright)
		star_mat.albedo_color            = col
		star_mat.emission_enabled        = true
		star_mat.emission                = col
		star_mat.emission_energy_multiplier = rng.randf_range(0.5, 2.5)
		star_mat.flags_unshaded          = true
		star.material_override           = star_mat
		star.cast_shadow                 = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(star)
		_stars.append(star)

	_star_base = 0.0

# ── Breathing ambient (very subtle, ~0.1 Hz) ──────────────────────────────────
func _process(delta: float) -> void:
	if not enable_breathing: return
	_breathe_t += delta * 0.12   # ~12 seconds per cycle
	var breath = 0.5 + 0.5 * sin(_breathe_t * TAU)   # 0..1

	# Modulate ambient light very slightly — barely perceptible
	if environment:
		environment.ambient_light_energy = lerp(0.15, 0.28, breath)
