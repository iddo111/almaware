# -*- coding: utf-8 -*-
"""Build the Perceptron-movie shot list from the Hebrew narration blocks.

One prompt per ~4.6 s of narration, so the footage follows what is being said
rather than being generic B-roll. 30 narration blocks -> 158 shots.
"""
import json

SUF = (", full frame edge to edge, no borders, no letterbox, no text, no captions, "
       "photorealistic, slow deliberate camera movement, rich detail")

B = {}

# ================= ACT I : the history =================

B[1] = [  # 1958, Cornell, a machine did what no machine had done: it learned to see
    "Empty corridor of a 1950s American university science building at night, green linoleum, frosted glass doors, a single warm lamp glowing at the far end, slow forward dolly",
    "Interior of a 1958 electronics laboratory, grey steel racks, thick cloth wrapped cables, dust drifting in a shaft of window light, slow push in",
    "Close macro of an array of small round glass photocells set in a black metal grid, each lens catching a point of warm light, slow lateral tracking shot",
    "A single glass photocell lens filling the frame, reflection of a laboratory window curving across it, the light slowly brightening like an eye opening",
]

B[2] = [  # they called it the Perceptron; Rosenblatt; the New York Times prophecy
    "A young American scientist in a white shirt and dark tie in 1958, standing beside a tall grey electronic cabinet, one hand resting on a control panel, warm tungsten light, thoughtful expression, documentary portrait",
    "Over the shoulder view of a man in 1950s clothing writing equations in pencil in a notebook on a cluttered laboratory desk, slide rule and coffee cup beside him",
    "A tall grey electromechanical cabinet covered in hundreds of small round dials and toggle switches, warm tungsten light raking across it, slow reveal from left to right",
    "Newspaper printing press rollers spinning at speed in 1958, folded broadsheet papers flying through steel guides, black and white archival look, dramatic motion",
    "Stacks of freshly printed newspapers sliding across a conveyor in a 1950s pressroom, ink shine, motion blur, warm overhead lamps",
    "A 1950s living room at dusk, a man in an armchair lowering a newspaper, a small round television glowing, dust in the lamplight, quiet domestic scene",
]

B[3] = [  # it could do none of that; a box of motors and dials; but it was the seed
    "Interior of a large electronic machine, rows of relay contacts clicking open and closed, small sparks of contact light, dark background, extreme macro",
    "Small electric motors with brass gears turning a rotary dial shaft inside a grey machine chassis, oiled metal, warm practical light, macro",
    "A white paper card with a simple black square printed on it held in a metal clamp under a lamp on a clean laboratory table, slow push in",
    "A single seed of grain resting on dark soil, extreme macro, a thin pale root beginning to emerge, soft morning light, shallow focus",
    "Time lapse of a pale green shoot pushing up out of dark earth and unfolding its first leaves, soft window light, macro",
]

B[4] = [  # every act of intelligence begins with one question: this, or that?
    "A young child face in soft window light, eyes moving as they look at something off camera, curious, warm skin tones, shallow focus portrait",
    "Two objects on a plain white table under soft light, a smooth grey stone and a rough brown stone, a small hand entering frame and hovering between them",
    "Macro of a human eye, iris contracting, reflection of a bright window curving across it, extremely detailed, slow zoom out",
]

B[5] = [  # animals scattered by size and domestication; a child sees it instantly
    "A domestic tabby cat sitting still on a wooden floor in warm afternoon light, tail curling slowly, sharp fur detail, shallow depth of field",
    "A golden retriever turning its head towards the camera in a sunlit garden, ears lifting, slow motion, warm backlight",
    "Wide shot of many different animals scattered across a foggy open field at dawn, sheep, dogs, horses, cats, soft grey light, static composition",
    "Small white spheres and small dark spheres scattered across a large sheet of white paper on a table, top down view, soft even studio light, slow drift",
    "A child of about three years old pointing at something off camera and laughing, soft daylight, warm interior, handheld documentary feel",
    "A chalk line being drawn slowly across a dark grey slate surface by an unseen hand, chalk dust falling, side light, macro",
]

B[6] = [  # not to program the answer, but to let the machine find it, like a child
    "Punched paper tape running through a reader head in a 1950s computer, holes flickering past, warm lamp light, macro, fast motion",
    "Hands in a 1958 laboratory turning a large calibration dial slowly, close macro, brass and bakelite, warm light",
    "A child learning to walk across a wooden floor towards outstretched adult hands, backlit by a bright window, warm and soft, slow motion",
    "A blank sheet of white paper on a desk under a lamp, a pencil resting beside it, the shadow of a window frame slowly moving across it",
]

