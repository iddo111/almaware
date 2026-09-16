# boulevard_cafe.gd -- THE BOULEVARD. One short stretch of Rothschild, built for detail.
#
# BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.
#
# Iddo, 2026-08-30:
#   "תעשה לי עולם זעיר של השדירה - זה קפה קלוד - זה אשכרה מספיק להתחיל את ערן VR
#    שמה כולם נפגשים בקפה בשדירה הוירטואלית"
#   "מספיק מקטע קטן"  ...  "אבל סופר דיטיילד ואיכותי 4K HDR ריל לייף"
#   "הכי טוב שאפשר - לקחת את הזמן - זה קווסט לא FPS"
#
# "קווסט לא FPS" is read here as GENRE, not hardware: an exploration quest. Nobody
# needs 120 Hz to sit at a cafe. That is what buys the polygon budget -- 30-60 fps
# with heavy geometry is the correct trade, and it is the whole reason this file
# exists separately from scripts/tel_aviv_1933.gd, which must keep covering 7x7
# blocks cheaply. THAT FILE IS NOT TOUCHED. This one spends everything on ~78 m.
#
# ---------------------------------------------------------------------------
# WHERE THE SHAPES COME FROM
# Not from a memory of Tel Aviv -- from reference/iddo/, seven photographs Iddo took
# on 2026-08-30 sitting on a boulevard bench. What those pictures actually show, and
# what is therefore built here:
#
#   * the median is a SEQUENCE OF STRIPS, not a lawn: clipped hedge on bare soil,
#     a bike lane, small-square paving, a narrow bright green ribbon, more paving.
#     Getting that cross-section right is most of the recognition.
#   * the trees are tamarisk/ficus: SHORT thick furrowed trunks, often forked at the
#     base, with heavy limbs that leave low (1.5-2.5 m) and travel SIDEWAYS a long
#     way. In boulevard-06 one limb lies nearly horizontal across the whole frame at
#     chest height. Tree #4 here is built to do exactly that.
#   * the canopy is WISPY, grey-green, and full of holes. It is not a ball.
#   * therefore the light on the ground is HARD DAPPLE. That is the signature of the
#     place. Everything in the lighting block below exists to serve it: a small sun
#     angular diameter, an 8k shadow map with the splits crushed close to the camera,
#     and ~50 separate leaf clumps per tree so there is something to dapple WITH.
#   * benches: dark red-brown slats, black iron ends with a curl, facing along.
#   * the cafe is a KIOSK with square canvas shade sails on a central mast, small
#     round tables, and a rank of bicycles. That is Cafe Claude.
#
# The facades are 1930s Bauhaus (the period the rest of this project is set in);
# the median furniture is straight off his photographs. Said plainly so nobody
# later mistakes the mix for an accident.
# ---------------------------------------------------------------------------
extends Node3D

# ------------------------------------------------------------------ the plan
# z runs along the boulevard. x crosses it. The sea is west, -x.
const LENGTH := 78.0          # metres of boulevard. "מקטע קטן".
const HALF := LENGTH * 0.5

# The cross-section, in metres of x. Read it as a section drawing.
const MED_W := 6.3            # median half-width
const HEDGE_IN := 5.1         # hedge/soil strip runs from MED_W in to here
const BIKE_IN := 2.7          # bike lane from HEDGE_IN in to here (west side only)
const TURF_W := 0.45          # the green ribbon, half-width
const ROAD_OUT := 12.0        # carriageway from MED_W+0.2 out to here
const WALK_OUT := 15.5        # pavement out to the building line
const DECK := 0.17            # the median deck stands this proud of the road

const CAFE_Z0 := 3.0          # the kiosk zone: no green ribbon through it
const CAFE_Z1 := 21.0

@export var seed_value := 1933
@export var people := true
@export var tree_count := 22
@export var verbose := true

var _rng := RandomNumberGenerator.new()
var _t0 := 0

# groups, so the triangle census can be reported per part instead of as one lump
var _g := {}

# materials
var m_paving: StandardMaterial3D
var m_kerb: StandardMaterial3D
var m_asphalt: StandardMaterial3D
var m_bike: StandardMaterial3D
var m_turf: StandardMaterial3D
var m_soil: StandardMaterial3D
var m_bark: StandardMaterial3D
var m_leaf: StandardMaterial3D
var m_hedge: StandardMaterial3D
var m_plaster: StandardMaterial3D
var m_plaster_warm: StandardMaterial3D
var m_shade: StandardMaterial3D
var m_glass: StandardMaterial3D
var m_shopglass: StandardMaterial3D
var m_wood: StandardMaterial3D
var m_wood_dark: StandardMaterial3D
var m_iron: StandardMaterial3D
var m_brass: StandardMaterial3D
var m_steel: StandardMaterial3D
var m_marble: StandardMaterial3D
var m_canvas: StandardMaterial3D
var m_paint_dark: StandardMaterial3D
var m_rubber: StandardMaterial3D
var m_cloth_light: StandardMaterial3D
var m_cloth_dark: StandardMaterial3D
var m_skin: StandardMaterial3D
var m_stone: StandardMaterial3D

# shared meshes, so 4000 cylinders do not become 4000 mesh resources
var _cyl_cache := {}
var _sph_leaf: SphereMesh
var _sph_hedge: SphereMesh


func _ready() -> void:
	_t0 = Time.get_ticks_msec()
	_rng.seed = seed_value
	_build_textures_and_materials()
	_build_sky_and_light()
	_build_ground()
	_build_hedges()
	_build_trees()
	_build_benches_and_furniture()
	_build_cafe()
	_build_facades()
	_build_vehicles()
	if people:
		_build_people()
	_census()


func _grp(n: String) -> Node3D:
	if _g.has(n):
		return _g[n]
	var g := Node3D.new()
	g.name = n
	add_child(g)
	_g[n] = g
	return g


# =========================================================================
# TEXTURES -- generated in code, so the repo carries no binary and no licence.
# Every surface gets albedo + a normal map derived from the same height field,
# because at a 25-degree sun it is the NORMAL MAP, not the colour, that stops a
# pavement from looking like a painted plane.
# =========================================================================
func _normal_tex(hh: PackedFloat32Array, s: int, strength: float) -> ImageTexture:
	var img := Image.create(s, s, true, Image.FORMAT_RGB8)
	for y in s:
		for x in s:
			var l: float = hh[y * s + (x - 1 + s) % s]
			var r: float = hh[y * s + (x + 1) % s]
			var u: float = hh[((y - 1 + s) % s) * s + x]
			var d: float = hh[((y + 1) % s) * s + x]
			var v := Vector3((l - r) * strength, (u - d) * strength, 1.0).normalized()
			img.set_pixel(x, y, Color(v.x * 0.5 + 0.5, v.y * 0.5 + 0.5, v.z * 0.5 + 0.5))
	img.generate_mipmaps()
	return ImageTexture.create_from_image(img)


func _tex_paving() -> Array:
	# Small square concrete slabs. In his photographs they are roughly 40-50 cm,
	# laid square, every one a slightly different shade, joints full of dust.
	var s := 512
	# MUST divide 512 exactly: with tiles = 10 the tile pitch is 51 px, x/51 reaches
	# 10 at x = 510, and the per-tile tone lookup ran off the end of the array --
	# which took out every material built after it. 8 tiles, and the slab size is
	# set by the UV scale below instead (3.2 m period / 8 = 0.4 m slabs).
	var tiles := 8
	var tp := s / tiles
	var grain := FastNoiseLite.new()
	grain.seed = 7
	grain.frequency = 0.35
	var dirt := FastNoiseLite.new()
	dirt.seed = 11
	dirt.frequency = 0.012
	dirt.fractal_octaves = 4
	var tone := PackedFloat32Array()
	tone.resize(tiles * tiles)
	for i in tone.size():
		tone[i] = _rng.randf_range(-0.075, 0.075)
	var alb := Image.create(s, s, true, Image.FORMAT_RGB8)
	var rgh := Image.create(s, s, true, Image.FORMAT_RGB8)
	var hh := PackedFloat32Array()
	hh.resize(s * s)
	for y in s:
		for x in s:
			var ix := x % tp
			var iy := y % tp
			var edge: int = mini(mini(ix, iy), mini(tp - 1 - ix, tp - 1 - iy))
			var joint: float = clampf(float(edge) / 2.0, 0.0, 1.0)   # 0 in the joint
			var t: float = tone[clampi((y / tp) * tiles + (x / tp), 0, tone.size() - 1)]
			var g: float = grain.get_noise_2d(x, y) * 0.028
			var dv: float = dirt.get_noise_2d(x, y) * 0.085
			var base := Color(0.600, 0.575, 0.522)
			var c := base * (1.0 + t + g + dv)
			# joints darker but NOT black -- at 0.85 the pavement read as a chessboard
			c = c.lerp(Color(0.436, 0.412, 0.368), (1.0 - joint) * 0.70)
			alb.set_pixel(x, y, c)
			hh[y * s + x] = joint * 0.85 + g * 3.0
			var rv: float = 0.86 + g * 2.0 + (1.0 - joint) * 0.06
			rgh.set_pixel(x, y, Color(rv, rv, rv))
	alb.generate_mipmaps()
	rgh.generate_mipmaps()
	return [ImageTexture.create_from_image(alb), _normal_tex(hh, s, 3.0),
			ImageTexture.create_from_image(rgh)]


func _tex_noise(s: int, base: Color, spread: float, freq: float, octaves: int,
		bump: float) -> Array:
	var n := FastNoiseLite.new()
	n.seed = _rng.randi()
	n.frequency = freq
	n.fractal_octaves = octaves
	var fine := FastNoiseLite.new()
	fine.seed = _rng.randi()
	fine.frequency = 0.4
	var alb := Image.create(s, s, true, Image.FORMAT_RGB8)
	var hh := PackedFloat32Array()
	hh.resize(s * s)
	for y in s:
		for x in s:
			var v: float = n.get_noise_2d(x, y) * spread
			var f: float = fine.get_noise_2d(x, y) * spread * 0.35
			alb.set_pixel(x, y, base * (1.0 + v + f))
			hh[y * s + x] = v + f
	alb.generate_mipmaps()
	return [ImageTexture.create_from_image(alb), _normal_tex(hh, s, bump)]


