# tzelem_cube360.gd -- SIX CUBEMAP FACES from ONE camera origin, for a 360 VR plate.
#
# BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.
#
# This is tzelem_gbuffer.gd with ONE change of intent: instead of four small steps
# along a walk (whose point was exact optical flow between them), it exports the SIX
# faces of a cube from a SINGLE, IDENTICAL eye. Everything else -- the format, the
# neutral data lens, the sRGB undo, the warm-up, the per-frame flatness check -- is
# carried over unchanged and for the reasons stated there.
#
# WHY A CUBEMAP AND NOT "A WIDE LENS": a 360 image is not a photograph. Six 90-degree
# pinhole views tile the sphere exactly, and a pinhole camera is the only thing this
# engine (or TZELEM's numpy raycaster) has. The equirectangular plate is then a
# RESAMPLING of these six, done in numpy.
#
# THE THREE THINGS THAT MAKE OR BREAK THE SEAM, all handled here:
#   1. ONE ORIGIN. _eye is a single value used by all six poses. Two faces from two
#      different points do not tile a sphere; they tile nothing.
#   2. EXACTLY 90.0 DEGREES, HORIZONTALLY AND VERTICALLY. Godot's Camera3D.fov is the
#      VERTICAL fov under the default keep_aspect = KEEP_HEIGHT, and
#      fov_h = 2*atan(tan(fov_v/2)*aspect). They are equal ONLY when the render target
#      is SQUARE. So the SubViewport here is forced square (--res=N gives NxN) and
#      keep_aspect is set explicitly rather than trusted.
#   3. PER-FACE UP VECTORS. look_at(dir, Vector3.UP) is DEGENERATE for the +Y and -Y
#      faces -- forward parallel to up, and the basis collapses. Those two faces get
#      up = (0,0,1). The up vector actually used is WRITTEN INTO THE JSON (the parent
#      file hardcoded [0,1,0]); the numpy side rebuilds the identical basis from it,
#      and that is what makes a Godot face and a stage.Camera face the same rays.
#
# BASIS AGREEMENT, checked by reading both sources rather than by hoping:
#   Godot  Basis.looking_at:   v_z = -f ; v_x = up x v_z = f x up ; v_y = v_z x v_x
#   TZELEM stage.Camera.basis: r = f x up ; u = r x f = (f x up) x f
#   v_y = (-f) x (f x up) = -(f x (f x up)) = (f x up) x f = u.   Identical, both axes.
#   Projection then matches term for term: Godot ndc.x = (v.x/-v.z)/(tan(fovy/2)*aspect)
#   and TZELEM gx = (D.r)/(D.f) with half = tan(45) = 1 and aspect = 1.
#
# Run (NOT --headless: that swaps in the dummy renderer and there are no pixels):
#   Godot_v4.3-stable_win64_console.exe --path . --audio-driver Dummy \
#       res://scenes/tzelem_cube360.tscn -- --dir=D:/out --res=2048 --far=400 \
#       --eye=-5.20,1.62,10.5
extends Node

static var MAGIC := PackedByteArray([0x54, 0x5A, 0x47, 0x42, 0x55, 0x46, 0x31, 0x00])
const HAS_NORMAL := 1
const HAS_ALBEDO := 2

const WARMUP_FRAMES := 150   # SDFGI / volumetric fog / reflection probe are TEMPORAL
const SETTLE_FRAMES := 60    # after each camera turn

# forward, up-hint, label. ONE eye for all six -- see note 1 above.
const FACES := [
	[Vector3( 1, 0, 0), Vector3(0, 1, 0), "px"],
	[Vector3(-1, 0, 0), Vector3(0, 1, 0), "nx"],
	[Vector3( 0, 1, 0), Vector3(0, 0, 1), "py"],
	[Vector3( 0,-1, 0), Vector3(0, 0, 1), "ny"],
	[Vector3( 0, 0, 1), Vector3(0, 1, 0), "pz"],
	[Vector3( 0, 0,-1), Vector3(0, 1, 0), "nz"],
]

