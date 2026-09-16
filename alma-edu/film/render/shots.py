"""Shot list for ALMIDO / אוֹתִיּוֹת רָצוֹת — the film IS the method.

Order follows OTIYOT-RATSOT.md (§2 the room, §3 a day, §6 the letter table).

Framing rule, non-negotiable: children are shown through HANDS, BACKS,
SHOULDERS, FEET, WIDE ROOMS, SILHOUETTES and the letter itself. No lingering
close-up of a child's face, no named place, no logo, no identifiable person.

Two render routes:
  T2V  — text-to-video, for shots with no Hebrew glyph in them.
  I2V  — a FLUX plate + a REAL aleph composited by letter.py, then
         image-to-video. Used wherever the letter must actually be an aleph,
         because both models render Latin letters when asked for Hebrew.
"""

# TWO measured failures are baked into this block; do not undo either.
#
# 1. "observational documentary" + "cinematic 35mm film" made LTX render
#    BROADCAST frames, complete with invented station bugs — a National
#    Geographic logo, "WP" corner marks, gibberish chyrons.
# 2. The obvious fix made it strictly worse. Adding "no caption, no watermark,
#    no logo, no lettering" put those very tokens in the POSITIVE prompt, and
#    the distilled LTX runs at cfg 1.0 where the negative prompt is inert — so
#    the only thing those words can do is summon what they name. Every shot came
#    back with MORE marks, and "candid photograph" additionally produced
#    photographs OF photographs, complete with white borders and press logos.
#
# So: name no medium and no publication, and never negate. Describe the light
# and the room, and let the scene be a scene.
STYLE = (
    "warm natural light, hard Mediterranean sun, whitewashed walls, "
    "dust motes drifting in the air, shallow depth of field, soft focus falloff, "
    "muted palette of honey, terracotta, chalk white and olive, "
    "photorealistic, richly detailed, tender, unhurried, "
    "edge to edge scene filling the whole frame, plain empty corners"
)

NEG = (
    "cartoon, anime, illustration, 3d render, cgi, video game, plastic skin, "
    "text, caption, watermark, logo, signage, letters, distorted hands, extra fingers, "
    "deformed, blurry, oversaturated, harsh flash, stock photo smiles"
)

FPS = 24
LEN = 97  # 8n+1, = 4.04 s at 24 fps

# ---------------------------------------------------------------- text-to-video
T2V = [
    dict(id="01_dawn_window", order=1, seed=310411, prompt=(
        "An empty kindergarten room at dawn, low golden sunlight slanting through a tall "
        "shuttered window onto a bare tiled floor, dust turning slowly in the light beam, "
        "white plaster walls, a low wooden shelf, nobody in the room, camera drifting slowly "
        "forward. " + STYLE)),

    dict(id="02_the_line", order=2, seed=770412, prompt=(
        "Extreme low angle along a floor: a single strip of pale masking tape stretched across "
        "worn terracotta tiles, a small painted red mark at the right hand end of the tape, "
        "morning light raking across the floor, camera gliding low along the tape toward the "
        "red mark. No people. " + STYLE)),

    dict(id="03_lamp_on", order=3, seed=110413, prompt=(
        "Close on a small child's hand reaching up and pressing a big round switch on a squat "
        "warm table lamp; the bulb glows amber and fills the frame with warm light; the child's "
        "face is out of frame, only the small hand and forearm visible, white wall behind. "
        + STYLE)),

    dict(id="04_name_cards", order=4, seed=770414, prompt=(
        "A row of low wooden pegs on a white wall, small blank cards hanging from them, two "
        "small children's hands entering frame from below to lift one card off its peg, seen "
        "from behind the child's shoulder, face not visible, soft window light from the left. "
        + STYLE)),

    dict(id="05_rope_circle", order=5, seed=770415, prompt=(
        "Photographed from straight overhead, looking directly down at a tiled floor: five "
        "small children in plain cotton t-shirts and shorts walk slowly in a circle holding a "
        "knotted rope loop, seen from so far above that only the tops of their heads, their "
        "shoulders and their sandalled feet are visible and no face can be seen at all, "
        "sunlight pooling on the tiles, static camera. " + STYLE)),

    dict(id="07_walking_line", order=7, seed=770417, prompt=(
        "Seen from high behind, a line of four small children in plain cotton t-shirts and "
        "shorts walking nose to tail along a long white chalk stroke on sunlit concrete, only "
        "their backs and sandalled feet visible and no face turned toward the camera, arms out "
        "for balance, long afternoon shadows, static high camera. " + STYLE)),

    dict(id="11_body_letter", order=11, seed=770421, prompt=(
        "A pure black silhouette of a small child in a t-shirt and shorts against a blazing "
        "white sunlit wall, strongly backlit and heavily underexposed so the figure is a flat "
        "featureless dark shape with no face and no detail at all, standing with one fist "
        "raised high to the upper right and one foot stretched low to the left, holding the "
        "diagonal pose still, dust glowing in the light, static wide shot. " + STYLE)),

    dict(id="13_board_threads", order=13, seed=110423, prompt=(
        "Macro travelling shot across a flat carved wooden board covered in small shallow "
        "grooves in neat rows, short lengths of white wool, red cotton, blue leather lace, "
        "yellow raffia and gold cord tied into the grooves, some grooves still empty, warm "
        "raking light, no people. " + STYLE)),

    dict(id="14_disc_pouch", order=14, seed=770424, prompt=(
        "Close on a small flat wooden disc held between an adult thumb and finger while a wax "
        "crayon draws a mark on it, then the disc dropping into an open cloth pouch held by "
        "small children's hands below, soft indoor light, only hands in frame. " + STYLE)),

    dict(id="15_lamp_off", order=15, seed=770425, prompt=(
        "Late afternoon, deep orange light low across a quiet room; a small hand reaches into "
        "frame and presses the switch of a warm table lamp; the amber glow dies and the room "
        "settles to cool blue shadow; only the hand and the lamp in frame. " + STYLE)),
]

