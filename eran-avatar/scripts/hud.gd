## hud.gd -- the per-frame readout. A SubViewport rendered onto a quad in the scene (works in VR),
## plus a 2D overlay copy on desktop. Every line names a measured number; jaw is marked DERIVED.
extends Node3D

const VP_W := 1100
const VP_H := 400
const QUAD_W := 1.05

var viewport: SubViewport
var label: Label
var quad: MeshInstance3D
var overlay: Label = null


func setup(desktop_overlay: bool) -> void:
	viewport = SubViewport.new()
	viewport.name = "HudViewport"
	viewport.size = Vector2i(VP_W, VP_H)
	viewport.disable_3d = true
	viewport.transparent_bg = true
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	add_child(viewport)

	var bg := ColorRect.new()
	bg.color = Color(0.03, 0.04, 0.08, 0.82)
	bg.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	viewport.add_child(bg)

	label = Label.new()
	label.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	label.offset_left = 18
	label.offset_top = 10
	label.add_theme_font_size_override("font_size", 25)
	label.add_theme_color_override("font_color", Color(0.9, 0.95, 1.0))
	viewport.add_child(label)

	quad = MeshInstance3D.new()
	quad.name = "HudQuad"
	var qm := QuadMesh.new()
	qm.size = Vector2(QUAD_W, QUAD_W * float(VP_H) / float(VP_W))
	quad.mesh = qm
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.albedo_texture = viewport.get_texture()
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	quad.material_override = mat
	add_child(quad)

	if desktop_overlay:
		var layer := CanvasLayer.new()
		layer.name = "DesktopOverlay"
		add_child(layer)
		var panel := PanelContainer.new()
		var sb := StyleBoxFlat.new()
		sb.bg_color = Color(0.03, 0.04, 0.08, 0.80)
		sb.border_color = Color(0.3, 0.5, 0.8, 0.6)
		sb.set_border_width_all(1)
		sb.set_corner_radius_all(6)
		sb.set_content_margin_all(10)
		panel.add_theme_stylebox_override("panel", sb)
		panel.set_anchors_preset(Control.PRESET_BOTTOM_LEFT)
		panel.grow_vertical = Control.GROW_DIRECTION_BEGIN
		panel.offset_left = 12
		panel.offset_bottom = -12
		layer.add_child(panel)
		overlay = Label.new()
		overlay.add_theme_font_size_override("font_size", 15)
		overlay.add_theme_color_override("font_color", Color(0.92, 0.96, 1.0))
		panel.add_child(overlay)
		quad.visible = false          # on desktop the overlay is the HUD; the quad is for the headset


func set_text(t: String) -> void:
	label.text = t
	if overlay:
		overlay.text = t
