extends Node3D
# ERAN PLAYS THE GAME -- the auto-tester.
#
# BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.
#
# Iddo, 2026-08-30: "ערן שחקן הוא המוח מאחורי המשחק והוא גם משחק גיימר - אוטו טסטר."
#
# Two roles, one creature. The MIND of the world is the weave the NPCs think in. The
# PLAYER is this: ERAN walks the city by himself, on no one's schedule, and writes down
# what broke. It is the same machine that is searching for his /ba/ right now -- try,
# be scored, try again -- with the ear swapped for a floor.
#
# It runs HEADLESS on purpose. Nobody has to sit and watch, and nothing appears on
# Iddo's screen. He can leave it walking for an hour and read the report after.
#
# What counts as a finding, and every one of these is objective, not an opinion:
#   FELL      the floor was not there                 y < FELL_Y
#   STUCK     he pushed and the world did not move    < STUCK_MOVE over STUCK_WINDOW
#   BURIED    he woke up inside geometry              a body overlaps him at spawn
#   SLOW      he crossed, but the frame time spiked   worst frame over the leg
#   REACHED   he got there                            distance to goal < ARRIVE
#
#   godot --headless --path . res://scenes/eran_tester.tscn -- --legs 24 --seconds 240

const SPEED := 4.2
const STEP := 0.25            # seconds of simulated push per decision
const FELL_Y := -5.0
const STUCK_MOVE := 0.35      # metres
const STUCK_WINDOW := 12      # decisions
const ARRIVE := 3.5

var _body: CharacterBody3D
var _rng := RandomNumberGenerator.new()
var _report := {"legs": [], "started": "", "engine": Engine.get_version_info()}
var _leg := {}
var _hist: Array[Vector3] = []
var _t0 := 0.0
var _legs_wanted := 12
var _seconds := 180.0
var _goal := Vector3.ZERO
var _worst_frame := 0.0


func _ready() -> void:
	_rng.seed = 1933
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--legs="):
			_legs_wanted = int(a.split("=")[1])
		elif a.begins_with("--seconds="):
			_seconds = float(a.split("=")[1])
	_body = get_node_or_null("../Player")
	if _body == null:
		push_error("[eran] no Player node -- nothing to walk with")
		get_tree().quit(2)
		return
	_report["started"] = Time.get_datetime_string_from_system()
	_t0 = _now()
	print("[eran] walking. %d legs, up to %.0f s" % [_legs_wanted, _seconds])
	# A physics query inside _ready() searches a space the server has not stepped yet,
	# so it always finds nothing. The BURIED detector reported clean from a spawn buried
	# inside a building and I nearly shipped a test that could not fail. One frame first.
	await get_tree().physics_frame
	await get_tree().physics_frame
	# the leg has to exist BEFORE the probe, or a BURIED finding is printed and then
	# dropped on the floor -- which it was: the control printed BURIED and the report
	# still said "0 findings"
	_new_leg()
	_check_buried()


func _city_half() -> float:
	var city := get_node_or_null("../City")
	if city and "blocks_x" in city:
		return float(city.blocks_x) * 44.0 / 2.0
	return 154.0


func _now() -> float:
	return Time.get_ticks_msec() / 1000.0


func _check_buried() -> void:
	# A spawn inside a wall is the single most common way a scene is quietly broken,
	# and a screenshot will never show it because the camera is inside the brick.
	var space := get_world_3d().direct_space_state
	var q := PhysicsShapeQueryParameters3D.new()
	var sh := SphereShape3D.new()
	sh.radius = 0.45
	q.shape = sh
	q.transform = Transform3D(Basis(), _body.global_position)
	q.collide_with_bodies = true
	q.exclude = [_body.get_rid()]
	var hits := space.intersect_shape(q, 8)
	# say the number out loud -- a detector that reports nothing and a detector that
	# is not running look identical from the outside, and that is how a test lies
	print("[eran] probe at (%.0f, %.0f, %.0f): %d bodies overlap"
			% [_body.global_position.x, _body.global_position.y,
					_body.global_position.z, hits.size()])
	var down := PhysicsRayQueryParameters3D.create(_body.global_position,
			_body.global_position + Vector3(0, -30, 0))
	down.exclude = [_body.get_rid()]
	var hit := space.intersect_ray(down)
	print("[eran] floor below: %s" % ("none" if hit.is_empty() else "y=%.2f" % hit["position"].y))
	if hits.size() > 0:
		_finding("BURIED", "spawn point is inside geometry", _body.global_position)