func _tex_bark() -> Array:
	# Deep vertical furrows. boulevard-06 is a close-up of exactly this: the bark
	# is the most detailed thing in his whole set, so it gets the strongest relief.
	var s := 256
	var n := FastNoiseLite.new()
	n.seed = 23
	n.frequency = 0.02
	n.fractal_octaves = 3
	var alb := Image.create(s, s, true, Image.FORMAT_RGB8)
	var hh := PackedFloat32Array()
	hh.resize(s * s)
	for y in s:
		for x in s:
			# stretch the noise 6x vertically -> furrows that run with the trunk
			var w: float = n.get_noise_2d(float(x) * 3.0, float(y) * 0.5)
			var ridge: float = 1.0 - absf(w) * 2.2
			ridge = clampf(ridge, 0.0, 1.0)
			var c := Color(0.400, 0.336, 0.268).lerp(Color(0.196, 0.156, 0.124),
					1.0 - ridge)
			alb.set_pixel(x, y, c)
			hh[y * s + x] = ridge
	alb.generate_mipmaps()
	return [ImageTexture.create_from_image(alb), _normal_tex(hh, s, 5.0)]


func _std(albedo: Color, rough: float, metal: float) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = albedo
	m.roughness = rough
	m.metallic = metal
	return m


func _build_textures_and_materials() -> void:
	var pav := _tex_paving()
	m_paving = _std(Color(1, 1, 1), 0.86, 0.0)
	m_paving.albedo_texture = pav[0]
	m_paving.normal_enabled = true
	m_paving.normal_texture = pav[1]
	m_paving.normal_scale = 1.4
	m_paving.roughness_texture = pav[2]
	m_paving.uv1_triplanar = true
	m_paving.uv1_world_triplanar = true
	m_paving.uv1_scale = Vector3(0.3125, 0.3125, 0.3125)   # 3.2 m / 8 = 0.4 m slabs

	var pl := _tex_noise(256, Color(0.878, 0.850, 0.784), 0.10, 0.02, 4, 1.2)
	m_plaster = _std(Color(1, 1, 1), 0.90, 0.0)          # sand-render, never white
	m_plaster.albedo_texture = pl[0]
	m_plaster.normal_enabled = true
	m_plaster.normal_texture = pl[1]
	m_plaster.normal_scale = 0.55
	m_plaster.uv1_triplanar = true
	m_plaster.uv1_world_triplanar = true
	m_plaster.uv1_scale = Vector3(0.4, 0.4, 0.4)

	m_plaster_warm = m_plaster.duplicate()
	m_plaster_warm.albedo_color = Color(0.965, 0.900, 0.792)

	m_shade = m_plaster.duplicate()                      # soffits, balcony undersides
	m_shade.albedo_color = Color(0.742, 0.712, 0.652)

	var asp := _tex_noise(256, Color(0.196, 0.192, 0.190), 0.30, 0.05, 4, 1.0)
	# WET-LOOKING ASPHALT: roughness 0.42 (not 0.95). At a 25-degree sun a dry road
	# is a flat grey nothing; a slightly damp one throws a long sheet of specular
	# down the carriageway, and that specular is what makes late afternoon read.
	m_asphalt = _std(Color(1, 1, 1), 0.42, 0.0)
	m_asphalt.albedo_texture = asp[0]
	m_asphalt.normal_enabled = true
	m_asphalt.normal_texture = asp[1]
	m_asphalt.normal_scale = 0.6
	m_asphalt.uv1_triplanar = true
	m_asphalt.uv1_world_triplanar = true
	m_asphalt.uv1_scale = Vector3(0.35, 0.35, 0.35)

	m_bike = m_asphalt.duplicate()                       # the green-tinted bike lane
	m_bike.albedo_color = Color(0.560, 0.660, 0.520)
	m_bike.roughness = 0.62

	var tf := _tex_noise(256, Color(0.268, 0.372, 0.196), 0.30, 0.25, 3, 2.0)
	m_turf = _std(Color(1, 1, 1), 1.0, 0.0)
	m_turf.albedo_texture = tf[0]
	m_turf.normal_enabled = true
	m_turf.normal_texture = tf[1]
	m_turf.normal_scale = 1.0
	m_turf.uv1_triplanar = true
	m_turf.uv1_world_triplanar = true
	m_turf.uv1_scale = Vector3(1.5, 1.5, 1.5)

	var so := _tex_noise(256, Color(0.588, 0.512, 0.398), 0.22, 0.08, 4, 2.5)
	m_soil = _std(Color(1, 1, 1), 1.0, 0.0)              # the bare dusty rings
	m_soil.albedo_texture = so[0]
	m_soil.normal_enabled = true
	m_soil.normal_texture = so[1]
	m_soil.uv1_triplanar = true
	m_soil.uv1_world_triplanar = true
	m_soil.uv1_scale = Vector3(0.6, 0.6, 0.6)

	var bk := _tex_bark()
	m_bark = _std(Color(1, 1, 1), 0.98, 0.0)
	m_bark.albedo_texture = bk[0]
	m_bark.normal_enabled = true
	m_bark.normal_texture = bk[1]
	m_bark.normal_scale = 1.5
	m_bark.uv1_triplanar = true
	m_bark.uv1_world_triplanar = true
	# 0.9 put the tiling period at 1.1 m on a 0.4 m trunk -- one giant stripe per
	# tree, which rendered as corduroy. 3.2 puts the furrows at ~30 cm, near real.
	m_bark.uv1_scale = Vector3(3.2, 3.2, 3.2)

	m_kerb = _std(Color(0.700, 0.678, 0.628), 0.80, 0.0)

	# Tamarisk foliage: grey-green and THIN. backlight is doing real work -- a leaf
	# clump with the sun behind it should glow, and without this it reads as plastic.
	m_leaf = _std(Color(0.402, 0.462, 0.302), 0.96, 0.0)
	m_leaf.vertex_color_use_as_albedo = true
	m_leaf.backlight_enabled = true
	m_leaf.backlight = Color(0.31, 0.36, 0.19)
	m_leaf.cull_mode = BaseMaterial3D.CULL_BACK

	m_hedge = _std(Color(0.196, 0.300, 0.148), 1.0, 0.0)
	m_hedge.vertex_color_use_as_albedo = true
	m_hedge.backlight_enabled = true
	m_hedge.backlight = Color(0.16, 0.22, 0.10)

	# 1930s glass over an unlit room. Low roughness + a little metallic so the sky
	# lands in it; that reflection is the only thing that keeps a window from being
	# a black rectangle.
	m_glass = _std(Color(0.052, 0.066, 0.082), 0.06, 0.62)
	m_shopglass = _std(Color(0.052, 0.062, 0.076), 0.05, 0.70)

	m_wood = _std(Color(0.470, 0.318, 0.196), 0.72, 0.0)
	m_wood_dark = _std(Color(0.286, 0.152, 0.108), 0.66, 0.0)   # bench slats
	m_iron = _std(Color(0.072, 0.074, 0.080), 0.44, 0.85)       # black iron ends
	m_brass = _std(Color(0.716, 0.556, 0.276), 0.24, 1.0)       # counter rail
	m_steel = _std(Color(0.560, 0.570, 0.585), 0.30, 1.0)
	m_marble = _std(Color(0.900, 0.884, 0.856), 0.13, 0.0)      # cafe table tops
	m_marble.clearcoat_enabled = true
	m_marble.clearcoat = 0.8
	m_marble.clearcoat_roughness = 0.06

	m_canvas = _std(Color(0.842, 0.796, 0.686), 0.85, 0.0)      # the shade sails
	m_canvas.cull_mode = BaseMaterial3D.CULL_DISABLED
	m_canvas.backlight_enabled = true
	m_canvas.backlight = Color(0.45, 0.41, 0.33)

	m_paint_dark = _std(Color(0.058, 0.076, 0.062), 0.14, 0.0)  # car coachwork
	m_paint_dark.clearcoat_enabled = true
	m_paint_dark.clearcoat = 1.0
	m_paint_dark.clearcoat_roughness = 0.04
	m_rubber = _std(Color(0.042, 0.042, 0.046), 0.88, 0.0)
	m_cloth_light = _std(Color(0.878, 0.856, 0.808), 0.94, 0.0)
	m_cloth_dark = _std(Color(0.186, 0.196, 0.226), 0.92, 0.0)
	m_skin = _std(Color(0.700, 0.550, 0.440), 0.72, 0.0)
	m_stone = _std(Color(0.760, 0.728, 0.662), 0.70, 0.0)

	# 6x3 spheres, ~36 triangles each. Deliberately coarse, because the canopy now
	# needs ~450 of them PER TREE to be a canopy with holes rather than a lid.
	_sph_leaf = SphereMesh.new()
	_sph_leaf.radius = 0.5
	_sph_leaf.height = 1.0
	_sph_leaf.radial_segments = 6
	_sph_leaf.rings = 3
	_sph_leaf.material = m_leaf

	_sph_hedge = SphereMesh.new()
	_sph_hedge.radius = 0.5
	_sph_hedge.height = 1.0
	_sph_hedge.radial_segments = 6
	_sph_hedge.rings = 4
	_sph_hedge.material = m_hedge