B[7] = [  # the idea came from the brain: one neuron, many inputs, each with a weight
    "Extreme macro of living neurons in a dish, glowing faint blue and gold, long branching dendrites, slow drift, scientific microscopy look",
    "A dense three dimensional web of glowing fibres in dark space, points of light travelling along them, slow rotation, volumetric",
    "A single neuron cell body with many branching dendrites reaching outward into darkness, soft gold glow, slow orbit around it",
    "Many faint pulses of light travelling inward along thin branching filaments toward one central bright node, dark background, macro",
    "Close macro of a synapse, two membranes almost touching, tiny glowing particles crossing the gap, deep blue and amber, very shallow focus",
]

B[8] = [  # multiply by weight, sum it all, compare to a threshold, fire or stay silent
    "Rows of brass weighing scales of different sizes on a dark wooden table, pans tipping slightly, warm side light, slow tracking shot",
    "Water droplets falling one by one into a glass beaker, the level rising steadily toward a marked line, macro, backlit",
    "A brass balance beam tipping past its balance point and swinging down decisively, macro, dark background, warm rim light",
    "A bright flash of electrical discharge jumping between two metal points in darkness, slow motion, blue white arc, sparks",
]

B[9] = [  # that is the whole device: one or zero, yes or no, fire or stay quiet
    "A single incandescent filament inside clear glass warming from dark to bright orange and back to dark, extreme macro, black background",
    "An old toggle switch on a grey metal panel being flipped by a finger, macro, warm light, satisfying mechanical motion",
    "A row of small indicator lamps on a black panel, one lighting brightly while the rest stay dark, macro, slow drift",
    "Darkness, then a single point of light igniting in the centre of frame and steadily growing, no other detail",
]

B[10] = [  # one equation; deceptive simplicity; inside the weights a decision waits
    "White chalk equations being written slowly on a black slate blackboard by an unseen hand, chalk dust in the air, side light, macro",
    "Extreme macro across the surface of a printed circuit board, tiny resistors and solder joints, warm reflected light, slow lateral tracking",
    "Hundreds of small brass potentiometer dials in a grid, each at a slightly different angle, warm raking light, slow push in",
    "A slow orbit around a dense cloud of tiny glowing points suspended in dark space, drifting and reorganising",
]

B[11] = [  # he actually built it: steel, copper, wire; four hundred photocells as its retina
    "Sheets of steel and coils of copper wire on a workshop bench, sparks from a grinder in the background, industrial 1950s workshop, warm light",
    "A grid of four hundred small round photocells mounted in a black metal frame, each lens glinting, slow lateral tracking across the whole array",
    "Reverse view from behind a photocell array, hundreds of soldered wires fanning out into a thick braided bundle, macro, warm light",
    "A grid of photocells seen from the front as a bright lamp sweeps across it, each cell lighting in turn like an eye waking, slow motion",
]

B[12] = [  # wires, association units, and weights that were physical dials turned by motors
    "A thick bundle of cloth insulated wires in many colours running across a laboratory ceiling and down into a cabinet, warm tungsten light, slow tracking",
    "Rows of vacuum tubes glowing orange inside a dark metal chassis, heat shimmer above them, macro, slow lateral move",
    "Banks of relays and terminal strips inside a grey cabinet, dense hand soldered wiring, a warm work lamp, slow push in",
    "Extreme macro of a single potentiometer, its brass shaft slowly rotating, carbon track visible, wiper arm sweeping across it",
    "A small electric motor with reduction gears turning a potentiometer shaft, oil sheen on the gear teeth, macro, warm light",
    "Dozens of small motors turning dials simultaneously inside a large machine, mechanical motion everywhere, dark chassis, warm practical lighting",
    "A man in 1958 standing with his ear close to a humming machine cabinet, eyes closed, listening intently, warm tungsten light, documentary portrait",
]

B[13] = [  # this is what learning looked like: motors turning dials, each error a nudge
    "Macro of a single dial rotating a few degrees clockwise, stopping, then a few degrees back, precise mechanical motion, warm light",
    "A wall of dials seen at a low angle, several of them twitching and adjusting at different moments, warm tungsten light, shallow focus",
    "Close macro of gear teeth meshing and advancing one tooth at a time, brass and steel, oil sheen, dark background",
    "A needle on an analogue meter swinging past centre, overshooting, then settling, macro, glass reflection, warm light",
]