func _finding(kind: String, note: String, at: Vector3) -> void:
	var f := {"kind": kind, "note": note,
			"at": [snappedf(at.x, 0.1), snappedf(at.y, 0.1), snappedf(at.z, 0.1)],
			"t": snappedf(_now() - _t0, 0.1)}
	if _leg.has("findings"):
		_leg["findings"].append(f)
	print("[eran] %-8s %s  at (%.0f, %.0f, %.0f)" % [kind, note, at.x, at.y, at.z])


func _new_leg() -> void:
	if _leg.has("findings"):
		_leg["worst_frame_ms"] = snappedf(_worst_frame * 1000.0, 0.1)
		_report["legs"].append(_leg)
	if _report["legs"].size() >= _legs_wanted or (_now() - _t0) > _seconds:
		_finish()
		return
	# Somewhere else IN THE CITY. The first run of this walked to x=245 -- the grid is
	# 7 blocks of 44 m, so it ends at 154 -- and reported five clean legs because there
	# was nothing out there to collide with. A walker that leaves town always passes.
	var half := _city_half()
	_goal = Vector3(_rng.randf_range(-half, half), 0.0, _rng.randf_range(-half, half))
	var half2 := half + 20.0
	var out_x := absf(_body.global_position.x) > half2
	var out_z := absf(_body.global_position.z) > half2
	var off_map := out_x or out_z
	if _body.global_position.y < 0.5 or off_map:
		_body.global_position = Vector3(_rng.randf_range(-half, half), 2.0,
				_rng.randf_range(-half, half))
	_hist.clear()
	_worst_frame = 0.0
	_leg = {"n": _report["legs"].size() + 1,
			"from": [snappedf(_body.global_position.x, 0.1),
					snappedf(_body.global_position.z, 0.1)],
			"goal": [snappedf(_goal.x, 0.1), snappedf(_goal.z, 0.1)],
			"findings": []}


func _finish() -> void:
	var ok := 0
	var bad := 0
	for l in _report["legs"]:
		if l["findings"].is_empty():
			ok += 1
		else:
			bad += l["findings"].size()
	_report["clean_legs"] = ok
	_report["findings_total"] = bad
	var path := "user://eran-walk-report.json"
	var f := FileAccess.open(path, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify(_report, "\t"))
		f.close()
	print("[eran] done. %d legs, %d clean, %d findings -> %s"
			% [_report["legs"].size(), ok, bad, ProjectSettings.globalize_path(path)])
	get_tree().quit(0)


func _physics_process(delta: float) -> void:
	if _body == null or _leg.is_empty():
		return
	_worst_frame = max(_worst_frame, delta)

	var p := _body.global_position
	if p.y < FELL_Y:
		_finding("FELL", "left the world through the floor", p)
		_body.global_position = Vector3(p.x, 2.0, p.z)   # put him back and carry on
		_new_leg()
		return

	var to_goal := Vector3(_goal.x - p.x, 0, _goal.z - p.z)
	if to_goal.length() < ARRIVE:
		_leg["result"] = "REACHED"
		_new_leg()
		return

	# push toward the goal; the body does the colliding
	var dir := to_goal.normalized()
	_body.velocity.x = dir.x * SPEED
	_body.velocity.z = dir.z * SPEED
	_body.velocity.y -= 9.8 * delta
	_body.move_and_slide()

	_hist.append(p)
	if _hist.size() > STUCK_WINDOW:
		_hist.pop_front()
		var moved := (_hist[-1] - _hist[0]).length()
		if moved < STUCK_MOVE:
			_finding("STUCK", "pushed for %d frames and moved %.2f m"
					% [STUCK_WINDOW, moved], p)
			_leg["result"] = "STUCK"
			# step him aside so the walk continues and we find more than one wall
			_body.global_position = p + Vector3(_rng.randf_range(-4, 4), 0.5,
					_rng.randf_range(-4, 4))
			_new_leg()