# =========================================================================
# LIGHT -- late afternoon, and everything about it is aimed at the dapple.
# =========================================================================
func _build_sky_and_light() -> void:
	var sun := DirectionalLight3D.new()
	sun.name = "Sun"
	# THE SUN HAD TO MOVE, and it is worth saying why, because two renders in a row
	# came back with a pavement that was uniformly lit and I blamed the leaves.
	# It was geometry. At 24 degrees elevation an 8 m tree throws its shadow 18 m --
	# clean over the median, over the kerb, and onto the far carriageway. There was
	# never going to be dapple UNDER the trees at that angle, however finely the
	# canopy was subdivided.
	# So: 37 degrees, and the azimuth swung round to the south-west so the light
	# runs ALONG the boulevard instead of across it. Shadows now fall on the walk
	# the trees stand on. Still late afternoon in colour and still long-shadowed,
	# but honestly more like 4 pm than 6 pm -- the alternative was a beautiful sun
	# angle and no dappled light, and the dapple is the place.
	sun.basis = Basis.looking_at(Vector3(0.45, -0.60, 0.66).normalized())
	sun.light_color = Color(1.0, 0.836, 0.652)
	# Render 2 raised ambient to 1.9 to lift the shade, and that killed the very
	# thing this scene is for: sky fill that strong washes a leaf shadow out to
	# nothing, and the paving came back uniformly lit. The ratio is what makes
	# dapple, not the absolute level -- so the sun goes UP and the fill comes DOWN,
	# and exposure carries the overall brightness instead.
	sun.light_energy = 4.6
	sun.light_specular = 1.0
	sun.shadow_enabled = true
	# The real sun subtends about half a degree. Godot defaults to 0 (perfectly hard).
	# Giving it its true angular size is what makes leaf shadows soft at the edges
	# and razor sharp under the trunk -- the actual look of dapple.
	sun.light_angular_distance = 0.45
	sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS
	sun.directional_shadow_max_distance = 70.0
	sun.directional_shadow_split_1 = 0.05     # splits crushed close to the camera:
	sun.directional_shadow_split_2 = 0.14     # the near 5 m of pavement is the shot,
	sun.directional_shadow_split_3 = 0.38     # so it gets most of the 8k map
	sun.directional_shadow_blend_splits = true
	# Normal bias 1.1 pushes the shadow of a 0.3 m leaf clump most of a clump-width
	# off its caster -- peter-panning that erases small shadows outright. Small
	# casters need small bias.
	sun.shadow_bias = 0.016
	sun.shadow_normal_bias = 0.35
	sun.shadow_blur = 0.6
	sun.sky_mode = DirectionalLight3D.SKY_MODE_LIGHT_AND_SKY
	add_child(sun)

	var wenv := WorldEnvironment.new()
	wenv.name = "Env"
	var e := Environment.new()

	# --- sky: physical, so the horizon is genuinely hazier and warmer than the zenith
	var sky := Sky.new()
	var ps := PhysicalSkyMaterial.new()
	ps.turbidity = 6.5                       # dust + sea haze, not alpine air
	ps.rayleigh_coefficient = 2.4
	ps.mie_coefficient = 0.012
	ps.mie_eccentricity = 0.80
	ps.mie_color = Color(0.96, 0.88, 0.76)
	ps.sun_disk_scale = 1.4
	ps.ground_color = Color(0.470, 0.436, 0.384)
	ps.energy_multiplier = 1.0
	sky.sky_material = ps
	sky.radiance_size = Sky.RADIANCE_SIZE_256
	e.background_mode = Environment.BG_SKY
	e.sky = sky
	e.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	e.ambient_light_sky_contribution = 1.0
	e.ambient_light_energy = 0.78    # sky fill. Above ~1.2 the dapple disappears.
	e.reflected_light_source = Environment.REFLECTION_SOURCE_SKY

	# --- tonemapping: ACES. The scene is lit in real HDR ratios (a 3.1-energy sun
	# against 1.0 sky ambient blows straight past 1.0), so without a filmic curve the
	# lit plaster clips to flat white. ACES is what rolls it off instead.
	e.tonemap_mode = Environment.TONE_MAPPER_ACES
	# 0.92 left every shadow on the boulevard in near-black -- measured whole-frame
	# mean luminance 0.126 across five stills. A Mediterranean afternoon is BRIGHT
	# and the shade under a tamarisk is still perfectly readable.
	e.tonemap_exposure = 1.02
	e.tonemap_white = 6.0                    # HDR headroom before anything clips

	# --- glow: only above 1.0, so it is a bloom on genuinely bright things (sky
	# through the canopy, the specular on the road) and not a haze over everything.
	e.glow_enabled = true
	e.glow_normalized = true
	e.glow_intensity = 0.55
	e.glow_strength = 1.0
	e.glow_bloom = 0.05
	e.glow_blend_mode = Environment.GLOW_BLEND_MODE_SOFTLIGHT
	e.glow_hdr_threshold = 1.05
	e.glow_hdr_scale = 2.0
	e.set("glow_levels/2", 0.4)
	e.set("glow_levels/3", 0.8)
	e.set("glow_levels/4", 1.0)
	e.set("glow_levels/5", 0.6)

	# --- SSAO: contact darkening where the bench meets the paving, in the bark
	# furrows, under the hedge. Small radius on purpose -- large-radius SSAO makes
	# everything look dirty.
	e.ssao_enabled = true
	e.ssao_radius = 0.7
	e.ssao_intensity = 2.4
	e.ssao_power = 1.6
	e.ssao_detail = 0.6
	e.ssao_horizon = 0.06
	e.ssao_sharpness = 0.98
	e.ssao_light_affect = 0.12
	e.ssao_ao_channel_affect = 0.35

	# --- SSIL: cheap bounce. The warm plaster should throw light back into the
	# shaded side of the trunks; without it every shadow is sky-blue and cold.
	e.ssil_enabled = true
	e.ssil_radius = 3.5
	e.ssil_intensity = 0.85
	e.ssil_sharpness = 0.98
	e.ssil_normal_rejection = 1.0

	# --- SDFGI: the real-time GI. Chosen over baked lightmaps because the whole
	# point of the generator is that the street is rebuilt from data each run --
	# a lightmap would have to be re-baked every time a parameter moved, and none
	# of this geometry exists as an asset to bake.
	e.sdfgi_enabled = true
	e.sdfgi_use_occlusion = true
	e.sdfgi_read_sky_light = true
	e.sdfgi_bounce_feedback = 0.6
	e.sdfgi_cascades = 4
	e.sdfgi_min_cell_size = 0.15             # ~0.15 m first cascade: bench-scale GI
	e.sdfgi_y_scale = Environment.SDFGI_Y_SCALE_75_PERCENT
	e.sdfgi_energy = 1.10
	e.sdfgi_normal_bias = 1.1
	e.sdfgi_probe_bias = 1.1

	# --- fog: sea haze plus dust. Aerial perspective pushes the far end of the
	# street back, which is the only depth cue a 78 m scene has.
	e.fog_enabled = true
	e.fog_mode = Environment.FOG_MODE_EXPONENTIAL
	e.fog_light_color = Color(0.870, 0.816, 0.718)
	e.fog_light_energy = 1.0
	e.fog_sun_scatter = 0.35
	e.fog_density = 0.0028
	e.fog_aerial_perspective = 0.35
	e.fog_sky_affect = 0.25

	# --- volumetric fog: shafts of light through the canopy. Low density -- this is
	# a dusty afternoon, not a smoke machine.
	e.volumetric_fog_enabled = true
	e.volumetric_fog_density = 0.008
	e.volumetric_fog_albedo = Color(0.92, 0.87, 0.78)
	e.volumetric_fog_emission = Color(0, 0, 0)
	e.volumetric_fog_gi_inject = 0.9
	e.volumetric_fog_anisotropy = 0.35
	e.volumetric_fog_length = 70.0
	e.volumetric_fog_detail_spread = 2.0
	e.volumetric_fog_ambient_inject = 0.6
	e.volumetric_fog_sky_affect = 0.0

	e.adjustment_enabled = true
	e.adjustment_brightness = 1.0
	e.adjustment_contrast = 1.04
	e.adjustment_saturation = 1.06
	wenv.environment = e
	add_child(wenv)

	# A probe over the cafe so the marble tops and the shopfront glass have something
	# local to reflect instead of only the sky.
	var probe := ReflectionProbe.new()
	probe.name = "CafeProbe"
	probe.position = Vector3(0, 4.0, (CAFE_Z0 + CAFE_Z1) * 0.5)
	probe.size = Vector3(26, 12, 26)
	probe.origin_offset = Vector3(0, -2.0, 0)
	probe.intensity = 1.0
	probe.max_distance = 60.0
	probe.box_projection = true
	probe.update_mode = ReflectionProbe.UPDATE_ONCE
	add_child(probe)


# =========================================================================
# PRIMITIVES
# =========================================================================
func _box(parent: Node3D, size: Vector3, pos: Vector3, mat: Material,
		rot := Vector3.ZERO) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	var b := BoxMesh.new()
	b.size = size
	mi.mesh = b
	mi.position = pos
	if rot != Vector3.ZERO:
		mi.rotation = rot
	mi.material_override = mat
	parent.add_child(mi)
	return mi


func _body(parent: Node3D, size: Vector3, pos: Vector3, mat: Material) -> void:
	# Collision, so the walker cannot stroll through the kiosk.
	var sb := StaticBody3D.new()
	sb.position = pos
	var cs := CollisionShape3D.new()
	var sh := BoxShape3D.new()
	sh.size = size
	cs.shape = sh
	sb.add_child(cs)
	var mi := MeshInstance3D.new()
	var b := BoxMesh.new()
	b.size = size
	mi.mesh = b
	mi.material_override = mat
	sb.add_child(mi)
	parent.add_child(sb)


func _cyl_mesh(seg: int) -> CylinderMesh:
	# One mesh resource per segment count, reused thousands of times.
	if _cyl_cache.has(seg):
		return _cyl_cache[seg]
	var c := CylinderMesh.new()
	c.top_radius = 0.5
	c.bottom_radius = 0.5
	c.height = 1.0
	c.radial_segments = seg
	c.rings = 1
	_cyl_cache[seg] = c
	return c


func _tube(parent: Node3D, a: Vector3, b: Vector3, r: float, mat: Material,
		seg := 8) -> MeshInstance3D:
	# A cylinder from a to b. Scaling one unit cylinder is far cheaper than
	# building a new CylinderMesh per branch segment.
	var d := b - a
	var h := d.length()
	if h < 0.0005:
		return null
	var yv := d / h
	var up := Vector3.UP if absf(yv.dot(Vector3.UP)) < 0.96 else Vector3.RIGHT
	var xv := up.cross(yv).normalized()
	var zv := xv.cross(yv)
	var mi := MeshInstance3D.new()
	mi.mesh = _cyl_mesh(seg)
	mi.material_override = mat
	mi.transform = Transform3D(Basis(xv, yv, zv).scaled(Vector3(r * 2.0, h, r * 2.0)),
			(a + b) * 0.5)
	parent.add_child(mi)
	return mi


func _cone(parent: Node3D, a: Vector3, b: Vector3, r_a: float, r_b: float,
		mat: Material, seg := 8) -> void:
	# Tapered: used for trunks and limbs, where a constant radius reads as pipework.
	var c := CylinderMesh.new()
	c.bottom_radius = r_a
	c.top_radius = r_b
	c.height = 1.0
	c.radial_segments = seg
	c.rings = 1
	# Capped. Uncapped tubes leave the parent branch's open end visible wherever a
	# thinner child starts on it, and the lit inner wall showed up in render 2 as
	# bright rings banding every trunk.
	c.cap_top = true
	c.cap_bottom = true
	var d := b - a
	var h := d.length()
	if h < 0.0005:
		return
	var yv := d / h
	var up := Vector3.UP if absf(yv.dot(Vector3.UP)) < 0.96 else Vector3.RIGHT
	var xv := up.cross(yv).normalized()
	var zv := xv.cross(yv)
	var mi := MeshInstance3D.new()
	mi.mesh = c
	mi.material_override = mat
	mi.transform = Transform3D(Basis(xv, yv, zv).scaled(Vector3(1, h, 1)),
			(a + b) * 0.5)
	parent.add_child(mi)


func _slab(parent: Node3D, x0: float, x1: float, z0: float, z1: float,
		y: float, t: float, mat: Material) -> MeshInstance3D:
	return _box(parent, Vector3(x1 - x0, t, z1 - z0),
			Vector3((x0 + x1) * 0.5, y - t * 0.5, (z0 + z1) * 0.5), mat)


