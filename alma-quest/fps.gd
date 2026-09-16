# fps.gd — Alma Quest, first person. "Just take a camera." Iddo, 2026-08-23.
#
# The simplest real step from a walking-memorial to a GAME: a camera you
# control with your body. WASD to move, mouse to look, Space to jump, Esc to
# free the mouse. Same dusk boulevard, same moon, same Alma light at the end —
# but now you are IN it, first person, walking on your own legs.
extends Node3D

var player: CharacterBody3D
var cam: Camera3D
var speed := 4.6
var run_speed := 8.0
var gravity := 20.0
var jump_v := 6.5
var yaw := 0.0
var pitch := 0.0
var sens := 0.0025
var heb: FontFile
var t := 0.0
var alma_light: Node3D


func _ready() -> void:
	heb = _load_heb_font()
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	_build_env()
	_sky_and_moon()
	_stars()
	_build_world()
	_build_player()
	_build_hud()
	if OS.has_environment("ALMA_SHOT"):
		get_tree().create_timer(1.4).timeout.connect(_shot)


func _load_heb_font() -> FontFile:
	var ff := FontFile.new()
	for p in ["C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/tahoma.ttf"]:
		if FileAccess.file_exists(p):
			ff.load_dynamic_font(p)
			break
	return ff


func _build_env() -> void:
	var we := WorldEnvironment.new()
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.02, 0.03, 0.07)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.20, 0.26, 0.42)
	env.ambient_light_energy = 0.55
	env.fog_enabled = true
	env.fog_light_color = Color(0.12, 0.15, 0.26)
	env.fog_density = 0.006
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	env.glow_enabled = true
	we.environment = env
	add_child(we)


func _sky_and_moon() -> void:
	var moon_dir := DirectionalLight3D.new()
	moon_dir.rotation_degrees = Vector3(-42, -28, 0)
	moon_dir.light_color = Color(0.75, 0.82, 1.0)
	moon_dir.light_energy = 0.6
	add_child(moon_dir)
	var fill := DirectionalLight3D.new()
	fill.rotation_degrees = Vector3(-18, 150, 0)
	fill.light_color = Color(0.9, 0.7, 0.5)
	fill.light_energy = 0.16
	add_child(fill)
	var moon_pos := Vector3(26, 21, -88)
	var moon := MeshInstance3D.new()
	var ms := SphereMesh.new()
	ms.radius = 6.0
	ms.height = 12.0
	moon.mesh = ms
	var mm := StandardMaterial3D.new()
	mm.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mm.albedo_color = Color(1.0, 0.97, 0.88)
	mm.emission_enabled = true
	mm.emission = Color(1.0, 0.96, 0.85)
	mm.emission_energy_multiplier = 3.0
	moon.material_override = mm
	moon.position = moon_pos
	add_child(moon)
	var occ := MeshInstance3D.new()
	var os := SphereMesh.new()
	os.radius = 6.0
	os.height = 12.0
	occ.mesh = os
	var om := StandardMaterial3D.new()
	om.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	om.albedo_color = Color(0.02, 0.03, 0.07)
	occ.material_override = om
	occ.position = moon_pos + Vector3(-10.5, 0.2, 1.5)
	add_child(occ)


func _stars() -> void:
	var sm := SphereMesh.new()
	sm.radius = 0.16
	sm.height = 0.32
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.albedo_color = Color(1, 1, 1)
	mat.emission_enabled = true
	mat.emission = Color(0.9, 0.95, 1.0)
	mat.emission_energy_multiplier = 1.4
	for i in range(160):
		var s := MeshInstance3D.new()
		s.mesh = sm
		var az := randf_range(-PI, PI)
		var el := randf_range(0.12, 1.25)
		var r := 130.0
		var y := sin(el) * r
		var horiz := cos(el) * r
		s.position = Vector3(sin(az) * horiz, max(12.0, y), cos(az) * horiz - 25.0)
		var sc := randf_range(0.4, 1.6)
		s.scale = Vector3(sc, sc, sc)
		s.material_override = mat
		add_child(s)


