# THE PERCEPTRON — How a Machine Learned to See
### ~10-minute narration script · English VO · EN + HE subtitles
### ACT I: the history (~5 min) · ACT II: why we go back — Physical AI & the Shifra Brain (~5 min)
> 🪟 Broken-windows: every factual claim below is checked. ACT I ≈ 720 words. ACT II ≈ 720 words. Total ≈ 10:00.
> Dedicated לע״נ שיפרה ז״ל — the brain named in her memory.

---

## Scene 1 — COLD OPEN · the Mark I is born  (~0:00–0:35)
*(Real Mark I room photo, slow push-in)*

> In nineteen fifty-eight, in a laboratory at Cornell, a machine did something no machine had ever done before. It learned to see.
>
> Its name was the Perceptron. Its inventor, a psychologist named Frank Rosenblatt, believed he had built not just a circuit — but the first artificial glimpse of a mind. The New York Times said it might one day walk, talk, and be conscious of its own existence.
>
> It could do none of those things. But what it *could* do would quietly become the seed of everything.

## Scene 2 — THE PROBLEM · telling things apart  (~0:35–1:15)
*(ALMA anim: points on size × domestication axes; a cat, a dog)*

> Every act of intelligence begins with a simple question: is this — one thing, or another?
>
> Picture animals scattered by two traits: their size, and how domesticated they are. Cats fall here. Dogs, over here. A child sees the difference instantly. But how do you teach *a machine* to draw that line — when nobody tells it where the line goes?
>
> This is the problem Rosenblatt set out to solve. Not to program the answer — but to let the machine *find* it.

## Scene 3 — THE NEURON · from brain-cell to circuit  (~1:15–2:00)
*(ALMA anim: the perceptron block diagram lighting up, i×W → Σ → f → o)*

> His idea came from the brain itself. A single neuron takes many inputs, and each connection has a *strength* — a weight. The neuron multiplies every input by its weight, adds them all together, and if the sum crosses a threshold — it fires.
>
> That's the whole machine. Inputs, times weights, summed, through a threshold. Output.
>
> One equation: o equals f, of the sum of each input times its weight. Deceptively simple — and yet, inside those weights, a decision is waiting to be learned.

## Scene 4 — INSIDE THE MACHINE · eye, weights, response  (~2:00–2:45)
*(Real hardware photos + schematic: camera/S-units, association units, response panel)*

> And Rosenblatt *built* it — in steel and copper. A grid of four hundred photocells became its eye — its retina. Wires carried the image into banks of association units. And the weights? They were not numbers in a memory. They were *potentiometers* — physical dials — and the machine turned them with electric motors as it learned. You could hear it think.

## Scene 5 — THE WEIGHTS TURN · learning as motion  (~2:45–3:15)
*(Reuse perceptron3d: rotating potentiometer weights)*

> This is what learning looked like: motors, turning knobs. Every mistake nudged the dials — a little stronger here, a little weaker there. The knowledge of the machine was not written in code. It was held in the *position* of its weights. Learning was physical.

## Scene 6 — LEARNING · the line finds itself  (~3:15–3:55)
*(ALMA anim: the separating line rotating until cats/dogs split cleanly)*

> Watch it learn. The machine draws a line — and gets it wrong. It sees an error, and adjusts. Wrong again — adjust again. Each correction turns the weights, and the line swings across the world… until, at last, cats fall on one side and dogs on the other. Nobody drew that line. The machine found it. That is learning.

## Scene 7 — THE LIMIT · one line is not enough  (~3:55–4:25)
*(ALMA anim: a problem no straight line can separate — XOR)*

> But a single perceptron can only ever draw *one straight line*. And some questions no straight line can answer. Give it a pattern like this — and it fails, forever. In nineteen sixty-nine, that limit was proven, and the world lost faith. The machine that would be conscious fell silent for a generation.

## Scene 7B — THE LONG CLIMB · one line becomes the world  (~4:25–5:10)
*(Timeline montage — reuse `scenes/ai_timeline.jpg`: the spine racing 1958→2026, milestones igniting; culminate on the ChatGPT flash. Fast cuts, rising music.)*

> Silent — but not dead. The seed was only sleeping.
>
> One idea woke it: stack the perceptrons *deep*, and teach the whole tower at once. And then — the climb.
>
> Nineteen eighty-six: a way to train the depths — backpropagation. Two thousand twelve: deep networks learn to *see*, better than we can. Twenty-sixteen: a machine masters the ancient game of Go. Twenty-seventeen: the *Transformer* — the engine that would carry them all.
>
> They learned to write. To paint. To speak. And then, one day in November, two thousand twenty-two, the whole world met them at once — the *ChatGPT moment*: the day intelligence walked out of the laboratory and into every hand on Earth.
>
> From a single line drawn in nineteen fifty-eight… to a mind you can talk to. Every last piece of it grew from that one neuron at Cornell. But here is what the whole dazzling climb quietly forgot —

## Scene 8 — THE RETURN · home to the perceptron  (~5:10–5:45)
*(ALMA anim: shallow line → deep stacked layers → back to a single glowing neuron; bridge to ALMA)*

