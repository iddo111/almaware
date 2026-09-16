## emdr_orb.gd
## The bilateral stimulation orb.
## Smoothly sweeps left ↔ right in front of the user.
## Emits signals when it reaches each extreme.
##
## Visual design:
##   - Glowing sphere with pulsing inner light
##   - Smooth eased motion (sinusoidal, not linear)
##   - Colour shifts slightly blue (left) ↔ warm white (right)
##   - Particle trail that stretches in the direction of travel
##   - Size gently pulses at each endpoint arrival

extends Node3D

# ── Signals ──────────────────────────────────────────────────────────────────
signal reached_left
signal reached_right
signal sweep_done   # emitted after each full left→right→left cycle

# ── Public parameters (set by emdr_main.gd) ──────────────────────────────────
@export var speed           : float = 1.0    # full sweeps (L→R) per second
@export var h_range         : float = 1.5    # half-width of sweep in metres
@export var target_distance : float = 2.0    # metres in front of XROrigin
@export var orb_height      : float = 1.7    # metres (eye level default)
@export var orb_radius      : float = 0.06   # sphere radius in metres

# ── Colours ───────────────────────────────────────────────────────────────────
@export var color_left   : Color = Color(0.30, 0.70, 1.00)  # cool blue
@export var color_right  : Color = Color(1.00, 0.88, 0.60)  # warm amber
@export var color_centre : Color = Color(0.80, 0.95, 1.00)  # bright white-blue

# ── Node references ───────────────────────────────────────────────────────────
@onready var orb_mesh  : MeshInstance3D    = $OrbMesh
@onready var orb_glow  : OmniLight3D       = $OrbGlow
@onready var orb_trail : GPUParticles3D    = $OrbTrail

# ── Internal state ────────────────────────────────────────────────────────────
enum OrbState { STOPPED, RUNNING, PAUSED }
var orb_state       : OrbState = OrbState.STOPPED
var phase           : float    = 0.0    # 0..1 maps to left..right..left
var last_side       : int      = -1     # -1 = left, +1 = right
var at_left         : bool     = false
var at_right        : bool     = false
var pulse_timer     : float    = 0.0
var pulse_duration  : float    = 0.25
var is_pulsing      : bool     = false

# Mesh/material created at runtime
var orb_mat : StandardMaterial3D

func _ready() -> void:
	_build_orb_mesh()
	_build_trail()
	_update_position(0.0)  # start at centre
	hide()

# ── Runtime mesh construction ────────────────────────────────────────────────
func _build_orb_mesh() -> void:
	var sphere            = SphereMesh.new()
	sphere.radius         = orb_radius
	sphere.height         = orb_radius * 2.0
	sphere.radial_segments = 32
	sphere.rings          = 16
	orb_mesh.mesh         = sphere

	orb_mat                         = StandardMaterial3D.new()
	orb_mat.emission_enabled        = true
	orb_mat.emission                = color_centre
	orb_mat.emission_energy_multiplier = 4.0
	orb_mat.albedo_color            = color_centre
	orb_mat.roughness               = 0.0
	orb_mat.metallic                = 0.3
	# Subtle rim to make it pop in dark VR environment
	orb_mat.rim_enabled             = true
	orb_mat.rim                     = 0.8
	orb_mat.rim_tint                = 0.5
	orb_mesh.material_override      = orb_mat

	orb_glow.light_color            = color_centre
	orb_glow.light_energy           = 3.0
	orb_glow.omni_range             = orb_radius * 20.0

