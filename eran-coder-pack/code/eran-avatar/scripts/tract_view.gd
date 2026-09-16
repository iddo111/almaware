## tract_view.gd -- THE GLASS THROAT. 100% real, zero invention.
## One ring per tract section, radius r_cm = sqrt(A[i]/pi). This IS the data.
## Straight vertical centreline: glottis at the bottom, lips at the top. (A bent centreline
## would be anatomy the 1-D data does not contain -- deliberately not done.)
extends Node3D

const SCALE := 0.05            # metres per cm -> 16.77 cm tract = 0.84 m object (lengths TRUE)
const RADIUS_GAIN := 1.6       # radii drawn x1.6 for legibility at arm's length -- stated on the label
const RING_VERTS := 24
const R_FLOOR_CM := 0.02       # visibility floor for a sealed section (data floor is 0.001 cm^2)

var art: Articulation
var tube: MeshInstance3D
var tube_mesh := ArrayMesh.new()
var tube_mat := StandardMaterial3D.new()
var nasal: MeshInstance3D
var nasal_mat := StandardMaterial3D.new()
var nasal_label: Label3D
var ring: MeshInstance3D
var ring_mat := StandardMaterial3D.new()
var glottis: MeshInstance3D
var glottis_mat := StandardMaterial3D.new()
var glottis_light: OmniLight3D
var lip_label: Label3D
var con_label: Label3D

var _n := 23
var _section_m := 0.7292 * SCALE


func setup(a: Articulation) -> void:
	art = a
	_n = art.n_sections
	_section_m = art.section_cm * SCALE

	# -- the tube --------------------------------------------------------------
	tube = MeshInstance3D.new()
	tube.name = "TubeMesh"
	tube.mesh = tube_mesh
	tube_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	tube_mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	tube_mat.vertex_color_use_as_albedo = true
	tube_mat.albedo_color = Color(1, 1, 1, 1)
	tube_mat.emission_enabled = true
	tube_mat.emission = Color(0.15, 0.55, 1.0)
	tube_mat.emission_energy_multiplier = 0.9
	tube_mat.roughness = 0.15
	tube_mat.metallic = 0.1
	tube.material_override = tube_mat
	add_child(tube)

	# -- nasal branch: leaves the tract at the nasal junction (section 9, c_pos 0.41) -----
	nasal = MeshInstance3D.new()
	nasal.name = "NasalBranch"
	var cyl := CylinderMesh.new()
	cyl.top_radius = 0.018
	cyl.bottom_radius = 0.026
	cyl.height = 0.34
	nasal.mesh = cyl
	nasal_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	nasal_mat.albedo_color = Color(0.9, 0.5, 0.2, 0.25)
	nasal_mat.emission_enabled = true
	nasal_mat.emission = Color(1.0, 0.55, 0.15)
	nasal_mat.emission_energy_multiplier = 0.0
	nasal.material_override = nasal_mat
	var jy := (art.nasal_junction + 0.5) * _section_m
	nasal.position = Vector3(-0.13, jy + 0.12, 0.0)
	nasal.rotation = Vector3(0, 0, deg_to_rad(38))
	add_child(nasal)
	nasal_label = _label("nasal port  SHUT", Vector3(-0.30, jy + 0.30, 0.0), Color(0.9, 0.6, 0.3))

	# -- constriction ring: slides to argmin(A) ----------------------------------------
	ring = MeshInstance3D.new()
	ring.name = "ConstrictionRing"
	var torus := TorusMesh.new()
	torus.inner_radius = 0.098
	torus.outer_radius = 0.114
	ring.mesh = torus
	ring_mat.albedo_color = Color(1.0, 0.9, 0.2, 0.9)
	ring_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	ring_mat.emission_enabled = true
	ring_mat.emission = Color(1.0, 0.8, 0.1)
	ring_mat.emission_energy_multiplier = 1.5
	ring.material_override = ring_mat
	add_child(ring)
	con_label = _label("constriction", Vector3(0.20, 0.0, 0.0), Color(1.0, 0.85, 0.3))

	# -- glottis: pulses with voicing ---------------------------------------------------
	glottis = MeshInstance3D.new()
	glottis.name = "Glottis"
	var sph := SphereMesh.new()
	sph.radius = 0.045
	sph.height = 0.09
	glottis.mesh = sph
	glottis_mat.albedo_color = Color(0.9, 0.2, 0.4)
	glottis_mat.emission_enabled = true
	glottis_mat.emission = Color(1.0, 0.25, 0.5)
	glottis_mat.emission_energy_multiplier = 0.2
	glottis.material_override = glottis_mat
	glottis.position = Vector3(0, -0.03, 0)
	add_child(glottis)
	glottis_light = OmniLight3D.new()
	glottis_light.light_color = Color(1.0, 0.4, 0.6)
	glottis_light.omni_range = 0.9
	glottis_light.light_energy = 0.0
	glottis.add_child(glottis_light)
	_label("glottis (voicing)", Vector3(0.16, -0.05, 0.0), Color(1.0, 0.5, 0.7))

	lip_label = _label("lips", Vector3(0.16, _n * _section_m + 0.03, 0.0), Color(0.6, 0.9, 1.0))
	var title := _label("ERAN vocal tract  17.60 cm  23 sections -- measured, section by section\nradius = sqrt(A/pi) drawn x%.1f for legibility; lengths true" % RADIUS_GAIN,
		Vector3(0.0, _n * _section_m + 0.15, 0.0), Color(0.8, 0.9, 1.0), 18)
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER

	# initial shape: the open vowel
	var v := art.syllable("a")
	if not v.is_empty():
		apply_frame(v["frames"][v["frames"].size() - 1])