# =========================================================================
# GROUND -- the cross-section. This is most of the recognition.
# =========================================================================
func _build_ground() -> void:
	var g := _grp("Ground")
	var z0 := -HALF
	var z1 := HALF

	# subsoil, so nothing shows sky underneath at a grazing angle
	_slab(g, -60, 60, z0 - 40, z1 + 40, -0.30, 1.0, m_soil)

	# carriageways, both sides, dropped to street level
	_slab(g, -ROAD_OUT, -(MED_W + 0.2), z0 - 30, z1 + 30, 0.0, 0.30, m_asphalt)
	_slab(g, MED_W + 0.2, ROAD_OUT, z0 - 30, z1 + 30, 0.0, 0.30, m_asphalt)

	# pavements outside the carriageways
	_slab(g, -WALK_OUT, -ROAD_OUT, z0 - 30, z1 + 30, DECK, 0.30, m_paving)
	_slab(g, ROAD_OUT, WALK_OUT, z0 - 30, z1 + 30, DECK, 0.30, m_paving)
	for sgn in [-1.0, 1.0]:
		_box(g, Vector3(0.28, 0.34, LENGTH + 60),
				Vector3(sgn * (ROAD_OUT + 0.14), DECK - 0.17, 0), m_kerb)

	# ---- THE MEDIAN, strip by strip, outside in
	# kerb
	for sgn in [-1.0, 1.0]:
		_box(g, Vector3(0.4, 0.40, LENGTH), Vector3(sgn * (MED_W + 0.0), -0.03, 0),
				m_kerb)
	# soil + hedge strip
	_slab(g, -MED_W, -HEDGE_IN, z0, z1, DECK - 0.02, 0.36, m_soil)
	_slab(g, HEDGE_IN, MED_W, z0, z1, DECK - 0.02, 0.36, m_soil)
	# bike lane (west side of the median, tinted, as in boulevard-06/07)
	_slab(g, -HEDGE_IN, -BIKE_IN, z0, z1, DECK, 0.36, m_bike)
	_box(g, Vector3(0.10, 0.03, LENGTH), Vector3(-BIKE_IN + 0.06, DECK + 0.005, 0),
			_std(Color(0.90, 0.90, 0.88), 0.75, 0.0))
	# paving, both sides of the ribbon
	_slab(g, -BIKE_IN, -TURF_W, z0, z1, DECK, 0.36, m_paving)
	_slab(g, TURF_W, HEDGE_IN, z0, z1, DECK, 0.36, m_paving)
	# the green ribbon -- but NOT through the cafe, where the median is all paving
	_slab(g, -TURF_W, TURF_W, z0, CAFE_Z0, DECK + 0.015, 0.38, m_turf)
	_slab(g, -TURF_W, TURF_W, CAFE_Z1, z1, DECK + 0.015, 0.38, m_turf)
	_slab(g, -TURF_W, TURF_W, CAFE_Z0, CAFE_Z1, DECK, 0.36, m_paving)

	# two pedestrian crossings cut through the hedge line
	for cz in [-24.0, 26.0]:
		_slab(g, -MED_W - 0.5, MED_W + 0.5, cz - 1.6, cz + 1.6, DECK, 0.40, m_paving)

	# a floor to stand on
	var sb := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var sh := BoxShape3D.new()
	sh.size = Vector3(140, 1.0, LENGTH + 80)
	cs.shape = sh
	cs.position = Vector3(0, DECK - 0.5, 0)
	sb.add_child(cs)
	g.add_child(sb)


# Clipped box hedge, built as ~2000 small spheres inside a box envelope rather than
# as a green cuboid. A cuboid casts a cuboid shadow and reads instantly as a prop;
# the lumpy silhouette is the entire difference.
func _build_hedges() -> void:
	var g := _grp("Hedges")
	var xf: Array[Transform3D] = []
	var cols: Array[Color] = []
	for sgn in [-1.0, 1.0]:
		var cx: float = sgn * (MED_W + HEDGE_IN) * 0.5
		var z := -HALF + 0.4
		while z < HALF - 0.4:
			# gaps at the crossings and at the cafe frontage
			var gap := absf(z - (-24.0)) < 2.6 or absf(z - 26.0) < 2.6
			if sgn > 0.0 and z > CAFE_Z0 - 1.0 and z < CAFE_Z1 + 1.0:
				gap = true
			if not gap:
				var hgt := _rng.randf_range(0.72, 0.92)
				for i in 22:
					var b := Vector3(
							cx + _rng.randf_range(-0.46, 0.46),
							DECK + _rng.randf_range(0.10, hgt),
							z + _rng.randf_range(-0.30, 0.30))
					var s := _rng.randf_range(0.15, 0.28)
					xf.append(Transform3D(Basis().rotated(Vector3.UP,
							_rng.randf_range(0, TAU)).scaled(
							Vector3(s * 1.25, s, s * 1.25)), b))
					var v := _rng.randf_range(0.72, 1.22)
					cols.append(Color(v, v * 1.04, v * 0.92))
			z += 0.42
	_multimesh(g, "Hedge", _sph_hedge, m_hedge, xf, cols)


func _multimesh(parent: Node3D, nm: String, mesh: Mesh, mat: Material,
		xf: Array[Transform3D], cols: Array[Color]) -> MultiMeshInstance3D:
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.use_colors = true
	mm.mesh = mesh
	mm.instance_count = xf.size()
	for i in xf.size():
		mm.set_instance_transform(i, xf[i])
		mm.set_instance_color(i, cols[i])
	var mi := MultiMeshInstance3D.new()
	mi.name = nm
	mi.multimesh = mm
	mi.material_override = mat
	parent.add_child(mi)
	return mi


# =========================================================================
# THE TREES -- the most important object on the boulevard.
#
# Grown, not placed: a recursive branch that carries direction, length and radius
# down three levels, jittering every segment. The three rules taken straight off
# his photographs and enforced here:
#   1. the base often FORKS into 2-3 trunks
#   2. limbs leave low and go SIDEWAYS -- the tilt at depth 0 is nearly horizontal
#   3. leaves live in ~50 separate clumps, never one canopy volume
# =========================================================================
func _build_trees() -> void:
	var g := _grp("Trees")
	# Two independent rows, one each side of the green ribbon, offset half a pitch
	# so the trees interlock rather than lining up in pairs. (First version walked
	# ONE z-cursor and alternated sides, which silently halved the row spacing and
	# gave 11 trees where 22 were asked for -- caught by the draw-call census.)
	var spots := []
	for side in [-1.0, 1.0]:
		var z: float = -HALF + 3.0 + (0.0 if side < 0.0 else 3.4)
		while z < HALF - 3.0:
			if not (z > CAFE_Z0 - 3.5 and z < CAFE_Z1 + 2.5 and side > 0.0):
				spots.append(Vector3(side * _rng.randf_range(1.3, 2.6), DECK, z))
			z += _rng.randf_range(6.2, 8.0)
	spots.shuffle()
	var n: int = mini(tree_count, spots.size())
	for i in n:
		var p: Vector3 = spots[i]
		# The hero: boulevard-06's tree, the one whose main limb lies across the
		# path at chest height. Placed where the first still will meet it.
		var hero: bool = absf(p.z - (-9.0)) < 6.0 and i % 3 == 0
		_tree(g, p, _rng.randf_range(0.88, 1.22), hero)
	# soil rings under every trunk are added by _tree itself


func _tree(parent: Node3D, pos: Vector3, s: float, hero: bool) -> void:
	var t := Node3D.new()
	t.position = pos
	t.rotation.y = _rng.randf_range(0.0, TAU)
	parent.add_child(t)

	# the ragged sandy patch the paving gives up around every trunk
	var ring := MeshInstance3D.new()
	var cm := CylinderMesh.new()
	cm.top_radius = _rng.randf_range(0.85, 1.30) * s
	cm.bottom_radius = cm.top_radius
	cm.height = 0.05
	cm.radial_segments = 14
	ring.mesh = cm
	ring.position = Vector3(0, 0.012, 0)
	ring.material_override = m_soil
	t.add_child(ring)

	var clumps: Array[Transform3D] = []
	var cols: Array[Color] = []
	var trunks := 1 if _rng.randf() < 0.55 else _rng.randi_range(2, 3)
	# THE FIRST RENDER SHOWED THIS WAS WRONG: trunks of radius 0.30-0.44 m with
	# 5-8 radial segments and a lean of up to 0.44 came out as crossed wooden
	# PLANKS. Real boulevard trunks are ~0.20 m radius at this height, close to
	# upright, and round enough at 3 m that the facets cannot be counted.
	var base_r: float = _rng.randf_range(0.17, 0.25) * s
	for k in trunks:
		var a := TAU * float(k) / float(trunks) + _rng.randf_range(-0.5, 0.5)
		var lean := _rng.randf_range(0.06, 0.22) * (1.0 + 0.6 * float(trunks - 1))
		var d := Vector3(cos(a) * lean, 1.0, sin(a) * lean).normalized()
		var start := Vector3(cos(a) * 0.07 * float(trunks - 1), 0.0,
				sin(a) * 0.07 * float(trunks - 1))
		# a short flare where the trunk leaves the ground, instead of the spiky
		# root fins the first version grew
		_cone(t, start + Vector3(0, -0.05, 0), start + d * 0.55,
				base_r * 1.55 / sqrt(float(trunks)), base_r / sqrt(float(trunks)),
				m_bark, 12)
		_branch(t, start + d * 0.55, d, _rng.randf_range(2.1, 2.8) * s,
				base_r / sqrt(float(trunks)), 3, clumps, cols, s)
	if hero:
		# THE LIMB THAT LIES ACROSS THE PATH. boulevard-06 is nothing but this.
		var a2 := _rng.randf_range(0.0, TAU)
		_branch(t, Vector3(0, 1.25 * s, 0),
				Vector3(cos(a2), 0.09, sin(a2)).normalized(),
				5.4 * s, base_r * 0.62, 2, clumps, cols, s)
	_multimesh(t, "Canopy", _sph_leaf, m_leaf, clumps, cols)


# Radial segments by level: a trunk you can stand next to needs 12, a twig needs 4.
const RING_BY_DEPTH := [4, 5, 8, 12]


