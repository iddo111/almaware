# boulevard_walker.gd -- how you move on the boulevard.
#
# BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY.
#
# player.gd runs at 9 m/s, which is right for the neuron forest and wrong here:
# "זה קווסט לא FPS". You WALK a boulevard -- 1.5 m/s, shift to hurry, a little bob
# so the head is attached to a body. player.gd is left exactly as it was.
extends CharacterBody3D

const WALK := 1.55
const HURRY := 3.6
const SENS := 0.0022
const EYE := 1.68

@onready var cam: Camera3D = $Camera3D
var _bob := 0.0


func _ready() -> void:
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


func _unhandled_input(e: InputEvent) -> void:
	if e is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		rotate_y(-e.relative.x * SENS)
		cam.rotate_x(-e.relative.y * SENS)
		cam.rotation.x = clampf(cam.rotation.x, -1.35, 1.25)
	if e is InputEventKey and e.pressed and e.keycode == KEY_ESCAPE:
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	if e is InputEventMouseButton and e.pressed:
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


func _physics_process(dt: float) -> void:
	var dir := Vector3.ZERO
	dir += transform.basis.z * (Input.get_action_strength("move_back")
			- Input.get_action_strength("move_forward"))
	dir += transform.basis.x * (Input.get_action_strength("move_right")
			- Input.get_action_strength("move_left"))
	var speed: float = HURRY if Input.is_key_pressed(KEY_SHIFT) else WALK
	if dir.length() > 0.1:
		dir = dir.normalized()
		velocity.x = dir.x * speed
		velocity.z = dir.z * speed
		_bob += dt * speed * 4.6
	else:
		velocity.x = 0.0
		velocity.z = 0.0
	velocity.y = -6.0
	move_and_slide()
	cam.position.y = EYE - 0.9 + sin(_bob) * 0.022
	cam.rotation.z = sin(_bob * 0.5) * 0.006
