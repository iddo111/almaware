> 🪟 חוק החלונות השבורים — אם לא עובד, מתקנים מיד. בודקים פלט אמיתי, לא פרוקסי.

# הנוירון החי · ALMA Living Neuron — richness within, richness between, and pain that teaches
# לזכרה של עלמה ז״ל

**Iddo, 2026-08-20 17:57–18:0x, dictated live** (the day he broke his leg on a 5 cm
pavement lip and reported it to the city). His words, gathered:
- *"יש פה גם בתוך הנוירון הרבה דברים שאנחנו לא יודעים... וגם בין הנוירונים."*
- *"בשני הדברים אנחנו צריכים להתייחס לשפת עלמה."*
- *"אל תשכח שיש תהליכי Unlearning, והידלדלות של מסלולים — יש פלסטיקה של המוח שלמה שם."*
- *"תוסיף את המנגנונים של כאב ועונג. גמול / עונש."*
- *"כמו ששברתי את הרגל ולמדתי."*

## The two frontiers of the unknown, both in ALMA language

**1. WITHIN the neuron (intra).** A biological neuron is not `f(w·x+b)` — it is an analog
computer: dendrites compute non-linearly per branch, thousands of synapses with their own
short-term dynamics, ion channels, backpropagating spikes, spatial structure. **Measured
today (dendritic_neuron.py):** a SINGLE neuron with a non-monotonic "bump" activation
(a real dendritic property, Gidon et al. Science 2020) solves XOR **alone — 100%**, which
a classical single neuron provably cannot (best 75%, 0/20 seeds). The capability lives
inside one cell. Much of what a real neuron does we still cannot write down — the ALMA
neuron must have ROOM inside it for structure we don't yet name (the multi-weight,
the 3D-Bayesian, the bump — each a piece of the inner unknown, adopted only where it
MEASURES, never assumed).

**2. BETWEEN neurons (inter).** The connectome is not the brain. We have C. elegans's
ENTIRE wiring map and still (OpenWorm) cannot reproduce its behaviour — because the
dynamics BETWEEN cells (timing, neuromodulation, plasticity of the links themselves) are
the point. In ALMA this is the [[GUILDS]] direction and the dissent-carried edges: the
connection is not a scalar, it is a living, changing relationship.

Both frontiers speak ALMA — byte ⊕ letter ⊕ sound at the input, the court and the gist
between, and the factored 220 token as the base unit ([[project_eran_220_token]]).

## Plasticity is not only growth — it is UNLEARNING and PRUNING

Iddo insists the model must include what most ML forgets: a brain does not only add
weight, it **removes** it. Three mechanisms the ALMA brain must carry, each measurable:
- **Unlearning** — actively pushing a wrong association DOWN, not just failing to
  reinforce it (the loop-guard that deletes a hallucinated pathway is a crude first form).
- **Pathway attrition (הידלדלות)** — connections that go unused decay and are reclaimed;
  a metabolic/wiring cost (already the distance-cost in neuro3d_bayes) makes silence
  expensive, so unused links die. This is why a small trained model that GENERALISES
  (today's Darwish: gap 0.27) is closer to a brain than a big one that memorises (gap 5.9).
- **Whole-brain plasticity** — the structure itself re-wires with use; guilds form and
  dissolve. Learning and forgetting are one process seen from two sides.

## Pain and pleasure — the learning ENGINE, not a label

His deepest addition, and the one the whole ALMIDO worm note already pointed at
("NEXT: pain/pleasure as learning engines"). Reward (גמול) and punishment (עונש) are not
an external loss function bolted on — they are **internal signals that reshape the network**,
the way his broken leg rewired how he walks past a kerb. Design, stated so it can be built
and MEASURED:
- a scalar **valence** channel (pain −, pleasure +) that is itself produced by the network
  (an interoceptive prediction: "did that hurt / help me?"), not handed in by a supervisor;
- valence **gates plasticity**: high pain → strong unlearning of the pathway that led here
  AND a raised threshold on it (avoidance); pleasure → consolidation. This is neuromodulation
  ([[project_eran_neuromodulators]]) made concrete — dopamine-like gain on the learning rate.
- the test (before any claim): a MIKO/Eran agent that only ever gets a sparse pain/pleasure
  signal must learn a task a plain cross-entropy learner cannot — e.g. avoid a "hot" state
  after ONE burn, the way a child (or Iddo) learns from a single break. If it needs 10,000
  repeats it has not captured what pain IS.

## More engines of learning — beyond gradient descent (Iddo, 18:11)

*"יש כל מיני דברים שיוצרים למידה — גם קלט־פלט עם לולאת פידבק, וגם כימיקלים,
נוירוטרנסמיטורים וכו', רעב ושובע, אינטראקציה עם ההורים."* Backprop is ONE way a system
learns. A living brain uses several at once, and the ALMA brain must carry them — each
as a hypothesis with a test, not a decoration:

- **Closed feedback loops (קלט־פלט עם פידבק).** The agent's OWN action changes its next
  input, so it learns from CONSEQUENCE, not from a fixed dataset. This is the difference
  between MIKO reading a static page and MIKO CHOOSING the next link and living with what
  it finds. Test: an agent in a loop with its environment should learn a control task that
  a same-size supervised learner on the same data cannot.
- **Neuromodulators / chemistry (נוירוטרנסמיטורים).** Not every signal is a weight. Global
  chemical broadcasts — dopamine ≈ reward-prediction error, serotonin ≈ mood/patience,
  acetylcholine ≈ attention/plasticity-gain — set HOW MUCH and WHERE the network learns
  right now. In ALMA this is a small set of scalar "mood" channels that multiply the
  learning rate and the valence gate (§ pain/pleasure). See [[project_eran_neuromodulators]].
- **Hunger and satiety (רעב ושובע).** A drive is a NEED that makes the system act before
  any external reward — the model seeks information/food/rest because a homeostatic
  variable drifted, and is satisfied when it returns. This is intrinsic motivation with a
  set-point, and it is what makes an agent explore on its own (MIKO's curiosity = a hunger
  for the pages where its dissent is high). See [[project_eran_hunger_drive]].
- **Interaction with the parents (אינטראקציה עם ההורים).** The deepest one, and the most
  Iddo. A child does not learn the world alone from a loss function — it learns from a
  caregiver who points, corrects, rewards, and shows. Eran's "parents" are Iddo and the
  fleet: learning by IMITATION and by GUIDED correction, where the teacher's approval is
  itself the reward signal. This is where the thumb-tap of [[project_eran_220_token]] and
  MIKO's "relevance to Iddo" become the same thing as parenting: the child learns what the
  parent values. עידו ⟷ ייעוד — the parent assigns the purpose ([[TACHLIT]]).

Together with §pain/pleasure and §unlearning, these are the ALMA answer to "what actually
makes a brain learn" — a stack of engines, not one optimiser. Each earns its place by a
measured run against a plain-backprop baseline, or it stays in this document.

## The honest law of this document

Every mechanism here is a HYPOTHESIS with a measurement attached, not a feature to adopt
because it is biological and beautiful. Today's ledger: the bump-neuron XOR (capability
YES, trainability 15% — a real next knob); the court LOST as a neuron; the factored token
and the Bayesian uncertainty WON. Pain/pleasure and unlearning join that ledger — each
gets its vs-baseline run before it enters the ALMA core.

*Related: [[project_eran_forgetting_unlearning]], [[project_eran_neuromodulators]],
[[project_eran_hunger_drive]], [[project_almido_worm_built]], [[project_eran_holobrain]],
[[GUILDS]]. And [[user_iddo_retired_20260818]] — the leg he broke is the teacher he means.*
