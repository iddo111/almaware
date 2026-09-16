# shot.gd -- the city photographs ITSELF.
#
# Written 2026-08-29 after a desktop screen-grab meant to show the game caught the
# rest of Iddo's screen with it. The engine already holds the only pixels anyone
# needs; taking them from the OS was both worse-quality and a privacy leak. This
# reads the viewport directly, writes one PNG, and quits.
#
# Attach to a scene root, or run:
#   Godot --path <project> --script res://scripts/shot.gd  (not used; scene-attached)
extends Node

@export var out_path := "user://shot.png"
@export var settle_frames := 12

var _n := 0


func _ready() -> void:
	# A camera needs a few frames before shadows, sky and fog have resolved.
	set_process(true)


func _process(_delta: float) -> void:
	_n += 1
	if _n < settle_frames:
		return
	set_process(false)
	var img := get_viewport().get_texture().get_image()
	var path: String = out_path
	var err := img.save_png(path)
	if err != OK:
		push_error("shot.gd: save_png(%s) failed: %d" % [path, err])
	else:
		print("[shot] wrote %s (%dx%d)" % [ProjectSettings.globalize_path(path),
				img.get_width(), img.get_height()])
	get_tree().quit()
