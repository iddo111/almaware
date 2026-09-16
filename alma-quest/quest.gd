# quest.gd — Alma Quest. "הפרופסור" as a 3D point-and-click, LucasArts style.
#
# Iddo's idea, since age 15 — before there was even a computer. 2026-08-22.
# לזכרה של עלמה ז"ל.
#
# The boulevard (שדרות בן־גוריון, where Alma's memorial chess board stands) at
# night, 10 Elul. Twenty glowing orbs march down it — one per chapter of the
# book. Overhead: tonight's real moon, waxing gibbous, the one Iddo's father
# taught him to read. At the far end, past every chapter: one warm light —
# שפת עלמה, the language the professor built so no one would be alone.
#
# Click the ground to walk. Click a light to read. Walk all the way to the end.
extends Node3D

var player: CharacterBody3D
var target := Vector3.ZERO
var speed := 4.4
var label: Label
var title_label: Label
var chapters: Array = []
var orbs: Array = []
var alma_light: Node3D
var cam: Camera3D
var t := 0.0
var heb: FontFile

const ALMA_TITLE := "שְׂפַת עַלְמָה"
const ALMA_LINE := "פּוֹפְּקוֹצוּץ. הקפה עם הקינמון, האוהל מהשמיכות בשבת.\nהוא בנה שפה שלמה כדי שאף אחד לא יהיה לבד — וקרא לה בשמך.\nלזכרך, עלמה.  🤍"


func _ready() -> void:
	heb = _load_heb_font()
	_load_chapters()
	_build_env()
	_sky_and_moon()
	_stars()
	_build_world()
	_fireflies()
	_build_ui()
	_say("שְׂדֵרוֹת בֶּן־גּוּרְיוֹן — לילה, י׳ בֶּאֱלוּל",
		"עשרים אורות על השדרה, כל אחד — פרק. בקצה, אור אחד מחכה.\nלחץ על הרצפה כדי ללכת · על אור כדי לקרוא · לך עד הסוף.")
	if OS.has_environment("ALMA_SHOT"):
		get_tree().create_timer(1.4).timeout.connect(_shot)


func _load_heb_font() -> FontFile:
	var ff := FontFile.new()
	for p in ["C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf",
			"C:/Windows/Fonts/tahoma.ttf", "C:/Windows/Fonts/david.ttf"]:
		if FileAccess.file_exists(p):
			ff.load_dynamic_font(p)
			break
	return ff


func _load_chapters() -> void:
	var f := FileAccess.open("res://quest_data.json", FileAccess.READ)
	if f:
		var data = JSON.parse_string(f.get_as_text())
		if data is Array:
			chapters = data
	if chapters.is_empty():
		chapters = [{"title": "פרק א׳", "line": "הפרופסור קם בבוקר."}]


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
	env.glow_intensity = 0.9
	env.glow_bloom = 0.15
	we.environment = env
	add_child(we)


func _sky_and_moon() -> void:
	# cool moonlight down the boulevard
	var moon_dir := DirectionalLight3D.new()
	moon_dir.rotation_degrees = Vector3(-42, -28, 0)
	moon_dir.light_color = Color(0.75, 0.82, 1.0)
	moon_dir.light_energy = 0.6
	add_child(moon_dir)
	# faint warm fill so faces aren't pure blue
	var fill := DirectionalLight3D.new()
	fill.rotation_degrees = Vector3(-18, 150, 0)
	fill.light_color = Color(0.9, 0.7, 0.5)
	fill.light_energy = 0.16
	add_child(fill)

	# THE MOON — tonight, waxing gibbous, ~10 days old (10 Elul). Iddo's father's moon.
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
	# a sky-coloured sphere biting the left edge → gibbous, bright on the right (waxing)
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
	# chase camera, stored for follow
	cam = Camera3D.new()
	cam.position = Vector3(0, 8, 16)
	cam.rotation_degrees = Vector3(-24, 0, 0)
	cam.current = true
	add_child(cam)

	# the boulevard floor (the שדרה) — long enough for all 20 chapters + Alma
	var floor_body := StaticBody3D.new()
	var floor_mesh := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(24, 220)
	floor_mesh.mesh = pm
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.13, 0.15, 0.14)
	mat.roughness = 0.9
	floor_mesh.material_override = mat
	floor_body.add_child(floor_mesh)
	var col := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(24, 0.2, 220)
	col.shape = box
	col.position.y = -0.1
	floor_body.add_child(col)
	floor_body.set_meta("ground", true)
	add_child(floor_body)

	# ficus trees down each side, the boulevard feel
	for i in range(34):
		var z := 8.0 - i * 3.0
		for sx in [-7.0, 7.0]:
			_tree(Vector3(sx, 0, z))

	# Alma's memorial — the concrete chess board on the corner, and the bench
	# where the professor first sat with coffee, before the rainbow.
	_chessboard(Vector3(6.5, 0.02, 6.0))
	_bench(Vector3(6.6, 0.0, 9.5))

	# one glowing orb per chapter, marching down the boulevard
	for i in range(chapters.size()):
		var z := 2.0 - i * 4.0
		_orb(i, Vector3(0, 1.1, z), chapters[i])

	# THE LIGHT AT THE END — שפת עלמה. past every chapter.
	_alma_light(Vector3(0, 1.4, 2.0 - chapters.size() * 4.0 - 6.0))

	# the Professor
	player = CharacterBody3D.new()
	var body := MeshInstance3D.new()
	var caps := CapsuleMesh.new()
	caps.height = 1.8
	caps.radius = 0.35
	body.mesh = caps
	body.position.y = 0.9
	var pmat := StandardMaterial3D.new()
	pmat.albedo_color = Color(0.88, 0.80, 0.64)
	body.material_override = pmat
	player.add_child(body)
	var pcol := CollisionShape3D.new()
	var pshape := CapsuleShape3D.new()
	pshape.height = 1.8
	pshape.radius = 0.35
	pcol.shape = pshape
	pcol.position.y = 0.9
	player.add_child(pcol)
	player.position = Vector3(0, 0, 6)
	target = player.position
	add_child(player)


