## main.gd -- ERAN articulatory avatar, first demo.
## Plays a mouth-school syllable at real speed with its wav (frame index driven by the audio
## playback position, so audio and geometry cannot drift), then replays it at 0.2x, silent,
## looping. `B` alternates ba <-> ma: identical at the lips, only the soft palate differs.
##
## Keys: 1=ba 2=ma 3=sha  Space=replay  B=A/B ba<->ma  Esc=quit
## VR:   right trigger = next syllable, right grip = replay
## `-- --capture` : deterministic evidence run (muted): saves PNGs + a playback log to build/evidence, then quits.
extends Node3D

const ART_PATH := "res://data/articulation.json"
const DEMO := ["ba", "ma", "sha"]
const SLOW_RATE := 0.2
const EVIDENCE_DIR := "res://build/evidence/"

enum Mode { IDLE, REAL, SLOW }

@onready var xr_camera: XRCamera3D = $XROrigin3D/XRCamera3D
@onready var right_ctrl: XRController3D = $XROrigin3D/RightController
@onready var tract: Node3D = $Tract
@onready var face: Node3D = $Face
@onready var hud: Node3D = $HUD
@onready var player: AudioStreamPlayer3D = $Player

var art: Articulation
var xr: XRInterface
var xr_active := false
var syl: Dictionary = {}
var syl_name := ""
var mode: int = Mode.IDLE
var mode_label := "idle"
var slow_t := 0.0
var ab_mode := false
var ab_queue: Array = []
var burst_fired := false
var cur_frame := -1
var cur_t := 0.0
var demo_idx := 0
var capture := false
var wall_started := 0.0
var _streams: Dictionary = {}
var _logf: FileAccess = null


func _log(msg: String) -> void:
	print(msg)
	if _logf == null:
		DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path("res://build/"))
		_logf = FileAccess.open(ProjectSettings.globalize_path("res://build/run.log"), FileAccess.WRITE)
	if _logf:
		_logf.store_line("%s  %s" % [Time.get_time_string_from_system(), msg])
		_logf.flush()


func _ready() -> void:
	capture = "--capture" in OS.get_cmdline_user_args()
	_log("[ERAN-AVATAR] _ready  user_args=%s  capture=%s" % [str(OS.get_cmdline_user_args()), str(capture)])
	if capture:
		var wd := get_tree().create_timer(60.0)
		wd.timeout.connect(func(): _log("[ERAN-AVATAR] WATCHDOG quit"); get_tree().quit())
	if not capture:
		_init_xr()
	if not xr_active:
		xr_camera.current = true
		xr_camera.rotation.x = deg_to_rad(-6.0)

	art = Articulation.load_from(ART_PATH)
	if not art.ok:
		push_error("[ERAN-AVATAR] no articulation data -- nothing to show")
		return
	_log("[ERAN-AVATAR] articulation: tract=%s fps=%d syllables=%d written_by=%s" % [
		str(art.meta.get("tract", {})), int(art.fps), art.syllables.size(), str(art.meta.get("written_by", "?"))])
	tract.setup(art)
	_log("[ERAN-AVATAR] tract ok")
	face.setup(art)
	_log("[ERAN-AVATAR] face ok")
	hud.setup(not xr_active)
	_log("[ERAN-AVATAR] hud ok")
	if right_ctrl:
		right_ctrl.button_pressed.connect(_on_vr_button)

	if capture:
		_run_capture()
	else:
		play("ba")


# -- XR (verbatim pattern from emdr-vive/scripts/emdr_main.gd:67-76, known-good) --------------
func _init_xr() -> void:
	xr = XRServer.find_interface("OpenXR")
	if xr and xr.initialize():
		get_viewport().use_xr = true
		DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
		xr_active = true
		_log("[ERAN-AVATAR] XR active: " + xr.get_name())
	else:
		_log("[ERAN-AVATAR] No XR runtime -- desktop preview mode")


# -- playback ---------------------------------------------------------------------------------
func _select(name: String) -> bool:
	if not art.has(name):
		push_warning("[ERAN-AVATAR] unknown syllable " + name)
		return false
	syl_name = name
	syl = art.syllable(name)
	burst_fired = false
	cur_frame = -1
	return true


func _stream_for(name: String) -> AudioStream:
	if not _streams.has(name):
		_streams[name] = load(String(syl.get("wav", "res://audio/ERAN-%s.wav" % name)))
	return _streams[name]