# DEPTH IS MEASURED PER FRAGMENT, and that is a BUG FIX, not a style change.
# (claude-cli-VR-RENDER, 2026-09-06 -- measured, then fixed.)
#
# This shader used to read
#       varying float dist;
#       void vertex() { dist = length((MODELVIEW_MATRIX * vec4(VERTEX,1.0)).xyz); }
#       void fragment() { float v = clamp(dist / far_plane, ...); }
# i.e. it took the distance at the three VERTICES and let the rasteriser interpolate
# it across the triangle. `length()` is not affine, so that is only right when a
# triangle is small compared to how far away it is.
#
# THE NUMBER THAT CONDEMNS IT. boulevard_cafe.gd builds the entire ground out of 240
# triangles, so each one is tens of metres across. On the 'ny' face -- the camera at
# 1.68 m looking STRAIGHT DOWN at the pavement -- the old shader reported 21.89 m at
# frame centre. The true distance is 1.68 m: wrong by 13x. The world NORMAL at the
# same pixel came back as exactly (0,1,0), so the geometry was never in doubt; only
# the distance was. That matters more here than anywhere else, because TZELEM anchors
# every stroke at `point = eye + ray * depth` -- a wrong depth puts the paint in the
# wrong place in the WORLD, and it then lands in the wrong place on the neighbouring
# cube face, which is a seam.
#
# THE FIX. In a Godot 4 spatial fragment() the built-in VERTEX is already the
# view-space position OF THIS FRAGMENT (perspective-correct), so the distance is
# length(VERTEX) with no varying and no vertex() at all. Exact for any triangle size.
#
# THE SAME LINE IS STILL IN tzelem_gbuffer.gd -- deliberately not touched here: gate-1
# numbers and out/godot frames were measured with it, and its owner has to decide what
# to re-run. Flagged in RAMCHAT.
const DEPTH_SHADER := """
shader_type spatial;
render_mode unshaded, cull_disabled;
uniform float far_plane = 400.0;
void fragment() {
	float v = clamp(length(VERTEX) / far_plane, 0.0, 0.999999);
	vec3 enc = fract(vec3(1.0, 255.0, 65025.0) * v);
	enc -= enc.yzz * vec3(1.0/255.0, 1.0/255.0, 0.0);
	ALBEDO = enc;
}
"""

const NORMAL_SHADER := """
shader_type spatial;
render_mode unshaded, cull_disabled;
void fragment() {
	vec3 n = normalize((INV_VIEW_MATRIX * vec4(NORMAL, 0.0)).xyz);
	ALBEDO = n * 0.5 + 0.5;
}
"""

# THE MARGIN, and why a cubemap out of a modern renderer needs one.
# SSAO, glow and volumetric fog are SCREEN-SPACE: they read neighbouring pixels. At
# the border of a frame there are no neighbours, so the renderer invents them, and
# the invention differs between the two faces that share that border -- a bright
# hedge just outside face A's frame blooms into it and does not exist for face B.
# That is a seam nothing downstream can undo. So each face is RENDERED at
# (N + 2*MARGIN) square with a correspondingly wider fov, and only the central N x N
# -- which is exactly 90.0 degrees, because the focal length is unchanged -- is kept.
# The discarded ring is where the edge artefacts live.
#   focal f = N / (2*tan(45 deg)) = N/2, so fov_render = 2*atan((N + 2M) / N).
# It does not remove the effect entirely (glow's coarsest mip is wider than any
# affordable margin); it removes the hard part. The residual is MEASURED downstream
# and reported, not assumed away.
var _dir := "user://"
var _n := 2048
var _margin := 256
var _far := 400.0
var _warmup := WARMUP_FRAMES
var _eye := Vector3(-5.20, 1.62, 10.5)
var _sv: SubViewport
var _cam: Camera3D
var _raw_env: Environment
var _beauty_env: Environment = null
var _no_screen_fx := false
var _keep_ssao := false
var _failures: Array[String] = []


func _ready() -> void:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--dir="): _dir = a.substr(6)
		elif a.begins_with("--res="): _n = int(a.substr(6))
		elif a.begins_with("--far="): _far = float(a.substr(6))
		elif a.begins_with("--margin="): _margin = int(a.substr(9))
		elif a.begins_with("--wait="): _warmup = int(a.substr(7))
		elif a == "--no-screen-fx": _no_screen_fx = true
		elif a == "--keep-ssao": _keep_ssao = true
		elif a.begins_with("--eye="):
			var p := a.substr(6).split(",")
			if p.size() == 3:
				_eye = Vector3(float(p[0]), float(p[1]), float(p[2]))
	DirAccess.make_dir_recursive_absolute(_dir)
	_build()
	# Aim at the first face BEFORE warming up: SDFGI builds its cascades around
	# wherever the camera is, so warming up somewhere else warms up the wrong place.
	_cam.global_position = _eye
	_cam.look_at(_eye + FACES[0][0], FACES[0][1])
	print("[cube360] eye=%v  face=%dx%d kept from %dx%d rendered at fov=%.4f deg "
			% [_eye, _n, _n, _n + 2 * _margin, _n + 2 * _margin, _cam.fov]
			+ "(square viewport, so H-FOV == V-FOV); the kept crop is exactly 90.0")
	await _settle(_warmup)
	var t0 := Time.get_ticks_msec()
	for f in FACES:
		await _export(f[0], f[1], f[2])
	print("[cube360] six faces in %.1f s" % [(Time.get_ticks_msec() - t0) / 1000.0])
	var world := get_node_or_null("../World")
	var tris: int = int(world.get_meta("triangles", 0)) if world else 0
	print("[cube360] scene triangles=%d" % tris)
	if tris < 200000:
		printerr("*** FAIL: triangle count below the 200k detail floor ***")
		_failures.append("triangles")
	if _failures.is_empty():
		print("[cube360] OK: %d faces written to %s" % [FACES.size(), _dir])
		get_tree().quit(0)
	else:
		for f in _failures: printerr("FLAT OR EMPTY FACE: ", f)
		get_tree().quit(1)