# ------------------------------------------------- plate + real aleph + i2v
I2V = [
    dict(id="06_chalk_aleph", order=6, seed=210416,
         plate=("Top down aerial view of a sunlit grey concrete courtyard floor, completely "
                "empty, scattered chalk dust, hard midday sun, the sharp shadow of a leafy "
                "tree falling across one corner, photorealistic documentary photograph, "
                "35mm film grain, no people, no text"),
         letter=dict(style="chalk", height_frac=0.74, centre=(0.5, 0.5), rotate=-2.0,
                     opacity=0.9),
         length=65,
         motion=("Locked off static overhead camera, the framing does not move at all. A big "
                 "white chalk letter stays exactly where it is on sunlit concrete; only a "
                 "little chalk dust stirs and the leaf shadows tremble very slightly in the "
                 "breeze. Almost a still photograph. " + STYLE)),

    dict(id="08_tile_groove", order=8, seed=210418,
         plate=("Photographed from directly overhead, flat on: a smooth square olive wood tile "
                "with rounded corners lying flat on a linen cloth, the tile filling most of "
                "the frame, blank polished surface, fine wood grain, warm side light raking "
                "from the left, photorealistic macro photograph, no text"),
         letter=dict(style="groove", height_frac=0.42, centre=(0.5, 0.5), rotate=0.0,
                     depth=0.62),
         motion=("Extremely slow macro push across a carved wooden tile, the channel cut into "
                 "the wood catching warm light, dust motes, shallow depth of field. " + STYLE)),

    dict(id="09_salt_tray", order=9, seed=210419,
         plate=("Top down macro photograph of a shallow wooden tray filled with coarse white "
                "salt, the surface smoothly raked flat, warm window light from the left, a "
                "small child's hand withdrawing at the top edge of the frame, photorealistic, "
                "no text"),
         letter=dict(style="trail", height_frac=0.58, centre=(0.5, 0.62), rotate=1.5),
         motion=("A furrow drawn through coarse salt in a wooden tray, a few loose grains "
                 "rolling into the trail, warm light slowly shifting across the salt, macro, "
                 "top down. " + STYLE)),

    dict(id="10_dough_cutter", order=10, seed=210420,
         plate=("Top down close up photograph of a slab of pale rolled dough on a scratched "
                "wooden table, dusted with flour, two small floury children's hands resting at "
                "the bottom edge of the frame, kitchen daylight, photorealistic, no text"),
         letter=dict(style="groove", height_frac=0.46, centre=(0.52, 0.46), rotate=-3.0,
                     depth=0.70, erode_frac=0.015,
                     dark=(138, 110, 76), mid=(166, 138, 102),
                     lip_rgb=(255, 251, 240), lip_a=0.85),
         length=65,
         motion=("Locked off static overhead camera, the framing does not move at all. A shape "
                 "pressed into a slab of pale dough on a wooden table stays exactly where it "
                 "is; only fine flour dust settles and the small floury hands at the bottom "
                 "edge shift very slightly. Almost a still photograph. " + STYLE)),

    dict(id="12_honey", order=12, seed=210422,
         plate=("Photographed from directly overhead, flat on: a square olive wood tile lying "
                "on a linen cloth filling the left two thirds of the frame, a small wooden "
                "spoon of dark glossy date honey resting on the cloth beside it, warm amber "
                "light, photorealistic macro photograph, no text"),
         letter=dict(style="groove", height_frac=0.40, centre=(0.42, 0.5), rotate=0.0,
                     depth=0.9),
         length=65,
         motion=("Locked off static overhead camera, the framing does not move at all. A pool "
                 "of dark date honey sits over a channel carved in a wooden tile and creeps "
                 "very slowly along it, amber light glinting on the syrup. Almost a still "
                 "photograph. " + STYLE)),

    dict(id="16_letter_left", order=16, seed=210426,
         plate=("Top down aerial view of an empty concrete courtyard at dusk, deep orange low "
                "light along one edge, long soft shadows, a coiled rope loop lying on the "
                "ground, nobody there, photorealistic documentary photograph, no text"),
         letter=dict(style="chalk", height_frac=0.7, centre=(0.5, 0.5), rotate=-2.0,
                     opacity=0.55, chalk_rgb=(228, 218, 202)),
         length=65,
         motion=("Locked off static overhead camera, the framing does not move at all. An "
                 "empty concrete courtyard at dusk with a faint scuffed white chalk mark on "
                 "the ground; only the warm light dims very slowly and a little dust drifts. "
                 "Almost a still photograph. " + STYLE)),
]

ALL_IDS = sorted([s["id"] for s in T2V] + [s["id"] for s in I2V],
                 key=lambda i: int(i.split("_")[0]))
