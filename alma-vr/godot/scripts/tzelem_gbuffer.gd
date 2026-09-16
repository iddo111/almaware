# tzelem_gbuffer.gd -- the door the engine's world comes through, for TZELEM.
#
# BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.
#
# STATUS, said first so nobody is misled: RUN AND VERIFIED 2026-09-05 on the PC under
# Godot 4.3.stable.official.77dcf97d8 (local D:\tools\godot43, RTX 3070 Ti, Vulkan
# Forward+), at 960x540 (13 s) and again at 1920x1080 (43 s; 48 s once the warm-up
# below was added). It writes frame_00..03 .tzg + .json into --dir; at 1920x1080 each
# .tzg is 58,060,820 bytes and tzelem/gbuffer.py loads all four with no conversion.
# PROOF, not a green tick:
#   * normals    |n| = 1.00003 +/- 0.0015 over hit pixels, 99.98% inside [0.99, 1.01];
#                the pavement's world normal comes back as exactly (0, 1, 0).
#   * depth      metric, checked against the SCENE'S OWN ground truth -- horizontal
#                surfaces within 12 m have their modal height at +0.215 m against
#                boulevard_cafe.gd's `const DECK := 0.17`, i.e. within 4.5 cm -- and
#                that figure is IDENTICAL at --wait=1 and --wait=150, which is how we
#                know the warm-up fix below did not move the geometry. Sky is a real
#                miss, not a false hit.
#   * beauty     a correctly lit, correctly oriented render of the boulevard, with a
#                canopy that is now actually lit -- see DEFECT 1, now FIXED.
#
# THE CLAIM THAT THIS NEEDED GODOT 4.7 WAS WRONG, and it cost this file five days of
# being believed unrunnable. The actual blocker was one word on line 47: GDScript 4.3
# rejects `const MAGIC := PackedByteArray([...])` as not a constant expression, so the
# script failed to PARSE. The scene still ran, the world still built, the Export node
# silently had no script at all, and the process hung until killed -- a parse error
# fails before _ready(), so every measurement below it was mute. Diagnosis is cheap;
# assuming the blocker is someone else's missing binary is not.
#
# DEFECT 1 -- FIXED 2026-09-05. What it was, and what the fix is worth in numbers.
#      It used to take the beauty pass after ONE process frame, so SDFGI and the
#      volumetric fog had converged to nothing and the tree canopy read near-black.
#      It now waits WARMUP_FRAMES=150 before the first pose and SETTLE_FRAMES=60
#      after each camera move -- the two numbers boulevard_shots.gd:42 and :148
#      already used, for the reason it already gave.
#      MEASURED on a MATCHED PAIR: two runs whose world census was byte-identical
#      (810,468 tris / 4,557 draws / 12,362 multimesh instances), one at --wait=1 and
#      one at --wait=150, so the world variance of DEFECT 2 cannot explain the gap:
#          canopy (upper third, hit pixels) median luminance   0.220 -> 0.507
#          canopy mean luminance                               0.385 -> 0.564
#      And against the old 1-frame files, over ALL FOUR frames:
#          canopy fraction below luminance 0.02   32-37%  ->  0.000% on every frame
#          canopy median luminance            0.092-0.154 ->  0.498-0.599
#          full-frame albedo mean   [0.346 0.317 0.266] -> [0.619 0.565 0.474]
#      Geometry did NOT move: |n| = 1.00003, 99.98% in [0.99, 1.01], and the ground's
#      modal height +0.215 m in BOTH arms of the matched pair.
#      TWO TRAPS the fix had to step around, either of which makes a wait that is not
#      a wait: (a) the camera must be aimed at the first pose BEFORE warming up,
#      because SDFGI builds its cascades around wherever the camera is; (b) a viewport
#      left on UPDATE_ONCE reverts to DISABLED once it has drawn, and this scene has
#      no other camera at all (boulevard_cafe.gd builds no Camera3D), so the viewport
#      must be put back to UPDATE_ALWAYS or the 150 frames draw nothing whatsoever.
#
# STILL KNOWN-WRONG:
#   2. boulevard_cafe.gd does not rebuild the same world twice despite "seed 1933":
#      runs have now given 810,468 / 821,946 / 838,494 / 866,304 / 888,030 / 932,958 /
#      969,816 / 985,542 triangles. The four poses inside ONE run share one world, so
#      flow between consecutive frames is valid; comparing .tzg files ACROSS runs is
#      not. Hit fraction is the loudest symptom -- 93.6% to 99.1% across runs, tracking
#      how much canopy hangs overhead -- so it is NOT a cross-run invariant and must
#      never be used as a regression check. It was nearly read as damage on 09-05.
#   3. NEW, found 2026-09-05 while proving DEFECT 1, and it is NOT defect 2: two runs
#      with a byte-identical world census AND the same --wait still differ -- hit
#      93.92% vs 93.65%, distinct depths 994,045 vs 960,266. So a frame is not
#      reproducible even when the world is. It is small and it lives on canopy leaf
#      edges (the ground-truth height check does not move), but the likely cause is
#      that _shot() grabs the image after a SINGLE frame_post_draw while
#      material_override is still propagating across 4,557 draws -- a capture race.
#      Not fixed, not yet diagnosed beyond this. Do not assume a frame is repeatable.
#
# The PYTHON side of this contract was already verified: tzelem/gbuffer.py round-trips
# the format exactly (normals bit-identical, mask identical, depth to float32
# precision), tested by writing our own numpy world out in this format and reading it
# back. Both halves now stand.
#
# WHAT IT DOES. For each pose it renders the scene THREE times into a SubViewport and
# writes one .tzg + .json pair that tzelem/gbuffer.py can load with no conversion:
#
#   1. BEAUTY   the scene as it is -> the colour the EYE RECEIVES. That, and not the
#               raw material colour, is what a stroke must carry: TZELEM's scatter()
#               samples the shaded image, and a painter paints what he sees.
#   2. DEPTH    a shader packing linear view distance into RGBA8 and unpacked here to
#               float. 8-bit channels are used deliberately: an HDR viewport read back
#               as half-float carries about three decimal digits, while this packing
#               carries twenty-four bits across the far plane, which is more.
#   3. NORMAL   world-space normal, written as n * 0.5 + 0.5.
#
# DEPTH IS DISTANCE FROM THE EYE, not z along the forward axis. gbuffer.py stores and
# stage.flow() compares that convention, and mixing the two is the classic way to get
# a renderer that is subtly wrong everywhere and obviously wrong nowhere.
#
# NEVER a desktop screenshot -- the same rule boulevard_shots.gd states and for the
# same reason: on 2026-08-30 grabbing the whole screen to look at a render caught
# Iddo's private windows twice. The pixels wanted are inside the viewport.
#
# EVERY FRAME IS MEASURED BEFORE IT IS TRUSTED. A render that produced nothing --
# driver fell over, camera inside a wall, nothing in front of it -- writes a perfectly
# valid file full of zeros, and a check that cannot notice that is not a check. So each
# frame reports its hit fraction, depth range and luminance spread, and the run EXITS
# NON-ZERO if any frame is empty or flat.
#
# Run:
#   godot --path . --audio-driver Dummy res://scenes/tzelem_gbuffer.tscn -- \
#         --dir=D:/CLAUDE/eran-brain/holobrain/tzelem/out/godot --res=480x360 --far=200
# NOT --headless: that swaps in the dummy renderer and there are no pixels to read.
# --wait=N overrides the warm-up; --wait=1 reproduces the old near-black canopy.
extends Node

