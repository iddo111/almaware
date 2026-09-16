## face_view.gd -- THE FACE: a readable skin over three numbers. Deliberately simple,
## not photoreal, not a person. Its job is to make the glass throat legible.
##   lips   <- lip_open01 = sqrt(A[22]/3.813)      (REAL: the lip section area)
##   tongue <- constriction position + tightness  (REAL: argmin(A), min(A))
##   nose   <- velum > 0.05                        (REAL: the nasal port switch)
##   throat <- voicing                             (REAL)
##   jaw    <- jaw_open01_derived                  (DERIVED from the front-cavity mean -- not in the data)
extends Node3D

const LIP_GAP_M := 0.03        # cosmetic: 30 mm at full open (brief said 22 mm; scaled for legibility at 1.2 m)
const MOUTH_Y := -0.05
const MOUTH_Z := 0.115

var art: Articulation
var head: MeshInstance3D
var upper_lip: MeshInstance3D
var lower_lip: MeshInstance3D
var lip_mat := StandardMaterial3D.new()
var jaw: MeshInstance3D
var tongue: MeshInstance3D
var tongue_mat := StandardMaterial3D.new()
var nose: MeshInstance3D
var nose_mat := StandardMaterial3D.new()
var nose_label: Label3D
var throat: MeshInstance3D
var throat_mat := StandardMaterial3D.new()
var puff: GPUParticles3D
var jaw_label: Label3D


func setup(a: Articulation) -> void:
	art = a
	var skin := StandardMaterial3D.new()
	skin.albedo_color = Color(0.55, 0.58, 0.66, 0.55)   # translucent so the tongue and jaw inside are visible
	skin.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	skin.roughness = 0.6

	head = MeshInstance3D.new()
	head.name = "Head"
	var cap := CapsuleMesh.new()
	cap.radius = 0.13
	cap.height = 0.36
	head.mesh = cap
	head.material_override = skin
	add_child(head)

	lip_mat.albedo_color = Color(0.85, 0.35, 0.45)
	lip_mat.roughness = 0.4
	upper_lip = _box("UpperLip", Vector3(0.10, 0.016, 0.03), lip_mat)
	lower_lip = _box("LowerLip", Vector3(0.10, 0.016, 0.03), lip_mat)

	var jaw_mat := StandardMaterial3D.new()
	jaw_mat.albedo_color = Color(0.48, 0.5, 0.58)
	jaw = _box("Jaw", Vector3(0.17, 0.07, 0.13), jaw_mat)
	jaw.position = Vector3(0, -0.15, 0.03)

	tongue = MeshInstance3D.new()
	tongue.name = "Tongue"
	var tm := SphereMesh.new()
	tm.radius = 0.032
	tm.height = 0.05
	tongue.mesh = tm
	tongue_mat.albedo_color = Color(0.9, 0.45, 0.5)
	tongue_mat.emission_enabled = true
	tongue_mat.emission = Color(1.0, 0.6, 0.3)
	tongue_mat.emission_energy_multiplier = 0.0
	tongue.material_override = tongue_mat
	tongue.position = Vector3(0, MOUTH_Y - 0.02, 0.06)
	add_child(tongue)

	nose = MeshInstance3D.new()
	nose.name = "Nose"
	var nm := SphereMesh.new()
	nm.radius = 0.028
	nm.height = 0.05
	nose.mesh = nm
	nose_mat.albedo_color = Color(0.6, 0.6, 0.68)
	nose_mat.emission_enabled = true
	nose_mat.emission = Color(1.0, 0.6, 0.2)
	nose_mat.emission_energy_multiplier = 0.0
	nose.material_override = nose_mat
	nose.position = Vector3(0, 0.02, 0.125)
	add_child(nose)
	nose_label = _label("", Vector3(0.09, 0.05, 0.13), Color(1.0, 0.7, 0.3))

	throat = MeshInstance3D.new()
	throat.name = "Throat"
	var thm := CylinderMesh.new()
	thm.top_radius = 0.05
	thm.bottom_radius = 0.06
	thm.height = 0.12
	throat.mesh = thm
	throat_mat.albedo_color = Color(0.5, 0.52, 0.6)
	throat_mat.emission_enabled = true
	throat_mat.emission = Color(1.0, 0.25, 0.5)
	throat_mat.emission_energy_multiplier = 0.0
	throat.material_override = throat_mat
	throat.position = Vector3(0, -0.27, -0.01)
	add_child(throat)

	# burst puff at the lips (one-shot, fired at t_release iff the gesture has a burst block)
	puff = GPUParticles3D.new()
	puff.name = "BurstPuff"
	puff.one_shot = true
	puff.emitting = false
	puff.amount = 48
	puff.lifetime = 0.45
	puff.explosiveness = 1.0
	var pm := ParticleProcessMaterial.new()
	pm.direction = Vector3(0, 0, 1)
	pm.spread = 28.0
	pm.initial_velocity_min = 0.5
	pm.initial_velocity_max = 1.1
	pm.gravity = Vector3(0, 0.1, 0)
	pm.scale_min = 0.6
	pm.scale_max = 1.4
	pm.damping_min = 1.5
	pm.damping_max = 2.5
	puff.process_material = pm
	var pmesh := SphereMesh.new()
	pmesh.radius = 0.009
	pmesh.height = 0.018
	var pmat := StandardMaterial3D.new()
	pmat.albedo_color = Color(1, 1, 1, 0.8)
	pmat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	pmat.emission_enabled = true
	pmat.emission = Color(0.9, 0.95, 1.0)
	pmat.emission_energy_multiplier = 2.0
	pmesh.material = pmat
	puff.draw_pass_1 = pmesh
	puff.position = Vector3(0, MOUTH_Y, MOUTH_Z + 0.02)
	add_child(puff)

	jaw_label = _label("jaw: DERIVED (not in the data)", Vector3(0.11, -0.17, 0.05), Color(0.75, 0.75, 0.8), 15)
	var cap_label := _label("stylized face -- a skin over the numbers\n(not a person, not ERAN's face)",
		Vector3(0.0, 0.30, 0.0), Color(0.8, 0.85, 0.9), 15)
	cap_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER

	var v := art.syllable("a")
	if not v.is_empty():
		apply_frame(v["frames"][v["frames"].size() - 1], v)


