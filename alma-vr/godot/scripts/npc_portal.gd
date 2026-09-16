# npc_portal.gd — a shimmering gate whose voice is the REAL DGX fleet.
# E near the portal → the informant answers through eran1:8010.
# The same contract bridge/npc.py proved from python (2026-08-18 13:44).
extends Node3D

const ROUTER := "http://<lan-ip>:8010/v1/chat/completions"
const SYSTEM := """You are שמוליק, a nervous informant hiding INSIDE the neural
network in the game ALMA-VR (he dove in too deep and lives here now, between
the neurons). Hebrew with bits of English, 2-3 sentences, in character,
never break the fourth wall. You know: tonight's target is a bank fraud-model
and something that is NOT the bank's lives inside it. You want fresh rambutan
as payment."""

var _http: HTTPRequest
var _label: Label3D
var _busy := false

func _ready() -> void:
	add_to_group("npc_portal")
	var ring := MeshInstance3D.new()
	var torus := TorusMesh.new()
	torus.inner_radius = 1.7
	torus.outer_radius = 2.2
	ring.mesh = torus
	var m := StandardMaterial3D.new()
	m.emission_enabled = true
	m.emission = Color(1.0, 0.55, 0.1)
	m.emission_energy_multiplier = 2.5
	ring.material_override = m
	ring.rotation.x = PI / 2
	add_child(ring)

	_label = Label3D.new()
	_label.text = "שמוליק\n[E] לדבר"
	_label.font_size = 220
	_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	_label.position.y = 3.4
	add_child(_label)

	_http = HTTPRequest.new()
	_http.timeout = 60.0
	add_child(_http)
	_http.request_completed.connect(_on_reply)

func converse() -> void:
	if _busy:
		return
	_busy = true
	_label.text = "…"
	var body := JSON.stringify({
		"model": "qwen3-coder-next-fp8",
		"messages": [
			{"role": "system", "content": SYSTEM},
			{"role": "user", "content": "שמוליק, אין זמן. מה מחכה לי בפנים הלילה?"},
		],
		"max_tokens": 200,
		"temperature": 0.9,
	})
	_http.request(ROUTER, ["Content-Type: application/json"],
				  HTTPClient.METHOD_POST, body)

func _on_reply(_result: int, code: int, _headers: PackedStringArray,
			   body: PackedByteArray) -> void:
	_busy = false
	if code != 200:
		_label.text = "הרשת רועשת… נסה שוב\n[E]"
		return
	var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
	var text: String = ""
	if parsed is Dictionary and parsed.has("choices"):
		text = str(parsed["choices"][0]["message"]["content"]).strip_edges()
	_label.text = text if text != "" else "…שקט מוזר.\n[E]"