func _label(text: String, pos: Vector3, col: Color, size: int = 16) -> Label3D:
	var l := Label3D.new()
	l.text = text
	l.position = pos
	l.font_size = size
	l.pixel_size = 0.0018
	l.modulate = col
	l.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	l.no_depth_test = true
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_LEFT
	add_child(l)
	return l


## f: one frame dict of articulation.json
func apply_frame(f: Dictionary) -> void:
	var areas: Array = f.get("areas", [])
	if areas.size() != _n:
		return
	_rebuild_tube(areas, f)

	# constriction ring -> argmin(A)
	var mi := int(f.get("min_section", 0))
	var min_a := float(f.get("min_area", 1.0))
	ring.position = Vector3(0, (mi + 0.5) * _section_m, 0)
	var tight := art.tightness01(f)
	var rc := Color(1.0, 0.9, 0.2).lerp(Color(1.0, 0.15, 0.1), tight)
	ring_mat.albedo_color = Color(rc.r, rc.g, rc.b, 0.35 + 0.6 * tight)
	ring_mat.emission = rc
	ring_mat.emission_energy_multiplier = 0.4 + 2.2 * tight
	con_label.position = Vector3(0.20, (mi + 0.5) * _section_m, 0)
	con_label.text = "constriction  sec %d  %.1f cm from lips\n%.3f cm2%s" % [
		mi, float(f.get("constriction_cm_from_lips", 0.0)), min_a,
		"  SEALED" if art.sealed(f) else ""]

	# nasal port -> a switch above 0.05 cm^2
	var nopen := art.nasal_open(f)
	var vel := float(f.get("velum", 0.0))
	nasal_mat.emission_energy_multiplier = 2.5 if nopen else 0.0
	nasal_mat.albedo_color = Color(1.0, 0.6, 0.2, 0.75) if nopen else Color(0.9, 0.5, 0.2, 0.18)
	nasal_label.text = ("nasal port  OPEN  %.2f cm2\nair -> NOSE" % vel) if nopen else "nasal port  SHUT"
	nasal_label.modulate = Color(1.0, 0.7, 0.3) if nopen else Color(0.6, 0.45, 0.35)

	# glottis pulses with voicing
	var voi := float(f.get("voicing", 0.0))
	glottis_mat.emission_energy_multiplier = 0.2 + 3.0 * voi
	glottis_light.light_energy = 3.5 * voi
	var s := 1.0 + 0.25 * voi
	glottis.scale = Vector3(s, s, s)

	lip_label.text = "lips  %.3f cm2%s" % [float(f.get("lip_area", 0.0)),
		"  SEALED" if float(f.get("lip_area", 1.0)) < art.seal_cm2 else ""]


