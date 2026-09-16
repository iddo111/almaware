extends Node
# The game photographs ITSELF. No screen capture, ever.
#
# BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY.
#
# 2026-08-30: I twice grabbed the whole desktop to show Iddo the city, and twice the
# capture contained his private windows -- once his WhatsApp. Screen-grabbing his machine
# to look at MY render is the wrong access entirely: the pixels I want are inside the
# viewport, and the viewport can hand them over directly.
#
# This waits for the frame to be drawn, saves the viewport texture, and quits. The window
# still flashes on screen, but nothing outside the game is ever read.
#
#   godot --path . --resolution 1920x1080 res://scenes/tel_aviv_shot.tscn -- --out=X.png

var _out := "user://shot.png"
var _wait := 40


func _ready() -> void:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--out="):
			_out = a.split("=", true, 1)[1]
		elif a.begins_with("--wait="):
			_wait = int(a.split("=")[1])


func _process(_d: float) -> void:
	_wait -= 1
	if _wait > 0:
		return
	await RenderingServer.frame_post_draw
	var img := get_viewport().get_texture().get_image()
	var err := img.save_png(_out)
	print("[shot] %s -> %s (%dx%d)"
			% ["saved" if err == OK else "FAILED", _out, img.get_width(), img.get_height()])
	get_tree().quit(0 if err == OK else 3)