## Build a simple particle trail using GPUParticles3D.
func _build_trail() -> void:
	orb_trail.emitting          = false
	orb_trail.amount            = 40
	orb_trail.lifetime          = 0.25
	orb_trail.local_coords      = false  # world-space trail
	orb_trail.fixed_fps         = 60

	var pm               = ParticleProcessMaterial.new()
	pm.direction         = Vector3(0, 0, 0)
	pm.spread            = 15.0
	pm.initial_velocity_min = 0.02
	pm.initial_velocity_max = 0.08
	pm.gravity           = Vector3(0, -0.1, 0)
	pm.scale_min         = 0.01
	pm.scale_max         = 0.03
	pm.color             = Color(0.6, 0.85, 1.0, 0.6)
	# Fade out over lifetime
	var alpha_curve         = Curve.new()
	alpha_curve.add_point(Vector2(0.0, 1.0))
	alpha_curve.add_point(Vector2(1.0, 0.0))
	var color_ramp          = GradientTexture1D.new()
	var grad                = Gradient.new()
	grad.add_point(0.0, Color(0.6, 0.85, 1.0, 0.8))
	grad.add_point(1.0, Color(0.2, 0.4,  0.8, 0.0))
	color_ramp.gradient     = grad
	pm.color_ramp           = color_ramp
	orb_trail.process_material = pm

	var quad            = QuadMesh.new()
	quad.size           = Vector2(0.025, 0.025)
	orb_trail.draw_pass_1 = quad

# ── Lifecycle ─────────────────────────────────────────────────────────────────
func start() -> void:
	orb_state = OrbState.RUNNING
	phase     = 0.0
	last_side = -1
	show()
	orb_trail.emitting = true

func pause() -> void:
	if orb_state == OrbState.RUNNING:
		orb_state = OrbState.PAUSED
		orb_trail.emitting = false

func resume() -> void:
	if orb_state == OrbState.PAUSED:
		orb_state = OrbState.RUNNING
		orb_trail.emitting = true

func stop() -> void:
	orb_state = OrbState.STOPPED
	orb_trail.emitting = false
	hide()

# ── Per-frame update ──────────────────────────────────────────────────────────
func _process(delta: float) -> void:
	if orb_state != OrbState.RUNNING: return

	# Advance phase: 0=left extreme, 0.5=right extreme, 1.0=back to left
	phase += delta * speed
	if phase >= 1.0:
		phase -= 1.0
		emit_signal("sweep_done")

	# Convert phase to a -1..+1 position using cosine for smooth ease-in/out
	# phase 0   → cos(0)   = 1  → x = -h_range  (left)
	# phase 0.5 → cos(π)   = -1 → x = +h_range  (right)
	var t : float = (1.0 - cos(phase * TAU)) / 2.0   # 0..1 smooth
	var x : float = lerp(-h_range, h_range, t)

	_update_position(x)
	_update_visuals(t)
	_check_endpoints(t)
	_update_pulse(delta)

## Position the orb in world-space in front of the XROrigin.
func _update_position(x: float) -> void:
	position = Vector3(x, orb_height, -target_distance)

## Update colour and glow based on horizontal position (t: 0=left, 1=right).
func _update_visuals(t: float) -> void:
	var col : Color
	if t < 0.5:
		col = color_left.lerp(color_centre, t * 2.0)
	else:
		col = color_centre.lerp(color_right, (t - 0.5) * 2.0)

	orb_mat.emission       = col
	orb_mat.albedo_color   = col
	orb_glow.light_color   = col

	# Glow pulses up at each endpoint
	var glow_base  : float = 3.0
	var glow_extra : float = 0.0
	if is_pulsing:
		var pulse_t = 1.0 - (pulse_timer / pulse_duration)
		glow_extra  = sin(pulse_t * PI) * 6.0
	orb_glow.light_energy  = glow_base + glow_extra

	# Subtle scale pulse at endpoints
	var scale_boost : float = 1.0
	if is_pulsing:
		var pulse_t    = 1.0 - (pulse_timer / pulse_duration)
		scale_boost    = 1.0 + sin(pulse_t * PI) * 0.35
	orb_mesh.scale = Vector3.ONE * scale_boost

## Detect when the orb reaches left/right extremes and fire signals.
func _check_endpoints(t: float) -> void:
	var threshold : float = 0.04   # ~4% from extreme counts as "arrived"

	if t < threshold and last_side != -1:
		last_side = -1
		_trigger_pulse()
		emit_signal("reached_left")

	elif t > (1.0 - threshold) and last_side != 1:
		last_side = 1
		_trigger_pulse()
		emit_signal("reached_right")

func _trigger_pulse() -> void:
	is_pulsing  = true
	pulse_timer = pulse_duration

func _update_pulse(delta: float) -> void:
	if is_pulsing:
		pulse_timer -= delta
		if pulse_timer <= 0.0:
			is_pulsing  = false
			pulse_timer = 0.0