B[14] = [  # the knowledge lived in the physical angle of the weights; learning was bodily
    "Extreme macro of a brass shaft with a fine engraved angle scale, the pointer resting at a precise position, warm raking light",
    "A hand in a 1950s laboratory holding a machined brass component up to the light and turning it slowly, fingerprints on metal, macro",
    "Slow orbit around a complex mechanical assembly of shafts, dials and small motors, warm rim light, dark background",
]

B[15] = [  # watch it learn: wrong, correct, wrong, correct, until the line settles
    "A pencil drawing a straight line across white paper at an angle, top down view, soft light",
    "A tabby cat and a golden dog sitting side by side on a wooden floor, both looking at the camera, warm daylight, shallow focus",
    "Macro of a red indicator lamp flashing on a grey control panel, a warning pulse, dark surroundings",
    "A brass dial being turned a small amount by a motor and then held, macro, warm light, precise motion",
    "The long straight shadow of a taut wire falling across a white table and slowly rotating as the light source moves, top down view",
    "Many small white and dark spheres on a white surface, the camera slowly rotating around them so they appear to separate into two groups",
    "A taut steel wire stretched across a white background slowly rotating to a new angle and coming to rest, macro, clean studio light",
    "A wall of dials finally still, no motion at all, warm tungsten light slowly dimming, quiet, slow push in",
    "Wide static shot of a large 1958 machine standing silent in a laboratory at night, one small lamp glowing on its panel, dust in the air",
]

B[16] = [  # but there was a limit: a single perceptron draws one straight line only
    "A single taut wire stretched across a white studio background, perfectly straight, slowly rotating around its centre, clean light",
    "A pencil line drawn firmly across white paper, then the pencil tip pressing until the lead snaps, extreme macro",
    "Four dark spheres at the corners of a square on a white surface, top down view, a straight shadow sweeping across them and never dividing them cleanly",
]

B[17] = [  # XOR; proven in 1969 by Minsky and Papert; the funding ended; a generation of silence
    "Top down view of four spheres at the corners of a square on white paper, two black and two white arranged diagonally, a straight ruler laid across them at different angles",
    "Pages of a dense mathematics book turning slowly under a desk lamp, printed diagrams and symbols, macro, warm light",
    "Two academics in dark suits in a 1969 university office, one closing a heavy book, cold window light, documentary portrait",
    "An empty laboratory with equipment covered in white dust sheets, cold blue light through dirty windows, slow dolly through the room",
    "A large electrical knife switch being pulled down and the lights in a machine hall going out one bank at a time, dust in the air",
    "Snow falling slowly outside the dark window of an empty institutional building at dusk, blue grey light, still and quiet",
]

# ================= ACT II : why we go back =================

B[18] = [  # depth woke it: stack the perceptrons and train them with backpropagation
    "Sheets of thin translucent film being stacked one on top of another on a light table, each adding density, macro, clean studio light",
    "A slow rise through many horizontal glowing layers suspended in dark space, points of light on each layer, volumetric",
    "A dense three dimensional lattice of glowing nodes and connecting lines rotating slowly in darkness, deep blue and white",
    "Pulses of light travelling forward through a layered glowing lattice and then travelling back again in the opposite direction, dark background",
    "Ripples spreading backward across a still black water surface from a single point, slow motion, high contrast rim light",
]

B[19] = [  # this is how every model learns today; but the brain almost certainly does not
    "A vast server hall with endless rows of racks, blue and green status lights blinking, cold light, slow forward dolly down the aisle",
    "Extreme macro across a modern graphics processor board, dense components and gold contacts, cold blue light, slow lateral tracking",
    "Cooling fans spinning at high speed behind a metal grille, dust particles in the airflow, cold blue light, macro",
    "A person face lit only by the glow of a screen at night, eyes moving as they read, warm and blue mixed light, quiet",
    "A modern smartphone lying on a wooden table, its screen glowing softly in a dark room, reflection on the wood",
    "Extreme macro of living brain tissue under a microscope, capillaries and neurons in soft pink and gold, slow drift",
    "A single living neuron in a dish, its dendrites twitching and extending very slowly, faint blue fluorescence, dark background",
]

