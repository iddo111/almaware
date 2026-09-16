# The Future of AI — An Encyclopedia of Where We Are Heading

*לזכרה של עלמה ז״ל*

---

## Preface: The One Through-Line

For a decade the story of AI had a single plot: make it bigger. More parameters, more data, more compute — and, reliably, more capability. That story is not over, but it is no longer the *interesting* one. The frontier is moving somewhere the scaling curve cannot reach on its own.

The through-line of this encyclopedia is a different bet: **the next intelligence will be grounded, embodied, physical, contestable — and it will learn from little.**

Grounded, because a system that has only ever seen text is guessing at a world it has never touched. The most promising research now insists that understanding begins in prediction of *what happens next* in the real, sensory world — not the next token, but the next state.

Embodied, because a body is not a container for a mind; it is part of how the mind is built. A learner that acts, fails, and feels the consequence generates its own data. That is the flywheel no dataset can hand you.

Physical, because intelligence built only in floating-point on von Neumann silicon pays an energy tax the brain does not. The exploratory edge is hardware where the weights are matter you could, in principle, touch — memristors, analog arrays, neuromorphic spikes.

Contestable, because power without the ability to argue back is not safety, it is obedience. The systems worth building can be questioned, corrected, and told they are wrong — and change.

And learning from little, because the deepest embarrassment in the field is still a two-year-old: she masters language, causality, and physical intuition on a trickle of noisy, unlabeled experience, while our largest models need a library of the internet. Closing that gap — sample efficiency, developmental learning, learning from byte zero — is not an optimization. It is the whole game.

None of this is a rejection of scale. It is a claim about *direction*. The exciting future is not a larger oracle answering from a warehouse of text. It is a small, curious, embodied learner that grows — and that we can always look in the eye and say: *convince me.*

This encyclopedia maps that road, chapter by chapter, from byte zero to the machine that started it all: Turing's question.

---

## The 10 Works to Read First

A starting library for the whole field — foundational stones and the forward-looking papers that point past pure scale. Read these and you can follow almost any argument in the chapters that follow.

1. **Turing, A. M. (1950), "Computing Machinery and Intelligence," *Mind*.** The paper that replaced the unanswerable "Can machines think?" with an operational test and a set of objections still unrefuted. Everything downstream is a footnote to this question. *Read it for the question, and for how carefully Turing anticipated the counter-arguments.*

2. **Rosenblatt, F. (1958), "The Perceptron," *Psychological Review*.** The first learning machine — weights adjusted from examples, not programmed. It also triggered the field's first winter, a cautionary tale about overclaiming. *Read it for the origin of "learning from data" and the danger of hype.*

3. **Rumelhart, Hinton & Williams (1986), "Learning representations by back-propagating errors," *Nature*.** Backpropagation made deep networks trainable and is still the engine under nearly every model today. *Read it for the algorithm that quietly powers the whole modern era.*

4. **Vaswani et al. (2017), "Attention Is All You Need," *NeurIPS*.** The Transformer — the architecture behind large language models, most modern vision, audio, and multimodal systems. *Read it for the design that scaled, and to understand what "attention" actually computes.*

5. **Sutton, R. (2019), "The Bitter Lesson" (essay).** A short, sharp argument that general methods leveraging computation beat hand-crafted human knowledge every time. It is the strongest case *for* scale — and the one the rest of this encyclopedia argues with. *Read it to know the position you must answer.*

6. **LeCun, Y. (2022), "A Path Towards Autonomous Machine Intelligence" (position paper).** The manifesto for world models and Joint-Embedding Predictive Architectures (JEPA): predict the *gist* of the future in a learned representation, not raw pixels or tokens. *Read it for the clearest articulation of the "grounded, predictive" future.*

7. **Ha & Schmidhuber (2018), "World Models," *NeurIPS*.** A compact, beautiful demonstration that an agent can learn a compressed internal simulator of its environment and then plan inside its own dream. *Read it for the idea that a mind builds a model of its world and lives partly inside it.*

8. **Silver et al. (2016, "Mastering the game of Go," *Nature*; 2017, AlphaZero).** Deep reinforcement learning plus self-play reaching, then exceeding, human mastery with no human game records. *Read it for the data flywheel — a system that generates its own experience.*

9. **Brown et al. (2020), "Language Models are Few-Shot Learners" (GPT-3), *NeurIPS*.** The paper where scale alone produced emergent in-context learning, launching the LLM era and the "just make it bigger" thesis. *Read it for what scale genuinely bought us — and where it stopped.*

10. **Christiano et al. (2017), "Deep Reinforcement Learning from Human Preferences," *NeurIPS*.** The technique (RLHF) that turned raw models into usable assistants and opened the entire modern alignment agenda. *Read it for the beginning of "teaching machines what we want" — and why that is harder than it looks.*

> *A note on citations:* every work above is real, with author and year as published. Where a paper is widely known by a nickname (GPT-3, AlphaGo, JEPA), the formal title is given so you can find the primary source, not a summary of it.

---

## The Open Questions

The eight things the field genuinely does not know. Not rhetorical — open. Anyone who tells you these are settled is selling something.

1. **When — or whether — AGI arrives.** Estimates from serious researchers span "within a few years" to "not this century," and some argue "AGI" is not even a coherent single milestone but a moving cluster of capabilities. We do not have a measurement that would let us agree we had reached it. *The honest answer is that we cannot yet name the finish line, let alone the date.*

2. **Whether we can align systems more capable than ourselves.** Current alignment (RLHF, Constitutional methods, red-teaming) works on systems we can still evaluate. Scalable oversight — supervising a system whose reasoning outruns our own — is an open research problem, not a solved engineering task. *We do not know if the methods that work today keep working as capability grows.*

3. **The data wall.** High-quality human text is finite and much of it is already consumed. Whether synthetic data, self-play, and embodied experience can substitute for it without collapsing into models trained on their own echoes is unresolved. *We do not know what the primary fuel of the next generation will be.*

4. **Consciousness and inner experience.** We do not know whether any current or future AI has, or could have, subjective experience — and, more troubling, we lack an agreed test that would tell us either way. This is a live scientific and philosophical question, not a settled "obviously not." *We may build minds whose inner status we cannot read.*

5. **Physical substrates.** Whether neuromorphic, analog, memristor, or other post-von-Neumann hardware will overtake digital accelerators for real workloads — or remain a promising sideline — is genuinely undecided. The energy gap between brains and datacenters says *something* is possible; nobody has shown it at scale. *We do not know what the winning hardware will be made of.*

6. **Learning from little.** A child masters language and physical intuition on a trickle of unlabeled experience; our best models need orders of magnitude more. We do not understand what makes biological learning so sample-efficient, nor how to reproduce it. *The core embarrassment of the field is still unsolved.*

7. **Understanding versus interpolation.** We cannot yet reliably tell whether a model has learned a genuine causal world model or an extraordinarily good statistical surface that fails off-distribution. Benchmarks are contaminated; probes are contested. *We do not have a trusted way to measure "real" understanding.*

8. **Governance and contestability.** Who decides what these systems may do, how power over them is distributed, and how a person keeps the standing to argue back and be heard — these are unsolved socially, legally, and technically at once. *We do not know how to keep the most capable machines contestable by the people they affect.*

---

*These are the questions this encyclopedia is written into — not around. The chapters that follow do not pretend to answer all eight. They map, honestly, how far the road has been built, and where it presently runs out.*