func _build_world() -> void:
	# boulevard floor WITH collision (you walk on it)
	var floor_body := StaticBody3D.new()
	var floor_mesh := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(26, 220)
	floor_mesh.mesh = pm
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.13, 0.15, 0.14)
	mat.roughness = 0.9
	floor_mesh.material_override = mat
	floor_body.add_child(floor_mesh)
	var col := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(26, 0.4, 220)
	col.shape = box
	col.position.y = -0.2
	floor_body.add_child(col)
	add_child(floor_body)

	# trees down both sides (with trunk collision so they feel solid)
	for i in range(34):
		var z := 8.0 - i * 3.0
		for sx in [-7.0, 7.0]:
			_tree(Vector3(sx, 0, z))

	# a lamp-lit orb per few metres, marching to Alma
	for i in range(20):
		var z := 2.0 - i * 4.0
		_orb(i, Vector3(0, 1.2, z))

	# Alma's memorial chess board on the corner
	_chessboard(Vector3(6.5, 0.02, 5.0))

	# Alma's light at the end of the walk
	_alma_light(Vector3(0, 1.5, 2.0 - 20 * 4.0 - 6.0))


func _tree(pos: Vector3) -> void:
	var body := StaticBody3D.new()
	var trunk := MeshInstance3D.new()
	var cyl := CylinderMesh.new()
	cyl.top_radius = 0.12
	cyl.bottom_radius = 0.16
	cyl.height = 2.2
	trunk.mesh = cyl
	trunk.position = Vector3(0, 1.1, 0)
	var tm := StandardMaterial3D.new()
	tm.albedo_color = Color(0.22, 0.16, 0.11)
	trunk.material_override = tm
	body.add_child(trunk)
	var tcol := CollisionShape3D.new()
	var tcap := CapsuleShape3D.new()
	tcap.radius = 0.25
	tcap.height = 2.2
	tcol.shape = tcap
	tcol.position = Vector3(0, 1.1, 0)
	body.add_child(tcol)
	var crown := MeshInstance3D.new()
	var sph := SphereMesh.new()
	sph.radius = 1.1
	sph.height = 2.0
	crown.mesh = sph
	crown.position = Vector3(0, 2.6, 0)
	var cm := StandardMaterial3D.new()
	cm.albedo_color = Color(0.10, 0.24, 0.12)
	crown.material_override = cm
	body.add_child(crown)
	body.position = pos
	add_child(body)


func _orb(idx: int, pos: Vector3) -> void:
	var mesh := MeshInstance3D.new()
	var sph := SphereMesh.new()
	sph.radius = 0.4
	sph.height = 0.8
	mesh.mesh = sph
	var m := StandardMaterial3D.new()
	var hue := float(idx) / 20.0
	m.albedo_color = Color.from_hsv(hue, 0.5, 1.0)
	m.emission_enabled = true
	m.emission = Color.from_hsv(hue, 0.6, 1.0)
	m.emission_energy_multiplier = 2.2
	mesh.material_override = m
	mesh.position = pos
	add_child(mesh)


func _chessboard(pos: Vector3) -> void:
	var lightm := StandardMaterial3D.new()
	lightm.albedo_color = Color(0.82, 0.80, 0.74)
	var darkm := StandardMaterial3D.new()
	darkm.albedo_color = Color(0.18, 0.18, 0.20)
	var sq := 0.55
	for r in range(8):
		for c in range(8):
			var tile := MeshInstance3D.new()
			var bm := BoxMesh.new()
			bm.size = Vector3(sq, 0.06, sq)
			tile.mesh = bm
			tile.material_override = lightm if (r + c) % 2 == 0 else darkm
			tile.position = pos + Vector3((c - 3.5) * sq, 0, (r - 3.5) * sq)
			add_child(tile)
	var l3 := Label3D.new()
	l3.text = "♟  לזכר עלמה ז\"ל"
	l3.font = heb
	l3.font_size = 40
	l3.pixel_size = 0.006
	l3.modulate = Color(0.95, 0.9, 0.75)
	l3.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	l3.position = pos + Vector3(0, 1.2, 0)
	add_child(l3)