## Real speed with audio; the frame index follows the audio playback position.
func play(name: String) -> void:
	if not _select(name):
		return
	player.stop()
	player.stream = _stream_for(name)
	player.play()
	mode = Mode.REAL
	mode_label = "REAL 1.0x + audio"
	wall_started = Time.get_ticks_msec() / 1000.0
	_log("[ERAN-AVATAR] play %s (%s)  dur %.3f s  frames %d  wav %s" % [
		name, str(syl.get("hebrew", "")), float(syl.get("duration_s", 0)), int(syl.get("n_frames", 0)), str(syl.get("wav", ""))])


func _start_slow() -> void:
	mode = Mode.SLOW
	mode_label = "SLOW 0.2x silent loop"
	slow_t = 0.0
	burst_fired = false


func _process(dt: float) -> void:
	if mode == Mode.IDLE or syl.is_empty():
		return
	var dur := float(syl.get("duration_s", 0.5))
	if mode == Mode.REAL:
		if player.playing:
			cur_t = player.get_playback_position() + AudioServer.get_time_since_last_mix()
		else:
			cur_t = dur
			if not ab_queue.is_empty():
				play(ab_queue.pop_front())
				return
			_start_slow()
	else:
		slow_t += dt * SLOW_RATE
		if slow_t >= dur:
			slow_t = 0.0
			burst_fired = false
			if ab_mode:
				_select("ma" if syl_name == "ba" else "ba")
		cur_t = slow_t
	var i := art.frame_index(syl, cur_t)
	_apply(i, cur_t)
	_maybe_burst(cur_t)


func _apply(i: int, t: float) -> void:
	cur_frame = i
	cur_t = t
	var f: Dictionary = syl["frames"][i]
	tract.apply_frame(f)
	face.apply_frame(f, syl)
	hud.set_text(_hud_text(f, i, t))


func _maybe_burst(t: float) -> void:
	if burst_fired or syl.get("burst_gain") == null or syl.get("t_release_s") == null:
		return
	if t >= float(syl["t_release_s"]):
		burst_fired = true
		face.burst()


func _hud_text(f: Dictionary, i: int, t: float) -> String:
	var lip_a := float(f.get("lip_area", 0))
	var min_a := float(f.get("min_area", 0))
	var nopen := art.nasal_open(f)
	var burst_s := "none (no pressure builds)"
	if syl.get("burst_gain") != null:
		burst_s = "gain %.1f at release t=%.3f s" % [float(syl["burst_gain"]), float(syl.get("t_release_s", 0))]
	elif syl.get("t_release_s") != null:
		burst_s = "none; release t=%.3f s" % float(syl["t_release_s"])
	return "\n".join([
		"ERAN articulatory avatar -- first demo   [%s]" % mode_label,
		"syllable  %s  %s   frame %d/%d   t = %.3f / %.3f s   (verified: %s)" % [
			syl_name, str(syl.get("hebrew", "")), i + 1, int(syl.get("n_frames", 0)), t,
			float(syl.get("duration_s", 0)), "yes" if syl.get("verified", false) else "NO"],
		"lips      A[22] = %.4f cm2  %s   lip_open01 = %.2f" % [
			lip_a, "SEALED" if lip_a < art.seal_cm2 else "open", art.lip_open01(f)],
		"constric. section %d  %.1f cm from lips  %.4f cm2  tightness %.2f" % [
			int(f.get("min_section", 0)), float(f.get("constriction_cm_from_lips", 0)), min_a, art.tightness01(f)],
		"velum     %.2f cm2  %s        voicing %.2f   tenseness %.2f" % [
			float(f.get("velum", 0)), "OPEN -> air out the NOSE" if nopen else "SHUT", float(f.get("voicing", 0)), float(f.get("tenseness", 0))],
		"burst     %s" % burst_s,
		"jaw       %.2f  -- DERIVED from front-cavity mean A[17..22]; NOT in the data" % float(f.get("jaw_open01_derived", 0)),
		"tract     %d sections x %.4f cm = %.3f cm ladder, adult 17.60 cm (AGE_MONTHS 300)" % [art.n_sections, art.section_cm, art.ladder_cm],
		"keys  1=ba  2=ma  3=sha   Space=replay   B=A/B ba<->ma %s   Esc=quit" % ("[ON]" if ab_mode else "[off]"),
	])