func _build() -> void:
	var big := _n + 2 * _margin
	_sv = SubViewport.new()
	_sv.size = Vector2i(big, big)             # SQUARE. See note 2 at the top.
	_sv.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	_sv.transparent_bg = false
	add_child(_sv)
	_sv.world_3d = get_viewport().world_3d
	_cam = Camera3D.new()
	_cam.keep_aspect = Camera3D.KEEP_HEIGHT   # explicit, not trusted to the default
	# same focal length as a 90-degree N-pixel face, just more pixels around it, so
	# the CENTRAL N x N crop below is exactly 90.0 degrees by construction.
	_cam.fov = rad_to_deg(2.0 * atan(float(big) / float(_n)))
	_cam.near = 0.05
	_cam.far = _far
	_sv.add_child(_cam)
	_cam.current = true

	# The DATA passes must not be photographed through the BEAUTY lens: the world's
	# WorldEnvironment has ACES tonemapping, glow, SSAO, SDFGI and volumetric fog, all
	# correct for the picture and fatal for the numbers. Camera3D.environment overrides
	# the world's for this camera only. White clear gives v = 1.0 >= 0.999, so the sky
	# becomes a MISS instead of a false hit.
	_raw_env = Environment.new()
	_raw_env.background_mode = Environment.BG_COLOR
	_raw_env.background_color = Color(1, 1, 1, 1)
	_raw_env.ambient_light_source = Environment.AMBIENT_SOURCE_DISABLED
	_raw_env.reflected_light_source = Environment.REFLECTION_SOURCE_DISABLED
	_raw_env.tonemap_mode = Environment.TONE_MAPPER_LINEAR
	_raw_env.tonemap_exposure = 1.0
	_raw_env.tonemap_white = 1.0

	# --- --no-screen-fx : OFF BY DEFAULT, AND THE MEASUREMENT SAYS LEAVE IT OFF.
	# (claude-cli-VR-RENDER, 2026-09-06. Kept because the switch is useful and the
	# result is worth recording; DO NOT reach for it expecting a better seam.)
	#
	# THE HYPOTHESIS. glow, SSAO and SSIL are SCREEN-SPACE: what they do to a pixel
	# depends on what else is in the frame, and six cube faces have six frames. So the
	# same world point gets two colours in the two faces that see it, and no margin can
	# close that because glow's coarsest mip is a large fraction of any frame. It looked
	# certain, and I nearly shipped it as the fix.
	#
	# IT IS WRONG, and here is the number that killed it. Measured on the finished
	# 8192x4096 plate by vr360_isline.py, which asks the only question the eye asks --
	# is the join column an OUTLIER against its own neighbourhood, in the SMOOTH regions
	# where a line would be glaring:
	#     RAW ENGINE equirect, effects ON        excess +6.9 / 255 at the join  (z 8.0)
	#     RAW ENGINE equirect, --no-screen-fx    excess +7.7 / 255              (z 14.4)
	#     RAW ENGINE, --no-screen-fx --keep-ssao excess +8.4 / 255              (z 19.5)
	#     TZELEM PAINTED, effects ON             excess +0.8 / 255              (z 3.9)
	# Turning the effects off did not help the raw plate at all, and the PAINTER already
	# removes the seam -- 6.9 down to 0.8 of a 255 level, i.e. under one 8-bit step.
	# That is world-anchored strokes doing the job they exist for: a stroke crossing a
	# cube edge is the SAME stroke on both sides, so the painting is continuous even
	# where the two renders underneath it are not.
	#
	# (Health warning on all four numbers: boulevard_cafe.gd does not rebuild the same
	# world twice -- 810,468 / 982,944 / 985,542 triangles across runs -- so the three
	# RAW rows are different boulevards and their ORDER is not to be trusted. What IS
	# trustworthy is that none of them came near the painted plate, and that the painted
	# row is a single image measured against itself.)
	#
	# So the default keeps glow, SSAO and SSIL: they are most of what makes the picture
	# read as solid, and they cost nothing at the join once it is painted.
	if _no_screen_fx:
		var src: Environment = get_viewport().world_3d.environment
		if src == null:
			printerr("--no-screen-fx: the world has no Environment; ignoring")
		else:
			_beauty_env = src.duplicate() as Environment
			_beauty_env.glow_enabled = false
			# --keep-ssao: SSAO's radius is 0.7 m, so its screen-space reach at the
			# DISTANCES that appear near a face edge is a few pixels and the margin
			# already covers it. Glow (mips a large fraction of the frame) and SSIL
			# (radius 3.5 m) are the wide ones. Kept as a separate switch so the
			# contact darkening -- which is most of what makes the picture read as
			# solid -- can be preserved if it costs nothing at the seam. MEASURED.
			_beauty_env.ssao_enabled = _keep_ssao
			_beauty_env.ssil_enabled = false
			_beauty_env.ssr_enabled = false
			print("[cube360] --no-screen-fx: glow/ssil/ssr OFF, ssao=%s, for the "
					% _keep_ssao + "beauty pass; sky, ACES, fog and SDFGI KEPT")