func _box(n: String, size: Vector3, mat: Material) -> MeshInstance3D:
	var m := MeshInstance3D.new()
	m.name = n
	var b := BoxMesh.new()
	b.size = size
	m.mesh = b
	m.material_override = mat
	add_child(m)
	return m


func _label(text: String, pos: Vector3, col: Color, size: int = 16) -> Label3D:
	var l := Label3D.new()
	l.text = text
	l.position = pos
	l.font_size = size
	l.pixel_size = 0.0018
	l.modulate = col
	l.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	l.no_depth_test = true
	add_child(l)
	return l


func apply_frame(f: Dictionary, syl: Dictionary) -> void:
	# lips (REAL)
	var lo := art.lip_open01(f)
	var gap := lo * LIP_GAP_M
	upper_lip.position = Vector3(0, MOUTH_Y + 0.008 + gap * 0.5, MOUTH_Z)
	lower_lip.position = Vector3(0, MOUTH_Y - 0.008 - gap * 0.5, MOUTH_Z)
	var lip_sealed := float(f.get("lip_area", 1.0)) < art.seal_cm2
	lip_mat.albedo_color = Color(1.0, 0.2, 0.25) if lip_sealed else Color(0.85, 0.35, 0.45)

	# jaw (DERIVED -- says so on the label)
	var jo := float(f.get("jaw_open01_derived", 0.0))
	jaw.position = Vector3(0, -0.15 - jo * 0.05, 0.03 + jo * 0.01)
	jaw.rotation = Vector3(deg_to_rad(jo * 14.0), 0, 0)
	lower_lip.position.y -= jo * 0.02
	jaw_label.text = "jaw %.2f: DERIVED (not in the data)" % jo

	# tongue (REAL: where the tract is narrowest, unless the narrowing is at the lips)
	var mi := int(f.get("min_section", 0))
	var cm := float(f.get("constriction_cm_from_lips", 8.0))
	var tight := art.tightness01(f)
	var at_lips := mi >= art.n_sections - 2
	var u := clampf(cm / art.ladder_cm, 0.0, 1.0)     # 0 = at the lips, 1 = at the glottis
	if at_lips:
		tongue.position = Vector3(0, MOUTH_Y - 0.03, 0.03)
		tongue_mat.emission_energy_multiplier = 0.0
	else:
		tongue.position = Vector3(0, MOUTH_Y - 0.03 + 0.03 * tight, 0.09 - 0.13 * u)
		tongue_mat.emission_energy_multiplier = 1.5 * tight

	# nose (REAL: the nasal port switch)
	var nopen := art.nasal_open(f)
	nose_mat.emission_energy_multiplier = 2.5 if nopen else 0.0
	nose_label.text = "NOSE OPEN\nvelum %.2f" % float(f.get("velum", 0.0)) if nopen else ""

	# throat glow (REAL: voicing)
	var voi := float(f.get("voicing", 0.0))
	throat_mat.emission_energy_multiplier = 2.5 * voi


func burst() -> void:
	puff.restart()
	puff.emitting = true