# The magic is built byte by byte on purpose: the format's eighth byte is a NUL,
# and a GDScript String is not the place to keep one. gbuffer.py compares all
# eight bytes and refuses the file if they differ, so a wrong magic is silent.
#
# It is a `static var`, NOT a `const`, and that is not a style choice. GDScript 4.3
# refuses `const MAGIC := PackedByteArray([...])` with "Assigned value for constant
# isn't a constant expression" -- a PackedByteArray constructor is not const-foldable.
# That single word is what stopped this file from ever loading (2026-09-05): the
# scene ran, the world built, the Export node silently had no script, and the
# process hung forever with nothing written. A parse error is not a runtime error;
# it fails BEFORE _ready(), so none of the measurement below ever gets to speak.
static var MAGIC := PackedByteArray([0x54, 0x5A, 0x47, 0x42, 0x55, 0x46, 0x31, 0x00])
const HAS_NORMAL := 1
const HAS_ALBEDO := 2

# CONVERGENCE. Exactly the two numbers boulevard_shots.gd:42 and :148 use, for exactly
# the reason it states: SDFGI, the volumetric fog and the reflection probe are all
# TEMPORAL -- they accumulate over frames and are wrong until they have had them.
# Taking the beauty pass after one process frame is what crushed the tree canopy to
# near-black (measured 2026-09-05: 35.7% of the canopy under luminance 0.02).
const WARMUP_FRAMES := 150   # before the FIRST pose: cold GI has nothing accumulated
const SETTLE_FRAMES := 60    # after each camera teleport, as _process() does there