func _alma_light(pos: Vector3) -> void:
	var area := Node3D.new()
	area.position = pos
	var mesh := MeshInstance3D.new()
	var sph := SphereMesh.new()
	sph.radius = 0.85
	sph.height = 1.7
	mesh.mesh = sph
	var m := StandardMaterial3D.new()
	m.albedo_color = Color(1.0, 0.95, 0.8)
	m.emission_enabled = true
	m.emission = Color(1.0, 0.92, 0.72)
	m.emission_energy_multiplier = 3.4
	mesh.material_override = m
	area.add_child(mesh)
	var lamp := OmniLight3D.new()
	lamp.light_color = Color(1.0, 0.9, 0.7)
	lamp.light_energy = 2.6
	lamp.omni_range = 16.0
	area.add_child(lamp)
	var l3 := Label3D.new()
	l3.text = "שְׂפַת עַלְמָה"
	l3.font = heb
	l3.font_size = 64
	l3.pixel_size = 0.009
	l3.modulate = Color(1.0, 0.95, 0.8)
	l3.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	l3.position = Vector3(0, 1.7, 0)
	area.add_child(l3)
	add_child(area)
	alma_light = area


func _build_player() -> void:
	player = CharacterBody3D.new()
	var pcol := CollisionShape3D.new()
	var caps := CapsuleShape3D.new()
	caps.height = 1.8
	caps.radius = 0.35
	pcol.shape = caps
	pcol.position.y = 0.9
	player.add_child(pcol)
	cam = Camera3D.new()
	cam.position = Vector3(0, 1.65, 0)   # eye height
	cam.current = true
	player.add_child(cam)
	player.position = Vector3(0, 1.0, 8)
	add_child(player)


func _build_hud() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)
	var hint := Label.new()
	hint.add_theme_font_override("font", heb)
	hint.add_theme_font_size_override("font_size", 18)
	hint.add_theme_color_override("font_color", Color(1, 0.9, 0.6))
	hint.text_direction = Control.TEXT_DIRECTION_RTL
	hint.text = "WASD — ללכת · עכבר — להסתכל · Shift — לרוץ · רווח — לקפוץ · Esc — לשחרר עכבר · לך עד האור"
	hint.position = Vector2(20, 16)
	layer.add_child(hint)
	# a small crosshair dot
	var dot := ColorRect.new()
	dot.color = Color(1, 1, 1, 0.6)
	dot.size = Vector2(4, 4)
	dot.anchor_left = 0.5
	dot.anchor_top = 0.5
	dot.offset_left = -2
	dot.offset_top = -2
	layer.add_child(dot)


func _shot() -> void:
	await RenderingServer.frame_post_draw
	var img := get_viewport().get_texture().get_image()
	if img:
		img.save_png(OS.get_environment("ALMA_SHOT"))


func _input(event: InputEvent) -> void:
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		yaw -= event.relative.x * sens
		pitch = clamp(pitch - event.relative.y * sens, -1.4, 1.4)
	elif event is InputEventKey and event.pressed:
		if event.keycode == KEY_ESCAPE:
			Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
		elif event.keycode == KEY_F:
			Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	elif event is InputEventMouseButton and event.pressed:
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


func _physics_process(delta: float) -> void:
	t += delta
	if alma_light:
		var s := 1.0 + sin(t * 1.2) * 0.06
		alma_light.scale = Vector3(s, s, s)
	if player == null:
		return
	player.rotation.y = yaw
	cam.rotation.x = pitch
	var input_dir := Vector3.ZERO
	if Input.is_key_pressed(KEY_W):
		input_dir.z -= 1.0
	if Input.is_key_pressed(KEY_S):
		input_dir.z += 1.0
	if Input.is_key_pressed(KEY_A):
		input_dir.x -= 1.0
	if Input.is_key_pressed(KEY_D):
		input_dir.x += 1.0
	var dir := (player.transform.basis * input_dir).normalized()
	var sp := run_speed if Input.is_key_pressed(KEY_SHIFT) else speed
	var v := player.velocity
	v.x = dir.x * sp
	v.z = dir.z * sp
	if player.is_on_floor():
		if Input.is_key_pressed(KEY_SPACE):
			v.y = jump_v
	else:
		v.y -= gravity * delta
	player.velocity = v
	player.move_and_slide()