func _settle(frames: int) -> void:
	_cam.environment = _beauty_env            # warm up through the BEAUTY lens
	_sv.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	for _i in frames:
		await get_tree().process_frame


# *** THE COLOUR BUG, FOUND AND FIXED 2026-09-06 (claude-cli-VR-CAFE). ***
#
# This used to be `_apply(scene, mat)` ... render ... `_apply(scene, null)`, i.e. it
# "cleared" the override by setting material_override = null on every
# GeometryInstance3D in the scene. That is not clearing. That is DELETING.
#
# boulevard_cafe.gd assigns TWENTY of its materials THROUGH material_override --
# m_skin on every head, m_iron, m_rubber, m_marble, m_steel, m_plaster, m_canvas,
# m_stone, the car paint (lines 585, 603, 636, 667, 781, 835, 1007, 1052, 1089, 1169,
# 1196, 1207, 1326, 1447, 1496, 1534, 1545, 1559, 1614, 1635). Nulling them wiped
# them for the REST OF THE RUN, and every mesh fell back to Godot's default white.
# Worse, the beauty pass was the FIRST call, so it destroyed the materials and then
# photographed the wreckage -- the very first face of every run was already ruined.
#
# The tell was sitting in plain sight: the trees and hedges kept their green, because
# _sph_leaf.material / _sph_hedge.material (lines 387, 394) are MESH-surface materials
# and this loop never touched those. Everything set by override went white.
#
# MEASURED against boulevard_shots.gd's own output at the same eye (it never calls
# _apply at all, which is why its stills are right):
#     boulevard_shots.gd pose 02   luminance mean 0.539, p05 0.084, 22.5% below 0.25,
#                                  saturation 0.550  -- pink shirts, brown wood, a
#                                  near-black shopfront window
#     this file, before the fix    mean 0.699, p05 0.522, 0.55% below 0.25,
#                                  saturation 0.329  -- all three of those WHITE
# Turning the screen-space effects off recovered only a third of it (sat 0.389); the
# rest was this.
#
# THE FIX: never null anything. The beauty pass touches no material at all, and a data
# pass SAVES each node's existing override and puts it back afterwards.
#
# NOTE FOR tzelem_gbuffer.gd's OWNER: the identical line is in that file, so every
# .tzg the boulevard has ever exported carries the wrecked colours in its albedo --
# including the frames gate 1 was measured on. Flagged in RAMCHAT; not changed here.
var _saved_overrides := {}


func _shot(mat: Material) -> Image:
	if mat != null:
		_apply(get_tree().current_scene, mat)
	_cam.environment = _beauty_env if mat == null else _raw_env
	_sv.render_target_update_mode = SubViewport.UPDATE_ONCE
	await RenderingServer.frame_post_draw
	var img := _sv.get_texture().get_image()
	if mat != null:
		_restore()
	return img


func _apply(node: Node, mat: Material) -> void:
	if node is GeometryInstance3D:
		var gi := node as GeometryInstance3D
		if not _saved_overrides.has(gi):
			_saved_overrides[gi] = gi.material_override
		gi.material_override = mat
	for c in node.get_children():
		_apply(c, mat)


