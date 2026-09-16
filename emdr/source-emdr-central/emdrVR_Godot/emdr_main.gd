## emdr_main.gd
## Root controller for the EMDR VR session.
## Manages: session state, speed/range controls, haptic dispatch,
##           bilateral audio routing, and the floating UI panel.
##
## HTC Vive (original) uses OpenVR via SteamVR.
## Godot 4 XR: XRServer + OpenXR plugin (or OpenVR plugin).
## Haptics: XRController3D.trigger_haptic_pulse()

extends Node3D

# ── Session parameters (tweakable from UI) ───────────────────────────────────
@export var default_speed     : float = 1.0   # sweeps per second
@export var default_range     : float = 1.5   # metres either side of centre
@export var default_distance  : float = 2.0   # metres in front of user
@export var default_height    : float = 1.7   # metres (eye level)
@export var haptic_duration   : float = 0.08  # seconds per pulse
@export var haptic_amplitude  : float = 0.7   # 0.0 – 1.0
@export var haptic_frequency  : float = 120.0 # Hz (Vive supports up to ~320 Hz)

# ── Node refs ────────────────────────────────────────────────────────────────
@onready var xr_origin       : XROrigin3D      = $XROrigin3D
@onready var xr_camera       : XRCamera3D      = $XROrigin3D/XRCamera3D
@onready var left_ctrl       : XRController3D  = $XROrigin3D/LeftController
@onready var right_ctrl      : XRController3D  = $XROrigin3D/RightController
@onready var emdr_orb        : Node3D          = $EMDROrb
@onready var audio_left      : AudioStreamPlayer3D = $AudioLeft
@onready var audio_right     : AudioStreamPlayer3D = $AudioRight
@onready var ui_anchor       : Node3D          = $UIAnchor

# ── Session state ────────────────────────────────────────────────────────────
enum SessionState { IDLE, RUNNING, PAUSED }
var state          : SessionState = SessionState.IDLE
var session_time   : float = 0.0
var sweep_count    : int   = 0

# ── XR interface ─────────────────────────────────────────────────────────────
var xr_interface   : XRInterface

# ── Signals (consumed by UI script) ─────────────────────────────────────────
signal session_started
signal session_paused
signal session_resumed
signal session_stopped
signal sweep_completed(count: int)
signal orb_side_changed(side: String)   # "left" or "right"

func _ready() -> void:
	_init_xr()
	_init_audio()
	_connect_orb_signals()
	_position_ui()
	print("[EMDR] Ready. State: IDLE")

# ── XR initialisation ────────────────────────────────────────────────────────
func _init_xr() -> void:
	# Try OpenXR first (Godot 4 preferred path, also works with SteamVR runtime)
	xr_interface = XRServer.find_interface("OpenXR")
	if xr_interface == null:
		# Fallback: OpenVR plugin (legacy, direct SteamVR)
		xr_interface = XRServer.find_interface("OpenVR")
	
	if xr_interface and xr_interface.initialize():
		get_viewport().use_xr = true
		DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
		print("[EMDR] XR interface active: ", xr_interface.get_name())
	else:
		push_warning("[EMDR] No XR interface found — running in desktop preview mode")

# ── Audio initialisation ─────────────────────────────────────────────────────
func _init_audio() -> void:
	# Generate a soft sine-tone tick at runtime (no asset file needed)
	# Replace with AudioStreamOggVorbis.load_from_file() for custom sounds
	var left_stream  = _make_tick_stream(440.0)   # A4 — left side
	var right_stream = _make_tick_stream(528.0)   # C5 — right side (slightly higher)
	audio_left.stream  = left_stream
	audio_right.stream = right_stream
	audio_left.volume_db  = -6.0
	audio_right.volume_db = -6.0

## Procedurally generates a short sine-wave "tick" AudioStreamWAV.
## duration_ms: length of the tone in milliseconds
## frequency: pitch in Hz
func _make_tick_stream(frequency: float, duration_ms: float = 80.0) -> AudioStreamWAV:
	var sample_rate : int   = 44100
	var num_samples : int   = int(sample_rate * duration_ms / 1000.0)
	var data        : PackedByteArray = PackedByteArray()
	data.resize(num_samples * 2)  # 16-bit mono
	
	for i in range(num_samples):
		var t       : float = float(i) / sample_rate
		# Envelope: quick attack (5ms), hold, quick release (10ms)
		var attack  : float = min(t / 0.005, 1.0)
		var release : float = max(1.0 - (t - (duration_ms/1000.0 - 0.010)) / 0.010, 0.0)
		var env     : float = attack * min(release, 1.0)
		var sample  : float = sin(TAU * frequency * t) * env * 0.7
		var s16     : int   = clamp(int(sample * 32767.0), -32768, 32767)
		data[i * 2]     = s16 & 0xFF
		data[i * 2 + 1] = (s16 >> 8) & 0xFF
	
	var wav = AudioStreamWAV.new()
	wav.format      = AudioStreamWAV.FORMAT_16_BITS
	wav.stereo      = false
	wav.mix_rate    = sample_rate
	wav.data        = data
	wav.loop_mode   = AudioStreamWAV.LOOP_DISABLED
	return wav