func _branch(t: Node3D, from: Vector3, dir: Vector3, length: float, r: float,
		depth: int, clumps: Array[Transform3D], cols: Array[Color],
		s: float) -> void:
	var segs := 4 if depth >= 2 else 3
	var p := from
	var d := dir.normalized()
	var rr := r
	var ring: int = RING_BY_DEPTH[clampi(depth, 0, 3)]
	var path: Array[Vector3] = [p]
	for i in segs:
		var j: float = 0.20 if depth >= 2 else 0.36
		# gnarl: jitter the direction each segment, and let old wood sag while
		# young wood reaches up. A straight cylinder chain reads as scaffolding.
		var grav: float = -0.14 if depth >= 2 else 0.12
		var nd := (d + Vector3(_rng.randf_range(-j, j), _rng.randf_range(-j, j) * 0.6
				+ grav * 0.4, _rng.randf_range(-j, j))).normalized()
		var q := p + nd * (length / float(segs))
		var r2 := rr * _rng.randf_range(0.78, 0.88)
		_cone(t, p, q, rr, r2, m_bark, ring)
		p = q
		d = nd
		rr = r2
		path.append(p)
	if depth <= 0:
		# FOLIAGE ALONG THE TWIG, NOT A BALL AT THE END.
		# Version one hung 2-4 clumps of radius up to 1.15 m off each tip. Scaled
		# up by the branching, that is a canopy of 2 m balloons: it sealed the sky,
		# killed every scrap of dapple and left the paving flat black (measured
		# frame mean 0.126). The dapple IS the boulevard, so the clumps are now
		# ~0.3 m and there are ten times as many, strung along the twig where
		# leaves actually grow.
		# Fewer per twig than render 2 but spread over a longer branch: the crown
		# needs HOLES. A solid crown is the balloon problem again in miniature.
		for k in _rng.randi_range(11, 16):
			var f := _rng.randf_range(0.05, 1.02)
			var seg: int = clampi(int(f * float(segs)), 0, segs - 1)
			var at: Vector3 = path[seg].lerp(path[seg + 1],
					f * float(segs) - float(seg))
			_clump(clumps, cols, at + Vector3(_rng.randf_range(-0.36, 0.36),
					_rng.randf_range(-0.22, 0.34), _rng.randf_range(-0.36, 0.36)),
					_rng.randf_range(0.22, 0.42) * s)
		# always cover the tip, or the twig sticks out past the foliage as the
		# black antenna that render 2 grew all over the crowns
		_clump(clumps, cols, path[segs] + Vector3(0, 0.04, 0),
				_rng.randf_range(0.28, 0.40) * s)
		return
	var kids := _rng.randi_range(2, 3)
	for k in kids:
		var axis := Vector3(_rng.randf_range(-1, 1), _rng.randf_range(-1, 1),
				_rng.randf_range(-1, 1)).normalized()
		var ang := _rng.randf_range(0.42, 1.05)
		var nd2 := d.rotated(axis, ang).normalized()
		# never let a child dive into the ground
		if nd2.y < -0.30:
			nd2.y = -0.30
			nd2 = nd2.normalized()
		_branch(t, p, nd2, length * _rng.randf_range(0.52, 0.70),
				rr * _rng.randf_range(0.58, 0.72), depth - 1, clumps, cols, s)
	# Leaves on the way out, not only at the tips. Render 3 put foliage only at
	# depth 0 and the mid-crown came back as a yard of bare scaffolding poles.
	if depth <= 2:
		for k in (6 if depth == 1 else 3):
			_clump(clumps, cols, p + Vector3(_rng.randf_range(-0.55, 0.55),
					_rng.randf_range(-0.15, 0.45), _rng.randf_range(-0.55, 0.55)),
					_rng.randf_range(0.24, 0.44) * s)


func _clump(clumps: Array[Transform3D], cols: Array[Color], at: Vector3,
		rad: float) -> void:
	var b := Basis()
	b = b.rotated(Vector3.UP, _rng.randf_range(0, TAU))
	b = b.rotated(Vector3.RIGHT, _rng.randf_range(-0.7, 0.7))
	b = b.scaled(Vector3(rad * 2.0 * _rng.randf_range(0.9, 1.5),
			rad * 2.0 * _rng.randf_range(0.45, 0.75),
			rad * 2.0 * _rng.randf_range(0.9, 1.5)))
	clumps.append(Transform3D(b, at))
	# lighter at the top of the crown, darker deep inside: fake self-shading that
	# survives even where the shadow map cannot resolve a single clump
	var v: float = clampf(0.66 + at.y * 0.050 + _rng.randf_range(-0.16, 0.16),
			0.42, 1.30)
	cols.append(Color(v * 1.02, v, v * 0.78))


# =========================================================================
# BENCHES, LAMPS, BINS, RACKS
# =========================================================================
func _bench(parent: Node3D, at: Vector3, yaw: float) -> void:
	var b := Node3D.new()
	b.position = at
	b.rotation.y = yaw
	parent.add_child(b)
	# black iron ends, with the curl that every one of his benches has
	for sx in [-1.0, 1.0]:
		var x: float = sx * 0.82
		_box(b, Vector3(0.055, 0.44, 0.06), Vector3(x, 0.22, 0.20), m_iron)
		_box(b, Vector3(0.055, 0.44, 0.06), Vector3(x, 0.22, -0.20), m_iron)
		_box(b, Vector3(0.055, 0.06, 0.52), Vector3(x, 0.43, 0.0), m_iron)
		# armrest, sloping back
		_box(b, Vector3(0.05, 0.05, 0.46), Vector3(x, 0.68, 0.02), m_iron,
				Vector3(-0.10, 0, 0))
		_box(b, Vector3(0.05, 0.28, 0.05), Vector3(x, 0.55, 0.24), m_iron)
		_box(b, Vector3(0.05, 0.52, 0.05), Vector3(x, 0.72, -0.20), m_iron,
				Vector3(0.22, 0, 0))
	# seat: 4 slats with gaps
	for i in 4:
		_box(b, Vector3(1.70, 0.035, 0.11),
				Vector3(0, 0.455, 0.20 - float(i) * 0.135), m_wood_dark)
	# back: 4 slats, raked
	for i in 4:
		_box(b, Vector3(1.70, 0.105, 0.032),
				Vector3(0, 0.60 + float(i) * 0.135, -0.22 - float(i) * 0.048),
				m_wood_dark, Vector3(0.22, 0, 0))


func _lamp(parent: Node3D, at: Vector3) -> void:
	var l := Node3D.new()
	l.position = at
	parent.add_child(l)
	_cone(l, Vector3.ZERO, Vector3(0, 4.3, 0), 0.085, 0.055, m_iron, 8)
	_box(l, Vector3(0.30, 0.20, 0.30), Vector3(0, 0.12, 0), m_iron)
	# the 1930s swan neck
	var prev := Vector3(0, 4.3, 0)
	for i in range(1, 6):
		var a := PI * 0.5 * float(i) / 5.0
		var p := Vector3(sin(a) * 0.75, 4.3 + (1.0 - cos(a)) * 0.42, 0)
		_tube(l, prev, p, 0.045, m_iron, 6)
		prev = p
	var shade := MeshInstance3D.new()
	var cm := CylinderMesh.new()
	cm.top_radius = 0.06
	cm.bottom_radius = 0.30
	cm.height = 0.24
	cm.radial_segments = 12
	shade.mesh = cm
	shade.position = prev + Vector3(0, -0.10, 0)
	shade.material_override = m_iron
	l.add_child(shade)
	var lamp := OmniLight3D.new()
	lamp.position = prev + Vector3(0, -0.24, 0)
	lamp.light_color = Color(1.0, 0.80, 0.52)
	lamp.light_energy = 0.0        # late afternoon: the lamps are not lit yet
	lamp.omni_range = 9.0
	l.add_child(lamp)


func _bike_rack(parent: Node3D, at: Vector3, yaw: float, bikes: int) -> void:
	var r := Node3D.new()
	r.position = at
	r.rotation.y = yaw
	parent.add_child(r)
	var yellow := _std(Color(0.760, 0.600, 0.140), 0.44, 0.70)
	for i in 3:
		var x := -1.0 + float(i) * 1.0
		var prev := Vector3(x, 0, -0.35)
		for k in range(1, 9):
			var a := PI * float(k) / 8.0
			var p := Vector3(x, sin(a) * 0.72, -cos(a) * 0.35)
			_tube(r, prev, p, 0.028, yellow, 6)
			prev = p
	for i in bikes:
		_bicycle(r, Vector3(-1.0 + float(i) * 0.62 + _rng.randf_range(-0.1, 0.1),
				0, _rng.randf_range(-0.15, 0.15)),
				_rng.randf_range(-0.18, 0.18) + PI * 0.5)


func _bicycle(parent: Node3D, at: Vector3, yaw: float) -> void:
	var b := Node3D.new()
	b.position = at
	b.rotation = Vector3(0, yaw, _rng.randf_range(-0.09, 0.09))
	parent.add_child(b)
	var tyre := TorusMesh.new()
	tyre.inner_radius = 0.30
	tyre.outer_radius = 0.34
	tyre.rings = 20
	tyre.ring_segments = 6
	for zz in [-0.53, 0.53]:
		var w := MeshInstance3D.new()
		w.mesh = tyre
		w.position = Vector3(0, 0.34, zz)
		w.rotation = Vector3(0, 0, PI * 0.5)
		w.material_override = m_rubber
		b.add_child(w)
		for k in 6:
			var a := PI * float(k) / 6.0
			_tube(b, Vector3(0, 0.34, zz) + Vector3(0, cos(a), sin(a)) * 0.31,
					Vector3(0, 0.34, zz) - Vector3(0, cos(a), sin(a)) * 0.31,
					0.006, m_steel, 4)
	var frame := _std(Color(0.62, 0.16, 0.14), 0.22, 0.30)
	var bb := Vector3(0, 0.29, 0.05)
	var head := Vector3(0, 0.92, -0.44)
	var seat := Vector3(0, 0.86, 0.24)
	_tube(b, bb, head, 0.021, frame, 6)
	_tube(b, bb, seat, 0.021, frame, 6)
	_tube(b, head, seat, 0.019, frame, 6)
	_tube(b, head, Vector3(0, 0.34, -0.53), 0.017, frame, 6)
	_tube(b, bb, Vector3(0, 0.34, 0.53), 0.017, frame, 6)
	_tube(b, seat, Vector3(0, 0.34, 0.53), 0.015, frame, 6)
	_tube(b, head + Vector3(0, 0.06, 0), head + Vector3(0, 0.14, -0.02), 0.016,
			m_steel, 6)
	_tube(b, head + Vector3(-0.22, 0.14, -0.02), head + Vector3(0.22, 0.14, -0.02),
			0.014, m_steel, 6)
	_box(b, Vector3(0.09, 0.05, 0.24), seat + Vector3(0, 0.09, 0.01), m_wood_dark)