# -- input ------------------------------------------------------------------------------------
func _unhandled_input(ev: InputEvent) -> void:
	if capture or not (ev is InputEventKey) or not ev.pressed or ev.echo:
		return
	match ev.keycode:
		KEY_1: ab_mode = false; ab_queue.clear(); play("ba")
		KEY_2: ab_mode = false; ab_queue.clear(); play("ma")
		KEY_3: ab_mode = false; ab_queue.clear(); play("sha")
		KEY_SPACE:
			if syl_name != "":
				play(syl_name)
		KEY_B:
			ab_mode = not ab_mode
			if ab_mode:
				ab_queue = ["ma"]
				play("ba")
		KEY_ESCAPE: get_tree().quit()


func _on_vr_button(bname: String) -> void:
	if bname == "trigger_click":
		demo_idx = (demo_idx + 1) % DEMO.size()
		ab_mode = false
		play(DEMO[demo_idx])
	elif bname == "grip_click":
		if syl_name != "":
			play(syl_name)
	elif bname == "ax_button" or bname == "by_button":
		ab_mode = not ab_mode
		if ab_mode:
			ab_queue = ["ma"]
			play("ba")


# -- evidence run: deterministic frames -> PNG, then a live muted playback log ----------------
func _run_capture() -> void:
	AudioServer.set_bus_mute(0, true)     # Iddo's audio is sacred: the evidence run is silent
	var dir := ProjectSettings.globalize_path(EVIDENCE_DIR)
	var mk := DirAccess.make_dir_recursive_absolute(dir)
	_log("[EVIDENCE] dir %s mkdir=%s" % [dir, error_string(mk)])
	var lines: PackedStringArray = []
	lines.append("# ERAN avatar evidence -- generated by main.gd --capture, %s" % Time.get_datetime_string_from_system())
	lines.append("# each PNG is the rendered scene at the named frame of data/articulation.json; the numbers are what drove the mesh")
	await get_tree().process_frame
	await get_tree().process_frame
	for name in DEMO:
		_select(name)
		mode = Mode.IDLE
		mode_label = "CAPTURE (frame set directly)"
		var picks: Array = [0.0, 0.05, 0.10, 0.15, 0.20, 0.30]
		picks.append(float(syl["duration_s"]) - 0.001)
		for t in picks:
			var i := art.frame_index(syl, t)
			_apply(i, t)
			await RenderingServer.frame_post_draw
			await RenderingServer.frame_post_draw
			var img := get_viewport().get_texture().get_image()
			var fn := "%s_t%03dms_f%02d.png" % [name, int(round(t * 1000)), i]
			img.save_png(dir + fn)
			var f: Dictionary = syl["frames"][i]
			var line := "%-3s frame %2d t=%.3f  lipA=%.4f minA=%.4f sec=%2d cm_from_lips=%5.2f velum=%.2f voicing=%.2f jaw_derived=%.2f -> %s" % [
				name, i, t, float(f["lip_area"]), float(f["min_area"]), int(f["min_section"]),
				float(f["constriction_cm_from_lips"]), float(f["velum"]), float(f["voicing"]), float(f["jaw_open01_derived"]), fn]
			_log("[EVIDENCE] " + line)
			lines.append(line)
	# live run: play ba for real (muted) and log what the audio position drove, every process frame
	lines.append("# --- live playback of ba, frame index driven by AudioStreamPlayer3D.get_playback_position() ---")
	lines.append("# wall_s  audio_t  frame  lipA  minA  velum  voicing")
	play("ba")
	var t0 := Time.get_ticks_msec() / 1000.0
	while mode == Mode.REAL:
		await get_tree().process_frame
		if mode != Mode.REAL:
			break
		if cur_frame < 0:
			continue          # _process has not run yet this frame
		var f: Dictionary = syl["frames"][cur_frame]
		lines.append("%.3f  %.4f  %2d  %.4f  %.4f  %.2f  %.2f" % [
			Time.get_ticks_msec() / 1000.0 - t0, cur_t, cur_frame, float(f["lip_area"]), float(f["min_area"]), float(f["velum"]), float(f["voicing"])])
	lines.append("# playback ended after %.3f s wall (wav %.3f s); burst_fired=%s" % [
		Time.get_ticks_msec() / 1000.0 - t0, float(syl["wav_duration_s"]), str(burst_fired)])
	# also grab one frame of the slow loop mid-vowel for the record
	_start_slow()
	slow_t = 0.30
	await RenderingServer.frame_post_draw
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(dir + "ba_slowloop_t300ms.png")
	var fa := FileAccess.open(dir + "evidence_log.txt", FileAccess.WRITE)
	fa.store_string("\n".join(lines) + "\n")
	fa.close()
	_log("[EVIDENCE] wrote " + dir)
	await get_tree().process_frame
	get_tree().quit()