# ── Orb signal connections ────────────────────────────────────────────────────
func _connect_orb_signals() -> void:
	emdr_orb.reached_left.connect(_on_orb_reached_left)
	emdr_orb.reached_right.connect(_on_orb_reached_right)
	emdr_orb.sweep_done.connect(_on_sweep_done)

# ── UI positioning ────────────────────────────────────────────────────────────
func _position_ui() -> void:
	# Float panel slightly below eye level, in front of user
	ui_anchor.position = Vector3(0, 1.3, -1.3)

# ── Per-frame ────────────────────────────────────────────────────────────────
func _process(delta: float) -> void:
	if state == SessionState.RUNNING:
		session_time += delta
		_update_orb_target()
	
	# Keep UI panel facing the camera (billboard)
	if xr_camera:
		var cam_pos = xr_camera.global_position
		var ui_pos  = ui_anchor.global_position
		var look_dir = (cam_pos - ui_pos).normalized()
		if look_dir.length_squared() > 0.001:
			ui_anchor.look_at(cam_pos, Vector3.UP)
			ui_anchor.rotate_y(PI)

# ── Orb target positioning ────────────────────────────────────────────────────
func _update_orb_target() -> void:
	if not emdr_orb: return
	# Orb script handles its own lerp; we just feed it the parameters
	emdr_orb.speed    = emdr_orb.speed     # driven by UI via set_speed()
	emdr_orb.h_range  = emdr_orb.h_range   # driven by UI via set_range()

# ── Bilateral callbacks ───────────────────────────────────────────────────────
func _on_orb_reached_left() -> void:
	_play_bilateral_audio("left")
	_trigger_haptic(left_ctrl)
	emit_signal("orb_side_changed", "left")

func _on_orb_reached_right() -> void:
	_play_bilateral_audio("right")
	_trigger_haptic(right_ctrl)
	emit_signal("orb_side_changed", "right")

func _on_sweep_done() -> void:
	sweep_count += 1
	emit_signal("sweep_completed", sweep_count)

# ── Audio ─────────────────────────────────────────────────────────────────────
func _play_bilateral_audio(side: String) -> void:
	match side:
		"left":
			audio_left.stop()
			audio_left.play()
		"right":
			audio_right.stop()
			audio_right.play()

## Load a custom audio file (ogg/wav) for bilateral tones.
## Call from UI script when user selects a custom sound.
func load_custom_audio(left_path: String, right_path: String) -> void:
	var l = load(left_path)
	var r = load(right_path)
	if l: audio_left.stream  = l
	if r: audio_right.stream = r

# ── Haptic dispatch ───────────────────────────────────────────────────────────
## Sends a haptic pulse to the specified controller.
## XRController3D.trigger_haptic_pulse(action, frequency, amplitude, duration, delay)
func _trigger_haptic(controller: XRController3D) -> void:
	if controller == null: return
	if not controller.get_is_active(): return
	controller.trigger_haptic_pulse(
		"haptic",          # action name (defined in OpenXR action map)
		haptic_frequency,
		haptic_amplitude,
		haptic_duration,
		0.0                # no delay
	)

# ── Public API (called by UI script) ─────────────────────────────────────────
func start_session() -> void:
	if state == SessionState.RUNNING: return
	state        = SessionState.RUNNING
	session_time = 0.0
	sweep_count  = 0
	emdr_orb.start()
	emit_signal("session_started")
	print("[EMDR] Session started")

func pause_session() -> void:
	if state != SessionState.RUNNING: return
	state = SessionState.PAUSED
	emdr_orb.pause()
	emit_signal("session_paused")

func resume_session() -> void:
	if state != SessionState.PAUSED: return
	state = SessionState.RUNNING
	emdr_orb.resume()
	emit_signal("session_resumed")

func stop_session() -> void:
	state       = SessionState.IDLE
	session_time = 0.0
	sweep_count  = 0
	emdr_orb.stop()
	emit_signal("session_stopped")
	print("[EMDR] Session stopped. Sweeps: ", sweep_count)

func set_speed(sweeps_per_second: float) -> void:
	emdr_orb.speed = clamp(sweeps_per_second, 0.2, 4.0)

func set_range(metres: float) -> void:
	emdr_orb.h_range = clamp(metres, 0.3, 3.0)

func set_distance(metres: float) -> void:
	emdr_orb.target_distance = clamp(metres, 1.0, 4.0)

func set_haptic_amplitude(value: float) -> void:
	haptic_amplitude = clamp(value, 0.0, 1.0)

func set_haptic_frequency(hz: float) -> void:
	haptic_frequency = clamp(hz, 10.0, 320.0)

func set_audio_volume(db: float) -> void:
	audio_left.volume_db  = db
	audio_right.volume_db = db

func get_session_time() -> float:
	return session_time

func get_sweep_count() -> int:
	return sweep_count