func _rebuild_tube(areas: Array, f: Dictionary) -> void:
	# rings: glottis base (y=0), 23 section centres, lip cap (y = ladder)
	var ring_y := PackedFloat32Array()
	var ring_r := PackedFloat32Array()
	var ring_c := PackedColorArray()
	var nopen := art.nasal_open(f)
	var mi := int(f.get("min_section", -1))
	var first_a := float(areas[0])
	ring_y.append(0.0)
	ring_r.append(_radius_m(first_a))
	ring_c.append(_ring_color(first_a, 0, mi, nopen))
	for i in range(_n):
		var a := float(areas[i])
		ring_y.append((i + 0.5) * _section_m)
		ring_r.append(_radius_m(a))
		ring_c.append(_ring_color(a, i, mi, nopen))
	var last_a := float(areas[_n - 1])
	ring_y.append(_n * _section_m)
	ring_r.append(_radius_m(last_a))
	ring_c.append(_ring_color(last_a, _n - 1, mi, nopen))

	var nr := ring_y.size()
	var verts := PackedVector3Array()
	var norms := PackedVector3Array()
	var cols := PackedColorArray()
	var idx := PackedInt32Array()
	verts.resize(nr * RING_VERTS)
	norms.resize(nr * RING_VERTS)
	cols.resize(nr * RING_VERTS)
	for r in range(nr):
		for k in range(RING_VERTS):
			var ang := TAU * float(k) / float(RING_VERTS)
			var nx := cos(ang)
			var nz := sin(ang)
			var vi := r * RING_VERTS + k
			verts[vi] = Vector3(nx * ring_r[r], ring_y[r], nz * ring_r[r])
			norms[vi] = Vector3(nx, 0, nz)
			cols[vi] = ring_c[r]
	for r in range(nr - 1):
		for k in range(RING_VERTS):
			var k1 := (k + 1) % RING_VERTS
			var a0 := r * RING_VERTS + k
			var a1 := r * RING_VERTS + k1
			var b0 := (r + 1) * RING_VERTS + k
			var b1 := (r + 1) * RING_VERTS + k1
			idx.append_array(PackedInt32Array([a0, b0, a1, a1, b0, b1]))

	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = verts
	arrays[Mesh.ARRAY_NORMAL] = norms
	arrays[Mesh.ARRAY_COLOR] = cols
	arrays[Mesh.ARRAY_INDEX] = idx
	tube_mesh.clear_surfaces()
	tube_mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)


func _radius_m(a_cm2: float) -> float:
	return maxf(sqrt(maxf(a_cm2, 0.0) / PI), R_FLOOR_CM) * SCALE * RADIUS_GAIN


func _ring_color(a: float, i: int, mi: int, nopen: bool) -> Color:
	if a < art.seal_cm2:
		return Color(1.0, 0.1, 0.1, 0.95)          # sealed: a red knot
	var c := Color(0.35, 0.75, 1.0, 0.42)          # glass
	if i == mi and a < art.no_noise_cm2:
		c = Color(1.0, 0.85, 0.3, 0.7)             # the constriction
	if nopen and i <= art.nasal_junction:
		c = c.lerp(Color(1.0, 0.6, 0.25, 0.55), 0.5)   # air routed to the nose below the junction
	return c
