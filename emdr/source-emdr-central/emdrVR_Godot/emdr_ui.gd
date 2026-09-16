## emdr_ui.gd
## Floating control panel rendered as a 3D quad + SubViewport.
## The panel shows session controls and allows parameter adjustment.
## Interaction: Vive controller laser pointer (XRController3D ray).
##
## This script drives the visual panel; the actual Godot Control nodes
## live inside the SubViewport child. Layout is built procedurally below.

extends Node3D

# ── Node refs ─────────────────────────────────────────────────────────────────
@onready var main_node    : Node3D    = get_parent()
@onready var viewport     : SubViewport   = $ControlPanel
@onready var panel_mesh   : MeshInstance3D = $PanelMesh

# ── UI Control refs (built in _ready) ─────────────────────────────────────────
var lbl_status    : Label
var lbl_time      : Label
var lbl_sweeps    : Label
var btn_start     : Button
var btn_pause     : Button
var btn_stop      : Button
var sld_speed     : HSlider
var sld_range     : HSlider
var sld_haptic    : HSlider
var sld_volume    : HSlider
var lbl_speed_val : Label
var lbl_range_val : Label
var lbl_haptic_val: Label
var lbl_volume_val: Label

# ── Session display ───────────────────────────────────────────────────────────
var _update_tick  : float = 0.0

func _ready() -> void:
	_build_panel_mesh()
	_build_ui_controls()
	_connect_main_signals()

# ── Build the physical 3D panel ───────────────────────────────────────────────
func _build_panel_mesh() -> void:
	var quad       = QuadMesh.new()
	quad.size      = Vector2(0.6, 0.4)   # 60cm × 40cm in VR
	panel_mesh.mesh = quad

	var mat        = StandardMaterial3D.new()
	mat.transparency            = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.albedo_color            = Color(0.05, 0.07, 0.14, 0.88)
	mat.emission_enabled        = true
	mat.emission                = Color(0.1, 0.2, 0.4)
	mat.emission_energy_multiplier = 0.3
	mat.flags_unshaded          = true

	# Use the SubViewport as the albedo texture
	var vp_tex                  = ViewportTexture.new()
	vp_tex.viewport_path        = viewport.get_path()
	mat.albedo_texture          = vp_tex
	mat.albedo_color            = Color.WHITE   # let texture show through
	panel_mesh.material_override = mat

# ── Build Control tree inside SubViewport ─────────────────────────────────────
func _build_ui_controls() -> void:
	var root = PanelContainer.new()
	root.size = Vector2(600, 400)
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)

	# Dark background theme
	var style       = StyleBoxFlat.new()
	style.bg_color  = Color(0.05, 0.07, 0.14, 0.0)  # transparent (panel_mesh handles bg)
	root.add_theme_stylebox_override("panel", style)

	var vbox        = VBoxContainer.new()
	vbox.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	vbox.add_theme_constant_override("separation", 8)
	root.add_child(vbox)

	# ── Header ──────────────────────────────────────────────────────────────
	var header      = Label.new()
	header.text     = "EMDR Bilateral Stimulation"
	header.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_style_label(header, 18, Color(0.5, 0.85, 1.0))
	vbox.add_child(header)

	_add_separator(vbox)

	# ── Status row ──────────────────────────────────────────────────────────
	var status_row  = HBoxContainer.new()
	vbox.add_child(status_row)

	lbl_status      = _make_label("● IDLE", Color(0.8, 0.8, 0.8), 14)
	lbl_time        = _make_label("00:00", Color(0.6, 0.9, 0.6), 14)
	lbl_sweeps      = _make_label("Sweeps: 0", Color(0.6, 0.8, 1.0), 14)
	status_row.add_child(lbl_status)
	status_row.add_child(_spacer())
	status_row.add_child(lbl_time)
	status_row.add_child(_spacer())
	status_row.add_child(lbl_sweeps)

	_add_separator(vbox)

	# ── Buttons ──────────────────────────────────────────────────────────────
	var btn_row = HBoxContainer.new()
	btn_row.alignment = BoxContainer.ALIGNMENT_CENTER
	btn_row.add_theme_constant_override("separation", 16)
	vbox.add_child(btn_row)

	btn_start = _make_button("▶  START",  Color(0.2, 0.8, 0.4))
	btn_pause = _make_button("⏸  PAUSE",  Color(0.9, 0.7, 0.2))
	btn_stop  = _make_button("⏹  STOP",   Color(0.9, 0.3, 0.3))
	btn_pause.disabled = true
	btn_stop.disabled  = true
	btn_row.add_child(btn_start)
	btn_row.add_child(btn_pause)
	btn_row.add_child(btn_stop)

	btn_start.pressed.connect(_on_start)
	btn_pause.pressed.connect(_on_pause)
	btn_stop.pressed.connect(_on_stop)

	_add_separator(vbox)

	# ── Sliders ──────────────────────────────────────────────────────────────
	_add_slider_row(vbox, "Speed",         "sweeps/s", 0.2, 4.0, 1.0,
		func(v): main_node.set_speed(v),     lbl_speed_val)
	_add_slider_row(vbox, "Range",         "m",        0.3, 3.0, 1.5,
		func(v): main_node.set_range(v),     lbl_range_val)
	_add_slider_row(vbox, "Haptic",        "%",        0.0, 1.0, 0.7,
		func(v): main_node.set_haptic_amplitude(v), lbl_haptic_val)
	_add_slider_row(vbox, "Audio volume",  "dB",      -24.0, 6.0, -6.0,
		func(v): main_node.set_audio_volume(v),      lbl_volume_val)

	viewport.add_child(root)