func _tree(pos: Vector3) -> void:
	var trunk := MeshInstance3D.new()
	var cyl := CylinderMesh.new()
	cyl.top_radius = 0.12
	cyl.bottom_radius = 0.16
	cyl.height = 2.2
	trunk.mesh = cyl
	trunk.position = pos + Vector3(0, 1.1, 0)
	var tm := StandardMaterial3D.new()
	tm.albedo_color = Color(0.22, 0.16, 0.11)
	trunk.material_override = tm
	add_child(trunk)
	var crown := MeshInstance3D.new()
	var sph := SphereMesh.new()
	sph.radius = 1.1
	sph.height = 2.0
	crown.mesh = sph
	crown.position = pos + Vector3(0, 2.6, 0)
	var cm := StandardMaterial3D.new()
	cm.albedo_color = Color(0.10, 0.24, 0.12)
	crown.material_override = cm
	add_child(crown)


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
	# a quiet plaque, floating just above the board
	var l3 := Label3D.new()
	l3.text = "♟  לזכר עלמה ז\"ל"
	l3.font = heb
	l3.font_size = 40
	l3.pixel_size = 0.006
	l3.modulate = Color(0.95, 0.9, 0.75)
	l3.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	l3.position = pos + Vector3(0, 1.1, 0)
	add_child(l3)


func _bench(pos: Vector3) -> void:
	var wood := StandardMaterial3D.new()
	wood.albedo_color = Color(0.30, 0.20, 0.12)
	var seat := MeshInstance3D.new()
	var sb := BoxMesh.new()
	sb.size = Vector3(2.0, 0.12, 0.6)
	seat.mesh = sb
	seat.material_override = wood
	seat.position = pos + Vector3(0, 0.55, 0)
	add_child(seat)
	var back := MeshInstance3D.new()
	var bb := BoxMesh.new()
	bb.size = Vector3(2.0, 0.6, 0.12)
	back.mesh = bb
	back.material_override = wood
	back.position = pos + Vector3(0, 0.95, -0.28)
	add_child(back)


func _orb(idx: int, pos: Vector3, data: Dictionary) -> void:
	var area := Area3D.new()
	area.position = pos
	var mesh := MeshInstance3D.new()
	var sph := SphereMesh.new()
	sph.radius = 0.5
	sph.height = 1.0
	mesh.mesh = sph
	var m := StandardMaterial3D.new()
	var hue: float = float(idx) / max(1.0, float(chapters.size()))
	m.albedo_color = Color.from_hsv(hue, 0.5, 1.0)
	m.emission_enabled = true
	m.emission = Color.from_hsv(hue, 0.6, 1.0)
	m.emission_energy_multiplier = 2.2
	mesh.material_override = m
	area.add_child(mesh)
	var col := CollisionShape3D.new()
	var sh := SphereShape3D.new()
	sh.radius = 0.65
	col.shape = sh
	area.add_child(col)
	area.set_meta("chapter", idx)
	add_child(area)
	orbs.append(area)
	# optional prop (from later enrichment): a small floating word beside the orb
	if data.has("prop") and str(data.get("prop", "")) != "":
		var l3 := Label3D.new()
		l3.text = str(data["prop"])
		l3.font = heb
		l3.font_size = 42
		l3.pixel_size = 0.006
		l3.modulate = Color(1.0, 0.9, 0.6)
		l3.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		l3.position = pos + Vector3(1.0, 0.2, 0)
		add_child(l3)