func _bin(parent: Node3D, at: Vector3) -> void:
	var n := Node3D.new()
	n.position = at
	parent.add_child(n)
	var c := CylinderMesh.new()
	c.top_radius = 0.24
	c.bottom_radius = 0.20
	c.height = 0.72
	c.radial_segments = 14
	c.cap_top = false
	var mi := MeshInstance3D.new()
	mi.mesh = c
	mi.position = Vector3(0, 0.72, 0)
	mi.material_override = m_iron
	n.add_child(mi)
	_cone(n, Vector3.ZERO, Vector3(0, 0.40, 0), 0.045, 0.045, m_iron, 6)


func _build_benches_and_furniture() -> void:
	var g := _grp("Furniture")
	var z := -HALF + 5.0
	while z < HALF - 4.0:
		if not (z > CAFE_Z0 - 2.0 and z < CAFE_Z1 + 1.0):
			# benches face the walk, alternating which side of the ribbon
			var sgn: float = 1.0 if _rng.randf() < 0.5 else -1.0
			var x: float = sgn * _rng.randf_range(1.5, 3.0)
			_bench(g, Vector3(x, DECK, z), (0.0 if sgn > 0.0 else PI)
					+ _rng.randf_range(-0.12, 0.12))
		z += _rng.randf_range(9.0, 13.0)
	for lz in [-30.0, -12.0, 6.0, 24.0, 34.0]:
		_lamp(g, Vector3(-4.3, DECK, lz))
	for bz in [-27.0, -4.0, 30.0]:
		_bin(g, Vector3(3.6, DECK, bz))
	_bike_rack(g, Vector3(3.9, DECK, CAFE_Z0 + 3.0), 0.0, 4)
	_bike_rack(g, Vector3(3.9, DECK, CAFE_Z1 - 3.0), 0.0, 3)
	_bike_rack(g, Vector3(-3.4, DECK, -16.0), PI, 2)


# =========================================================================
# CAFE CLAUDE -- a boulevard kiosk with canvas sails. boulevard-04 and -05.
# =========================================================================
func _sail(parent: Node3D, at: Vector3, size: float, peak: float,
		corner: float) -> void:
	# A hypar canvas: high at the mast, low and sagging at the four corners.
	# Built as a real ArrayMesh because the whole point is the SAG -- a flat quad
	# on a pole is an umbrella from a menu, not the shade over a Tel Aviv kiosk.
	var n := 9
	var verts := PackedVector3Array()
	var uvs := PackedVector2Array()
	var idx := PackedInt32Array()
	var h := size * 0.5
	for j in n:
		for i in n:
			var u := float(i) / float(n - 1)
			var v := float(j) / float(n - 1)
			var px := lerpf(-h, h, u)
			var pz := lerpf(-h, h, v)
			# radial fall from the mast, plus a catenary sag along each edge
			var rad: float = maxf(absf(px), absf(pz)) / h
			var y: float = lerpf(peak, corner, pow(rad, 0.85))
			var sag: float = sin(u * PI) * sin(v * PI)
			y -= sag * 0.0
			# sag the free edges downward between the corners
			var eu: float = sin(u * PI)
			var ev: float = sin(v * PI)
			if rad > 0.62:
				y -= (rad - 0.62) / 0.38 * (eu * ev + 0.15) * size * 0.10
			verts.append(Vector3(px, y, pz))
			uvs.append(Vector2(u, v))
	for j in n - 1:
		for i in n - 1:
			var a := j * n + i
			idx.append(a)
			idx.append(a + n)
			idx.append(a + 1)
			idx.append(a + 1)
			idx.append(a + n)
			idx.append(a + n + 1)
	var arr := []
	arr.resize(Mesh.ARRAY_MAX)
	arr[Mesh.ARRAY_VERTEX] = verts
	arr[Mesh.ARRAY_TEX_UV] = uvs
	arr[Mesh.ARRAY_INDEX] = idx
	var am := ArrayMesh.new()
	am.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
	# normals from the geometry, so the fabric shades as a curved surface
	var st := SurfaceTool.new()
	st.create_from(am, 0)
	st.generate_normals()
	var final_mesh := st.commit()
	var mi := MeshInstance3D.new()
	mi.mesh = final_mesh
	mi.position = at
	mi.material_override = m_canvas
	parent.add_child(mi)
	# THE MAST. Version one ran it from at+(0,-peak,0) to at+(0,0.06,0) -- and the
	# sails are called with peak = 0.0, so that was a 6 cm stub and the canvas
	# floated unsupported in the first render. It runs from the ground now.
	_cone(parent, Vector3(at.x, DECK, at.z), at + Vector3(0, 0.10, 0), 0.10,
			0.06, m_steel, 12)
	for sx in [-1.0, 1.0]:
		for sz in [-1.0, 1.0]:
			_tube(parent, at + Vector3(sx * h, corner, sz * h),
					at + Vector3(sx * h * 1.05, corner - 1.1, sz * h * 1.05),
					0.012, m_steel, 4)


func _cafe_table(parent: Node3D, at: Vector3, chairs: int) -> void:
	var t := Node3D.new()
	t.position = at
	t.rotation.y = _rng.randf_range(0, TAU)
	parent.add_child(t)
	var top := MeshInstance3D.new()
	var c := CylinderMesh.new()
	c.top_radius = 0.34
	c.bottom_radius = 0.34
	c.height = 0.035
	c.radial_segments = 24
	top.mesh = c
	top.position = Vector3(0, 0.735, 0)
	top.material_override = m_marble
	t.add_child(top)
	_cone(t, Vector3(0, 0.02, 0), Vector3(0, 0.72, 0), 0.035, 0.030, m_iron, 10)
	var base := MeshInstance3D.new()
	var bc := CylinderMesh.new()
	bc.top_radius = 0.20
	bc.bottom_radius = 0.23
	bc.height = 0.035
	bc.radial_segments = 16
	base.mesh = bc
	base.position = Vector3(0, 0.018, 0)
	base.material_override = m_iron
	t.add_child(base)
	for i in chairs:
		var a := TAU * float(i) / float(chairs) + _rng.randf_range(-0.35, 0.35)
		_chair(t, Vector3(cos(a) * _rng.randf_range(0.62, 0.78), 0,
				sin(a) * _rng.randf_range(0.62, 0.78)), -a + PI * 0.5
				+ _rng.randf_range(-0.3, 0.3))
	# something on the table -- a cup and a glass. Small, and it is what says
	# somebody is HERE, as opposed to furniture waiting for opening time.
	if _rng.randf() < 0.75:
		_cone(t, Vector3(0.10, 0.752, 0.05), Vector3(0.10, 0.83, 0.05), 0.035,
				0.042, m_cloth_light, 10)
	if _rng.randf() < 0.55:
		_cone(t, Vector3(-0.12, 0.752, -0.06), Vector3(-0.12, 0.90, -0.06), 0.032,
				0.038, _std(Color(0.86, 0.78, 0.52), 0.10, 0.0), 10)


func _chair(parent: Node3D, at: Vector3, yaw: float) -> void:
	var c := Node3D.new()
	c.position = at
	c.rotation.y = yaw
	parent.add_child(c)
	for sx in [-1.0, 1.0]:
		for sz in [-1.0, 1.0]:
			_cone(c, Vector3(sx * 0.19, 0, sz * 0.19),
					Vector3(sx * 0.16, 0.44, sz * 0.16), 0.018, 0.016, m_wood, 6)
	for i in 4:
		_box(c, Vector3(0.38, 0.018, 0.062),
				Vector3(0, 0.45, -0.15 + float(i) * 0.10), m_wood)
	# bentwood back: two uprights and three rails
	for sx in [-1.0, 1.0]:
		_cone(c, Vector3(sx * 0.16, 0.44, -0.16), Vector3(sx * 0.15, 0.88, -0.22),
				0.016, 0.014, m_wood, 6)
	for i in 3:
		_box(c, Vector3(0.31, 0.045, 0.016),
				Vector3(0, 0.66 + float(i) * 0.11, -0.185 - float(i) * 0.008),
				m_wood)


