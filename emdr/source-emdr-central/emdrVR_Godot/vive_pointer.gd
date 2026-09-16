## vive_pointer.gd
## Attach to each XRController3D node.
## Casts a ray from the controller tip; on trigger pull, clicks
## the UI element under the ray (works with SubViewport panels).
##
## Also handles the "trigger pressed" shortcut:
##   Right trigger → Start / Resume session
##   Left trigger  → Pause session

extends XRController3D

@export var pointer_length  : float  = 5.0
@export var pointer_color   : Color  = Color(0.3, 0.8, 1.0, 0.7)
@export var is_right_hand   : bool   = true

@onready var main_node : Node3D = get_node("/root/Main")

var _ray_cast    : RayCast3D
var _laser_mesh  : MeshInstance3D
var _dot_mesh    : MeshInstance3D
var _laser_mat   : StandardMaterial3D
var _last_trigger: float = 0.0

func _ready() -> void:
	_build_laser()
	_build_raycast()

# ── Visual laser beam ─────────────────────────────────────────────────────────
func _build_laser() -> void:
	# Beam
	_laser_mesh  = MeshInstance3D.new()
	var cyl      = CylinderMesh.new()
	cyl.height   = pointer_length
	cyl.top_radius    = 0.002
	cyl.bottom_radius = 0.002
	cyl.radial_segments = 8
	_laser_mesh.mesh     = cyl
	_laser_mesh.position = Vector3(0, 0, -pointer_length / 2.0)
	_laser_mesh.rotation = Vector3(PI / 2.0, 0, 0)

	_laser_mat                = StandardMaterial3D.new()
	_laser_mat.albedo_color   = pointer_color
	_laser_mat.emission_enabled = true
	_laser_mat.emission       = pointer_color
	_laser_mat.emission_energy_multiplier = 2.0
	_laser_mat.transparency   = BaseMaterial3D.TRANSPARENCY_ALPHA
	_laser_mesh.material_override = _laser_mat
	add_child(_laser_mesh)

	# Dot at hit point
	_dot_mesh    = MeshInstance3D.new()
	var sphere   = SphereMesh.new()
	sphere.radius = 0.008; sphere.height = 0.016
	_dot_mesh.mesh = sphere
	var dot_mat  = StandardMaterial3D.new()
	dot_mat.albedo_color       = Color(1, 1, 1, 0.9)
	dot_mat.emission_enabled   = true
	dot_mat.emission           = Color(0.5, 0.9, 1.0)
	dot_mat.emission_energy_multiplier = 3.0
	_dot_mesh.material_override = dot_mat
	add_child(_dot_mesh)

func _build_raycast() -> void:
	_ray_cast              = RayCast3D.new()
	_ray_cast.target_position = Vector3(0, 0, -pointer_length)
	_ray_cast.collision_mask  = 0xFFFFFFFF
	_ray_cast.enabled         = true
	add_child(_ray_cast)

# ── Per-frame ─────────────────────────────────────────────────────────────────
func _process(delta: float) -> void:
	if not get_is_active(): return

	# Update laser visibility
	var trigger_val : float = get_float("trigger")

	# Trigger shortcut: skip UI, directly control session
	if trigger_val > 0.8 and _last_trigger <= 0.8:
		_on_trigger_pressed()
	_last_trigger = trigger_val

	# Raycast against UI panel
	_ray_cast.force_raycast_update()
	if _ray_cast.is_colliding():
		var hit_pt = _ray_cast.get_collision_point()
		_dot_mesh.global_position = hit_pt
		_dot_mesh.visible = true

		# Scale laser to actual hit distance
		var dist = global_position.distance_to(hit_pt)
		_laser_mesh.scale.y = dist / pointer_length
		_laser_mesh.position.z = -dist / 2.0

		# On trigger pull: inject pointer event into SubViewport
		if trigger_val > 0.8 and _last_trigger <= 0.8:
			_inject_viewport_click(hit_pt)
	else:
		_dot_mesh.visible = false
		_laser_mesh.scale.y = 1.0
		_laser_mesh.position.z = -pointer_length / 2.0

# ── Trigger shortcut ──────────────────────────────────────────────────────────
func _on_trigger_pressed() -> void:
	if not main_node: return
	if is_right_hand:
		# Right trigger: start or resume
		match main_node.state:
			main_node.SessionState.IDLE:   main_node.start_session()
			main_node.SessionState.PAUSED: main_node.resume_session()
	else:
		# Left trigger: pause
		if main_node.state == main_node.SessionState.RUNNING:
			main_node.pause_session()

# ── Viewport click injection ──────────────────────────────────────────────────
func _inject_viewport_click(world_pos: Vector3) -> void:
	# Find the UIAnchor/PanelMesh and map world_pos → viewport UV → pixel pos
	var ui_anchor  = get_node_or_null("/root/Main/UIAnchor")
	if ui_anchor == null: return
	var panel_mesh = ui_anchor.get_node_or_null("PanelMesh")
	var vp         = ui_anchor.get_node_or_null("ControlPanel")
	if panel_mesh == null or vp == null: return

	# Transform hit point into panel local space
	var local_pos  = panel_mesh.to_local(world_pos)
	# Panel quad is 0.6×0.4 m centred at origin → map to 0..1 UV
	var uv_x = (local_pos.x + 0.3) / 0.6
	var uv_y = (local_pos.y + 0.2) / 0.4  # note: y flipped in Godot UV
	uv_y     = 1.0 - uv_y

	var px   = int(uv_x * vp.size.x)
	var py   = int(uv_y * vp.size.y)

	# Inject mouse button event
	var ev             = InputEventMouseButton.new()
	ev.button_index    = MOUSE_BUTTON_LEFT
	ev.pressed         = true
	ev.position        = Vector2(px, py)
	vp.push_input(ev)
	ev.pressed = false
	vp.push_input(ev)
