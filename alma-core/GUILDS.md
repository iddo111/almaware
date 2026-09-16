# גילדות · GUILDS — spontaneous courts, neuroplastic
# (concept, 2026-08-20 11:55 — Iddo thinking aloud, NOT yet built)

**Iddo, verbatim:** *"כל 3 נוירונים או כל כך וכך נוירונים יוצרים גילדות — מולטיפלקסינג
של גילדות ובתי דינים ספונטניים המשקפים נוירופלסטיקה."*

## The idea

The Beit-Din we tested was FIXED: three seats wired at build time, forever. Today it
LOST as a neuron (music 2.65 vs 2.56; Pong last). Iddo's move is to make the court
DYNAMIC:

- neurons are not permanently bound into courts. They **form guilds** — groups of
  ~3 (or k) — **spontaneously**, based on what they are doing, and **dissolve** when
  the work changes. A neuron can sit in different courts at different times.
- **multiplexing**: one neuron participates in several guilds at once, time- or
  context-shared, so the same unit judges different questions in different panels.
- the forming and dissolving IS **neuroplasticity** — the wiring of courts is
  learned and re-learned, not fixed. A guild that keeps ruling well is reinforced;
  one that adds nothing dissolves.

## Why this might rescue the Beit-Din — and how we would know

The fixed court's failure has a plausible cause: **three seats on EVERY unit is a
tax paid everywhere, useful nowhere in particular.** A plastic guild pays the tax
only where a hard, contested decision actually needs a panel, and stays a single
cheap neuron elsewhere. That is testable and it is the honest frame:

- **מבחן (the test that would make it real):** a plastic-guild layer vs (a) the fixed
  3-seat court and (b) a plain neuron, matched parameter budget, same task. The claim
  is that guilds match the plain neuron's accuracy on easy inputs AND beat it where
  the input is genuinely contested — measured by the Bayesian uncertainty from
  neuro3d_bayes (wide uncertainty = "this one deserves a court"). If guilds don't beat
  a plain neuron anywhere, the idea joins the fixed court in the document, honestly.
- **mechanism sketch (for when it is built, not now):** a router scores each token's
  "contestedness" (the off-data uncertainty the Bayesian layer already produces);
  above a threshold it convenes a guild of the k nearest-in-3D units for that token
  (locality from neuro3d_bayes), takes their median, carries the dissent; below it, a
  single unit answers. The threshold and the guild membership are learned. This is
  mixture-of-experts with the gate driven by UNCERTAINTY and the experts arranged as
  courts — a real, trainable architecture, not a metaphor.

## Status

Concept only. Parked beside [[project_eran_brain_beitdin]] and alma_core's beitdin
(the fixed version that lost). Reflects the same north star as
[[project_eran_neuromodulators]] and [[project_eran_forgetting_unlearning]] — a brain
whose structure changes with use. Build only after MIKO's core and the Darwish
right-size are done, and only with the vs-plain-neuron control in hand from the start.

*The honest one-liner: the fixed court lost; a court that forms only where it is
needed has not been tested, and that is a different claim — worth one measured run.*