func _build_cafe() -> void:
	var g := _grp("Cafe")
	var cz := (CAFE_Z0 + CAFE_Z1) * 0.5
	var kx := 2.4                     # the kiosk sits east of the ribbon
	var kw := 3.6                     # across
	var kd := 7.2                     # along
	var kh := 3.05

	# plinth + body
	_slab(g, kx - kw * 0.5 - 0.5, kx + kw * 0.5 + 0.5, cz - kd * 0.5 - 0.5,
			cz + kd * 0.5 + 0.5, DECK + 0.06, 0.30, m_stone)
	_body(g, Vector3(kw, kh, kd), Vector3(kx, DECK + 0.06 + kh * 0.5, cz),
			m_plaster_warm)
	# dark recessed interior showing through the serving openings
	_box(g, Vector3(kw - 0.30, 1.60, kd - 0.40),
			Vector3(kx, DECK + 1.30, cz), _std(Color(0.10, 0.085, 0.072), 0.9, 0.0))
	# serving openings, both long faces: reveal, counter shelf, brass rail
	for sx in [-1.0, 1.0]:
		var fx: float = kx + sx * kw * 0.5
		_box(g, Vector3(0.10, 1.10, kd - 0.9), Vector3(fx, DECK + 1.45, cz),
				_std(Color(0.055, 0.05, 0.045), 0.9, 0.0))
		_box(g, Vector3(0.46, 0.06, kd - 0.7), Vector3(fx + sx * 0.16,
				DECK + 0.90, cz), m_wood)
		_tube(g, Vector3(fx + sx * 0.30, DECK + 0.99, cz - kd * 0.5 + 0.35),
				Vector3(fx + sx * 0.30, DECK + 0.99, cz + kd * 0.5 - 0.35),
				0.018, m_brass, 8)
		# mullions
		for i in 5:
			_box(g, Vector3(0.12, 1.10, 0.05), Vector3(fx, DECK + 1.45,
					cz - kd * 0.5 + 0.45 + float(i) * (kd - 0.9) / 4.0), m_wood_dark)
		# the fascia sign board
		_box(g, Vector3(0.10, 0.42, kd - 0.6), Vector3(fx + sx * 0.05,
				DECK + 2.34, cz), m_wood_dark)
	# things on the counter
	for i in 7:
		_cone(g, Vector3(kx - kw * 0.5 - 0.10, DECK + 0.93,
				cz - 2.6 + float(i) * 0.85),
				Vector3(kx - kw * 0.5 - 0.10, DECK + 1.12,
				cz - 2.6 + float(i) * 0.85), 0.035, 0.030,
				_std(Color(0.62, 0.72, 0.55), 0.12, 0.0), 8)
	# roof slab with a real overhang, and its shadow line
	_box(g, Vector3(kw + 1.3, 0.22, kd + 1.3),
			Vector3(kx, DECK + 0.06 + kh + 0.11, cz), m_plaster)
	_box(g, Vector3(kw + 1.5, 0.10, kd + 1.5),
			Vector3(kx, DECK + 0.06 + kh + 0.27, cz), m_shade)
	# warm interior light -- the kiosk should already be glowing at this hour
	var inner := OmniLight3D.new()
	inner.position = Vector3(kx, DECK + 1.9, cz)
	inner.light_color = Color(1.0, 0.78, 0.50)
	inner.light_energy = 3.2
	inner.omni_range = 6.0
	inner.omni_attenuation = 1.6
	inner.shadow_enabled = false
	g.add_child(inner)

	# --- the shade sails, west of the kiosk over the tables
	for i in 3:
		_sail(g, Vector3(-1.35, DECK + 3.45, cz - 5.2 + float(i) * 5.2),
				5.0, 0.0, -0.95)

	# --- tables under them
	var placed := 0
	for i in 9:
		var tx := _rng.randf_range(-3.3, 0.5)
		var tz := cz + _rng.randf_range(-7.0, 7.0)
		_cafe_table(g, Vector3(tx, DECK, tz), _rng.randi_range(2, 3))
		placed += 1
	# a couple of tables on the far side too, in the sun
	_cafe_table(g, Vector3(4.5, DECK, cz - 2.2), 2)
	_cafe_table(g, Vector3(4.5, DECK, cz + 2.4), 2)
	# planters, as in boulevard-04
	for pz in [cz - 4.4, cz + 4.6]:
		var pot := MeshInstance3D.new()
		var pc := CylinderMesh.new()
		pc.top_radius = 0.42
		pc.bottom_radius = 0.34
		pc.height = 0.62
		pc.radial_segments = 18
		pot.mesh = pc
		pot.position = Vector3(kx - 2.9, DECK + 0.31, pz)
		pot.material_override = m_stone
		g.add_child(pot)
		var xf: Array[Transform3D] = []
		var cs: Array[Color] = []
		for k in 26:
			var a := _rng.randf_range(0, TAU)
			var rr := _rng.randf_range(0.0, 0.40)
			var s2 := _rng.randf_range(0.18, 0.34)
			xf.append(Transform3D(Basis().rotated(Vector3.UP, a).scaled(
					Vector3(s2, s2 * 0.8, s2)),
					Vector3(kx - 2.9 + cos(a) * rr, DECK + 0.62
					+ _rng.randf_range(0.0, 0.55), pz + sin(a) * rr)))
			var v := _rng.randf_range(0.7, 1.2)
			cs.append(Color(v, v * 1.05, v * 0.85))
		_multimesh(g, "Planter%d" % int(pz), _sph_hedge, m_hedge, xf, cs)


# =========================================================================
# FACADES -- 1930s International Style, both sides, with real depth.
# What makes them read: the window band is RECESSED 0.22 m, the balconies have
# rounded ends, and about half the openings carry louvred shutters. Flat glass
# rectangles painted on a wall never look like anything.
# =========================================================================
const STOREY := 3.15


func _build_facades() -> void:
	var g := _grp("Facades")
	for side in [-1.0, 1.0]:
		var z := -HALF - 6.0
		while z < HALF + 6.0:
			var w := _rng.randf_range(11.0, 17.0)
			_bauhaus(g, side, z + w * 0.5, w)
			z += w + _rng.randf_range(0.6, 1.6)


func _bauhaus(g: Node3D, side: float, cz: float, w: float) -> void:
	var storeys := _rng.randi_range(3, 4)
	var depth := _rng.randf_range(11.0, 15.0)
	var front: float = side * WALK_OUT
	var cx: float = front + side * depth * 0.5
	var h: float = float(storeys) * STOREY
	var ground_h := 3.6
	var b := Node3D.new()
	b.position = Vector3(cx, 0, cz)
	g.add_child(b)
	var inward: float = -side          # +1 for the west block, -1 for the east

	# ground floor: a stone plinth with recessed shopfronts
	_body(b, Vector3(depth, ground_h, w), Vector3(0, ground_h * 0.5, 0), m_stone)
	var fx: float = inward * depth * 0.5
	_box(b, Vector3(0.5, ground_h - 1.0, w - 1.0),
			Vector3(fx + inward * 0.22, 1.55, 0), m_shopglass)
	var shops := int(w / 4.2)
	for i in shops:
		var sz: float = -w * 0.5 + w * (float(i) + 0.5) / float(shops)
		_box(b, Vector3(0.34, ground_h - 1.0, 0.22), Vector3(fx, 1.55, sz),
				m_wood_dark)
		# awning over every second shop
		if i % 2 == 0:
			_box(b, Vector3(1.5, 0.06, w / float(shops) - 0.5),
					Vector3(fx + inward * 0.75, 2.95, sz),
					_std(Color(0.55, 0.20, 0.16), 0.85, 0.0),
					Vector3(0, 0, inward * 0.16))
	_box(b, Vector3(depth, 0.55, w), Vector3(0, ground_h + 0.10, 0), m_shade)

	# the upper mass, set back a little from the shopfront line
	var setback := 0.30
	_body(b, Vector3(depth - setback, h, w),
			Vector3(inward * setback * 0.5, ground_h + 0.4 + h * 0.5, 0),
			m_plaster)
	var face: float = inward * (depth * 0.5 - setback)

	for s in storeys:
		var y: float = ground_h + 0.4 + float(s) * STOREY
		# RIBBON WINDOW, recessed. The recess is the whole trick: it gives the
		# facade a hard shadow line at this sun angle, which is what horizontal
		# banding actually looks like on Rothschild.
		_box(b, Vector3(0.44, STOREY * 0.50, w * 0.86),
				Vector3(face - inward * 0.22, y + STOREY * 0.60, 0), m_glass)
		# reveal: head, sill, and the two returns
		_box(b, Vector3(0.30, 0.16, w * 0.88),
				Vector3(face - inward * 0.06, y + STOREY * 0.86, 0), m_shade)
		_box(b, Vector3(0.34, 0.12, w * 0.88),
				Vector3(face - inward * 0.04, y + STOREY * 0.33, 0), m_plaster)
		# glazing bars
		var bays := int(w / 2.4)
		for i in bays:
			var sz2: float = -w * 0.43 + w * 0.86 * float(i) / float(maxi(bays - 1, 1))
			_box(b, Vector3(0.20, STOREY * 0.50, 0.07),
					Vector3(face - inward * 0.13, y + STOREY * 0.60, sz2),
					m_plaster)
			# louvred shutters on roughly half the bays -- the tris in this loop
			# are the single best-spent triangles on the whole building
			if _rng.randf() < 0.45:
				var open := _rng.randf_range(0.25, 1.0)
				var slats := int(9.0 * open)
				for k in slats:
					_box(b, Vector3(0.05, 0.036, w * 0.86 / float(bays) - 0.14),
							Vector3(face - inward * 0.05,
							y + STOREY * 0.84 - float(k) * 0.055, sz2 + 1.0),
							m_shade, Vector3(0, 0, inward * 0.35))

		# BALCONY: deep, cantilevered, with a rounded end and a horizontal railing
		if s > 0 or _rng.randf() < 0.5:
			var bw: float = w * _rng.randf_range(0.34, 0.52)
			var bz: float = _rng.randf_range(-w * 0.22, w * 0.22)
			var bd := 1.85
			_box(b, Vector3(bd, 0.20, bw),
					Vector3(face + inward * bd * 0.5, y + STOREY * 0.24, bz),
					m_plaster)
			# rounded end
			var rend := MeshInstance3D.new()
			var rc := CylinderMesh.new()
			rc.top_radius = bd * 0.5
			rc.bottom_radius = bd * 0.5
			rc.height = 0.20
			rc.radial_segments = 20
			rend.mesh = rc
			rend.position = Vector3(face + inward * bd * 0.5,
					y + STOREY * 0.24, bz + bw * 0.5)
			rend.material_override = m_plaster
			b.add_child(rend)
			# A SOLID PARAPET, not a bar railing. Thin bars vanish by 20 m and the
			# first render's balconies read as bare shelves. A rendered plaster
			# parapet with a pipe rail on top is both what Rothschild actually has
			# and the thing that still reads as a balcony from across the street.
			var rail := _std(Color(0.90, 0.88, 0.84), 0.50, 0.25)
			var ends := [
				[Vector3(face + inward * bd, y + STOREY * 0.24 + 0.52, bz), false],
				[Vector3(face + inward * bd * 0.5, y + STOREY * 0.24 + 0.52,
						bz + bw * 0.5), true],
				[Vector3(face + inward * bd * 0.5, y + STOREY * 0.24 + 0.52,
						bz - bw * 0.5), true],
			]
			for e2 in ends:
				var along: bool = e2[1]
				var sz3 := Vector3(bd if along else 0.10, 0.86,
						0.10 if along else bw + 0.10)
				_box(b, sz3, e2[0], m_plaster)
				_box(b, Vector3(sz3.x + 0.06, 0.06, sz3.z + 0.06),
						e2[0] + Vector3(0, 0.46, 0), rail)
			_box(b, Vector3(bd, 0.06, 0.05),
					Vector3(face + inward * bd * 0.5, y + STOREY * 0.24 - 0.13, bz),
					m_shade)

	# the "thermometer": the glazed stair tower, the one vertical gesture
	var tz: float = w * _rng.randf_range(-0.34, 0.34)
	_box(b, Vector3(1.1, h + 1.4, 3.4),
			Vector3(face + inward * 0.40, ground_h + 0.4 + (h + 1.4) * 0.5, tz),
			m_plaster)
	for s in storeys + 1:
		_box(b, Vector3(0.16, STOREY * 0.66, 2.3),
				Vector3(face + inward * 0.92,
				ground_h + 0.4 + float(s) * STOREY + STOREY * 0.5, tz), m_glass)
	# parapet and the roof tanks
	_box(b, Vector3(depth - setback + 0.2, 0.70, w + 0.2),
			Vector3(inward * setback * 0.5, ground_h + 0.4 + h + 0.35, 0),
			m_plaster)
	for i in _rng.randi_range(2, 4):
		var tk := MeshInstance3D.new()
		var tc := CylinderMesh.new()
		tc.top_radius = 0.50
		tc.bottom_radius = 0.50
		tc.height = 1.5
		tc.radial_segments = 12
		tk.mesh = tc
		tk.position = Vector3(_rng.randf_range(-depth * 0.25, depth * 0.25),
				ground_h + 0.4 + h + 1.2, _rng.randf_range(-w * 0.3, w * 0.3))
		tk.rotation = Vector3(0, 0, PI * 0.5)
		tk.material_override = m_steel
		b.add_child(tk)
	# downpipe
	_cone(b, Vector3(face + inward * 0.06, ground_h + 0.4, w * 0.46),
			Vector3(face + inward * 0.06, ground_h + 0.4 + h, w * 0.46),
			0.055, 0.055, m_iron, 6)


