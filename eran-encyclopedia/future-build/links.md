Between Turing's question in 1950 and the perceptron's fame in 1958 — and again in the long winter
after it — sits a handful of people most histories skip. They are the load-bearing joints of the whole
lineage: each took an idea that was philosophy and made it math, or took math and made it a machine.
Skip them and the chain from Ada to LeCun has holes you could fall through. Here they are, in order,
each with the one move that made him necessary.

## McCulloch & Pitts, 1943 — the first neuron made of logic

A neurophysiologist, Warren McCulloch, and a runaway teenage logician, Walter Pitts, asked a question
nobody had posed cleanly: *what can a network of idealized neurons compute?* Their answer, "A Logical
Calculus of the Ideas Immanent in Nervous Activity," proved that neurons modeled as simple threshold
switches — fire if the weighted inputs cross a bar — can, wired together, compute **any logical
proposition**. This is the birth certificate of the artificial neuron: the exact unit that, eighty
years later, is still the atom of every network in this book. Ada imagined symbols manipulated by
rule; McCulloch and Pitts built the symbol out of a cell. Their neuron could not *learn* — the wiring
was fixed by hand — but it proved the substrate was capable in principle. Everything after is the
story of letting that wiring set itself.

## Donald Hebb, 1949 — the rule that lets it learn

McCulloch–Pitts neurons were frozen. Donald Hebb, a psychologist, supplied the thaw in one sentence
from *The Organization of Behavior* that every student still memorizes: **"Cells that fire together,
wire together."** Formally: when neuron A repeatedly helps fire neuron B, the connection between them
strengthens. This is **Hebbian learning** — the first mechanism by which experience, not an engineer,
sets a weight. It is local (each synapse changes using only what it can see), unsupervised (no teacher,
no labels), and it is still the biological backbone of how real brains are believed to learn. Almost
every learning rule since — including the backpropagation that trains today's giants — is a descendant
or a disciplined cousin of Hebb's idea that **correlation carves the connection.**

## Norbert Wiener, 1948 — feedback, and the word "cybernetics"

Wiener, a mathematician who worked on anti-aircraft prediction in the war, saw that steering an animal,
a gun, and a thermostat are the same problem: **sense the error, feed it back, correct.** His book
*Cybernetics* gave the field its first name and its first big idea — that control and communication in
the animal and the machine obey one set of laws, and that **feedback loops** are how any system, alive
or built, holds a goal against a changing world. Every world model, every reinforcement learner, every
robot in the chapters ahead is a machine that senses, predicts, and corrects. That is Wiener's loop,
running still.

## Claude Shannon, 1948 — information becomes a quantity

The same year, Claude Shannon published "A Mathematical Theory of Communication" and, almost as a side
effect, made intelligence *measurable*. He defined **information** as the reduction of uncertainty,
gave it a unit (the bit), and proved the limits of what any channel can carry. Why does this belong in
a lineage of minds? Because every modern learner is, at heart, a compressor: a system that predicts
what comes next is exactly a system that has found the redundancy — the *pattern* — in its data, and
compression **is** prediction. Shannon handed the field the ruler it still uses to say whether a model
has actually learned anything, or only memorized. When a later chapter says a model "predicts the
gist," it is speaking Shannon's language.

## Paul Werbos, 1974 — backpropagation, twelve years too early

Minsky and Papert's 1969 critique had shown a single-layer perceptron could not even learn XOR, and
the field's funding and faith collapsed into the first winter. The way out was already written — it
just went unread. In his 1974 Harvard thesis, **Paul Werbos** described how to train a *multi-layer*
network by propagating the error backward through the layers, assigning each weight its share of the
blame. This is **backpropagation**, the single algorithm under nearly every model alive today. It sat
almost unnoticed for over a decade — the winter was too cold for anyone to look — until Rumelhart,
Hinton, and Williams rediscovered and popularized it in 1986 (see the next chapter) and the thaw
began. Werbos is the field's great lesson that **the answer can exist years before the community is
ready to hear it** — a lesson worth holding for whoever is reading a forgotten paper right now.

## John Hopfield, 1982 — memory as a landscape, and the bridge to physics

As the winter thawed, the physicist **John Hopfield** showed that a network of neurons with symmetric
connections behaves like a physical system rolling downhill toward the low points of an **energy
landscape** — and that those low points can be made to store *memories*, recalled from a fragment. It
was the moment neural networks stopped being a fringe idea and became something physicists took
seriously, importing the whole toolbox of statistical mechanics. That bridge matters directly to this
book: the **physical AI** of a later chapter — memristors, analog arrays, computing in the settling of
matter toward a minimum — is Hopfield's insight taken literally into hardware. (In 2024 he shared the
Nobel Prize in Physics for exactly this line of work.)

## Why they are one chapter

Read them together and the shape of the whole field appears. **McCulloch–Pitts** gave us the neuron;
**Hebb** let it learn; **Wiener** gave it a goal to hold; **Shannon** gave us the ruler to measure
what it learned; **Werbos** gave us the algorithm to train it deep; **Hopfield** carried it back to
physics and, from there, toward hardware you can touch. Every later triumph — the transformer, the
world model, the embodied learner — stands on these six joints. They are the missing links precisely
because they are so load-bearing that the popular story walks over them without noticing the bridge.

### Read next
- **McCulloch, W. & Pitts, W. (1943), "A Logical Calculus of the Ideas Immanent in Nervous Activity,"
  *Bulletin of Mathematical Biophysics*.** The artificial neuron's founding paper — dense, but the
  root of everything.
- **Hebb, D. O. (1949), *The Organization of Behavior*.** For "cells that fire together, wire
  together" and the first learning rule set by experience.
- **Shannon, C. E. (1948), "A Mathematical Theory of Communication," *Bell System Technical
  Journal*.** The paper that made learning measurable; read it for why prediction and compression are
  the same act.