func _alma_light(pos: Vector3) -> void:
	var area := Area3D.new()
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
	var col := CollisionShape3D.new()
	var sh := SphereShape3D.new()
	sh.radius = 1.2
	col.shape = sh
	area.add_child(col)
	var lamp := OmniLight3D.new()
	lamp.light_color = Color(1.0, 0.9, 0.7)
	lamp.light_energy = 2.6
	lamp.omni_range = 16.0
	area.add_child(lamp)
	var l3 := Label3D.new()
	l3.text = ALMA_TITLE
	l3.font = heb
	l3.font_size = 64
	l3.pixel_size = 0.009
	l3.modulate = Color(1.0, 0.95, 0.8)
	l3.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	l3.position = Vector3(0, 1.7, 0)
	area.add_child(l3)
	area.set_meta("alma", true)
	add_child(area)
	alma_light = area


func _fireflies() -> void:
	var fx := CPUParticles3D.new()
	fx.amount = 70
	fx.lifetime = 7.0
	fx.position = Vector3(0, 2.0, -34.0)
	fx.emission_shape = CPUParticles3D.EMISSION_SHAPE_BOX
	fx.emission_box_extents = Vector3(9, 3.0, 46)
	fx.gravity = Vector3.ZERO
	fx.initial_velocity_min = 0.1
	fx.initial_velocity_max = 0.45
	fx.scale_amount_min = 0.5
	fx.scale_amount_max = 1.4
	var mesh := SphereMesh.new()
	mesh.radius = 0.05
	mesh.height = 0.1
	var mm := StandardMaterial3D.new()
	mm.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mm.albedo_color = Color(1.0, 0.85, 0.5)
	mm.emission_enabled = true
	mm.emission = Color(1.0, 0.82, 0.45)
	mm.emission_energy_multiplier = 2.5
	mesh.material = mm
	fx.mesh = mesh
	fx.emitting = true
	add_child(fx)


func _build_ui() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)
	var panel := ColorRect.new()
	panel.color = Color(0, 0, 0, 0.74)
	panel.anchor_left = 0.06
	panel.anchor_right = 0.94
	panel.anchor_top = 0.73
	panel.anchor_bottom = 0.97
	layer.add_child(panel)
	title_label = Label.new()
	title_label.add_theme_font_size_override("font_size", 27)
	title_label.add_theme_color_override("font_color", Color(1, 0.85, 0.35))
	title_label.add_theme_font_override("font", heb)
	title_label.text_direction = Control.TEXT_DIRECTION_RTL
	title_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	title_label.anchor_left = 0.03
	title_label.anchor_right = 0.97
	title_label.offset_top = 12
	panel.add_child(title_label)
	label = Label.new()
	label.add_theme_font_size_override("font_size", 20)
	label.add_theme_color_override("font_color", Color(0.95, 0.95, 0.95))
	label.add_theme_font_override("font", heb)
	label.text_direction = Control.TEXT_DIRECTION_RTL
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.anchor_left = 0.03
	label.anchor_right = 0.97
	label.anchor_bottom = 1.0
	label.offset_top = 52
	panel.add_child(label)


func _say(title: String, text: String) -> void:
	title_label.text = title
	label.text = text

func _shot() -> void:
	await RenderingServer.frame_post_draw
	var img := get_viewport().get_texture().get_image()
	if img:
		img.save_png(OS.get_environment("ALMA_SHOT"))


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		var camera := get_viewport().get_camera_3d()
		if camera == null:
			return
		var from := camera.project_ray_origin(event.position)
		var dir := camera.project_ray_normal(event.position)
		var space := get_world_3d().direct_space_state
		var q := PhysicsRayQueryParameters3D.create(from, from + dir * 400.0)
		q.collide_with_areas = true
		var hit := space.intersect_ray(q)
		if hit.is_empty():
			return
		var c = hit.collider
		if c.has_meta("chapter"):
			var idx: int = c.get_meta("chapter")
			var ch = chapters[idx]
			_say(ch.get("title", "פרק"), ch.get("line", ""))
			target = Vector3(c.global_position.x, 0, c.global_position.z + 2.2)
		elif c.has_meta("alma"):
			_say(ALMA_TITLE, ALMA_LINE)
			target = Vector3(c.global_position.x, 0, c.global_position.z + 2.6)
		elif c.has_meta("ground"):
			target = Vector3(hit.position.x, 0, hit.position.z)


func _physics_process(delta: float) -> void:
	t += delta
	# gently bob the orbs so the boulevard feels alive
	for i in range(orbs.size()):
		orbs[i].position.y = 1.1 + sin(t * 1.5 + i) * 0.12
	# Alma's light breathes
	if alma_light:
		var s := 1.0 + sin(t * 1.2) * 0.06
		alma_light.scale = Vector3(s, s, s)
	# chase camera follows the professor down the boulevard
	if cam and player:
		var desired := player.position + Vector3(0, 8.0, 11.0)
		cam.position = cam.position.lerp(desired, clamp(delta * 3.0, 0.0, 1.0))
		cam.look_at(player.position + Vector3(0, 1.2, -4.0), Vector3.UP)
	if player == null:
		return
	var to := target - player.position
	to.y = 0
	if to.length() > 0.15:
		player.velocity = to.normalized() * speed
		player.look_at(player.position + to, Vector3.UP)
	else:
		player.velocity = Vector3.ZERO
	player.move_and_slide()