# =========================================================================
# VEHICLES -- a few period cars at the kerb. Kept low in number: this is the
# boulevard at 5 pm, and the median is the subject.
# =========================================================================
func _car(parent: Node3D, at: Vector3, yaw: float, col: Color) -> void:
	var c := Node3D.new()
	c.position = at
	c.rotation.y = yaw
	parent.add_child(c)
	var paint := m_paint_dark.duplicate()
	paint.albedo_color = col
	# 1930s saloon: long bonnet, upright cabin, separate swept wings
	_box(c, Vector3(1.62, 0.52, 4.20), Vector3(0, 0.66, 0), paint)
	_box(c, Vector3(1.50, 0.62, 1.90), Vector3(0, 1.20, -0.20), paint)
	_box(c, Vector3(1.30, 0.44, 1.70), Vector3(0, 1.03, 1.28), paint)   # bonnet
	_box(c, Vector3(1.34, 0.40, 1.60), Vector3(0, 1.34, -0.22), m_glass)
	_box(c, Vector3(1.10, 0.28, 0.14), Vector3(0, 1.40, 0.62), m_glass)
	# running boards + wings
	for sx in [-1.0, 1.0]:
		_box(c, Vector3(0.30, 0.08, 2.10), Vector3(sx * 0.86, 0.44, 0.0), m_iron)
		for zz in [1.42, -1.36]:
			var wg := MeshInstance3D.new()
			var t := TorusMesh.new()
			t.inner_radius = 0.34
			t.outer_radius = 0.52
			t.rings = 14
			t.ring_segments = 5
			wg.mesh = t
			wg.position = Vector3(sx * 0.80, 0.50, zz)
			wg.rotation = Vector3(0, 0, PI * 0.5)
			wg.material_override = paint
			c.add_child(wg)
			var wheel := MeshInstance3D.new()
			var wc := CylinderMesh.new()
			wc.top_radius = 0.36
			wc.bottom_radius = 0.36
			wc.height = 0.20
			wc.radial_segments = 16
			wheel.mesh = wc
			wheel.position = Vector3(sx * 0.78, 0.36, zz)
			wheel.rotation = Vector3(0, 0, PI * 0.5)
			wheel.material_override = m_rubber
			c.add_child(wheel)
	_cone(c, Vector3(0, 1.00, 2.14), Vector3(0, 1.00, 2.24), 0.16, 0.16,
			m_steel, 10)   # headlamp mount bar
	for sx in [-1.0, 1.0]:
		var lamp := MeshInstance3D.new()
		var lc := CylinderMesh.new()
		lc.top_radius = 0.17
		lc.bottom_radius = 0.13
		lc.height = 0.20
		lc.radial_segments = 14
		lamp.mesh = lc
		lamp.position = Vector3(sx * 0.52, 1.02, 2.16)
		lamp.rotation = Vector3(PI * 0.5, 0, 0)
		lamp.material_override = m_steel
		c.add_child(lamp)


func _build_vehicles() -> void:
	var g := _grp("Vehicles")
	var cols := [Color(0.055, 0.058, 0.062), Color(0.10, 0.16, 0.12),
			Color(0.22, 0.10, 0.08), Color(0.30, 0.29, 0.26)]
	var spots := [
		[Vector3(-8.4, 0.30, -18.0), 0.0], [Vector3(-8.4, 0.30, -11.0), 0.0],
		[Vector3(-8.4, 0.30, 14.0), 0.0], [Vector3(8.4, 0.30, 5.0), PI],
		[Vector3(8.4, 0.30, -2.0), PI], [Vector3(8.4, 0.30, 29.0), PI],
	]
	for i in spots.size():
		_car(g, spots[i][0], spots[i][1] + _rng.randf_range(-0.03, 0.03),
				cols[i % cols.size()])


# =========================================================================
# PEOPLE -- deliberately few and deliberately simple. They are here because
# "כולם נפגשים בקפה" is the point of the place; they are NOT here to be looked
# at closely, and the report says so honestly.
# =========================================================================
func _person(parent: Node3D, at: Vector3, yaw: float, seated: bool) -> void:
	var p := Node3D.new()
	p.position = at
	p.rotation.y = yaw
	parent.add_child(p)
	var shirt := m_cloth_light.duplicate()
	shirt.albedo_color = Color.from_hsv(_rng.randf(), _rng.randf_range(0.05, 0.35),
			_rng.randf_range(0.55, 0.92))
	var trous := m_cloth_dark.duplicate()
	trous.albedo_color = Color.from_hsv(_rng.randf(), _rng.randf_range(0.02, 0.20),
			_rng.randf_range(0.10, 0.45))
	if seated:
		for sx in [-1.0, 1.0]:
			_cone(p, Vector3(sx * 0.10, 0.45, 0.0), Vector3(sx * 0.12, 0.45, 0.36),
					0.075, 0.065, trous, 7)
			_cone(p, Vector3(sx * 0.12, 0.45, 0.36), Vector3(sx * 0.12, 0.05, 0.40),
					0.062, 0.050, trous, 7)
		_cone(p, Vector3(0, 0.45, 0.02), Vector3(0, 1.05, -0.05), 0.155, 0.135,
				shirt, 9)
		for sx in [-1.0, 1.0]:
			_cone(p, Vector3(sx * 0.16, 0.98, -0.02), Vector3(sx * 0.24, 0.70, 0.20),
					0.048, 0.040, shirt, 6)
		_cone(p, Vector3(0, 1.05, -0.05), Vector3(0, 1.18, -0.03), 0.055, 0.055,
				m_skin, 7)
		var hd := MeshInstance3D.new()
		var hs := SphereMesh.new()
		hs.radius = 0.105
		hs.height = 0.24
		hs.radial_segments = 12
		hs.rings = 8
		hd.mesh = hs
		hd.position = Vector3(0, 1.28, -0.03)
		hd.material_override = m_skin
		p.add_child(hd)
	else:
		for sx in [-1.0, 1.0]:
			_cone(p, Vector3(sx * 0.10, 0.90, 0.0),
					Vector3(sx * 0.11, 0.02, _rng.randf_range(-0.16, 0.16)),
					0.078, 0.055, trous, 7)
		_cone(p, Vector3(0, 0.88, 0), Vector3(0, 1.46, 0), 0.150, 0.140, shirt, 9)
		for sx in [-1.0, 1.0]:
			_cone(p, Vector3(sx * 0.155, 1.40, 0),
					Vector3(sx * 0.19, 0.92, _rng.randf_range(-0.12, 0.12)),
					0.048, 0.038, shirt, 6)
		_cone(p, Vector3(0, 1.46, 0), Vector3(0, 1.58, 0), 0.055, 0.055, m_skin, 7)
		var hd2 := MeshInstance3D.new()
		var hs2 := SphereMesh.new()
		hs2.radius = 0.105
		hs2.height = 0.24
		hs2.radial_segments = 12
		hs2.rings = 8
		hd2.mesh = hs2
		hd2.position = Vector3(0, 1.68, 0)
		hd2.material_override = m_skin
		p.add_child(hd2)


func _build_people() -> void:
	var g := _grp("People")
	var cz := (CAFE_Z0 + CAFE_Z1) * 0.5
	for i in 6:
		var a := _rng.randf_range(0, TAU)
		_person(g, Vector3(-1.4 + cos(a) * _rng.randf_range(1.4, 3.2), DECK,
				cz + sin(a) * _rng.randf_range(2.0, 6.5)),
				_rng.randf_range(0, TAU), true)
	for i in 4:
		_person(g, Vector3(_rng.randf_range(-2.4, 3.4), DECK,
				_rng.randf_range(-32.0, 34.0)), _rng.randf_range(0, TAU), false)


# =========================================================================
# THE CENSUS -- the detail budget as a NUMBER, not an adjective.
# Counted off the mesh data (surface index counts), so it works under --headless
# where the GPU never draws a thing and RenderingServer's frame counters are 0.
# =========================================================================
func _tris_of(mesh: Mesh) -> int:
	if mesh == null:
		return 0
	var n := 0
	for s in mesh.get_surface_count():
		var arr := mesh.surface_get_arrays(s)
		if arr.is_empty():
			continue
		var idx = arr[Mesh.ARRAY_INDEX]
		if idx != null and idx.size() > 0:
			n += idx.size() / 3
		else:
			var v = arr[Mesh.ARRAY_VERTEX]
			if v != null:
				n += v.size() / 3
	return n


func _walk(n: Node, acc: Dictionary) -> void:
	if n is MultiMeshInstance3D:
		var mm: MultiMesh = n.multimesh
		if mm != null and mm.mesh != null:
			acc["tris"] += _tris_of(mm.mesh) * mm.instance_count
			acc["draws"] += 1
			acc["mm_inst"] += mm.instance_count
	elif n is MeshInstance3D:
		acc["tris"] += _tris_of(n.mesh)
		acc["draws"] += 1
	acc["nodes"] += 1
	for c in n.get_children():
		_walk(c, acc)


func _census() -> void:
	var total := {"tris": 0, "draws": 0, "nodes": 0, "mm_inst": 0}
	var lines := []
	for k in _g.keys():
		var a := {"tris": 0, "draws": 0, "nodes": 0, "mm_inst": 0}
		_walk(_g[k], a)
		lines.append("%-10s %9d tris  %6d draws" % [k, a["tris"], a["draws"]])
		total["tris"] += a["tris"]
		total["draws"] += a["draws"]
		total["nodes"] += a["nodes"]
		total["mm_inst"] += a["mm_inst"]
	var ms := Time.get_ticks_msec() - _t0
	print("[boulevard] built in %d ms  (seed %d)" % [ms, seed_value])
	if verbose:
		for l in lines:
			print("[boulevard]   " + l)
	print("[boulevard] TRIANGLES=%d  DRAWS=%d  NODES=%d  MULTIMESH_INSTANCES=%d"
			% [total["tris"], total["draws"], total["nodes"], total["mm_inst"]])
	# The check that can fail: an empty or near-empty street is a build that
	# silently did nothing. 200k triangles is the floor for "super detailed".
	if total["tris"] < 200000:
		push_error("[boulevard] FAIL: only %d triangles -- the street did not build"
				% total["tris"])
	set_meta("triangles", total["tris"])
	set_meta("draws", total["draws"])