# The camera path the ruler is measured over: small steps, so the exact optical flow
# between consecutive frames has something to be exact ABOUT.
const POSES := [
	[Vector3(-1.10, 1.68, -26.0), Vector3(0.60, 1.35, 8.0), "00"],
	[Vector3(-0.95, 1.68, -25.6), Vector3(0.62, 1.35, 8.0), "01"],
	[Vector3(-0.80, 1.68, -25.2), Vector3(0.64, 1.35, 8.0), "02"],
	[Vector3(-0.65, 1.68, -24.8), Vector3(0.66, 1.35, 8.0), "03"],
]

const DEPTH_SHADER := """
shader_type spatial;
render_mode unshaded, cull_disabled;
uniform float far_plane = 200.0;
varying float dist;
void vertex() { dist = length((MODELVIEW_MATRIX * vec4(VERTEX, 1.0)).xyz); }
void fragment() {
	float v = clamp(dist / far_plane, 0.0, 0.999999);
	vec3 enc = fract(vec3(1.0, 255.0, 65025.0) * v);
	enc -= enc.yzz * vec3(1.0/255.0, 1.0/255.0, 0.0);
	ALBEDO = enc;
}
"""
# NOTE ON THE MISSING FOURTH CHANNEL. This packing was written across RGBA and set
# ALPHA = enc.a. Writing ALPHA in a spatial shader makes the surface TRANSPARENT, so
# every fragment got a pseudo-random opacity from the low bits of its own depth and
# was alpha-blended against the background -- which is where the salt-and-pepper
# speckle in the 2026-09-05 first run came from. RGB alone still carries the twenty-four
# bits the header claims (the fourth channel was the 32nd bit, worth 200/16581375 m
# = 1.2e-5 m at a 200 m far plane), so dropping it costs nothing measurable and buys
# an opaque pass. The CPU decode below drops the matching term.

const NORMAL_SHADER := """
shader_type spatial;
render_mode unshaded, cull_disabled;
void fragment() {
	vec3 n = normalize((INV_VIEW_MATRIX * vec4(NORMAL, 0.0)).xyz);
	ALBEDO = n * 0.5 + 0.5;
}
"""

var _dir := "user://"
var _w := 480
var _h := 360
var _far := 200.0
var _warmup := WARMUP_FRAMES
var _sv: SubViewport
var _cam: Camera3D
var _raw_env: Environment
var _failures: Array[String] = []


func _ready() -> void:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--dir="): _dir = a.substr(6)
		elif a.begins_with("--res="):
			var p := a.substr(6).split("x")
			if p.size() == 2: _w = int(p[0]); _h = int(p[1])
		elif a.begins_with("--far="): _far = float(a.substr(6))
		# --wait= exists so the warm-up can be TESTED, exactly as boulevard_shots.gd:59
		# allows. `--wait=1` reproduces the old, wrong, near-black canopy on demand,
		# which is the only way to tell the warm-up apart from the world rebuilding
		# itself differently every run (defect 2 above).
		elif a.begins_with("--wait="): _warmup = int(a.substr(7))
	DirAccess.make_dir_recursive_absolute(_dir)
	_build()
	# Aim at the first pose BEFORE warming up, the way boulevard_shots.gd calls _aim(0)
	# in _ready() and only then counts down: SDFGI cascades are built around wherever
	# the camera is, so warming up at the origin warms up the wrong place.
	_cam.global_position = POSES[0][0]
	_cam.look_at(POSES[0][1], Vector3.UP)
	await _settle(_warmup)
	for pose in POSES:
		await _export(pose[0], pose[1], pose[2])
	if _failures.is_empty():
		print("TZELEM g-buffer: %d frames written to %s" % [POSES.size(), _dir])
		get_tree().quit(0)
	else:
		for f in _failures: printerr("FLAT OR EMPTY FRAME: ", f)
		get_tree().quit(1)