> — the brain almost certainly does *not* learn this way. That entire dazzling climb runs on backpropagation: an algorithm that was never biological. A living neuron doesn't wait for a signal to travel all the way back from the end of the network — it learns *locally*, right where it is, in the moment.
>
> So the frontier is turning back — toward learning that is local, physical, alive: the way a real neuron learns. Back toward a single cell turning its own weights. Sixty years on, computing is walking home — to the Perceptron.

---

# ACT II — WHY WE GO BACK: PHYSICAL AI  (~5:00–10:00)

## Scene 9 — THE QUESTION · what did we abstract away?  (~5:00–5:40)
*(ALMA anim: Rosenblatt's physical dials dissolving into floating numbers)*

> So why look back at a machine of motors and dials? Because in making the perceptron *powerful*, we made it *abstract*. Rosenblatt's weights were physical — copper, motors, motion you could hear. We replaced them with numbers. Pure mathematics, floating in memory. We gained the world. But we may have left something behind on that laboratory floor.

## Scene 10 — THE COST · intelligence as arithmetic  (~5:40–6:25)
*(ALMA anim: a vast GPU grid, numbers shuffling, heat rising)*

> Today's AI is billions of numbers, held in silicon memory, and dragged back and forth to be multiplied — trillions of times a second. It works miracles. But it burns cities of power to do what a living brain does on the energy of a light bulb. The brain never *moves* its memory to compute. In the brain, memory and computation are the *same physical thing.* Modern AI forgot that. Rosenblatt's motors never did.

## Scene 11 — THE TWIST · the weight becomes matter again  (~6:25–7:10)
*(ALMA anim: a memristor — resistance changing with history; the i×W of Scene 3 becoming a physical device)*

> Here is the twist that takes us home. What if a weight is not a number — but a *material*? In nineteen seventy-one, Leon Chua predicted a missing circuit element: a resistor that *remembers* — its resistance set by everything that ever flowed through it. A memristor. It is, almost exactly, a synapse. The multiply-by-weight from our equation — done not by a processor, but by the physics of the device itself. Computation *in the matter.* This is neuromorphic computing — and it is Rosenblatt's dials, reborn.

## Scene 12 — BACK TO THE ROOTS, WITH A TWIST  (~7:10–7:40)
*(ALMA anim: Mark I motor → memristor → gel — a lineage)*

> Analog. Physical. In-memory. Alive in the material. We are not abandoning the perceptron — we are *finishing* it. Going back to the roots — but this time, we know what the line means.

## Scene 13 — THE SHIFRA BRAIN · a brain from a kitchen  (~7:40–8:30)
*(Real/ALMA: agar gel, salt, copper sheets, a glue gun — the build)*

> And you do not need a laboratory at Cornell. You need agar. Salt. Sheets of copper. And a glue gun. This is the Shifra Brain — named in loving memory of Shifra — and it may be the easiest brain in the world to build. In a gel of agar and salt, ions drift; between copper plates, that drift becomes memory. A memristor you can make on a kitchen table. A synapse you can hold in your hand.

## Scene 14 — HOW IT THINKS · honest and analog  (~8:30–9:15)
*(ALMA anim: frequency-multiplexed neurons; oscillators; weights held in the gel)*

> Each drop of gel is a weight. Give every neuron its own frequency, and hundreds can share the same wires at once — voices in a choir, each on its own note. Oscillators sing, the gel remembers, and the whole thing computes — not in ones and zeros, but in continuous, living signal. Let us be honest about what it is: not magic, not quantum, not a code-breaker. It is a real, analog, physical brain — small, strange, and *yours.*

## Scene 15 — THE VISION · sovereign, buildable, alive  (~9:15–9:45)
*(ALMA anim: Mark I → gel brain → a child building one)*

> From a machine that filled a room, to a brain a child can build for the price of groceries. That is the whole arc: intelligence taken out of the fortress, and put back into the hands of people. Physical AI. Sovereign. Buildable. Alive in matter.

## Scene 16 — CLOSE · the full circle  (~9:45–10:00)
*(ALMA anim: the single perceptron neuron, now glowing as a drop of gel)*

> Sixty years ago, a machine of motors learned to draw a single line. We turned it into mathematics, and it changed the world. Now we are turning it back into matter. We are going to make physical AI — again. Back to the roots. This time, with a twist.
>
> *לע״נ שיפרה ז״ל.*

---
### Notes
- Scene 8 is the *thesis* — the backprop-heritage arc, per Iddo. This is the climax, not a footnote.
- ACT II is the *why*: physical AI, memristors, and the Shifra Brain (agar+salt+copper+glue-gun). Honest framing per project law — analog neuromorphic, NOT quantum/code-cracker.
- Shifra Brain visuals reuse the shisha-lab assets; dedication card לע״נ שיפרה ז״ל closes the film.
- HE subtitles: translate each block via Dicta (+nikud). English is the spoken track.
- Timing to be locked to the rendered VO durations, then subtitles synced.