# ── Slider builder helper ─────────────────────────────────────────────────────
func _add_slider_row(parent: VBoxContainer, name_text: String, unit: String,
		min_val: float, max_val: float, default_val: float,
		callback: Callable, out_label: Label) -> void:
	var row = HBoxContainer.new()
	parent.add_child(row)

	var lbl_name = _make_label(name_text + ":", Color(0.75, 0.85, 1.0), 13)
	lbl_name.custom_minimum_size = Vector2(110, 0)
	row.add_child(lbl_name)

	var sld = HSlider.new()
	sld.min_value = min_val
	sld.max_value = max_val
	sld.value     = default_val
	sld.step      = (max_val - min_val) / 100.0
	sld.custom_minimum_size = Vector2(220, 0)
	sld.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(sld)

	var val_lbl   = _make_label("%.2f %s" % [default_val, unit], Color(0.9, 0.95, 1.0), 13)
	val_lbl.custom_minimum_size = Vector2(80, 0)
	row.add_child(val_lbl)
	out_label = val_lbl   # assign to the member but note GDScript doesn't support ref params

	sld.value_changed.connect(func(v: float) -> void:
		callback.call(v)
		val_lbl.text = "%.2f %s" % [v, unit]
	)

# ── Signal connections ────────────────────────────────────────────────────────
func _connect_main_signals() -> void:
	main_node.session_started.connect(_on_session_started)
	main_node.session_paused.connect(_on_session_paused)
	main_node.session_resumed.connect(_on_session_resumed)
	main_node.session_stopped.connect(_on_session_stopped)
	main_node.sweep_completed.connect(_on_sweep_completed)
	main_node.orb_side_changed.connect(_on_side_changed)

# ── Button handlers ───────────────────────────────────────────────────────────
func _on_start() -> void:
	main_node.start_session()

func _on_pause() -> void:
	if main_node.state == main_node.SessionState.RUNNING:
		main_node.pause_session()
	else:
		main_node.resume_session()

func _on_stop() -> void:
	main_node.stop_session()

# ── Main signal handlers ──────────────────────────────────────────────────────
func _on_session_started() -> void:
	lbl_status.text = "● RUNNING"
	lbl_status.add_theme_color_override("font_color", Color(0.2, 0.9, 0.4))
	btn_start.disabled = true
	btn_pause.disabled = false
	btn_stop.disabled  = false

func _on_session_paused() -> void:
	lbl_status.text = "⏸ PAUSED"
	lbl_status.add_theme_color_override("font_color", Color(0.9, 0.7, 0.2))
	btn_pause.text = "▶  RESUME"

func _on_session_resumed() -> void:
	lbl_status.text = "● RUNNING"
	lbl_status.add_theme_color_override("font_color", Color(0.2, 0.9, 0.4))
	btn_pause.text = "⏸  PAUSE"

func _on_session_stopped() -> void:
	lbl_status.text = "● IDLE"
	lbl_status.add_theme_color_override("font_color", Color(0.7, 0.7, 0.7))
	lbl_time.text   = "00:00"
	lbl_sweeps.text = "Sweeps: 0"
	btn_start.disabled = false
	btn_pause.disabled = true
	btn_stop.disabled  = true
	btn_pause.text = "⏸  PAUSE"

func _on_sweep_completed(count: int) -> void:
	if lbl_sweeps: lbl_sweeps.text = "Sweeps: %d" % count

func _on_side_changed(side: String) -> void:
	# Flash status colour briefly when orb arrives
	pass  # visual feedback is handled by orb's own glow pulse

# ── Per-frame: update session timer ──────────────────────────────────────────
func _process(delta: float) -> void:
	_update_tick += delta
	if _update_tick >= 0.5:
		_update_tick = 0.0
		if main_node and lbl_time:
			var t   = int(main_node.get_session_time())
			lbl_time.text = "%02d:%02d" % [t / 60, t % 60]

# ── UI style helpers ──────────────────────────────────────────────────────────
func _make_label(text: String, color: Color, size: int = 14) -> Label:
	var l = Label.new(); l.text = text
	_style_label(l, size, color); return l

func _style_label(l: Label, size: int, color: Color) -> void:
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", color)

func _make_button(text: String, color: Color) -> Button:
	var b         = Button.new()
	b.text        = text
	b.custom_minimum_size = Vector2(120, 40)
	b.add_theme_font_size_override("font_size", 14)
	b.add_theme_color_override("font_color", color)
	return b

func _add_separator(parent: VBoxContainer) -> void:
	var sep = HSeparator.new()
	sep.add_theme_color_override("color", Color(0.2, 0.35, 0.55, 0.6))
	parent.add_child(sep)

func _spacer() -> Control:
	var s = Control.new()
	s.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	return s