func _build() -> void:
	_sv = SubViewport.new()
	_sv.size = Vector2i(_w, _h)
	_sv.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	_sv.transparent_bg = false
	add_child(_sv)
	# the house way, and the correct one: share the MAIN viewport's world, exactly as
	# boulevard_shots.gd:83 does. Taking current_scene.get_world_3d() would work only
	# by accident of scene layout.
	_sv.world_3d = get_viewport().world_3d
	_cam = Camera3D.new()
	_cam.fov = 50.0
	_sv.add_child(_cam)
	_cam.current = true

	# THE DATA PASSES MUST NOT BE PHOTOGRAPHED THROUGH THE BEAUTY LENS.
	# boulevard_cafe.gd:443-547 hangs a WorldEnvironment on the shared world with ACES
	# tonemapping (exposure 1.02, white 6.0), glow, SSAO, SDFGI, exponential fog AND
	# volumetric fog. Every one of those is correct for the picture and fatal for the
	# numbers: measured 2026-09-05, the depth and normal passes came back with the right
	# GEOMETRY and the wrong VALUES -- depth read 113 m for the sky and 113 m for the
	# pavement at the camera's feet, and |normal| ran 0.23..1.44 instead of 1. Structured
	# garbage, which is worse than black, because the flatness check upstream cannot see it.
	# Camera3D.environment overrides the world's for this camera only, so the beauty pass
	# keeps every effect and the data passes get a linear, unlit, effect-free lens.
	# The clear colour is WHITE on purpose: white decodes to v = 1.0 >= 0.999, which is
	# exactly the miss marker, so the sky becomes a miss instead of a false hit.
	_raw_env = Environment.new()
	_raw_env.background_mode = Environment.BG_COLOR
	_raw_env.background_color = Color(1, 1, 1, 1)
	_raw_env.ambient_light_source = Environment.AMBIENT_SOURCE_DISABLED
	_raw_env.reflected_light_source = Environment.REFLECTION_SOURCE_DISABLED
	_raw_env.tonemap_mode = Environment.TONE_MAPPER_LINEAR
	_raw_env.tonemap_exposure = 1.0
	_raw_env.tonemap_white = 1.0


# Let the temporal effects accumulate. Two things here are not optional and both were
# found the hard way:
#   * the BEAUTY lens must be the one mounted while it converges -- _raw_env is the
#     data lens, with SDFGI and fog switched off, so warming up through it warms up
#     nothing. After a normal pass _cam.environment is still _raw_env, hence the reset.
#   * UPDATE_ONCE reverts the SubViewport to UPDATE_DISABLED once it has drawn, and
#     this scene has NO other camera (boulevard_cafe.gd builds no Camera3D, which is
#     why the window shows only the clear colour). So without putting the viewport back
#     to UPDATE_ALWAYS, awaiting 60 frames awaits 60 frames in which nothing is drawn
#     and nothing converges -- a wait that looks like a fix and is not.
func _settle(frames: int) -> void:
	_cam.environment = null
	_sv.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	for _i in frames:
		await get_tree().process_frame


func _shot(mat: Material) -> Image:
	_apply(get_tree().current_scene, mat)
	# mat == null is the beauty pass and keeps the world's own environment; every
	# override material is a DATA pass and gets the neutral lens built in _build().
	_cam.environment = null if mat == null else _raw_env
	_sv.render_target_update_mode = SubViewport.UPDATE_ONCE
	await RenderingServer.frame_post_draw
	var img := _sv.get_texture().get_image()
	_apply(get_tree().current_scene, null)
	return img


func _apply(node: Node, mat: Material) -> void:
	if node is GeometryInstance3D:
		(node as GeometryInstance3D).material_override = mat
	for c in node.get_children():
		_apply(c, mat)


