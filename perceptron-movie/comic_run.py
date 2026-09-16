import sys, json; sys.path.insert(0,'.')
from pathlib import Path
import fleet_render as fr
VIS = {
1:"a small 1950s university laboratory at dusk, dust in a shaft of window light, dark equipment racks",
2:"portrait of a young 1950s psychologist in shirtsleeves beside a room-sized machine, hopeful",
3:"a grey steel cabinet of motors and dials, a square card and a circle card on a stand before it",
4:"a cat on the left and a dog on the right, separated by one clean dividing line, minimal",
5:"a scatter of animal silhouettes across two axes, cats clustering one side, dogs the other",
6:"a hand drawing one straight line through a scatter of points, deciding a boundary",
7:"a single biological neuron, dendrites receiving many inputs, synapses of unequal brightness",
8:"a neuron cell body as a summing junction, weighted inputs, one threshold gate firing",
9:"a grid of 400 photocells behind a lens, a letter shape focused onto the array",
10:"motor-driven potentiometers in a rack, shafts turning, each one a weight being set",
11:"inside the Mark I Perceptron, a dense forest of hand-soldered wires and brass terminals",
12:"a patch panel of tangled coloured cables connecting photocells to summing units",
13:"a decision boundary line rotating step by step across two classes of points, converging",
14:"the same line settled correctly, every point on its right side",
15:"a 1969 book on a desk casting a long shadow across a machine, cold light",
16:"four points arranged as XOR, a single straight line failing to separate them",
17:"an empty laboratory, equipment under dust sheets, unopened letters, winter light",
18:"a modern GPU rack glowing in a dark data centre, warm rebirth after cold",
19:"a deep stack of neural layers in perspective, signal flowing forward",
20:"a red wave of error travelling backward through the same layers, weights shifting",
21:"an enormous modern model as a city of light seen from above at night",
22:"a memristor crossbar array, nanoscale wires crossing, junctions holding memory",
23:"macro of a crossbar junction, a conductive filament forming in the oxide",
24:"analogue computation in matter, current finding its own path through a resistive lattice",
25:"a simple homemade device on a kitchen table, agar gel, salt, copper wire, a glue gun",
26:"two copper electrodes in a dish of agar gel, a multimeter reading beside it",
27:"a hand-drawn lab notebook page beside the agar dish, honest and unglamorous",
28:"a child's hand reaching toward a glowing simple circuit, wonder",
29:"dawn over the Negev desert, a small workshop shed with its light on",
30:"a campfire at night with people around it, warm, a small machine among them",
}
jobs=[{"id":"panel_%02d"%n,
 "prompt":v+". cinematic documentary illustration, painterly graphic-novel panel, warm amber and deep teal, dramatic light, film grain, no text, no words, no letters, no watermark",
 "seed":9000+n,"width":1024,"height":768,"steps":24,"guidance":3.4} for n,v in sorted(VIS.items())]
print("dispatching %d panels"%len(jobs))
fr.run(jobs, Path("comic-panels"))