B[20] = [  # why look back? making it powerful made it abstract; we left something behind
    "Slow reverse dolly away from a 1958 machine of dials and motors, the laboratory darkening around it, warm tungsten light",
    "A hand turning a heavy brass dial, the weight and resistance of the metal visible in the fingers, extreme macro, warm light",
    "Copper wire being wound tightly onto a steel core by hand, macro, warm workshop light, tactile detail",
    "Solid brass mechanical parts slowly dissolving into drifting particles of light against a dark background, slow motion",
    "Thousands of tiny glowing points drifting in a vast dark space, cold and weightless, slow parallax movement",
    "An empty laboratory floor of worn linoleum with the marks where heavy equipment once stood, cold window light, slow pan",
    "A single small brass screw lying alone on a dusty concrete floor in a shaft of light, macro, shallow focus",
]

B[21] = [  # billions of numbers dragged back and forth; it burns a city to do what a bulb can
    "Wide aerial view at night of a huge data centre complex glowing in the desert, cooling towers venting steam, cold blue and orange light",
    "Heat shimmer rising above rows of cooling units on a rooftop at sunset, distorted air, warm and cold contrast",
    "Extreme macro of a memory module, dense black chips on a green board, gold contacts catching cold light, lateral tracking",
    "A high voltage transmission tower silhouetted against an orange evening sky, cables stretching to the horizon, slow drift",
    "A single small light bulb glowing warmly in an otherwise completely dark room, filament visible, macro, intimate",
]

B[22] = [  # in the brain memory and computation are the same thing; the motors never forgot
    "Extreme macro of a synapse between two neurons, the gap glowing faintly, particles crossing it, deep blue and gold, very shallow focus",
    "A slow orbit inside a dense glowing neural web where each junction pulses gently, warm gold on deep blue, volumetric",
    "Freight wagons of a long train passing at speed through a dark industrial yard, cold sodium light, motion blur",
    "Data cables in a server rack carrying rapid flickering light along their length, cold blue, extreme macro, fast motion",
    "The motors and potentiometers of a 1958 machine turning quietly in warm tungsten light, dust in the air, macro, calm",
    "A brass potentiometer shaft turning slowly in warm light beside a faintly glowing biological synapse, matched framing",
]

B[23] = [  # the twist: Chua 1971, the memristor, a resistor that remembers, computation in matter
    "A slow push in toward a single small dark electronic component resting alone on a white laboratory bench under a bright lamp",
    "An engineer hand in 1971 drawing a circuit symbol carefully with a technical pen on graph paper, macro, warm desk lamp",
    "Four small electronic components arranged in a square on a white surface, three of them clearly visible and one covered by a small card, top down, studio light",
    "Extreme macro of a thin film of dark metal oxide between two electrodes, its texture shifting subtly, scientific microscopy look",
    "Electric current visualised as glowing filaments carving faint permanent channels through a dark material, macro, slow motion",
    "Time lapse from above of a river slowly carving a channel through sand, the path deepening and remembering, warm daylight",
    "A crossbar array of fine metal wires crossing at right angles with a tiny device at each junction, extreme macro, cold light, slow lateral tracking",
    "A glowing biological synapse and a microscopic electronic junction side by side at matched scale, one warm and organic, one cold and crystalline",
    "Extreme macro of current flowing through a crystalline lattice, atoms shifting position slightly and staying there, blue and violet glow",
    "A slow orbit around a dense crossbar chip glowing faintly from within, cold blue light, dark background, volumetric",
]

B[24] = [  # analogue, physical, in memory, alive in matter; not abandoning it, finishing it
    "A smooth analogue meter needle sweeping continuously across its scale with no steps, macro, glass reflection, warm light",
    "Extreme macro of a brass dial turning continuously and smoothly, no clicks, warm raking light, dark background",
    "A 1958 potentiometer in warm light and a modern crossbar chip in cold light in matched framing, slow push in",
    "A coil of copper wire on a dark workbench, the camera orbiting it slowly, warm light, tactile metal detail",
    "Tree roots exposed in dark soil, thick and branching, water seeping between them, macro, soft daylight",
]

B[25] = [  # you do not need Cornell: agar, table salt, copper sheets and a glue gun
    "A kitchen table in warm daylight with a bowl of agar powder, a jar of coarse salt, thin copper sheets and a glue gun laid out, top down view",
    "Agar powder being poured slowly into a pot of hot water on a domestic stove, steam rising, warm kitchen light, macro",
    "Coarse salt crystals falling in slow motion onto a dark surface, backlit, extreme macro, each crystal catching light",
]