func _export(eye: Vector3, look: Vector3, label: String) -> void:
	_cam.global_position = eye
	_cam.look_at(look, Vector3.UP)
	await _settle(mini(SETTLE_FRAMES, _warmup))

	var beauty := await _shot(null)
	var dmat := ShaderMaterial.new()
	dmat.shader = Shader.new(); dmat.shader.code = DEPTH_SHADER
	dmat.set_shader_parameter("far_plane", _far)
	var depth_img := await _shot(dmat)
	var nmat := ShaderMaterial.new()
	nmat.shader = Shader.new(); nmat.shader.code = NORMAL_SHADER
	var normal_img := await _shot(nmat)

	var n := _w * _h
	var depth := PackedFloat32Array(); depth.resize(n)
	var normal := PackedFloat32Array(); normal.resize(n * 3)
	var albedo := PackedFloat32Array(); albedo.resize(n * 3)
	var hits := 0
	var dmin := INF
	var dmax := -INF
	var lmin := INF
	var lmax := -INF
	for y in _h:
		for x in _w:
			var i := y * _w + x
			# srgb_to_linear() is NOT a colour correction here, it is the inverse of
			# what the pipeline did to our data. Godot's tonemap stage writes the 8-bit
			# render target in sRGB transfer, so a value the shader wrote as V comes
			# back as linear_to_srgb(V). Measured 2026-09-05: undoing it takes the
			# normal pass from |n| = 0.23..1.44 (14.6% near unit) to |n| = 1.0000 with
			# 100.00% of pixels inside [0.9, 1.1], and turns the pavement's byte triple
			# (188,255,187) into exactly (0, 1, 0). That is proof, not preference.
			# The BEAUTY pass is deliberately left alone: it is what the eye receives,
			# i.e. display-referred, which is what gbuffer.py and scatter() want.
			var e := depth_img.get_pixel(x, y).srgb_to_linear()
			var v: float = e.r + e.g / 255.0 + e.b / 65025.0
			var d: float = v * _far
			# a ray that hit nothing sits at the far plane; 0 is our miss marker
			var miss: bool = v >= 0.999
			depth[i] = 0.0 if miss else d
			if not miss:
				hits += 1
				dmin = min(dmin, d); dmax = max(dmax, d)
			var nn := normal_img.get_pixel(x, y).srgb_to_linear()
			normal[i * 3 + 0] = nn.r * 2.0 - 1.0
			normal[i * 3 + 1] = nn.g * 2.0 - 1.0
			normal[i * 3 + 2] = nn.b * 2.0 - 1.0
			var c := beauty.get_pixel(x, y)
			albedo[i * 3 + 0] = c.r; albedo[i * 3 + 1] = c.g; albedo[i * 3 + 2] = c.b
			var lum: float = 0.2126 * c.r + 0.7152 * c.g + 0.0722 * c.b
			lmin = min(lmin, lum); lmax = max(lmax, lum)

	var hit_frac := float(hits) / float(n)
	print("frame %s: hit %.1f%%  depth %.2f..%.2f  luminance spread %.4f"
		% [label, hit_frac * 100.0, dmin if hits > 0 else 0.0,
		   dmax if hits > 0 else 0.0, lmax - lmin])
	if hits == 0 or (lmax - lmin) < 0.01:
		_failures.append(label)
		return

	var blob := PackedByteArray()
	blob.append_array(MAGIC)
	var head := PackedInt32Array([_w, _h, HAS_NORMAL | HAS_ALBEDO])
	blob.append_array(head.to_byte_array())
	blob.append_array(depth.to_byte_array())
	blob.append_array(normal.to_byte_array())
	blob.append_array(albedo.to_byte_array())

	var f := FileAccess.open("%s/frame_%s.tzg" % [_dir, label], FileAccess.WRITE)
	f.store_buffer(blob); f.close()

	var meta := {
		"eye": [eye.x, eye.y, eye.z],
		"target": [look.x, look.y, look.z],
		"up": [0.0, 1.0, 0.0],
		"fov_deg": _cam.fov, "width": _w, "height": _h,
	}
	var jf := FileAccess.open("%s/frame_%s.json" % [_dir, label], FileAccess.WRITE)
	jf.store_string(JSON.stringify(meta, "\t")); jf.close()
