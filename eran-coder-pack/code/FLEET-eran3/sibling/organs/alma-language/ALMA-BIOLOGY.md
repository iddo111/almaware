> 🪟 חוק החלונות השבורים — אם לא עובד, מתקנים מיד.

## ALMA-BIOLOGY.md — the biology of a learning brain, mapped to ALMA

This document maps real neurobiology onto the ALMA model (byte⊕letter⊕sound stream, GIST/JEPA world-model, the Beit-Din / median-of-three "neuron," scalar pain/pleasure, GUILDS/courts, an explicit unlearning path). Every mechanism below is a **hypothesis carrying one falsifiable measurement** — nothing is adopted on biological authority; a mechanism earns its place only if its test wins at matched params/FLOPs. Sections run from **inside the neuron outward**: single-neuron → synapse → plasticity → network → neuromodulation → drives → glia/sleep/metabolism → development/social. **Ledger this session — WON:** the non-monotonic dendritic *bump-unit* solved XOR at 100% as a single unit. **OPEN / COSTED:** the Beit-Din (median-of-3) neuron bought robustness *only* against saturation, at ~2× accuracy cost (flagged for retest under sleep-style downscaling, §7). Everything else is untested hypothesis.

---

## 1. Single-neuron computation

The scalar dot-product-then-nonlinearity unit is the crudest possible model of a neuron. Real cells compute over structured dendrites, in time, and multiplicatively.

- **Per-branch nonlinear integration (two-layer model).** Thin basal/apical dendrites act as semi-independent subunits: each sums local inputs then passes them through a sigmoidal NMDA-spike nonlinearity before the soma sums the subunits — a pyramidal cell ≈ a 2-layer net (Poirazi & Mel 2003; Polsky, Mel & Schiller 2004).
  - **ALMA:** add a *dendritic-subunit layer* — group each unit's fan-in into K fixed subgroups, apply a per-group saturating nonlinearity, then sum, at matched parameter count.
  - **Test:** on a linearly-non-separable classification (parity / interval XOR), the subunit-unit beats a plain-perceptron layer of equal weight-count; report accuracy gap over 3 seeds.

- **A single cortical neuron ≈ 5–8-layer temporal net.** Faithfully reproducing an L5 pyramidal cell's spike train (with NMDA channels) needs a temporally-convolutional DNN 5–8 layers deep; strip NMDA and the depth collapses (Beniaguev, Segev & London 2021).
  - **ALMA:** treat the "neuron" as a small fixed micro-MLP-with-memory over a short input window, not a scalar dot-product.
  - **Test:** fit the same target sequence with (a) scalar units and (b) micro-net units at *equal total params*; measure held-out next-token loss — depth-in-the-unit wins only if it lowers loss per param.

- **Non-monotonic dendritic Ca²⁺ spikes (dCaAPs).** Human L2/3 dendrites fire graded Ca spikes *maximal at threshold and suppressed by stronger input* — an inverted-U activation that lets one neuron compute XOR alone (Gidon et al. 2020).
  - **ALMA:** already measured — the dendritic "bump" (non-monotonic) unit did XOR at 100% single-unit (see ledger).
  - **Test (next):** swap a fraction of hidden units for bump-units in the live model; check whether it cuts the *units needed* to reach fixed accuracy vs an all-ReLU baseline.