B[26] = [  # the Shifra Brain; ions drift in the gel; between copper plates drift becomes memory
    "A warm domestic kitchen at golden hour, hands working carefully at a table, soft focus background, quiet and intimate",
    "Amber agar gel being poured slowly from a beaker onto a thin copper sheet, the gel spreading and settling, macro, warm daylight",
    "Extreme macro inside translucent amber gel, tiny particles drifting slowly through it, backlit, shallow focus",
    "Two thin copper sheets being pressed gently together with a drop of amber gel between them, hands visible, macro, warm light",
    "A single small square of copper with a dome of amber gel resting on an open palm, warm window light, shallow focus",
]

B[27] = [  # each drop is a weight; give each neuron a frequency; oscillators sing; analogue
    "A grid of many small amber gel drops on a copper sheet, evenly spaced, backlit so each one glows, top down view, slow drift",
    "Extreme macro of a single amber gel drop with light passing through it, internal structure visible, slow rotation",
    "Concentric ripples spreading across a shallow tray of water at several different frequencies at once, overhead light, macro",
    "An oscilloscope screen showing smooth overlapping sine waves in green phosphor, slow drift, dark room, macro",
    "Fine sand on a metal plate arranging itself into standing wave patterns as the plate vibrates, top down, side light, macro",
    "A choir of people singing in a warm hall, mouths open, eyes closed, soft window light behind them, slow motion",
    "Smooth continuous waveforms of coloured light flowing across a dark surface with no steps or edges, slow motion, macro",
]

B[28] = [  # be honest: not magic, not quantum, not a code breaker; small, strange, real, yours
    "A plain wooden table in honest daylight with a small copper and gel device sitting alone on it, no decoration, static shot",
    "A hand switching off a theatrical stage light, the beam collapsing, smoke drifting in the remaining darkness",
    "Extreme macro of a small gel and copper device, imperfect and slightly uneven, tiny bubbles visible, honest daylight",
    "A modest hand built electronic device with visible glue and uneven solder joints on a kitchen table, warm daylight, macro",
    "Open hands holding a small copper and gel device up to a window, backlit, warm and quiet, shallow focus",
]

B[29] = [  # from a room sized machine to a brain a child can build; out of the fortresses
    "A huge 1958 machine cabinet standing in a large empty hall, wide static shot, cold light through high windows",
    "A room sized grey machine in cold light and a small copper and gel device on a kitchen table in warm light, matched centre framing",
    "A child of about ten years old at a kitchen table carefully placing a drop of amber gel onto a copper sheet, concentrating hard, warm daylight",
    "A supermarket shopping basket on a kitchen counter containing salt, agar and a small roll of copper foil, warm daylight, top down",
    "A tall mirrored corporate tower seen from below against a grey sky, cold and impersonal, slow tilt up",
    "Many different hands of different ages placing small copper and gel devices onto a shared wooden table, warm daylight, top down, slow motion",
]

B[30] = [  # sixty years ago it learned one line; now we turn it back into matter; dedication
    "A 1958 machine of dials and motors in warm tungsten light, one last slow push in, dust drifting, reverent and quiet",
    "A slow orbit around a dense cloud of tiny glowing points in dark space, cold and beautiful, weightless",
    "Glowing points of light slowly condensing and settling into a single warm drop of amber gel on copper, macro, dark background",
    "A single amber gel drop on copper glowing faintly from within on a dark table, extremely slow push in, warm light",
    "A wide open field at dawn with low golden mist and a single small table standing in it, absolutely still, slow drift",
    "A single candle flame burning steadily in a dark room, absolutely still air, warm gold light, extreme slow push in",
]


def main():
    shots = []
    seed = 770613
    for n in sorted(B):
        for k, p in enumerate(B[n], 1):
            shots.append({"id": "b%02d_%02d" % (n, k), "block": n, "k": k,
                          "prompt": p + SUF, "seed": seed})
            seed += 7717
    print("blocks:", len(B), "shots:", len(shots))
    with open("shotlist_perceptron.json", "w") as f:
        json.dump(shots, f, indent=1)
    nodes = ["eran1", "eran4", "eran2"]
    for i, nd in enumerate(nodes):
        part = shots[i::len(nodes)]
        with open("shots_%s.json" % nd, "w") as f:
            json.dump(part, f, indent=1)
        print(nd, len(part))


if __name__ == "__main__":
    main()