func _restore() -> void:
	for gi in _saved_overrides:
		if is_instance_valid(gi):
			(gi as GeometryInstance3D).material_override = _saved_overrides[gi]
	_saved_overrides.clear()


func _export(dir_v: Vector3, up_v: Vector3, label: String) -> void:
	_cam.global_position = _eye
	_cam.look_at(_eye + dir_v, up_v)
	await _settle(mini(SETTLE_FRAMES, _warmup))

	var beauty := await _shot(null)
	var dmat := ShaderMaterial.new()
	dmat.shader = Shader.new(); dmat.shader.code = DEPTH_SHADER
	dmat.set_shader_parameter("far_plane", _far)
	var depth_img := await _shot(dmat)
	var nmat := ShaderMaterial.new()
	nmat.shader = Shader.new(); nmat.shader.code = NORMAL_SHADER
	var normal_img := await _shot(nmat)

	var w := _n
	var h := _n
	var n := w * h
	var depth := PackedFloat32Array(); depth.resize(n)
	var normal := PackedFloat32Array(); normal.resize(n * 3)
	var albedo := PackedFloat32Array(); albedo.resize(n * 3)
	var hits := 0
	var dmin := INF
	var dmax := -INF
	var lmin := INF
	var lmax := -INF
	for y in h:
		for x in w:
			var i := y * w + x
			var sx := x + _margin      # the central crop: the discarded ring is
			var sy := y + _margin      # where the screen-space edge artefacts live
			var e := depth_img.get_pixel(sx, sy).srgb_to_linear()
			var v: float = e.r + e.g / 255.0 + e.b / 65025.0
			var d: float = v * _far
			var miss: bool = v >= 0.999
			depth[i] = 0.0 if miss else d
			if not miss:
				hits += 1
				dmin = min(dmin, d); dmax = max(dmax, d)
			var nn := normal_img.get_pixel(sx, sy).srgb_to_linear()
			normal[i * 3 + 0] = nn.r * 2.0 - 1.0
			normal[i * 3 + 1] = nn.g * 2.0 - 1.0
			normal[i * 3 + 2] = nn.b * 2.0 - 1.0
			var c := beauty.get_pixel(sx, sy)
			albedo[i * 3 + 0] = c.r; albedo[i * 3 + 1] = c.g; albedo[i * 3 + 2] = c.b
			var lum: float = 0.2126 * c.r + 0.7152 * c.g + 0.0722 * c.b
			lmin = min(lmin, lum); lmax = max(lmax, lum)

	var hit_frac := float(hits) / float(n)
	print("[cube360] face %s: hit %.1f%%  depth %.2f..%.2f  luminance spread %.4f"
		% [label, hit_frac * 100.0, dmin if hits > 0 else 0.0,
		   dmax if hits > 0 else 0.0, lmax - lmin])
	# A face may legitimately be almost all sky (+Y looks straight up), so a low hit
	# fraction is NOT a failure here the way it is in the walk exporter. A face with
	# no luminance spread at all still is: that is a picture of nothing.
	if (lmax - lmin) < 0.01:
		_failures.append(label)
		return

	var blob := PackedByteArray()
	blob.append_array(MAGIC)
	var head := PackedInt32Array([w, h, HAS_NORMAL | HAS_ALBEDO])
	blob.append_array(head.to_byte_array())
	blob.append_array(depth.to_byte_array())
	blob.append_array(normal.to_byte_array())
	blob.append_array(albedo.to_byte_array())

	var f := FileAccess.open("%s/face_%s.tzg" % [_dir, label], FileAccess.WRITE)
	f.store_buffer(blob); f.close()

	# THE UP VECTOR IS WRITTEN, not assumed. tzelem_gbuffer.gd hardcodes [0,1,0],
	# which is wrong for +-Y and would silently hand numpy a different basis than the
	# one these pixels were rendered with.
	var target := _eye + dir_v
	var meta := {
		"eye": [_eye.x, _eye.y, _eye.z],
		"target": [target.x, target.y, target.z],
		"up": [up_v.x, up_v.y, up_v.z],
		# EXACTLY 90.0 -- the number the kept crop actually spans, not the wider fov
		# the GPU was driven at. The margin is a rendering detail; the face is 90.
		"fov_deg": 90.0, "width": w, "height": h,
		"face": label, "far": _far,
		"render_fov_deg": _cam.fov, "render_px": _n + 2 * _margin, "margin": _margin,
	}
	var jf := FileAccess.open("%s/face_%s.json" % [_dir, label], FileAccess.WRITE)
	jf.store_string(JSON.stringify(meta, "\t")); jf.close()
