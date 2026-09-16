# player.gd — the runner. WASD + mouse, E talks to the nearest portal.
# Stillness = low activation (M1 will make the sweep blind to a still player).
extends CharacterBody3D

const SPEED := 9.0
const MOUSE_SENS := 0.0025

@onready var cam: Camera3D = $Camera3D
var npc_ui: Control = null

func _ready() -> void:
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion:
		rotate_y(-event.relative.x * MOUSE_SENS)
		cam.rotate_x(-event.relative.y * MOUSE_SENS)
		cam.rotation.x = clampf(cam.rotation.x, -1.4, 1.4)
	if event.is_action_pressed("talk"):
		var portal := get_tree().get_first_node_in_group("npc_portal")
		if portal and portal.global_position.distance_to(global_position) < 12.0:
			portal.converse()
	if event is InputEventKey and event.pressed and event.keycode == KEY_ESCAPE:
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE

func _physics_process(_delta: float) -> void:
	var dir := Vector3.ZERO
	dir += transform.basis.z * (Input.get_action_strength("move_back")
								- Input.get_action_strength("move_forward"))
	dir += transform.basis.x * (Input.get_action_strength("move_right")
								- Input.get_action_strength("move_left"))
	velocity.x = dir.normalized().x * SPEED if dir.length() > 0.1 else 0.0
	velocity.z = dir.normalized().z * SPEED if dir.length() > 0.1 else 0.0
	velocity.y = 0.0            # M0: the forest floor holds you
	move_and_slide()