- **Multiplicative / sigma-pi gating.** Real dendrites multiply (shunting inhibition, NMDA supralinearity, coincidence gating), not just add; sigma-pi units compute weighted products (Rumelhart et al. 1986; Mel's "clusteron").
  - **ALMA:** add a gating term `y = Σ wᵢxᵢ · σ(Σ vⱼxⱼ)` so one input stream *gates* another.
  - **Test:** on a learned AND-of-features task (context-dependent routing, e.g. niqqud gates letter), the multiplicative unit reaches target accuracy in fewer steps than an additive layer of equal width.

- **Coincidence detection across compartments (BAC firing).** An apical Ca spike (top-down) coincident with basal (bottom-up) input yields a somatic burst — the cell signals *agreement between two input streams* (Larkum et al. 1999; Larkum 2013).
  - **ALMA:** give each unit two ports (bottom-up token, top-down GIST/context) and emit a strong "burst" output only on coincidence.
  - **Test:** on prediction-with-context, coincidence-gated units improve calibration/accuracy when top-down and bottom-up agree, at no cost when only one is present — measure vs a unit that simply concatenates the two. *(Cross-ref: learnable myelination delays, §7, make the two streams arrive in phase.)*

- **Backpropagating APs and dendritic sequence selectivity.** Somatic spikes propagate back into dendrites (Stuart & Sakmann 1994); a single dendrite is *direction-selective*, responding more to soma-ward than distal-ward input (Branco, Clark & Häusser 2010).
  - **ALMA:** make the unit sensitive to the *order* of its inputs within a short window (a tiny fixed temporal kernel per unit), not just their unordered sum.
  - **Test:** on a task where the label depends on input *order* (same multiset, different sequence), order-sensitive units beat order-blind sum-units at equal params.

---

## 2. The synapse

Each synapse is not a static scalar but a stateful, sign-switching, coincidence-reading, self-normalizing device.

- **LTP/LTD are Ca²⁺-threshold-gated and non-monotone (Bliss & Lømo 1973; BCM rule, Bienenstock–Cooper–Munro 1982).** Moderate postsynaptic Ca²⁺ drives LTD, high Ca²⁺ drives LTP, and the crossover threshold θ_m *slides up* with recent postsynaptic activity — the same input strengthens or weakens depending on the neuron's own history. *(The metaplastic, adaptive-step-size reading of the same sliding θ_m lives in §3.)*
  - **ALMA:** backprop already moves weights both ways, but the sign comes from the global loss gradient, not a local activity threshold. Add a per-unit sliding threshold θ tracking each unit's recent mean activation; local term = `f(pre·post − θ)`.
  - **Test:** on a nonstationary A→B stream, measure catastrophic forgetting of A at matched final-B accuracy vs plain-Adam — the sliding threshold should cut A-forgetting.

- **STDP: causal order sets the sign inside a ~20 ms window (Bi & Poo 1998).** Pre-before-post potentiates, post-before-pre depresses, magnitude decaying with |Δt| — a local, temporally asymmetric Hebbian credit signal with no global error.
  - **ALMA:** on ALMA's recurrent/state weights over the byte/letter/sound sequence, add an STDP local term keyed to token order.
  - **Test:** bits/byte on the factored-220 stream, STDP-augmented local updates vs backprop-only at equal FLOPs — does timing info lower loss or speed convergence?

- **Short-term plasticity makes each synapse a dynamic filter (Tsodyks & Markram 1997).** Facilitation (residual presynaptic Ca²⁺) and depression (vesicle depletion) act on ~50 ms–1 s: a depressing synapse is a novelty/high-pass detector, a facilitating one integrates bursts. Effective weight is state-dependent and recovers over time.
  - **ALMA:** add a fast multiplicative gain `g_ij(t)` that depresses on use and recovers with time constant τ.
  - **Test:** on a repeated-vs-novel-token stream, AUC for detecting repeats with no explicit "seen-before" feature, depressing-synapse layer vs a vanilla layer of equal params.

- **Silent synapses are latent AMPA-free connections (Isaac, Nicoll & Malenka 1995; Liao, Hessler & Malinow 1995).** NMDA-only synapses pass no current at rest; LTP "unsilences" them by inserting AMPA receptors — dormant capacity recruited on demand without new wiring.
  - **ALMA:** init a fraction of connections at zero output gain (masked) but keep their coincidence gate live; unmask a weight only once its gate crosses threshold.
  - **Test:** continual-learning capacity — number of sequential tasks learned before collapse, silent-synapse pool vs a fixed dense net of equal *active*-param count.

- **AMPA/NMDA coincidence detection is a molecular AND gate (Mayer, Westbrook & Guthrie 1984; Nowak et al. 1984).** NMDA conducts only when glutamate is bound AND the membrane is depolarized (Mg²⁺ block relieved); AMPA is fast/linear, NMDA is slow, supralinear, and the Ca²⁺ source that gates plasticity — it reads pre×post coincidence.
  - **ALMA:** on top of the dendritic-bump supralinearity (§1), add a two-channel synapse — a fast linear AMPA path plus a slow NMDA path with gain `σ(pre)·σ(post)` that feeds the plasticity signal.
  - **Test:** single-unit coincidence/XOR — one two-channel synapse-unit solving pairwise coincidence a one-channel linear unit cannot — and whether the NMDA Ca²⁺ signal predicts *which* weights should change on a held-out probe better than the raw gradient.

- **Synaptic tagging & capture (Frey & Morris 1997).** A weak event sets a short-lived tag but no lasting change; a strong event floods the cell with plasticity-related proteins that only tagged synapses capture, converting early-LTP to persistent late-LTP — why a trivial event near a salient one gets remembered.
  - **ALMA:** pairs directly with pain/pleasure (§6). Tag weights carrying large recent local activity (decaying tag); write to slow weights only when a global salience/reward signal fires.
  - **Test:** one-shot recall of a neutral cue seen just before a reward, tagging+capture vs flat consolidation, at matched slow-weight write budget. *(Cross-ref: one-shot salient write, §8.)*

- **Homeostatic synaptic scaling keeps Hebbian learning stable (Turrigiano et al. 1998).** *(Consolidated here — this mechanism appears identically as a plasticity brake.)* Multiplicative synaptic scaling renormalizes all of a neuron's inputs toward a firing-rate set-point, preserving *relative* weights (the Hebbian memory) while preventing runaway; hard/soft bounds keep individual weights finite. Stability without freezing plasticity — the brake on Hebbian potentiation.
  - **ALMA:** add per-unit multiplicative normalization of the *slow weights* toward a target output variance (distinct from LayerNorm, which is per-activation and carries no set-point memory); maintain a per-neuron running-mean activation and, between minibatches, scale incoming weights toward the target.
  - **Test:** (a) long training on a drifting input distribution — weight-norm blow-up and dead/saturated-unit fraction, scaling vs without, at equal task loss (scaling should hold the active-unit fraction up); and (b) with scaling on, max stable learning rate rises and grad-norm variance drops with no accuracy loss — quantify max-stable-LR and grad-norm variance. *(Offline/global version of this renormalization = sleep downscaling, §7.)*

---

## 3. Plasticity: pruning, forgetting, metaplasticity, replay

Learning is as much subtraction and gating as addition. The brain spends energy to prune, to forget, and to protect what is already good.

- **Synaptic pruning + use-it-or-lose-it competition.** *(Consolidated with microglial pruning from the glia domain — same mechanism, two vantage points.)* Cortex overproduces synapses, peaking in early childhood, then eliminates ~40% to adult levels (Huttenlocher 1979). Elimination is activity-dependent, *competitive*, and keyed on a **usage tag, not weight magnitude**: weak/inactive synapses are opsonized by complement (C1q→C3) and phagocytosed by microglia (Stevens 2007; Paolicelli 2011; Schafer 2012) — so a small-weight-but-critical synapse can survive and a large-but-idle one can go. At the NMJ, poly-innervation resolves to mono-innervation as active inputs win. Pruning is capacity reclaimed, not damage.
  - **ALMA:** *iterative activity-tagged structured pruning* — score each unit/weight by a running usage/credit tag (C3-like opsonization) rather than |w|, and remove competitively on a schedule *during* training to free capacity mid-run.
  - **Test:** at matched final parameter count, iterative usage-tagged pruning beats one-shot train-then-prune AND the dense baseline on held-out accuracy; the freed capacity measurably absorbs a later task B (lower ppl on B than a statically-pruned net); AND, at identical target sparsity, usage-tag pruning retains a *rarely-fired-but-necessary* injected feature that magnitude-pruning discards.

- **Active forgetting is enzymatic and rate-controlled, not passive decay.** Rac1 signaling sets forgetting speed in *Drosophila* (Shuai 2010); dopaminergic tone actively erases specific memories via AMPA-receptor removal (Berry 2012). The brain forgets on purpose.
  - **ALMA:** couple to pain/pleasure — a *forget signal* (low reward / prediction-confirmed-stale / boredom) actively decays the specific weights that carried the stale association, not a global L2. *(This is the same sign-flip-into-unlearning move driven chemically in §5.)*
  - **Test:** on a distribution that flips mid-stream, active-forget recovers to new-task accuracy in fewer steps than vanilla overwriting, with lower residual interference (old wrong-answer rate) — measure steps-to-recover and residual error.

- **Metaplasticity (the BCM sliding threshold, as adaptive step-size).** The threshold for potentiation vs depression is itself plastic (θ_m slides with postsynaptic history; BCM 1982; "metaplasticity," Abraham & Bear 1996). A recently-active synapse resists further potentiation — this prevents saturation and makes weights *protectable*. *(The local-term reading of the same θ_m is §2.)*
  - **ALMA:** per-weight adaptive step-size derived *online* from recent activity/importance (a θ_m analog) gating how far each weight may move — importance computed live, not a stored Fisher penalty.
  - **Test:** on a 3-task continual stream, online metaplastic LR beats fixed LR and matches/beats an EWC-style penalty on average accuracy and backward transfer, *without* storing per-task Fisher matrices.

- **Critical periods.** *(Full treatment consolidated in §8 Development, where onset/closure biology and the reopen hook live.)* Foundational representations get frozen once good enough; ALMA's version is a per-module plasticity schedule with a chondroitinase-style reopen hook — see §8.

- **Catastrophic forgetting vs biological interleaving (complementary learning systems).** Sequential training overwrites old tasks in plain nets (McCloskey & Cohen 1989). Brains dodge this: hippocampus learns fast and specific, then *interleaves* replayed traces into slow neocortex (McClelland, McNaughton & O'Reilly 1995) — the mechanism behind sleep replay.
  - **ALMA:** a small episodic buffer storing *GIST-summaries* (not raw inputs) of past examples, interleaved into new-task minibatches. *(This is the same buffer the "night phase" replays in §7.)*
  - **Test:** gist-replay beats no-replay and matches/beats raw-example replay on average sequence accuracy at a fraction of the stored bytes — plot accuracy vs bytes-stored, showing gist-replay on the Pareto front.

---

## 4. Network structure & dynamics

Wiring is not function. Above the synapse, computation lives in balance, timing, sparsity, recurrence, and topology.

- **Connectome ≠ dynamics.** *C. elegans* is fully wired — 302 neurons, ~7000 synapses (White et al. 1986) — yet OpenWorm still can't reproduce locomotion from the adjacency matrix: synaptic weights, gap-junction conductances, and extrasynaptic neuromodulation live nowhere in the wiring. One connectome runs *different* programs under different neuromodulatory states (Bargmann 2012). Structure underdetermines function.
  - **ALMA:** already splits "who connects" (ALMIDO courts) from "how they weigh" (Bayesian weights) + a neuromodulator sketch.
  - **Test:** freeze learned topology, retrain only a modulatory gain vector on task-2; a fixed graph + swapped gains that beats a from-scratch net at matched params proves the state-vs-wiring split earns its keep.

- **E/I balance.** Cortex holds tight excitation–inhibition balance: inhibition tracks excitation within a few ms (Wehr & Zador 2003; Okun & Lampl 2008), yielding irregular asynchronous firing (van Vreeswijk & Sompolinsky 1996) plus gain control and fast transients.
  - **ALMA:** add separate E/I units (Dale's law) + a homeostatic regularizer holding mean-I ≈ mean-E current per unit.
  - **Test:** activation-variance and gradient-norm across depth vs an unconstrained net — E/I earns its place only if it trains deeper without exploding/vanishing at equal accuracy, or survives an input-scale attack the baseline fails.

- **Oscillations & binding.** Gamma synchrony (30–80 Hz) is the classic binding candidate (Gray et al. 1989); nested theta–gamma gives a ~7-slot ordinal code (Lisman & Idiart 1995); communication-through-coherence gates which pathways talk (Fries 2005).
  - **ALMA:** GIST pools in one shot with no temporal axis. Add a phase tag per feature; bind features sharing a phase, route by phase-coherence.
  - **Test:** superposition task (two objects, attributes must not mix — the binding problem) — phase-tagged routing wins iff attribute-swap error drops vs flat attention at matched params.

- **Sparse & population coding.** Cortex uses sparse, distributed codes: sparse coding of natural images alone yields V1-like Gabor fields (Olshausen & Field 1996); "concept cells" are sparse but not grandmother codes (Quiroga et al. 2005).
  - **ALMA:** add k-winners-take-all / L1 activity penalty on the gist layer.
  - **Test:** retention on task-A after training task-B vs the dense baseline — sparse code earns its place if it cuts catastrophic interference at equal single-task accuracy. *(Sparsity has a second, metabolic justification — §7 energy.)*

- **Attractor dynamics.** Fixed-point attractors implement persistent working memory (Wang 1999); continuous ring attractors hold analog variables — the head-direction bump imaged in the fly ellipsoid body (Seelig & Jayaraman 2015; Kim et al. 2017); Hopfield (1982) recall as energy minima.
  - **ALMA:** feed-forward + JEPA has no recurrent state store. Add a small recurrent attractor memory module.
  - **Test:** delayed-match with distractors during the delay vs a GRU/plain-RNN — attractor wins if hold accuracy stays flat as delay length and distractor count grow.

- **Small-world / modular topology.** Brain graphs are small-world — high clustering, short path length (Watts & Strogatz 1998; Bassett & Bullmore 2006) — and modular with a hub "rich club" (van den Heuvel & Sporns 2011), balancing segregation against integration.
  - **ALMA:** replace all-to-all dense layers with modular blocks + sparse long-range hub links.
  - **Test:** accuracy at matched params/FLOPs plus graceful degradation under random-unit lesioning — earns its place only if it hits equal accuracy at fewer connections and lesions more gently than the dense net.

- **3D locality & wiring cost.** Neuron placement is near wire-length-optimal: *C. elegans* somatic positions minimize total connection length (Cherniak 1994; Chen, Hall & Chklovskii 2006); long axons are metabolically expensive, so short local links dominate.
  - **ALMA:** give units 3D coordinates and add a `distance × |weight|` wiring-cost term to the loss.
  - **Test:** does the net self-organize into local clusters + few long hubs (measure total wire length, modularity) while matching accuracy? Win = same accuracy at lower wire — i.e. small-world topology emerging for free rather than hand-designed.

---

## 5. Neuromodulation & chemistry

A few small nuclei broadcast low-dimensional chemical signals to all of cortex, deciding *where, how much, and in which direction* local plasticity is consolidated. This is the **three-factor learning rule** (pre × post × neuromodulator on slow eligibility traces; Frémaux & Gerstner 2016; Gerstner et al. 2018) — the single frame under which every channel below acts.

- **Dopamine = reward-prediction-error, not reward.** Phasic VTA/SNc dopamine encodes the TD error `δ = r + γV(s′) − V(s)`: it fires to *unexpected* reward, transfers back to the earliest predictive cue, and dips on omission (Schultz, Dayan & Montague 1997). Tonic dopamine is separate — it sets vigor/response rate as the opportunity cost of time (Niv, Daw, Joel & Dayan 2007).
  - **ALMA:** ALMA has scalar pain/pleasure (the reward r) but not its *derivative* — add a value head V(s) and gate credit/learning-rate by δ.
  - **Test:** on a non-stationary bandit where the rewarded token flips mid-run, δ-gated plasticity recovers in fewer samples than constant-LR backprop (measure samples-to-recovery).

- **Acetylcholine = attention × plasticity gain, signalling expected uncertainty.** Basal-forebrain ACh raises the learning rate and boosts feedforward (thalamocortical) drive while damping recurrent loops, switching cortex between encoding and retrieval (Hasselmo 2006); it codes *expected* (known, in-context) uncertainty (Yu & Dayan 2005).
  - **ALMA:** add a per-region ACh scalar = predicted-noise estimate that multiplies the local learning rate.
  - **Test:** interleaved clean vs noisy-label contexts — ACh-gated LR cuts overfitting to the noisy context (lower clean-holdout error) vs a single fixed LR.

- **Norepinephrine = neural gain + network reset, signalling unexpected uncertainty.** Locus-coeruleus NE multiplies the slope of the input–output nonlinearity (adaptive-gain theory; Aston-Jones & Cohen 2005): tonic-high NE flattens gain → exploration; phasic NE sharpens the winner and *resets* the network at change-points (Bouret & Sara 2005); complements ACh as *unexpected* uncertainty (Yu & Dayan 2005).
  - **ALMA:** one global arousal scalar that (a) scales activation gain / softmax temperature and (b) triggers a state reset when surprise spikes.
  - **Test:** on a change-point task, NE-reset drops post-change error faster than no-reset, and a tonic-NE temperature schedule traces a better explore/exploit frontier than fixed temperature.

- **Serotonin = patience / temporal discounting, opponent to dopamine.** Dorsal-raphe 5-HT sustains waiting for delayed rewards (Miyazaki, Miyazaki & Doya 2011) and acts as an opponent channel to dopamine over aversion and time (Daw, Kakade & Dayan 2002).
  - **ALMA:** a 5-HT scalar that raises the effective discount γ and the cost of aborting a wait.
  - **Test:** on a small-sooner vs large-later choice task, moving the 5-HT knob shifts choice toward large-later *without retraining weights* (measure fraction large-later vs knob setting).

- **Neuromodulators are diffuse global broadcasts → the three-factor bottleneck.** A single small nucleus projects a low-dimensional signal to all of cortex by volume transmission, so plasticity = pre × post × neuromodulator on slow eligibility traces — a global scalar decides where local Hebbian change consolidates.
  - **ALMA:** keep local eligibility traces and drive them with a k-dim broadcast (the DA/ACh/NE/5-HT channels above) instead of the full backprop gradient.
  - **Test:** does accuracy hold as broadcast bandwidth k shrinks? If a handful of channels ≈ full-gradient backprop, the neuromodulatory bottleneck earns its place (measure accuracy vs k).

- **Chemical context gates plasticity *type*, not just rate.** The same spike pair yields LTP or LTD depending on neuromodulatory context — dopamine can invert the STDP window (Frémaux & Gerstner 2016) — and receptor class sets the time constant (fast ionotropic vs slow metabotropic).
  - **ALMA:** let a neuromodulator flip the *sign* of the update (reward → consolidate; punishment → route into the existing unlearning path), unifying pain/pleasure with forgetting. *(Same move as active forgetting, §3.)*
  - **Test:** sign-flipped plasticity does targeted unlearning — erase a poisoned association with less collateral loss on held-out good associations than uniform weight decay.

---

## 6. Drives, homeostasis, pain & pleasure

Set-points, interoception, and self-generated teaching signals turn the model from a supervised learner into a self-supervising organism. The teaching signal is *computed inside*, from the mismatch between expectation and outcome.

- **Homeostatic set-points are predictive negative-feedback loops, not reactive.** AgRP neurons drive feeding, POMC signal satiety; leptin/ghrelin are slow error signals (Zhang et al. 1994). The twist: AgRP hunger neurons are *suppressed within seconds by the sight and smell of food*, before a calorie is absorbed — error corrected on anticipation (Chen et al. 2015; Betley et al. 2015).
  - **ALMA:** add a scalar "information-hunger" set-point = running mean of JEPA prediction error, with negative feedback gating learning-rate and exploration temperature.
  - **Test:** on a non-stationary byte/letter stream with distribution shifts, ALMA-with-homeostat vs fixed-LR/fixed-temp — measure adaptation lag (steps for prediction error to fall back under threshold after each shift); the homeostat must re-stabilize measurably faster at matched compute.

- **Interoception: the brain reads and predicts its own internal state as a first-class signal.** The insula is interoceptive cortex (Craig 2002); internal-state perception is predictive/inferential (Barrett & Simmons 2015; Seth 2013). Body state is an *input to cognition*, never a label handed in.
  - **ALMA:** feed the model its own telemetry as input tokens — current loss level, uncertainty (from the Bayesian neuron), Beit-Din dissent magnitude, compute/memory budget.
  - **Test:** on a defer-or-answer task where the right move depends on the model's own confidence, the interoceptive model vs a blind baseline — measure calibration (ECE) and abstention reward; reading its own state must improve selective-prediction risk-coverage.

- **Nociception and reward are internally *computed* teaching signals, not external labels.** Dopamine encodes (actual − predicted) generated inside the animal (Schultz et al. 1997); nociceptors (Aδ/C) manufacture an aversive scalar from tissue-state. The organism supervises itself.
  - **ALMA:** replace supervised labels on a data subset with self-generated scalars — *pain* = surprise / constraint-violation (large prediction error or high Beit-Din dissent), *pleasure* = gist-compression gain / confirmed prediction.
  - **Test:** reduced-label regime — train on pure self-generated RPE-style signal vs supervised baseline at matched *labeled* budget; measure how much of supervised accuracy the internal signal recovers (target: most of it, with the label budget cut ≥10×).

- **Allostasis: stability through predictive change of the set-point itself.** Unlike reactive homeostasis, allostasis anticipates demand and *moves the target ahead of the error* (Sterling & Eyer 1988; Sterling 2012); chronic over-adjustment carries "allostatic load" (McEwen 1998).
  - **ALMA:** reuse JEPA to predict *upcoming demand* and pre-adjust LR / exploration / attention budget before the shift lands; track cumulative adjustment as an allostatic-load penalty to punish thrashing.
  - **Test:** on a stream where a cue reliably precedes each regime change, predictive pre-adjustment vs the reactive homeostat above — measure peak error spike at each transition and cumulative adjustment cost; predictive must cut the spike without inflating load.

- **Valence gates plasticity: the amygdala instance of the three-factor rule.** *(The general three-factor rule is §5; this adds valence assignment + delayed credit.)* Valence is assigned in the amygdala — distinct BLA populations for appetitive vs aversive associations (Namburi et al. 2015) — and eligibility traces bridge the action→outcome delay (Gerstner et al. 2018).
  - **ALMA:** multiply the local gradient by (valence scalar × per-synapse eligibility trace) so only updates a global pain/pleasure signal endorses get consolidated.
  - **Test:** delayed-reward credit-assignment task (reward N steps after the relevant token), three-factor gated update vs plain backprop — measure samples-to-solve as N grows; eligibility+valence gating should still assign credit across the gap where uniform backprop stalls.

- **Intrinsic motivation as drive-reduction; curiosity as learning-progress.** Hull's drive-reduction (1943) and Berlyne's curiosity (1960) formalize as: intrinsic reward = *compression/prediction progress*, not raw novelty (Schmidhuber 1991/2010; Oudeyer & Kaplan 2007). Prediction-error reward alone drives exploration (Pathak et al. 2017) but is trapped by stochasticity — the "noisy-TV" problem (Burda et al. 2018); learning-*progress* escapes it.
  - **ALMA:** set intrinsic reward = the *drop* in JEPA prediction error over a recent window (learning progress), so curiosity falls as a region of gist becomes predictable — true drive-reduction, not novelty-seeking.
  - **Test:** sparse/no-reward exploration with an injected stochastic "noisy-TV" distractor — learning-progress reward vs (a) no intrinsic reward and (b) raw prediction-error novelty; measure state-space coverage and fraction of budget wasted on the noisy source; learning-progress must cover more and not get trapped.

---

## 7. The non-neuron brain: glia, metabolism, sleep

Slow, spatially-pooled, and offline controllers sit *above* fast synaptic traffic — setting gain, enforcing an energy budget, consolidating overnight, and growing capacity on demand.

- **Tripartite synapse / astrocyte slow modulation.** One astrocyte wraps ~10⁵ synapses and integrates them on a seconds-to-minutes Ca²⁺ timescale, then feeds back gliotransmitters that gate LTP/LTD and set local gain (Araque et al. 1999) — a slow, spatially-pooled controller, not another neuron.
  - **ALMA:** GIST already pools an "essence"; add a per-region slow leaky state `a` (EMA of recent activation) that multiplicatively scales *learning rate and gain* for the units it covers — a plasticity gate, not a signal path.
  - **Test:** on a context-switch / continual-learning suite, astro-gated vs identical net with `a` frozen, matched params — measure retention (task-A accuracy after training B) and switch speed.

- **Microglial pruning.** *(Consolidated into §3 — usage-tag-not-magnitude pruning, with the rare-but-decisive-weight survival test.)* Microglia and the complement cascade (C1q→C3) are the *agent* of the pruning in §3; see there.

- **Energy is a hard constraint, and it forces sparsity.** Brain ≈ 20% of resting metabolism; grey-matter cost is dominated by restoring ion gradients after spikes (Attwell & Laughlin 2001). Energy-optimal codes are sparse (Levy & Baxter 1996) — sparsity falls out of an ATP cap, not a regularizer choice.
  - **ALMA:** add an explicit per-example energy term = activation/compute actually spent, with a hard budget that gates conditional compute (skip experts/courts when the budget is spent).
  - **Test:** at *matched inference FLOPs*, energy-constrained ALMA vs train-dense-then-prune-to-same-FLOPs — metric is accuracy-per-FLOP; the constraint earns its place only if it wins at equal compute, not equal params. *(Complements the coding-based sparsity of §4.)*

- **Sleep = offline replay + global downscaling.** Hippocampus replays waking sequences during rest/sleep, driving them into cortex (Wilson & McNaughton 1994; CLS, McClelland et al. 1995); SHY holds that sleep also multiplicatively *downscales* synapses to renormalize and fight saturation (Tononi & Cirelli 2014); glymphatic clearance spikes in sleep (Xie et al. 2013). Fast episodic store + slow structural store + periodic renorm.
  - **ALMA:** add a "night" phase that replays the stored gist buffer (§3) into slow weights, then multiplicatively downscales all weights (the offline, global form of the §2 scaling brake).
  - **Test:** replay+downscale vs online-only on sequential tasks — measure catastrophic forgetting (A after B) and whether downscaling removes the saturation-robustness gap **without the 2× accuracy cost** (directly retests the Beit-Din ledger finding).

- **Neurogenesis adds capacity on demand for pattern separation.** Adult dentate gyrus makes new granule cells that are transiently hyper-plastic and hyper-excitable, recruited to *separate similar memories*; ablating them impairs discrimination of near-identical contexts (Clelland et al. 2009; Aimone, Deng & Gage 2010). Capacity grows where novelty is high; new units learn fast then stabilize.
  - **ALMA:** grow units (Net2Net-style) when a novelty/surprise signal stays high; new units start with high LR ("young, plastic") and anneal.
  - **Test:** neurogenesis-on-surprise vs fixed-width net at *matched final param count* — feed near-duplicate inputs and measure pattern separation (representational distance between near-duplicates) plus forgetting of old classes.

- **Myelination is learnable and tunes timing, not just speed.** Oligodendrocytes myelinate in an activity-dependent way, adjusting conduction velocity so spikes from different paths arrive *coincidentally* — timing is a trained variable (Gibson et al. 2014, Monje lab; Fields 2015). Inter-area synchrony is learned.
  - **ALMA:** add a learnable per-edge delay, adjusted by a coincidence (Hebbian-timing) rule so upstream signals land in phase at a downstream integrator — relevant to any recurrent/temporal/spiking ALMA variant and to the dendritic-bump/BAC coincidence unit (§1).
  - **Test:** learnable-delays vs fixed-delay on a temporal-binding task that *requires* coincidence (two features must arrive together to fire the bump) — measure accuracy and the sharpness of the learned arrival-time distribution.

---

## 8. Development & social learning

The organism is built by a schedule: plasticity opens, narrows, and locks; it learns by watching, by approval, and from single salient events. Constraint early is a feature, not a limitation.

- **Critical/sensitive windows are gated, not passive.** *(Full home for critical periods; §3 defers here.)* Ocular-dominance plasticity in kitten V1 has a hard onset/offset (Hubel & Wiesel 1962, 1970): onset is triggered by maturation of parvalbumin GABAergic interneurons shifting E/I balance; closure is enforced by molecular brakes — perineuronal nets, Nogo/Lynx1 (Hensch 2005). Digesting PNNs with chondroitinase-ABC *reopens* adult plasticity (Pizzorusso et al. 2002). The window is a controlled resource, spent then locked.
  - **ALMA:** a per-module *plasticity schedule* — learning-rate/effective-rank starts high and decays on a maturation signal (data-volume or loss-plateau gated), keeping foundational layers (byte↔letter↔sound binding) highly plastic early then PNN-locking them while upper layers stay plastic, with an explicit "chondroitinase" reopen hook.
  - **Test:** front-loaded-then-frozen vs constant-LR, matched compute, 3 seeds — measure retention of early letter/phoneme structure AND catastrophic-forgetting on an old task after a late distribution shift. Earns its place only if it beats constant-LR on *both*.

- **Perceptual narrowing / "starting small".** Infants discriminate all phoneme contrasts, then lose non-native ones by ~10–12 months (Werker & Tees 1984). A net with *limited* early working memory learns grammar a full-capacity net fails to (Elman 1993); Newport's "less is more" (1990) says the same for children.
  - **ALMA:** curriculum + capacity ramp — short sequences / small context / low-rank first, widened on schedule (Bengio et al. 2009).
  - **Test:** capacity-ramped vs full-capacity-throughout on the factored-220 letter model, matched final compute — samples-to-threshold and final grammaticality on held-out long sequences.

- **Imitation & mirror systems.** Macaque F5 "mirror" neurons fire during both execution and observation of an action (di Pellegrino et al. 1992; Gallese et al. 1996) — a shared code for self-act and other-act. *(Neonatal imitation itself, Meltzoff & Moore 1977, failed a large replication — Oostenbroek et al. 2016 — so treat "innate imitation" as unproven; later observational learning is robust.)*
  - **ALMA:** warm-start by behavioral-cloning a teacher's rollouts into a shared action/gist space before RL.
  - **Test:** imitation-warmstart (BC from a competent teacher) vs from-scratch RL on Pong, matched environment steps, 3 seeds — episodes-to-champion. Also probe whether the *same* GIST code activates for observed vs executed rollouts (representational overlap ≥ chance) — the mirror property, not just faster learning.

- **Guided learning: caregiver approval as a reward signal.** Social approval recruits striatal dopaminergic reward circuitry; learning is scaffolded within the Zone of Proximal Development (Vygotsky) and gated by a secure base (Bowlby/Ainsworth). This is structurally RLHF — approval *is* the reward.
  - **ALMA:** a learned "caregiver" preference model supplies a shaping reward on top of sparse task reward (the parent-approval signal already sketched).
  - **Test:** approval-shaped vs pure task reward, matched task-reward budget — samples-to-threshold, and safety on held-out states (does approval-shaping reduce catastrophic/off-charter actions, not just speed?). Guard reward-hacking the preference model as a named failure mode.

- **Motherese / scaffolding — shaping the input, not just the target.** Infant-directed speech hyperarticulates: expanded vowel space and exaggerated prosody, cross-linguistically (Kuhl et al. 1997), sharpening phonetic boundaries. Tutors "scaffold" — reduce degrees of freedom to the learner's level, then withdraw (Wood, Bruner & Ross 1976).
  - **ALMA:** curriculum over *input clarity* — train early on prototype-enhanced / denoised / slowed exemplars, anneal toward the natural noisy signal.
  - **Test:** hyperarticulated-then-natural vs natural-throughout for letter/sound category formation, matched compute — category-boundary sharpness (margin between clusters) and few-shot accuracy on natural held-out. Must beat natural-throughout to justify the pipeline.

- **One-shot learning from a single salient event.** A single burn or fall produces lasting avoidance. Conditioned taste aversion is learned in *one* trial across an hours-long taste→illness delay, stimulus-selective — "preparedness" (Garcia & Koelling 1966). Salient events consolidate via amygdala-modulated, noradrenaline-gated enhancement of hippocampal memory (McGaugh 2000); fear conditioning is amygdala one-trial (LeDoux).
  - **ALMA:** salience-gated fast write — when |reward| or prediction-surprise exceeds a threshold, take a single high-LR/episodic write (couples to pain/pleasure + unlearning + synaptic tagging, §2/§3/§6).
  - **Test:** trials-to-avoid after *one* aversive event vs standard replay-based training, on a gridworld with a rare high-pain cell, 3 seeds — one-shot avoidance rate AND false-avoidance of safe cells (preparedness/selectivity, so it doesn't over-generalize).

---

## PRIORITISED EXPERIMENTS

The five highest-value, cheapest-to-run measurements across all domains — each extends a keystone claim at single-unit or small-net scale.

1. **Bump-unit fraction (§1):** swap a fraction of hidden units to non-monotonic bump-units; measure reduction in units-needed to reach fixed accuracy vs all-ReLU — extends this session's one confirmed WIN.
2. **Deep-neuron per param (§1):** micro-MLP-with-memory unit vs scalar unit at *equal total params*, held-out next-token loss — tests the whole "a neuron is a small temporal net" thesis at minimal cost.
3. **Dopamine as derivative (§5):** add a value head, gate LR by δ, on a reward-flip bandit; measure samples-to-recovery vs constant-LR — the cheapest test of turning scalar pain/pleasure into an RPE, the keystone for everything valence-gated.
4. **Slow-weight homeostatic scaling (§2):** with vs without per-unit multiplicative scaling toward a target output variance; measure max-stable-LR and grad-norm variance — near-free, and it stabilizes the training of every other mechanism here.
5. **Self-generated pain/pleasure at ≥10× fewer labels (§6):** train on internal surprise/compression scalars vs supervised baseline at matched labeled budget; measure fraction of supervised accuracy recovered — directly validates ALMA's core bet that internal signals can replace labels.