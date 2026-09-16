# boulevard_shots.gd -- the acceptance check. The game photographs ITSELF, in 4K.
#
# BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.
#
# NEVER a desktop screenshot. On 2026-08-30 grabbing the whole screen to look at a
# render caught Iddo's private windows twice, once his WhatsApp. The pixels wanted
# are inside the viewport and the viewport hands them over directly. Same technique
# as scripts/shot_self.gd, extended two ways:
#
#   1. a 3840x2160 SubViewport instead of the window, so the stills are genuinely 4K
#      no matter what the monitor is. Requesting a 4K WINDOW gets clamped to the
#      display and you quietly get 2560x1440 while believing you got 4K.
#   2. every still is MEASURED before it is trusted. A render that produced nothing
#      -- driver fell over, camera inside a wall, SDFGI never converged -- saves a
#      perfectly valid PNG of flat black, and a check that cannot notice that is
#      not a check. So each image is reduced and its luminance mean, standard
#      deviation and near-black fraction are printed, and the run EXITS NON-ZERO if
#      any frame is flat. That is the floor this test can fall through.
#
# Run:
#   Godot_v4.3-stable_win64_console.exe --path . --audio-driver Dummy \
#       res://scenes/boulevard_shots.tscn -- --dir=D:/path/out --res=3840x2160
extends Node

const EYE := 1.68          # walking eye height, metres

# pos, look-at, label. Every one is from standing or sitting height ON the median.
const POSES := [
	[Vector3(-1.10, EYE, -26.0), Vector3(0.60, 1.35, 8.0), "01-walking-north"],
	[Vector3(-5.20, 1.62, 10.5), Vector3(2.40, 1.55, 12.6), "02-cafe-claude"],
	[Vector3(3.10, EYE, -15.5), Vector3(-1.60, 1.15, -7.0), "03-the-low-limb"],
	[Vector3(0.55, 1.22, 31.0), Vector3(-13.0, 6.5, 25.0), "04-from-the-bench"],
	[Vector3(0.00, 1.72, -36.5), Vector3(0.30, 1.55, 20.0), "05-down-the-median"],
]

var _dir := "user://"
var _w := 3840
var _h := 2160
var _sv: SubViewport
var _cam: Camera3D
var _i := 0
var _wait := 150           # frames before the FIRST shot: SDFGI, volumetric fog and
						   # the reflection probe all need time to converge
var _fail := 0
var _busy := false
var _done := false
var _saved := []


func _ready() -> void:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--dir="):
			_dir = a.split("=", true, 1)[1]
		elif a.begins_with("--res="):
			var p: PackedStringArray = a.split("=", true, 1)[1].split("x")
			if p.size() == 2:
				_w = int(p[0])
				_h = int(p[1])
		elif a.begins_with("--wait="):
			_wait = int(a.split("=")[1])
	if not _dir.ends_with("/"):
		_dir += "/"
	if not _dir.begins_with("user://") and not _dir.begins_with("res://"):
		DirAccess.make_dir_recursive_absolute(_dir)

	# --headless swaps in the dummy rendering driver: nothing is drawn and every
	# mesh handle is null, so building a SubViewport there only produces a wall of
	# "Parameter m is null". The headless pass is for the LOAD and the CENSUS; the
	# stills need a real GPU. Say which one this is and stop.
	if DisplayServer.get_name() == "headless":
		var w := get_node_or_null("../World")
		var t: int = int(w.get_meta("triangles", 0)) if w else 0
		print("[shots] headless: scene loaded, census done, triangles=%d. "
				% t + "No stills -- the dummy driver renders nothing.")
		get_tree().quit(0 if t >= 200000 else 4)
		return

	_sv = SubViewport.new()
	_sv.size = Vector2i(_w, _h)
	# Share the main world so the camera in here sees the boulevard that was built
	# out there. Without this the SubViewport makes its own empty World3D and every
	# still comes back as sky -- which the flatness check below would catch.
	_sv.world_3d = get_viewport().world_3d
	_sv.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	_sv.msaa_3d = Viewport.MSAA_4X
	_sv.screen_space_aa = Viewport.SCREEN_SPACE_AA_DISABLED
	_sv.use_taa = true
	_sv.positional_shadow_atlas_size = 4096
	_sv.transparent_bg = false
	add_child(_sv)

	_cam = Camera3D.new()
	_cam.fov = 62.0            # close to a 32 mm lens: how the boulevard is seen
	_cam.near = 0.05
	_cam.far = 400.0
	_cam.current = true
	_sv.add_child(_cam)
	_aim(0)
	print("[shots] subviewport %dx%d, %d poses, dir=%s" % [_w, _h, POSES.size(), _dir])


func _aim(i: int) -> void:
	var p: Vector3 = POSES[i][0]
	var t: Vector3 = POSES[i][1]
	_cam.position = p
	_cam.look_at(t, Vector3.UP)


func _process(_d: float) -> void:
	# _process awaits, which makes it a coroutine: without these two guards a second
	# frame enters while the first is still saving, and quit() is deferred so one
	# more frame arrives after the last pose. Both were real -- the first run ended
	# in "Out of bounds get index '5'".
	if _busy or _done:
		return
	_wait -= 1
	if _wait > 0:
		return
	_busy = true
	await RenderingServer.frame_post_draw
	var img := _sv.get_texture().get_image()
	var name: String = POSES[_i][2]
	var path: String = _dir + "boulevard-" + name + ".png"
	var err := img.save_png(path)
	var st := _stats(img)
	var ok: bool = err == OK and img.get_width() == _w and st["std"] > 0.02 \
			and st["black"] < 0.85
	if not ok:
		_fail += 1
	print("[shots] %-18s %s  %dx%d  mean=%.3f std=%.3f black=%.3f  %s"
			% [name, "saved" if err == OK else "SAVE-FAILED", img.get_width(),
			img.get_height(), st["mean"], st["std"], st["black"],
			"OK" if ok else "*** FLAT / WRONG SIZE -- FAIL ***"])
	_saved.append(path)
	_i += 1
	if _i >= POSES.size():
		var world := get_node_or_null("../World")
		var tris: int = int(world.get_meta("triangles", 0)) if world else 0
		print("[shots] %d/%d stills good, %d bad; scene triangles=%d"
				% [POSES.size() - _fail, POSES.size(), _fail, tris])
		if tris < 200000:
			print("[shots] *** FAIL: triangle count below the 200k detail floor ***")
			_fail += 1
		_done = true
		get_tree().quit(0 if _fail == 0 else 4)
		return
	_aim(_i)
	_wait = 60             # let TAA and SDFGI settle after the camera teleports
	_busy = false


# Reduce and measure. A PNG that saved fine can still be a picture of nothing.
func _stats(src: Image) -> Dictionary:
	var img := src.duplicate() as Image
	img.resize(192, 108, Image.INTERPOLATE_BILINEAR)
	var n := 192 * 108
	var sum := 0.0
	var sum2 := 0.0
	var black := 0
	for y in 108:
		for x in 192:
			var c := img.get_pixel(x, y)
			var l: float = c.r * 0.2126 + c.g * 0.7152 + c.b * 0.0722
			sum += l
			sum2 += l * l
			if l < 0.02:
				black += 1
	var mean := sum / float(n)
	var var_ := maxf(sum2 / float(n) - mean * mean, 0.0)
	return {"mean": mean, "std": sqrt(var_), "black": float(black) / float(n)}
