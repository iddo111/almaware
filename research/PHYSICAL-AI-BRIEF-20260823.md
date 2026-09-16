> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# PHYSICAL AI — INTELLIGENCE BRIEF
**Compiled 2026-08-23 · crawler run for Iddo · sources dated and labelled**

**Label key used throughout:**
`[MEASURED]` = number appears in a paper or model card with a described protocol ·
`[VENDOR]` = claimed by the organisation that built the thing, no independent check ·
`[PRESS]` = journalism / blog, primary source not located ·
`[UNSUPPORTED]` = widely repeated and I could not trace it, or it is wrong.

---

## 1. EXECUTIVE SUMMARY (read this, skip the rest if busy)

1. **The field consolidated on one recipe**: a 2–4B vision-language backbone + a separate *action expert* head emitting **action chunks** via **flow matching**. GR00T N1.7, π*0.6, Gemini Robotics 2 and Cosmos Policy are all variations. Architecture stopped being the differentiator; data became it.
2. **The headline 2026 result is EgoScale** (arXiv 2602.16710, 2026-02-18): 20,854 h of *human* egocentric video, action-labelled by hand-pose estimation + constrained retargeting, giving **downstream robot task completion 0.30 → 0.71 from 1k to 20k hours** `[MEASURED]`. It shipped — GR00T N1.7 is pretrained on it.
3. **And it is unreplicable in two independent ways.** (a) The published equation `L = 0.024 − 0.003·ln(D)` goes **negative for D > 2,981 h** — three of the five points it was fitted to. It cannot be an MSE. R²=0.9983 is on **5 points with 2 free parameters**. (b) **The 20,854-hour corpus is NVIDIA-internal** — no data-availability statement, "coming soon" on the project page, no HF repo; only the 829 h EgoDex slice is public. The *effect* is real; the *law* is decorative and the *x-axis* is private.
4. **The counter-evidence is stronger than the headline.** Lin et al. (ICLR 2025, 15,000+ real rollouts) `[MEASURED]`: **32 environment-object pairs is enough** for novel-environment generalisation; *"four data collectors working for one afternoon"* reached ~90% on unseen objects. And HumanScale (arXiv 2606.20521) `[MEASURED]`: at **equal data volume**, human egocentric video beats teleoperation — 24% lower validation loss, **+52.5%/+90%** real-robot success. The industry is buying the data type that saturates fastest and costs most.
5. **World models split cleanly**: (a) action-conditioned video generators used as data factories and learned simulators (Cosmos 3, Genie 3), (b) latent-dynamics predictors used for planning (V-JEPA 2). Only (b) closes a loop — V-JEPA 2-AC plans in **16 s** vs **4 min** for pixel generation, and beats it on manipulation **60–80% vs 0–20%** `[MEASURED]`.
6. **NVIDIA Cosmos 3** (2026-05-31): 64B Super / 16B Nano / 4B Edge, mixture-of-transformers (reasoning tower + diffusion generation tower), 1.3B training samples of which only **0.6% is action data**, **OpenMDW-1.1 — genuinely open, commercial use permitted** `[MEASURED, model card]`. Claims leadership on six benchmarks and publishes a number on none of them.
7. **The "robots fail 88% of real household tasks" statistic is misreported.** Both halves of the famous comparison are **simulators**: RLBench 89.4% and BEHAVIOR-1K 12.4%. It is a *sim-to-sim* gap between an easy short-horizon benchmark and a hard long-horizon one, not a measurement of real homes `[UNSUPPORTED as framed]`.
8. **The real failure evidence is better than the fake evidence.** Gemini Robotics 2 (2026-07-30, the current frontier) on its own published table: screw a bulb **36%**, dustpan **32%**, ziplock **40%**, trash bag **44%**, pick from floor **45.7%** `[MEASURED, DeepMind]`. Unscrew 92% / screw 36% is 2026 dexterity in one row.
9. **VLAs mostly memorise.** SAEs on π0.5 and OpenVLA: **97.37% of features on LIBERO, 89.19% on DROID, are memorised training sequences** (arXiv 2603.19183) `[MEASURED]`. Read every LIBERO leaderboard through that.
10. **Neuromorphic is worse than advertised, and partly fictional.** **"Intel Loihi 3" does not exist** — every circulating spec traces to AI-generated content farms. Innatera's "500× lower energy" has no baseline or methodology. The 2026 flagship neuromorphic-robotics paper's **chip never touched the robot**. Peer-reviewed: pruned SNNs use **1.61× MORE** energy than pruned ANNs once memory access counts.

**For Iddo specifically**: Isaac Sim/Lab and GR00T build natively on DGX Spark aarch64 (GR00T is an officially supported platform; N1.6-3B is 6.15 GB), but the whole SAPIEN ecosystem is x86-only and permanently out of reach. What transfers is *latent action pretraining*, *action chunking*, *relative action spaces*, and one memorisation diagnostic you specifically need. What does not is everything requiring a robot. **§9.**

---

## 2. ROBOT FOUNDATION MODELS / VLA POLICIES

### 2.1 The convergent architecture

By August 2026 essentially every frontier robot policy is:

```
[images ×N views] + [language] → VLM backbone (2B–4B)
                                       ↓ (cross-attn / shared tokens)
                                 action expert (0.3B–1.5B DiT)
                                       ↓ flow matching, K denoise steps
                                 action CHUNK: H future timesteps, emitted at once
```

Why chunks: a single-step policy re-plans every tick and jitters; a chunk of H≈16–50 steps executed open-loop is smoother and cheaper. Why flow matching over diffusion: fewer denoise steps for the same quality. Measured latency difference is large — **~750 ms/chunk for diffusion vs ~100 ms for flow matching** `[MEASURED, secondary]`; π0.5's 10-step flow chain is 241 ms of a 274 ms end-to-end budget on an A800 (arXiv 2605.08168 / 2604.05656 family).

**VLA-Perf** (arXiv 2602.18397, 2026-02-20) is the best inference-cost reference `[MEASURED]`. π0 (2.7B = SigLIP-So 0.4B + Gemma-2B + 0.3B action expert) end-to-end:

| Hardware | latency | rate |
|---|---|---|
| Jetson Thor | 52.57 ms | 19.0 Hz |
| RTX 4090 | 31.06 ms | 32.2 Hz |
| A100 | — | 61.7 Hz |
| H100 | — | 162.5 Hz |
| B100 | 3.18 ms | 314.4 Hz |

Key structural finding: **the action expert is memory-bound** (operator intensity 54.0 FLOPs/byte) while the vision encoder (321.4) and VLM (542.8) are compute-bound. Consequence: *adding more action tokens is nearly free; adding denoise steps is not* — 10→50 steps is 5× action-expert latency and 2.15× end-to-end.
<https://arxiv.org/html/2602.18397v1>

### 2.2 NVIDIA Isaac GR00T

| | N1.6 | N1.7 |
|---|---|---|
| Released | 2025-12-15 | 2026-04-17 |
| Params | 3B | 3B |
| VLM backbone | internal Cosmos-2B variant | **Cosmos-Reason2-2B** (Qwen3-VL arch) |
| Action head | 32-layer DiT (2× N1.5's 16) | same family |
| Action space | state-relative chunks | **relative end-effector, shared robot↔human** |
| State/action dim | 29 | **132** |
| Action horizon | 16 | **40** |
| Human video | — | **20K h EgoScale** |
| Export | — | ONNX + TensorRT |
| Code licence | Apache 2.0 | Apache 2.0 |
| Weight licence | NVIDIA one-way **non-commercial** (N1.6 card) | NVIDIA Open Model Licence, **commercially licensed** |

Sources: <https://research.nvidia.com/labs/gear/gr00t-n1_6> · <https://github.com/NVIDIA/Isaac-GR00T> · <https://huggingface.co/blog/nvidia/gr00t-n1-7> · <https://huggingface.co/nvidia/GR00T-N1.6-3B>

Hardware: inference **1 GPU, 16 GB+ VRAM**; fine-tuning **40 GB+ recommended, H100/L40** `[VENDOR, GitHub README]`. Data format: LeRobot v2 + `meta/modality.json`.

Note the architectural direction of travel: N1.6 *removed* the post-VLM adapter and instead unfroze the top 4 VLM layers. The trend is toward less bolted-on machinery and more of the backbone being trained.

**Unverified**: NVIDIA's own blog calls EgoScale "the first-ever scaling law for robot dexterity" and says 1k→20k h "more than doubles average task completion". The doubling claim **checks out** against the paper (0.30→0.71). The "first-ever" claim is marketing.

### 2.3 Gemini Robotics 2 (Google DeepMind, 2026-07-30) — newest frontier release

Three models shipped together `[MEASURED, DeepMind blog]`:
- **Gemini Robotics 2** — the VLA, vision+language → motor control, full humanoid and bi-arm, hands or grippers.
- **Gemini Robotics ER 2** — embodied-reasoning VLM, the planner; multi-step tasks "several minutes and hundreds of decisions"; multi-robot collaboration. **Publicly available via Google AI Studio.**
- **Gemini Robotics On-Device 2** — local, no network; adapts to a **new embodiment in a few hours / typically <200 examples**.

Published success rates — this is the honest picture of the frontier:

| Task | Robot | Success |
|---|---|---|
| Pick up from shelf | Apollo 2 + Inspire hands | 76.3% |
| Pick up from table | Apollo 2 | 68.4% |
| Pick up from floor | Apollo 2 | 45.7% |
| Unscrew bulb | Apollo + SharpaWave | 92% |
| **Screw bulb** | Apollo + SharpaWave | **36%** |
| Tie trash bag | Apollo + SharpaWave | 44% |
| Ziplock | Apollo + SharpaWave | 40% |
| Dustpan | Apollo + SharpaWave | 32% |
| Precise insertion | Franka Duo + gripper | 89.6% |
| Diverse tool kitting | Franka Duo | 78.9% |

Unscrew 92% / screw 36% is the whole story of 2026 dexterity in one row: destructive and tolerance-free actions work, assembly under tolerance does not.

Safety: new **ASIMOV-Agentic** benchmark; ER 2 claimed best-in-class on safety-constraint following and human-proximity `[VENDOR]`. Availability: VLA and On-Device are **Trusted Tester only, no published licence**.
<https://deepmind.google/blog/gemini-robotics-2-brings-whole-body-intelligence-to-robots/>

Predecessor Gemini Robotics 1.5 (arXiv 2510.03342) introduced the two things that carried forward: **Motion Transfer** (one unified motion representation across ALOHA / bi-arm Franka / Apptronik Apollo, so skills zero-shot across bodies) and **interleaved natural-language reasoning between action chunks**. <https://arxiv.org/abs/2510.03342>

### 2.4 Physical Intelligence π*0.6 + RECAP (arXiv 2511.14759, 2025-11-18)

The most important *learning-algorithm* contribution, as opposed to scale contribution.

Architecture `[PRESS, secondary analysis]`: **Gemma 3 4B VLM + 860M action expert**, emits sub-task text, discretised FAST tokens, and continuous action chunks at **50 Hz**.

**RECAP** = RL with Experience and Corrections via Advantage-conditioned Policies. Mechanism:
1. Train a value function that predicts *steps-to-success* from image+language, supervised on binary episode outcomes; reward −1 per step, −C_fail (≈−1000) on failure.
2. Advantage = actual outcome − V(state), **binarised** so ≈30% of actions are labelled "positive".
3. Train the policy conditioned on that label. **At inference, always condition on "Advantage: positive."**
4. Human teleop interventions are **forced to "positive"** regardless of computed advantage — this is how recovery behaviour gets into the distribution.

This converts RL into conditional supervised learning, which is why it works on a VLA at all.

Measured `[MEASURED, paper abstract]`: on the hardest tasks, **more than 2× throughput and roughly half the failure rate**. Per-task `[PRESS]`: laundry folding 2.1×, espresso 2.3×, box assembly 65%→90%. Deployment: 13 h continuous espresso, 2+ h novel laundry in unseen homes.
<https://arxiv.org/abs/2511.14759>

### 2.5 Figure Helix 02 (2026-02-02)

Three-tier, and the new tier is the interesting one `[VENDOR, Figure blog]`:
- **S0**: 10M-parameter whole-body controller, full joint state + base motion → actuator commands at **1 kHz**. Trained on **1,000+ h of human motion data** plus sim-to-real RL.
- **S1**: perception → full-body joint targets at **200 Hz**.
- **S2**: slow reasoning, scene understanding, sequencing.

Runs entirely on embedded GPUs on Figure 02. No parameter counts published for S1/S2, no benchmark table, no weights. Treat all Figure claims as `[VENDOR]` — they publish videos, not numbers.
<https://www.figure.ai/news/helix-02>

### 2.6 AgiBot GO-1 / GO-2 — the ViLLA idea

GO-1 (2025-03) introduced **ViLLA = Vision-Language-Latent-Action**: instead of conditioning actions directly on vision+language, predict **latent action tokens** first, then decode. Two experts: a **Latent Planner** trained on cross-embodiment *and human* data, and an **Action Expert** trained on 1M+ real robot demonstrations.
<https://agibot-world.com/blog/go1> · GO-2 announced: <https://www.agibot.com/article/231/detail/56.html>

Why this matters more than it looks: the latent-action layer means **you can pretrain on video with no action labels at all**. This is the same trick as LAPA (arXiv 2410.11758): train a VQ-VAE to quantise the *difference between consecutive frames* into discrete latent actions, pretrain a VLA to predict those, then fine-tune a small head mapping latent → real actuator commands. LAPA reports **>30× pretraining efficiency** vs conventional VLA pretraining and beat a SOTA model trained with ground-truth actions `[MEASURED]`. <https://arxiv.org/abs/2410.11758>

### 2.7 Others worth knowing

- **Cosmos Policy** (arXiv 2601.16163) — fine-tune a *video model* (Cosmos-Predict2) into a policy with **no architectural change**, encoding actions as latent frames inside the video latent diffusion. **LIBERO 98.5%, RoboCasa 67.1%** `[MEASURED]`, SOTA on both. Also emits predicted future frames + value, enabling test-time planning. <https://arxiv.org/abs/2601.16163>
- **X-VLA** (ICLR 2026) — soft-prompted transformer for cross-embodiment; now natively in LeRobot. <https://github.com/2toinf/X-VLA>
- **UnifoLM-VLA-0** (Unitree, 2026-01/03) — Qwen2.5-VL-7B base, 12-task manipulation, **weights released, CC BY-NC-SA 4.0**. Plus UnifoLM-WBT-Dataset, claimed largest open humanoid teleop dataset `[VENDOR]`. <https://github.com/unitreerobotics/unifolm-vla>
- **OpenVLA-OFT** — 97.1% LIBERO `[PRESS]`, the open baseline everyone reports against.

---

## 3. WORLD MODELS — what the word actually means in each case

The term is now doing three unrelated jobs. The 2026 surveys (arXiv 2605.00080, 2026-04-30, Abbeel/Malik/Wu/Du et al.; arXiv 2606.00113) settle on a useful test: **a world model must be action-conditioned and useful for downstream decision computation** — plausible video is not sufficient. "Visually plausible but action-inconsistent futures offer limited value for closed-loop decision making." <https://arxiv.org/abs/2605.00080>

### 3.1 The three concrete meanings

| Meaning | What it actually is | Examples | Used for |
|---|---|---|---|
| **Video prediction** | pixel-space generative model, optionally conditioned on actions | Cosmos 3, Genie 3, Sora-class | synthetic training data, eval environments |
| **Latent dynamics** | predict next *embedding*, never decode pixels | V-JEPA 2-AC, DINO-WM | planning in the loop, fast |
| **Learned simulator** | neural reconstruction of a *specific real scene*, interactive | PolaRiS, RobotArena∞, RoboWorld | cheap policy evaluation |

### 3.2 NVIDIA Cosmos 3 (announced 2026-05-31, GTC Taipei)

`[MEASURED, HuggingFace model cards]`:
- **Cosmos3-Super — 64B params.** Mixture-of-Transformers: an **autoregressive transformer for discrete tokens** + a **diffusion transformer for continuous multimodal generation**. Text ctx 4,096 (gen) / 256K (reasoning). Video up to 400 frames, 256p/480p/720p.
- **Cosmos3-Nano — 16B params.** Same architecture. Target: RTX PRO 6000-class workstation.
- **Cosmos3-Edge** — announced, "coming soon".
- **Cosmos3-Nano-Policy-DROID** — an actual action-generating policy variant for the DROID platform.
- In: text, image, video(+audio), **action trajectories**. Out: text, image, video, audio (AAC 48 kHz stereo), **action sequences as JSON**.
- Training data: **1.3B data points across 393 dataset entries** (2024–2026) — 22M text-reasoning, 767M image-gen, 348M video, 139M audio, **8M action** samples. Note how small the action slice is: 0.6%.
- Precision: **BF16 only** (FP4/FP8/FP16 unsupported at release). Ampere/Blackwell/Hopper, Linux only. 2×H200 ≈ 3 min per video.
- **Licence: OpenMDW1.1 — commercial use permitted.** This is genuinely open, unlike GR00T N1.6's weights.
- Stated limitations, in NVIDIA's own words: *"temporal inconsistency, unstable camera or object motion, imprecise physical interactions"*; **no explicit physics simulation**; unsuitable for safety-critical use without further validation.

<https://huggingface.co/nvidia/Cosmos3-Super> · <https://huggingface.co/nvidia/Cosmos3-Nano> · <https://nvidianews.nvidia.com/news/nvidia-launches-cosmos-3-the-open-frontier-foundation-model-for-physical-ai>

Also relevant, and more useful at your scale: **Cosmos-Reason2** at **2B / 8B / 32B**, post-trained from Qwen3-VL-2B/8B/32B-Instruct, NVIDIA Open Model Licence with Apache-2.0 additional info. This is the backbone GR00T N1.7 uses. <https://huggingface.co/nvidia/Cosmos-Reason2-2B>

**Benchmark claims are weak.** NVIDIA claims leadership on Artificial Analysis, Physics-IQ, PAI-Bench, R-Bench, RoboLab, RoboArena, VANTAGE-Bench, TAR — and publishes **no numbers** in either the press release or the developer blog `[VENDOR, unnumbered]`. See §6.4 for why the Physics-IQ claim in particular should be discounted.

### 3.3 Genie 3 (DeepMind)

Real-time interactive world generation from text: **20–24 fps at 720p**, coherent for "a few minutes", modifiable mid-exploration by prompt `[VENDOR]`. Robotics pitch is egocentric synthetic data at scale. **Access: research preview / Google AI Ultra in the US only.** No weights, no API for robotics. Treat as a demonstration of what is possible, not a tool you can use.
<https://deepmind.google/models/genie/>

### 3.4 V-JEPA 2 (Meta) — the one that plans

The counter-example to the video-generation approach, and the most intellectually interesting `[MEASURED]`:
- Self-supervised video pretraining, then **V-JEPA 2-AC** action-conditioned with only **62 hours of robot data**.
- Deployed **zero-shot on Franka arms in two different labs**, no data from those environments, no task-specific training, no reward.
- **65–80% pick-and-place success on new objects in unseen environments.**
- Head-to-head vs Cosmos: reach **100% vs 80%**, manipulation **60–80% vs 0–20%**.
- **Planning time 16 s vs ~4 min** for pixel-generation planning.

<https://ai.meta.com/blog/v-jepa-2-world-model-benchmarks/> · <https://arxiv.org/abs/2506.09985>

The lesson: for closed-loop use, **not decoding pixels is a feature**. Predicting in latent space is 15× faster and, on manipulation, better.

### 3.5 World models as evaluators (the quietly important use)

Real-robot evaluation is the bottleneck in the field, so 2026 built neural evaluators:
- **PolaRiS** (arXiv 2512.16881) — neural reconstruction turns a short video scan of a real scene into an interactive sim.
- **RobotArena∞** (arXiv 2510.23571) — real-to-sim benchmarking at scale. Its headline finding is a criticism: *VLAs' performance declines on environments beyond training, "current models are not true generalists yet."*
- **RoboArena** (arXiv 2506.18123) — crowd-sourced **double-blind pairwise** real-robot evaluation across 7 academic institutions on DROID, **600+ pairwise episodes, 7 policies**. Ranks policies more accurately than centralised eval `[MEASURED]`. This is the closest thing the field has to an honest leaderboard.
- **RoboWorld** (arXiv 2607.01060), **RoboDojo** (arXiv 2607.04434) — same direction, mid-2026.

---

## 4. SCALING LAWS FOR EMBODIMENT — and the crack in the headline one

### 4.1 EgoScale (arXiv 2602.16710, submitted 2026-02-18)

NVIDIA GEAR + UC Berkeley + UMD + Stanford. Authors incl. Ruijie Zheng, Trevor Darrell, Yuke Zhu, Danfei Xu, Linxi "Jim" Fan.

**What they built** `[MEASURED]`:
- **20,854 hours** of action-labelled egocentric human video — >20× prior efforts. **9,869 scenes, 6,015 tasks, 43,237 objects.** Includes EgoDex (829 h, Apple Vision Pro wrist+hand tracking) plus in-the-wild household/industrial/retail/educational recordings.
- **Action labels are derived, not recorded**: camera motion from off-the-shelf SLAM; hand pose from off-the-shelf estimators; then **25 keypoints/hand (3D position + orientation) retargeted into the 22-DoF joint space of the Sharpa Hand** by constrained optimisation (CasADi + IPOPT, enforcing joint limits and kinematics).
- Model: GR00T-N1-style flow VLA — VL backbone + DiT action expert + per-embodiment MLP adapters + shared wrist-motion prediction. **Parameter count not disclosed.**
- Plus 50 h of *aligned human-robot* mid-training data (separate from the 20,854 h).

**Headline results** `[MEASURED]`:
- Downstream average task completion rises **monotonically 0.30 (1k h) → 0.71 (20k h)** on a Galaxea R1Pro humanoid with 22-DoF Sharpa hands, 5 tasks: shirt rolling ~0.80, card sorting ~0.70, tong fruit transfer ~0.65, bottle-cap unscrewing ~0.55, syringe liquid transfer ~0.30.
- **+55% average task completion** vs training from scratch (the abstract says "54%" — the body says "over 55%"; minor internal inconsistency).
- Cross-embodiment: **>30 percentage points** absolute improvement on a Unitree G1 with a 7-DoF tri-finger hand, on both tested tasks.

### 4.2 ⚠️ THE SCALING LAW ITSELF DOES NOT SURVIVE ARITHMETIC

Verbatim from the paper:

> "we observe a remarkably clean log-linear scaling law: **L = 0.024 − 0.003 · ln(D)**, where D denotes the number of hours of human pretraining data. The fitted curve achieves an R² of 0.9983, indicating an almost perfect linear relationship in log space."

L is defined as **MSE on a held-out set of 2,000 egocentric human episodes**, predicting wrist and hand actions. An MSE cannot be negative. Solve for L = 0:

```
0.024 − 0.003·ln(D) = 0  →  ln(D) = 8  →  D = e^8 ≈ 2,981 hours
```

The five fitted points are **1k, 2k, 4k, 10k, 20k hours**. The equation as printed yields a **negative loss for 4k, 10k and 20k — three of the five points it was fitted to.**

Conclusion `[MEASURED — my own arithmetic on their published equation]`: **the printed equation is wrong.** Most likely the base is log₁₀, not ln. With log₁₀ the numbers become sane: L(1k)=0.0150, L(20k)=0.0111 — a **~26% reduction in held-out MSE for a 20× increase in data**.

Three further caveats, all material:
- **R²=0.9983 on 5 points with 2 free parameters is not evidence of a law.** Three degrees of freedom. Any smooth monotone curve fits.
- **The loss is measured on human video, not robot performance.** The law says "more human video → better prediction of human hand poses." That is close to a tautology. The link to robot success is a separate, correlational claim over the same 5 points.
- **There is no Limitations section.** The paper has no discussion of failure modes, no negative results, and no stated regime of validity. The Conclusion offers only future directions ("no saturation within the explored regime").

The **effect** is real and worth taking seriously — 0.30 → 0.71 downstream is a large, well-measured improvement, and it shipped in GR00T N1.7. The **law** is presentational.

### 4.3 Other scaling evidence, and it disagrees

- **Diminishing returns are the norm elsewhere** `[PRESS, aggregating multiple studies]`: task-specific fine-tuning shows steep initial gains then flattening — simple tasks ~5 h, complex bimanual 100+ h. Human-to-robot synthesis studies see most of the gain between 5 and 20 demonstrations, then ceiling effects.
- **Neural Scaling Laws in Robotics** (arXiv 2405.14005) is the earlier attempt; EgoScale did not supersede or cite-and-refute it.
- **Cross-embodiment scaling can be negative.** Adding more embodiments is not free: bipedal platforms (Unitree H1, G1) with little similar-embodiment data in the mix **suffer pronounced degradation** under cross-embodiment training vs isolated training. Negative transfer appears when suboptimal trajectories dominate and embodiment diversity is high (arXiv 2602.18025, 2511.04671) `[MEASURED]`.
- The honest summary of 2026: **scale in human video is the one axis with clean evidence of not-yet-saturating returns.** Robot teleop data, model depth, and embodiment count all show mixed or negative results.

### 4.4 The two results that most damage the scaling narrative

Both are in §5.8 in full; they belong here too because they are scaling results.

- **Lin et al., ICLR 2025** (arXiv 2410.18647) `[MEASURED]` — 40,000+ demonstrations, **15,000+ real-world rollouts**, controlled protocol. Generalisation is a power law in **environments** and **objects** (r = −0.94 to −0.98), but **saturates at 32 environment-object pairs**, ~50 demos each, plateauing at 800–1,600 total demos. Their own summary: *"with four data collectors working for one afternoon, we collect sufficient data to enable the policies for two tasks to achieve approximately 90% success rates in novel environments with unseen objects."*
- **HumanScale**, MIT/NUS (arXiv 2606.20521, 2026-06-19) `[MEASURED]` — at **equal pretraining volume**, egocentric human video beats teleoperation data: **24% lower validation loss** on real-robot action prediction, **+52.5%** in-distribution and **+90%** out-of-distribution real-robot success.

**The reconciliation** (see §5.9): pretraining scale still pays, but only from *cheap human video*; *task-specific teleoperation* saturates at a few dozen environment-object pairs. The frontier labs are spending most heavily on exactly the data type that saturates fastest and costs the most per hour.

</content>
---

## 5. DATA — where it comes from, what it costs, who owns it

### 5.1 The public real-robot corpus is about 5,000 hours. That is all of it.

| Dataset | Size | Embodiments | Licence | Owner |
|---|---|---|---|---|
| **Open X-Embodiment** | 1M+ trajectories, 527 skills, 160,266 tasks, 60 pooled datasets. **Hours not stated by the authors** | 22 | Apache-2.0 (code) + CC-BY 4.0 (materials); **components retain their own terms** | Google DeepMind + 21 institutions |
| **DROID** | 76,000 traj / **350 h**; 564 scenes, 86 tasks, 52 buildings, 1.7 TB | 1 (Franka Panda) | **CC-BY 4.0** | 13 institutions. Last substantive update Apr 2025. **No DROID 2.0 exists** |
| **BridgeData V2** | 60,096 traj (50,365 teleop + 9,731 scripted) | 1 (WidowX) | see repo | UC Berkeley RAIL |
| **AgiBot World Alpha** | 100k+ traj / **595.31 h**, 9.66 TB | mobile dual-arm | CC BY-**NC**-SA 4.0 | AgiBot |
| **AgiBot World Beta** | **1,003,672 traj / 2,976.4 h**, 100 robots, ~43.8 TB | mobile dual-arm | CC BY-**NC**-SA 4.0, gated | AgiBot / OpenDriveLab |
| **AgiBot World 2026** | 13.2 TB, "hundreds of hours", 100% real; includes an RL theme with 6-axis force/torque | AgiBot G2 | CC BY-**NC**-SA 4.0 | AgiBot |
| **RoboMIND v1** | 107k traj, 479 tasks, **5k labelled failure demos** | 4 | Apache-2.0, gated | Beijing Innovation Center + PKU + BAAI |
| **RoboMIND 2.0** | **310K+ dual-arm traj**, 739 tasks, 12K tactile eps | 6 | CC BY 4.0 | same |
| **ARIO** | ~3M "episodes" — but **only 3,662 are newly collected real-world**; 703,088 sim; 2,326,438 are reformatted existing datasets | aggregate | see project | Chinese consortium |
| **NVIDIA PhysicalAI-GR00T-X-Embodiment-Sim** | 320k+ **synthetic** traj, ~15 TB, 13.2M downloads | multi | **CC-BY 4.0** | NVIDIA GEAR |
| **LeRobot community** | 1,222 public datasets from 377 users | mostly SO-100 / Koch | per-dataset | Hugging Face |

**The load-bearing number, and it comes from a vendor with every interest in claiming the opposite** — Scale AI, 2025-09-24 `[VENDOR-CLAIM]`: *"Today's relevant open-source datasets, including DROID and Open X-Embodiment, offer only about 5,000 hours of interaction data combined."* The arithmetic checks out (DROID 350 + AgiBot Beta 2,976 + Alpha 595 + the rest).
<https://scale.com/blog/physical-ai>

**Note the ARIO trap**: a "3M episode" dataset in which **0.12% is new real-world data** and 78% is other people's datasets reformatted. Episode counts in this field are not comparable across datasets.

**LeRobot's data quality is poor, and Hugging Face says so themselves** `[MEASURED — first-party audit, 2025-05-11]`: missing and ambiguous task annotations, inconsistent camera naming (`images.laptop` used for both third-person and gripper views), episodes with "only 1 or very few frames", manually deleted files breaking sequence consistency, mismatched action/state dimensions for the same robot.
<https://huggingface.co/blog/lerobot-datasets>

### 5.2 Egocentric human video is now bigger than robot data by 20×

| Dataset | Hours | Licence | Notes |
|---|---|---|---|
| **Egocentric-100K** (Build AI) | **100,405 h**, 10.8B frames, 24.79 TB, 14,228 factory workers | **Apache-2.0**, gated | **The largest permissively-licensed egocentric corpus in existence.** 1.2M downloads. SE-Asian factory networks, head-mounted fisheye |
| Ego4D | 3,670 h; 931 wearers, 74 locations, 9 countries | CC-BY-**NC** + signed agreement | Meta-led consortium |
| Ego-Exo4D v2 | 1,286 h total / **221 ego-hours** | signed licence | Meta + 12 universities |
| **EgoDex** (Apple) | **829 h**, 338k episodes, 194 tasks, paired 3D hand/finger tracking | CC-BY-**NC-ND** | Apple Vision Pro. The ND clause arguably blocks derived annotation sets |
| EPIC-KITCHENS-100 | 100 h, 90K actions, 45 kitchens | non-commercial | Bristol |
| Aria Gen 2 Pilot | 12 sequences × ~5 min ≈ **1 hour** | Meta open terms | A demo, not a corpus |
| Noitom HiPHI | 617.5 h high-precision mocap | free public | Released at WRC 2026-08-20 `[PRESS/UNVERIFIED]` |
| "EgoSuite-Open100K" (Lightwheel) | *claimed* 100,000 h | claimed | **⚠️ Could not verify.** No `lightwheel` dataset on HF. Lightwheel's own page advertises 300,000 h delivered as a **B2B product** with no open release. `[UNSUPPORTED]` |

### 5.3 ⚠️ EgoScale's 20,854 hours is NVIDIA-internal. Verified negative.

You asked specifically. The answer is that **the corpus is not public and there is no stated plan to release it.**
- The paper contains **no data-availability statement**.
- The project page says only **"GitHub (Coming Soon!)"**.
- **No HuggingFace dataset exists.**
- The paper names exactly one component: *"we additionally incorporate 829 hours of EgoDex dataset."* The other ~20,000 hours is described only as "in-the-wild egocentric recordings." **No per-source breakdown is published.**
- The only independently obtainable slice is EgoDex's 829 h, under CC-BY-NC-**ND**.

**NVIDIA published a scaling law whose x-axis nobody else can reproduce.** Combined with §4.2 (the equation is arithmetically broken), the headline result of 2026 is unreplicable in two independent ways.

### 5.4 What a demonstration hour actually costs

Numbers with a traceable, named source:

| Rate | Who | Date | Label |
|---|---|---|---|
| **$25.25–$48/hr** | **Tesla**, posted pay for "Data Collection Operator, Optimus" — ~7 of 8 h in mocap suit + VR headset; height requirement 5'7"–5'11" | posting live 2024→2026 | `[VENDOR — employer's own rate card]` |
| **~$15/hr** | **micro1** — ~4,000 workers in 71 countries headcamming household tasks; receives **>160,000 h/month** | 2026-04-01 | `[PRESS — MIT Tech Review, named company]` |
| **¥20–40/hr (~$3–6)** to the worker; agency bills ¥25 for a ¥20 hour | Chinese teleop-glove operators | 2026-06 | `[PRESS — 36kr, first-person account]` |
| **¥50–100/hr** wearable capture; **~¥250/hr** robot-in-loop (internal production cost) | **Gao Jiyang, CEO of Galaxea** | 2026-06-17 | `[VENDOR — named executive]` |
| **¥200–400/hr** without robot; **¥500–1,000/hr** with robot (list price) | **Mifeng** platform (AgiBot-backed) | 2026-04-17 | `[VENDOR — price list]` |
| **¥4,000–6,000/month** full-time collector; ads quote ¥200/day | Chinese labour market (Boss Zhipin) | 2026-06 | `[PRESS]` |
| US wages **~3×** Vietnam/India for the same capture — US home environments are worth more | Ravi Rajalingam, founder, Objectways | 2026-04-01 | `[PRESS — named exec]` |
| **>100,000 production hours**; clients **Physical Intelligence, Generalist AI, Cobot** | Scale AI Physical AI Data Engine | 2025-09-24 | `[VENDOR]` — **no pricing disclosed** |

Converted: Chinese client-facing **robot-in-the-loop teleop ≈ $70–140/hour**; blended internal production cost **≈ $14–21/hour**; the labour input itself is **$3–6/hour**.

**⚠️ The Western benchmark series everyone quotes is unsourced.** The figures "$340/hr (early 2024) → $136/hr (Q4 2025) → $118/hr (Mar 2026 fully loaded)", and the "$15–30 / $40–80 / $80–150 per hour by program tier" ladder, appear across roboticscenter.ai, dataxpower.com, dexset.ai, evsint.com, claru.ai and truelabel.ai. Fetching the apparent origin (roboticscenter.ai, 2026-03-31) shows it cites **no research paper, analyst report, vendor data or external study for any figure**. These are self-published estimates that other SEO sites then re-cite as though sourced.

**A credible, independently sourced US/EU fully-loaded $/hour figure for teleoperated robot demonstration data is not publicly established as of August 2026.** `[UNSUPPORTED]` The only defensible Western anchors are Tesla's $25.25–$48/hr and micro1's ~$15/hr — both labour-only, neither loaded with hardware, QA or rejection rates.

### 5.5 Simulation: every quantified claim comes from the simulator vendor

`[VENDOR-CLAIM]` NVIDIA, 2025-03-18: *"NVIDIA generated 780,000 synthetic trajectories — the equivalent of 6,500 hours, or nine continuous months, of human demonstration data — in just 11 hours"*, and *"combining the synthetic data with real data, NVIDIA improved GR00T N1's performance by 40%, compared with using only real data."*

`[MEASURED-PAPER, first-party]` The GR00T N1 paper (arXiv 2503.14734) does show synthetic data helping in 30/100/300-demo sim regimes and in a real-world 10%-data regime.

**But note what happened next: GR00T N1.6 publishes no synthetic-data ablation at all.** Its stated additions are *"several thousand hours of teleoperated data"* from bimanual YAM arms, AgiBot Genie-1, simulated Galaxea R1 Pro on BEHAVIOR, and Unitree G1 locomanipulation.

Tooling as of Aug 2026: **Isaac Lab 3.0** in early access on **Newton physics 1.0** (GTC 2026); NVIDIA's **Physical AI Data Factory Blueprint** = Cosmos world models + OSMO orchestrator, turning one real scenario into thousands of synthetic variants. ManiSkill3 claims 10–1000× speedup at 30,000+ FPS `[AUTHOR-CLAIM]`.

**Honest read:** every quantified claim that synthetic data materially improves a *frontier* policy comes from the party selling the simulator. The frontier real-robot results of 2025–26 — π*0.6, Helix, LWD — attribute their gains to **real demonstrations, real corrections and real-robot RL**, not to synthetic data. Simulation is load-bearing for locomotion and RL and for cheap visual variation; there is **no public independent measurement showing it substitutes for real manipulation hours**.

### 5.6 The actual direction of travel: off teleop, onto video and fleet autonomy

- **RECAP / π*0.6**: pretrained on *"tens of thousands of hours of demonstrations"*, but per-iteration on-robot collection is **small** — 300 trajectories on four robots per iteration (laundry); 600 autonomous + 360 intervention trials per iteration (box assembly). `[MEASURED]`
- **LWD — Learning While Deploying** (Shanghai Innovation Institute / AgiBot / Columbia, arXiv 2605.00416, 2026-06-03) `[MEASURED]`: **16 dual-arm robots, 8 real tasks, ~60 total hours of online data across the fleet inside a 4-hour wall-clock budget.** SFT baseline 0.76 → **LWD 0.95** average success; long-horizon 0.68 → **0.91**.
- **Figure "Project Go-Big"** with Brookfield: claims first-person capture from **100,000+ residential units** `[VENDOR — no data released, no hours published]`.
- **Tesla** reportedly moved off mocap suits mid-2025 to a helmet+backpack rig with five cameras recording natural first-person execution `[PRESS/UNVERIFIED]`.

Both replacements — headcam human video and autonomous fleet rollouts with sparse human intervention — are **10–100× cheaper per hour** than robot-in-the-loop teleoperation.

### 5.7 Ownership: the moat is licensing, not secrecy

Commercially usable and at scale, the list is short: **DROID (350 h, CC-BY 4.0)**, parts of **OXE**, **NVIDIA's synthetic GR00T-X-Embodiment-Sim (CC-BY 4.0)**, and **Build AI's Egocentric-100K (Apache-2.0, gated)**.

Everything else large is **non-commercial** (all AgiBot World releases CC BY-NC-SA; Ego4D CC-BY-NC; EgoDex CC-BY-NC-ND), **gated**, or **entirely private** (EgoScale's 20k h, Physical Intelligence's mixture, Figure's Go-Big, Tesla's fleet, Lightwheel's 300k h, Scale AI's 100k h).

**So the Chinese "open source" datasets are open in name and closed in law.** CC BY-NC-SA means a US or EU company cannot legally pretrain a commercial model on AgiBot World. That is a moat implemented through licensing rather than secrecy — and it is more effective than secrecy, because it also generates goodwill.

Capital confirms the thesis: **Meta paid $14.3B for 49% of Scale AI at a $29B valuation** (June 2025) — an explicit bet that data collection, not architecture, is the scarce asset. Five Chinese embodied-AI companies are valued above ¥20bn primarily on data claims — and they measure data inconsistently (hours vs trajectories vs skills), making cross-company comparison impossible.

### 5.8 ⚠️ Four credible arguments that robot data is NOT the bottleneck

This is the most important subsection in §5, because it contradicts the entire industry narrative.

**① Diversity saturates fast. Volume buys very little.**
Lin et al., *Data Scaling Laws in Imitation Learning for Robotic Manipulation*, **ICLR 2025** (arXiv 2410.18647) `[MEASURED-PAPER]`: 40,000+ demonstrations and **15,000+ real-world rollouts** under a controlled protocol. Generalisation scales as a power law in **environments** and **objects** (r = −0.94 to −0.98) — but:

> *"when the number of training environment-object pairs reaches 32, it is generally sufficient to train a policy capable of operating in novel environments and interacting with previously unseen objects."*

Recommended 50 demos per pair; performance plateaus at ~800–1,600 total demos. And the punchline:

> *"with four data collectors working for one afternoon, we collect sufficient data to enable the policies for two tasks to achieve approximately 90% success rates in novel environments with unseen objects."*

**Four people. One afternoon. 90% on novel objects in novel environments.** If that holds, per-task data requirements are trivially small and the "millions of hours" framing is a fundraising artifact, not an engineering finding.

**② Human video beats teleoperation data hour-for-hour.**
*HumanScale* (MIT / NUS, arXiv 2606.20521, 2026-06-19) `[MEASURED-PAPER]`: under fixed post-training and validation protocols, **at equal pretraining data volume**, egocentric-pretrained models achieve **24% lower validation loss** on real-robot action prediction and **+52.5% / +90%** higher success in-distribution / out-of-distribution.

This attacks the teleop moat directly: **the expensive data source is also the worse one.**

**③ Engineering, not data.**
Ken Goldberg, *"Good old-fashioned engineering can close the 100,000-year data gap in robotics"*, **Science Robotics, Aug 2025** (DOI 10.1126/scirobotics.aea7390): internet-scale VLM training corresponds to ~100,000 years of experience; robotics will never collect that, so model-based methods, modular design and mechanical robustness must bootstrap learning rather than waiting for data. Goldberg to MIT Tech Review, 2026-04-01: *"It's going to take longer than people think."*

**④ The bottleneck is supervision conversion, not collection.**
Karcini, Schwager, Cadena, Hutter, Peters, Bou-Ammar et al., arXiv 2606.06556: *"The central bottleneck for future robotics is therefore not only how to scale policies, but how to convert unstructured physical experience into grounded robot supervision"* — because *"most of this information is not directly usable by robot policies because it lacks embodiment-specific action labels, task semantics, and reward structure."*

**⑤ And a competing bottleneck: evaluation.** RobotArena∞, PolaRiS and the ICLR 2026 real-to-sim cluster all argue real-world policy evaluation is unscalable and unreproducible — so the field **cannot reliably tell whether more data helped.**

### 5.9 Reconciling §5.8 with EgoScale

These look contradictory. They are not, and the reconciliation is the actual state of knowledge:

- **Lin et al.** measured *task-specific fine-tuning* data and found 32 environment-object pairs suffices. That is about the **last mile**.
- **EgoScale** measured *pretraining* data and found 1k→20k hours doubles downstream completion. That is about the **foundation**.
- **HumanScale** says that if you are going to spend on pretraining, spend it on **human video, not teleoperation** — 24% lower loss at equal volume.

The consistent picture: **pretraining scale still pays, but only from cheap human video; task-specific teleoperation data saturates at a few dozen environment-object pairs.** The industry is spending heavily on exactly the data type that saturates fastest and costs most.
---

## 6. NEUROMORPHIC / LOW-POWER EMBODIMENT

Short version: **the hardware story is worse than it is usually told, and two of the most-repeated facts in this field are false.**

### 6.1 ⚠️ "Intel Loihi 3" does not exist

Widely circulating in 2026: Loihi 3 at 4 nm, 8M neurons, 64B synapses/chip, 32-bit graded spikes, "commercial availability Q4 2026."

**Every one of those claims traces to AI-generated SEO content** — `tokenring-2026-*` articles auto-syndicated across financialcontent.com, thepilotnews.com, theeveningleader.com; `robocloud-dashboard.vercel.app` (which contradicts itself, quoting both 8M neurons and "1M neurons across 128 cores" — the latter being Loihi 2's actual spec); `machinebrief.com`; and `trainthealgo.com`, **dated June 2025, before the alleged announcement**.

Checked against Intel directly: the newsroom neuromorphic tag has no Loihi 3. Intel's only 2026 neuromorphic announcement is a research collaboration with Echo Neurotechnologies at Computex (**2026-06-02**) that names no chip.

**As of 2026-08-23, Loihi 2 is Intel's current and only shipping neuromorphic processor.** `[UNSUPPORTED — fabricated]`

### 6.2 ⚠️ Innatera's "500× lower energy" has no baseline

Innatera **Pulsar** is real and shipping — TSMC 28 nm, 2.8 × 2.6 mm, 36-pin WLCSP; 16K-parameter analog SNN engine + 49K-parameter digital SNN engine + 128K-parameter INT8 CNN accelerator + RISC-V CV32E40P at ≤160 MHz; 384 KB SRAM; **0.5 mW typical, 10 mW max**; est. <$5 in volume. Production since Q2 2025.
<https://www.innatera.com/product/> · <https://xpu.pub/2025/07/22/innatera-pulsar/>

Named-workload power `[VENDOR-CLAIM, no third-party replication]`: radar presence detection **600 µW**, audio scene classification **400 µW**.

But the headline "**100× lower latency, 500× lower energy**", repeated verbatim in every downstream article, has **no published benchmark, no named baseline chip, no methodology, and no third-party measurement**. `[UNSUPPORTED]`

Also undisclosed: **Innatera publishes no neuron count and no synapse count for Pulsar.** Open Neuromorphic lists both as N/A.

**Robotics deployments: zero.** All six CES 2026 partners are smart home, wearables, or industrial sensing — motor vibration monitoring, smoke/presence detection, wearable gesture, smart-home ODM, radar modules. No robot arm, no mobile robot, no drone. "Robotics" appears only as a future market category in a Synopsys EDA release.

The Loihi 2 robotics team's own assessment of Pulsar, in print: it *"appears to be more targeted towards one-dimensional sensor input for now"*, Talamo has no out-of-box multimodal fusion, *"Talamo is not open-source"*, and *"it is simply too early to know exactly what the Innatera Pulsar may be capable of."*

### 6.3 The 2026 flagship robotics paper — and its chip never touched the robot

**arXiv:2602.13747** (submitted 2026-02-14, accepted at IOP *Neuromorphic Computing and Engineering*), *"The More the Merrier: Running Multiple Neuromorphic Components On-Chip for Robotic Control"* — fortiss Munich + **Intel Neuromorphic Computing Lab Munich** + TUM + LMU. `[MEASURED-PAPER]`

Hardware: Intel Loihi 2 via vLab. **2–3 chips, 250–300 neurocores for ~30,000 neurons** — theoretical minimum was 4 neurocores, so a **~70× packing inefficiency** from connectivity and synapse footprint. Six concurrent on-chip components; the real contribution is an on-chip **neural state machine** that replaces off-chip process orchestration.

Measured on the Loihi 2 profiler: **0.22 W static + 0.67 W dynamic = 0.88 W**, **88 ms latency**, **59 mJ per step**.

Task results: simulated visual servoing **68%** (250 trials), real-robot insertion **70%**, ~1 minute per insertion.

**The caveat that reframes the whole paper:** three *disjoint* experiments.
1. Loihi 2 silicon — **pre-recorded event data only**; power/latency benchmark, no robot.
2. MuJoCo simulation — *"Due to the inefficiency and high latency of connecting the simulation to the real Loihi 2 chip within the Intel vlab we instead opt for running the architecture in simulated LAVA."*
3. Real KUKA iiwa — *"again using simulated LAVA"*, and with the relational network dropped and replaced by non-neural cropping.

Verbatim: **"Time and resource constraints prevented a full chip-robot integration."** The 68% and 70% figures were produced by **software SNN simulation on conventional hardware.**

Further honest limits the authors state: DNF peak forms ~1.8 s, classification spikes at 5–6 s; **80×80 input** downsampled from 640×480 by I/O bottlenecks; **~104 hand-tuned parameters** (34 interacting on one dynamic neural field); **non-deterministic LAVA compiler partitioning** changes spike timing and visibly changes behaviour between identical runs. Their own cited latency baseline — YOLOv8-s on Raspberry Pi 5 + Hailo-8L at **53 ms/frame** — is *faster* than their 88 ms.

Also note the abstract calls 0.88 W *"the milli Watt regime."* Against their own GPU comparison (~5 W mobile-GPU pipeline) the honest ratio is **~5.7×**.

### 6.4 The best real embodied result is from 2024 and is ~3×, not 200×

**Paredes-Vallés et al., *Science Robotics*, 2024-05-15** (TU Delft MAVLab) `[MEASURED-PAPER]`: fully neuromorphic drone, event camera → 5-layer 28,800-neuron SNN → control, on **Loihi generation 1** at 200 Hz.

| | Loihi | Embedded GPU |
|---|---|---|
| Idle | 0.94 W | 1 W |
| Network | **7–12 mW** | 2 W |
| **System total** | **~0.95 W** | **3 W** |

The "167–285×" figure everyone quotes is the **network-only** ratio. **System-level it is ~3×**, because Loihi's idle draw dominates. This is still the field's best embodied result, it is over two years old, and it is on the previous chip generation.
<https://www.science.org/doi/10.1126/scirobotics.adi0591>

### 6.5 Peer-reviewed evidence that SNNs *lose* on energy

- **ACM TACO 2026**, *"Rethinking the Energy Efficiency of SNNs and ANNs"* `[MEASURED-PAPER]`: once memory access is counted, **pruned SNNs consume 1.61× MORE energy than pruned ANNs** on CNN architectures. Code released. <https://dl.acm.org/doi/10.1145/3822176>
- **arXiv:2409.08290** (IEEE TCAD, v6 2026-08-04) `[MEASURED-PAPER]`: against *capacity-matched* quantized NNs (T timesteps ↔ ⌈log₂(T+1)⌉ bits), SNNs win only at **T = 5 with spike rate < 5.7%**, or **T < 4 with rate < ~7%**. *"SNN energy efficiency is not a given."*
- **Dampfhoffer et al., IEEE TETCI 2023**: SNNs compete only at **0.15–1.38 spikes per synapse per inference**; most published work ignores memory access and uses naive ANN baselines.

### 6.6 pJ/SOP — with provenance, and a warning

| Chip | pJ/SOP | Label | Note |
|---|---|---|---|
| LOKI (22 nm) | **0.266** | `[MEASURED-PAPER]` | academic accelerator, not a product |
| ODIN (28 nm FDSOI) | **12.7** | `[MEASURED-PAPER]` | silicon-measured, 256 neurons only |
| Loihi gen 1 (14 nm) | **23.6** (also quoted 15) | `[VENDOR]` | spread unresolved across sources |
| TrueNorth (28 nm) | **26** | `[VENDOR]` | IBM 2014 |
| Loihi 2 | ~10–12 | **`[UNSUPPORTED]`** | **Intel has never published an official pJ/SOP for Loihi 2.** No traceable primary source. Do not use |
| SpiNNaker2, Akida, Pulsar, Speck, Xylo, DYNAP-SE2 | **not published** | — | no vendor or third-party figure found |

**pJ/SOP is not comparable across chips.** Definitions of "synaptic operation" differ, and the metric excludes memory access, I/O and static power — exactly the terms §6.5 shows dominate. arXiv:2602.13747 makes the point concretely: **0.22 W of its 0.88 W is static**, and no pJ/SOP figure can see that.

Better-grounded system-level numbers: Loihi vs SpiNNaker2 on keyword spotting `[MEASURED-PAPER, IOP NCE 2021]` — **SpiNNaker2 7.1 µJ/inference @ 1000 inf/s** vs **Loihi 37 µJ @ 296 inf/s**; and on adaptive robotic control the winner *flips* with network shape. Neither dominates.

### 6.7 Everything else, briefly

- **IBM NorthPole** is **not neuromorphic** — 12 nm, 256 cores, 224 MB on-chip SRAM, 22B transistors, 200/400/800 TOPS at int8/4/2. It is a dense digital inference accelerator with **no spikes and no neuromorphic dynamics**. IBM's spiking chip was TrueNorth (2014). Calling NorthPole neuromorphic is a category error propagated by market reports. Not purchasable. No robotics deployment. `[MEASURED-PAPER: Science 2023, ISSCC 2024]`
- **BrainChip Akida** is **the only neuromorphic silicon a private person can buy**: AKD1000 PCIe **$289**, M.2 **$249**, RPi4 kit **$995**, RPi5 kit **$1,495**. On-chip learning is **final layer only**, binary weights and inputs. AKD1500/2000 not purchasable; Akida Pico is **FPGA-cloud evaluation only** since 2026-02-03 — no silicon exists you can hold. Commercial reality `[MEASURED — audited financials]`: BrainChip revenue **2025 $1.89M, 2024 $398K, 2023 $232K, 2022 $5.07M**. Under $2M/yr after a decade.
- **SynSense** Speck (DVS + SNN SoC, 320,000 neurons) / Xylo / DynapCNN2 — pricing "on application". The one concrete robotics case is a **toy robot** at a Chinese gaming fair that mirrors arm waving. A demo, not a deployment.
- **SpiNNaker2 / SpiNNcloud** — 152 ARM cores/chip, ≥10B neurons at rack scale. Real installs at **Sandia (June 2025, 150–180M neurons)** and TU Dresden. Datacentre scale, no pricing, irrelevant to embodiment.
- **Analog / in-memory / photonic**: one genuinely closed loop — a Bi₂Se₃ memristor reservoir network at U. Michigan balancing a **1-DoF seesaw at 7 µW** (ACS Nano, 2026-03-25). IBM HERMES (14 nm, 64 cores, 256×256 PCM crossbars) does CNN/LSTM, no robot control. Photonic accelerators reach 1 GHz / 3 ns per cycle but **no photonic accelerator has ever controlled a robot**. This track is device physics, not embodiment.

### 6.8 Is there a "neuromorphic winter"?

No peer-reviewed paper uses that framing, and the honest answer is more specific. Intel: research programme, no product, no announced successor. IBM: unbuyable and not spiking. BrainChip: <$2M/yr revenue, gen-1 silicon only. Innatera: shipping and real, and **explicitly not aimed at robotics**. SynSense: toy-robot demo. SpiNNcloud: two government/academic installs. Best embodied result: 2024, previous-gen chip, ~3× system-level. Peer-reviewed energy analyses put SNNs *behind* matched ANNs in the common case.

That is not a winter. It is a **fifteen-year plateau with exactly one commercially successful product, which avoids robotics on purpose.**

**Method warning for anyone else crawling this area:** it is heavily polluted by AI-generated content farms. Two of its most-repeated "facts" — Innatera's 500× and Intel's Loihi 3 — are respectively unsourced marketing and outright fabrication. Verify every spec against a vendor datasheet, a peer-reviewed paper, or an audited financial filing.
---

## 7. THE HONEST FAILURE MODES — what Physical AI cannot do in August 2026

### 7.1 First, kill a bad statistic

The most-repeated 2026 robotics number is **"robots fail 88% of real household tasks."** It ran in Forbes and eWeek in April 2026 and propagated to dozens of blogs, sourced to the Stanford HAI **2026 AI Index Report** (published 2026-04-13).

What the AI Index actually says, verbatim: *"Robots still have far to go on managing household chores—they succeed in only 12% of real household tasks like folding clothing or washing dishes."*
<https://hai.stanford.edu/news/inside-the-ai-index-12-takeaways-from-the-2026-report>

Tracing it back:
- The 12% is **12.4%** — the full-task success rate of the winning entry in the **1st BEHAVIOR Challenge @ NeurIPS 2025** (final eval 2025-11-16, results 2025-12-06/07). The same team's q-score, which includes partial credit, was **~0.26**. Method: a π0.5-derived VLA (SigLIP + Gemma). Training data: 200 demos/task, ~1,200 h across 50 tasks.
  <https://robot-learning-collective.github.io/winning-behavior-1k-challenge.html>
- **BEHAVIOR-1K runs in OmniGibson. It is a simulator.** 50 long-horizon household tasks in photorealistic simulation.
- The paired "89.4% in controlled simulation" figure is **RLBench** — which is *also* a simulator (CoppeliaSim/PyRep), and is short-horizon, single-arm, table-top.

**Therefore** `[UNSUPPORTED as framed]`: the famous "sim-to-real gap" comparison is **sim-to-sim**. It sets an easy short-horizon simulated benchmark against a hard long-horizon simulated benchmark. It contains no measurement of real homes at all. Describing BEHAVIOR-1K results as "real household tasks" is an error that originated in the AI Index's own summary wording and was amplified by press.

The underlying conclusion — long-horizon household autonomy is far away — is **true**. The evidence normally cited for it is **not the evidence people think it is**.

Also note: the **2026** BEHAVIOR Challenge had not concluded at time of writing — launched 2026-07-02, submissions close 2026-10-16, winners announced 2026-11-04. Anything presented as "2026 BEHAVIOR results" is the 2025 run.
<https://behavior.stanford.edu/challenge/index.html>

### 7.2 Use this evidence instead

**Frontier dexterity, self-reported by DeepMind, 2026-07-30** (see §2.3): screw a bulb **36%**, dustpan **32%**, ziplock **40%**, tie a trash bag **44%**, pick up from floor **45.7%**. These are the best numbers anyone has, published by the current leader, on purpose-built hardware, with hands that cost more than a car. Assembly under tolerance, deformable manipulation, and floor-level whole-body reaching are all sub-50%.

**RobotArena∞** (arXiv 2510.23571) `[MEASURED]`: *"VLAs exhibit notable sensitivity to dataset differences: their performance declines when evaluated on environments beyond those seen during training, suggesting that current models are not true generalists yet."*

### 7.3 VLAs largely memorise — the strongest negative result of 2026

**arXiv 2603.19183** (2026-03-19), sparse autoencoders on VLA residual streams `[MEASURED]`:
- Models probed: **π0.5** (PaliGemma + action expert) and **OpenVLA** (Llama 2 backbone).
- Method: TopK SAEs with AuxK auxiliary loss on residual activations across 8 layers; four activation-pattern metrics (episode coverage, mean onset count, mean activation magnitude, relative run length) classify each feature as general vs memorised **without running rollouts**.
- **97.37% of features are memorised training sequences on LIBERO. 89.19% on DROID.**
- The gap between those two numbers is the actual finding: **dataset diversity is the only lever that moves it**, and LIBERO — the benchmark the whole field reports — produces almost nothing but memorisation.
- The minority of general features are real and causal: steering F128 (pre-grasp alignment) makes the robot hover above objects without picking up; steering F1902 (transport) makes it skip grasps and fly straight to goal locations.

Corollary: **LIBERO scores of 97–98.5% (OpenVLA-OFT 97.1%, Cosmos Policy 98.5%) should be read as memorisation capacity, not capability.** This is the most important caveat in the whole brief for anyone reading leaderboards.

### 7.4 Turning a VLM into a VLA costs you the VLM

**arXiv 2606.19297** (2026-06-17), *"Does VLA Even Know the Basics? Measuring Commonsense and World Knowledge Retention in Vision-Language-Action Models"* `[MEASURED]`:
- **7 VLA models vs 9 VLM baselines.**
- New protocol **Act2Answer**: the agent must answer a knowledge question *through action* — placing an object on the correct answer in a tabletop scene.
- Finding: VLAs hold up on simple concepts but show **large gaps on richer semantic categories relative to their source VLMs**.
- Mechanistic detail: answer-relevant signal **peaks in middle VLA layers and attenuates in the upper layers**. VQA co-training during robot fine-tuning mitigates the loss.

This directly undercuts the central selling point of the VLA paradigm — that you inherit internet-scale semantic knowledge for free. You partly do not; fine-tuning on robot trajectories eats it.

### 7.5 Long horizon is a wall, and everyone hit it in Q2 2026

Four independent groups diagnosed the same failure between April and August 2026:
- **HELM** (arXiv 2604.18791): VLAs "fail systematically on long-horizon manipulation despite strong short-horizon performance", with three named deficits — **the memory gap, the verification gap, the recovery gap**.
- **Goal2Skill** (arXiv 2604.13942): limited observation windows plus end-to-end action prediction produce brittleness under partial observability and occlusion. Their result: **32.4% vs 9.8%** for the strongest baseline — note that a new state of the art on their benchmark is *32.4%*.
- **LoHo-Manip** (arXiv 2604.21924): long-horizon tasks are "brittle to compounding execution errors".
- **Don't Drop the Baton** (arXiv 2608.16889, August 2026): "errors compound beyond the policy's ability to correct, and the execution of one subtask silently constrains the next."

RECAP (§2.4) is the only method with a credible answer, and the answer is: **put a human in the loop and force their corrections into the positive-advantage distribution.** That is not autonomy.

### 7.6 Sim-to-real, measured properly for once

**arXiv 2603.22876** (submitted 2026-03-24, revised 2026-06-29), CUHK-Shenzhen, *"Grounding Sim-to-Real Generalization in Robotic Manipulation: An Empirical Study with VLA Models"* `[MEASURED]`:
- **Over 10,000 real-world trials** — the largest controlled sim-to-real study I found.
- Four axes: multi-level domain randomisation, photorealistic rendering, physics-realistic modelling, RL updates.
- Evaluation protocol explicitly controls background, lighting, distractors, object types, spatial features.
- **They release the robot platforms and the evaluation protocol** for independent verification. Rare, and worth rewarding with attention.

I could not extract the per-factor effect sizes from the abstract, and I am not going to guess them. The ranking of the four factors is in the full paper — open item.
<https://arxiv.org/abs/2603.22876>

### 7.7 The benchmarks themselves are unreliable

**"Physics-IQ Verified"** (arXiv 2606.18943, 2026-06-17) audits the very benchmark Cosmos 3 claims to lead `[MEASURED]`:
- The refinements touched **57.6% of dataset samples and 34.8% of prompts**.
- After removing spurious metric artifacts, **every model's score dropped**, p ≪ 10⁻⁵, Cohen's d ≤ −1 (large effect).
- **Ranking stability between original and corrected leaderboard: Kendall's τ = 0.46.** That is substantial reordering, not noise.
- Prompt wording alone moved **Sora 2 from 12.7 to 25.3** on the original metric — a **2× swing from rewriting the prompt**.

So "Cosmos 3 leads Physics-IQ" `[VENDOR, and published with no number]` is a claim on a benchmark demonstrated to be 2× prompt-sensitive and to reorder under artifact removal. Discount heavily.

### 7.8 Certification, not capability, is now the binding constraint

`[PRESS / standards documents — I did not read the ISO texts]`:
- **No single standard covers humanoid deployment in 2026.** Integrators stack ISO 10218:2025, ISO/TS 15066, ISO 13482 and ASTM standards.
- The humanoid-specific ones — **ASTM WK73939, revised ISO 10218, IEEE P7009** — are expected to ratify in **2027**.
- The structural problem is real and unsolved: ISO 12100 machinery risk assessment assumes bounded, pre-programmed trajectories with a definable worst case. A learned stochastic policy has no bounded worst case. Nobody has a certification story for that.
- The **EU AI Act August 2026 deadline did not move.**
- Survey: *A Comprehensive Survey on Physical Risk Control in the Era of Foundation Model-enabled Robotics* (arXiv 2505.12583).

DeepMind's **ASIMOV-Agentic** is the first serious attempt to make agentic robot safety measurable. It is one company's benchmark, self-scored, on its own models.

### 7.9 The position paper worth reading

**arXiv 2606.06556** (2026-06-08), *"Robots Need More than VLA and World Models"* — Karcini, Mehrban, Nguyen, Schwager, Ajoudani, Cadena, **Peters, Hutter**, Bou-Ammar. Argument: VLAs and world models are each incomplete; what is missing is physical grounding of constraints, explicit planning, temporal/causal reasoning, and reward modelling. Note the author list — Jan Peters and Marco Hutter are not outsiders throwing stones.
`[abstract-level only — PDF text extraction failed on my end; treat the detailed claims as unverified.]`

### 7.10 One paragraph: what does not work

Assembly under tolerance. Anything deformable that must end in a specified configuration. Recovery from the robot's own mistake. Tasks longer than roughly a minute without a human-authored decomposition. Any environment materially different from training. Retaining the base VLM's world knowledge. Being certified to operate near people. Everything else — pick, place, insert, wipe, pour, open, transport, in a seen environment, at chunk-level horizons — works well, and is genuinely new since 2024. The 2026 delta is real; it is just much narrower than the word "generalist" implies.
---

## 8. OPEN SOURCE — what you can actually download and run

Scoped to the hardware that exists in this house: **4× DGX Spark (GB10 Grace-Blackwell, aarch64, 121 GB unified, CUDA ≥13 / sm_121)** and one **RTX 3070 Ti (8 GB, x86)**. No robot.

### 8.1 The table

| Model / tool | Params | Licence | URL | Runs on DGX Spark? |
|---|---|---|---|---|
| **Isaac GR00T N1.7-3B** | 3B | NVIDIA Open Model Licence (weights) · Apache-2.0 (code) | <https://huggingface.co/nvidia/GR00T-N1.7-3B> | **YES — first-class.** Repo lists "DGX Spark (GB10): CUDA 13.0 / Py 3.12" as a supported platform |
| **Isaac GR00T N1.6-3B** | 3,286,608,832 | NVIDIA Open Model Licence | <https://huggingface.co/nvidia/GR00T-N1.6-3B> | **YES — measured on a real GB10:** 6.15 GB GPU mem, ~30 s load |
| **openpi** (π0 / π0-FAST / π0.5) | ~3.3B | Apache-2.0 + Gemma terms | <https://github.com/Physical-Intelligence/openpi> | **Unverified.** JAX-first, "tested on Ubuntu 22.04 only", no ARM claim anywhere |
| **SmolVLA** | 450M (915 MB) | Apache-2.0 | <https://huggingface.co/lerobot/smolvla_base> | Very likely — plain PyTorch, ~10–16 GB peak at batch 8 |
| **WALL-OSS-0.5** | 4B | **Apache-2.0** | <https://huggingface.co/x-square-robot/wall-oss-0.5> | Likely — LeRobot-integrated as `wall_x` |
| **RDT-1B** | 1B | **MIT — code, weights AND data** | <https://huggingface.co/robotics-diffusion-transformer/rdt-1b> | Likely |
| OpenVLA-7B / OFT | 7B | MIT code; **weights inherit Llama-2 terms** | <https://huggingface.co/openvla/openvla-7b> | Likely (PyTorch) — but its eval harness needs SAPIEN |
| AgiBot **GO-1** | ViLLA + MoE | see repo | <https://huggingface.co/agibot-world/GO-1> | Unknown. GO-2 announced Apr 2026, **no open weights found** |
| Unitree **UnifoLM-VLA-0 / WMA-0** | n/s | CC BY-NC-SA 4.0 | <https://huggingface.co/unitreerobotics/UnifoLM-WMA-0-Base> | Unknown |
| **Cosmos3-Edge** | 4B | **OpenMDW-1.1** (commercial OK) | <https://huggingface.co/nvidia/Cosmos3-Edge> | Likely — targets Jetson Thor/Orin, which are aarch64. GB10 not named |
| **Cosmos3-Nano** | 16B (8B reason + 8B gen) | OpenMDW-1.1 | <https://huggingface.co/nvidia/Cosmos3-Nano> | Probably — memory fits, **never validated on GB10** |
| Cosmos3-Super | 64B (32B+32B) | OpenMDW-1.1 | <https://huggingface.co/nvidia/Cosmos3-Super> | **NO on one Spark.** 64B bf16 ≈ 128 GB > 121 GB |
| Cosmos-Reason2 2B/8B/32B | 2/8/32B | NVIDIA Open Model Licence | <https://huggingface.co/nvidia/Cosmos-Reason2-2B> | Likely — vLLM cu130 aarch64 nightlies exist |
| **V-JEPA 2 / 2.1** | ViT-L→g | Meta research licence | <https://github.com/facebookresearch/vjepa2> | Likely — it is a first-class `transformers` model |
| **Newton 1.0** (physics) | — | **Apache-2.0** | <https://newton-physics.github.io/newton/> | **YES — docs name "Jetson Thor and DGX Spark" explicitly** |
| MuJoCo / MJX / Playground | — | Apache-2.0 | <https://github.com/google-deepmind/mujoco_playground> | Yes — MuJoCo ships Linux AArch64 wheels; MJX needs `jax[cuda13]` aarch64 |
| LIBERO / robosuite | — | MIT | <https://github.com/Lifelong-Robot-Learning/LIBERO> | Yes — MuJoCo-based, documented headless |
| Isaac Sim + Isaac Lab | — | Apache-2.0 | <https://learn.arm.com/learning-paths/laptops-and-desktops/dgx_spark_isaac_robotics/> | **YES but crippled — PhysX GPU is broken on GB10** |
| **ManiSkill3 / SAPIEN** | — | Apache-2.0 | <https://pypi.org/project/sapien/#files> | **NO. SAPIEN publishes zero Linux aarch64 wheels** |
| **SimplerEnv** | — | MIT | <https://github.com/simpler-env/SimplerEnv> | **NO. Needs SAPIEN (x86) *and* CUDA ≥11.8 and <13** |

### 8.2 The three things that matter in that table

**1. GR00T is officially supported on DGX Spark.** Not "should work" — the Isaac-GR00T repo lists GB10/CUDA 13.0/Python 3.12 as one of four supported platforms alongside x86 dGPU, Jetson AGX Thor and Orin. N1.6-3B was measured at **6.15 GB in bf16 on a real GB10**. You could hold fifteen copies in one Spark. This is not a memory-constrained problem.

**2. Licences are much better than they were.** Cosmos 3 ships under **OpenMDW-1.1** (Linux Foundation; commercial use and derivatives permitted with a "Built on NVIDIA Cosmos" attribution). GR00T N1.7 weights moved to the commercially-usable NVIDIA Open Model Licence. **RDT-1B is MIT for code, weights and data** — the most permissive thing in the field. WALL-OSS-0.5 is Apache-2.0. Note the trap in the other direction: **OpenVLA's code is MIT but its weights inherit Llama-2 restrictions** — do not treat them as MIT.

**3. Your fleet is a MuJoCo/Newton fleet, not a SAPIEN fleet.** This is the single biggest structural constraint and it is not negotiable. SAPIEN 3.0.3 on PyPI ships wheels for `win_amd64`, `manylinux_2_28_x86_64` and macOS universal2 — **and nothing else. No Linux aarch64 wheel exists.** SimplerEnv stacks a second, harder blocker: it requires CUDA ≥11.8 **and <13**, while GB10 *requires* ≥13. That is a logical contradiction, not a packaging inconvenience. ManiSkill3 and SimplerEnv are 3070 Ti workloads or nothing — and 8 GB will not hold a 7B OpenVLA eval.

### 8.3 The GR00T-on-GB10 recipe (four known breakages)

There is a published working fine-tune recipe: **Isaac-GR00T issue #474**. What breaks:
1. **`torch==2.5.1` pinned in `pyproject.toml` is wrong for this box** — no CUDA 13, no sm_121. Install `torch 2.9.1+cu130` from `download.pytorch.org/whl/cu130`. The "sm_121 not officially supported" warning is harmless (sm_120 kernels are binary-compatible).
2. **flash-attn has no official aarch64 wheel.** Community prebuild exists (`flash_attn-2.8.3+cu130torch2.9-cp310-linux_aarch64.whl`). *Contradicting advice worth knowing:* the `natolambert/dgx-spark-setup` notes argue flash-attn is not worth building on Blackwell — slower than SDPA. **Try SDPA first.**
3. **`pytorch3d` has no aarch64 wheel** — compile with `--no-build-isolation` from git, 10–20 min.
4. **`decord` has no aarch64 wheel** and `transformers` hard-checks for it → ship a mock stub. Same for `torchcodec`; use the `torchvision_av` backend.

Working config from the issue: `--batch-size 32 --max-steps 50000 --dataloader-num-workers 14 --video-backend torchvision_av`. **Batch 32 on one Spark is larger than an A100-40GB comfortably does for a 3B VLA** — the 121 GB unified pool is a genuine advantage. Throughput was not reported, so wall-clock is unknown.

**⚠️ The unified-memory trap, and it is serious:** on GB10 the memory is shared CPU+GPU, so "GPU OOM" is *system* OOM. Without swap disabled the box enters a swap death spiral and becomes unresponsive rather than failing cleanly. Reference: Qwen3-0.6B SFT at batch 8 used ~47 GB, at batch 16 ~81 GB — **memory scales superlinearly**. Also catalogued for GB10: hard power-offs traced to an EC cut (fixed by capping clocks at 2200 MHz), suspected throttling near 1400 MHz from a USB-PD fault, and a fixed 8192-token kernel guard that silently falls back to CPU.

**Universal rule for these boxes:** any wheel built against CUDA 12.x dies with `ImportError: libcudart.so.12`. Everything must be cu130. vLLM works via `wheels.vllm.ai/nightly/cu130`.

**openpi on GB10: no reports found anywhere.** He would be first. The JAX + CUDA 13 + aarch64 stack is the risk.

### 8.4 Isaac Sim/Lab on GB10 — yes, but read this first

NVIDIA publishes a DGX Spark playbook and Arm publishes a native aarch64 build path (GCC 11, CUDA ≥13, ~50 GB disk, `./build.sh`, 10–15 min on Grace, plus an `LD_PRELOAD=libgomp.so.1` workaround). **But PhysX GPU does not work on GB10** — IsaacLab issue #4813 documents that sm_121 aarch64 has no working PhysX GPU path. The workaround is the `feature/newton` branch, which does run GPU physics at ~0.5 ms/step at the cost of **1+ hour of NVCC JIT compilation on first run** (cached after). No NVIDIA staff response on that issue. Isaac Lab's own docs additionally list **SkillGen (cuRobo), OpenXR teleop, livestreaming, Hub Workstation Cache, Cosmos Transfer1 and JAX training** as unsupported/unvalidated on DGX Spark.

**Newton 1.0** is the safer physics bet: Apache-2.0, Linux Foundation, NVIDIA + Google DeepMind + Disney Research, released at GTC 2026, and its install docs **name DGX Spark directly**. It uses MuJoCo Warp as its primary backend and supersedes `warp.sim`.

### 8.5 Benchmarks runnable with no robot

| Benchmark | Robot? | On his hardware |
|---|---|---|
| **PAI-Bench** (CVPR 2026 Oral) | No | **Best fit.** 2,808 real-world cases, three tracks, public HF leaderboard, pure video-model eval, zero hardware. Cosmos 3 currently tops it — a visible target |
| **LIBERO** | No | **Best fit.** The de-facto VLA comparison point; GR00T N1.7-LIBERO, SmolVLA, UnifoLM and OpenVLA-OFT checkpoints all exist to compare against. *But see §7.3 — 97% of features on LIBERO are memorised* |
| **Physics-IQ** | No | Yes — but see §7.7, the metric is unstable |
| RoboLab | No | Heavy; Isaac/Omniverse-based, inherits every GB10 caveat |
| SimplerEnv | No | **3070 Ti only** — SAPIEN x86 + CUDA <13 |
| **RoboArena** | **YES** | **No.** Requires a physical DROID rig: Franka Panda + Robotiq 2F-85 + ZED cameras |

### 8.6 If he ever changed his mind about a robot (one paragraph)

The **SO-101** is the answer and it is cheap: **$199–269** for the kit; Seeed sells the motor kit at **$220** plus **$35** for printed parts — and he has a K2 Plus, so he prints them. Fully assembled stays under $500. It is LeRobot's flagship arm, and NVIDIA's own GR00T N1.5/N1.6 → SO-101 fine-tuning guides are written against it. **LeKiwi** is the same arm on a wheeled base. **Reachy Mini** is $299–449 and was demoed at CES 2026 driven by a DGX Spark. One caveat: teleop recording needs a *leader* arm too, so a real imitation-learning setup is two arms — call it **$400–550 all in**.
---

## 9. WHAT THIS MEANS FOR IDDO

You have: **ERAN** (from-scratch Hebrew-syllable learning organism, 4× DGX Spark GB10), the **optical loop** (OLED + polarisation as both input and output, measured 7.1 bits, 6 Hz round trip, 64-cell vector r²=0.62, MTF 12–16 cycles), and **biological-neuron models** (the Beit Din neuron — output is the MEDIAN of 3 seats plus a dissent channel). **No robot. No robot budget.**

Physical AI is a robot field. Most of it does not reach you. But the parts that do reach you are unusually good, because the robotics people spent 2025–26 solving a problem you also have: **how do you learn a continuous motor skill from data that has no action labels?**

That is ERAN's problem exactly. A mouth is an effector. Babble is motor babble.

### 9.1 TRANSFERS — and these are real

**① Latent action pretraining. This is the one. Do this one.**
LAPA (arXiv 2410.11758) and AgiBot's ViLLA both do the same trick: train a VQ-VAE to quantise **the difference between consecutive frames** into a small vocabulary of discrete *latent actions*; pretrain the big model to predict latent actions from unlabeled video; then fine-tune a **small** head that maps latent → real actuator commands. Reported **>30× pretraining efficiency**, and it beat a SOTA model trained with ground-truth actions.

Map it onto ERAN with no changes to the structure:
- consecutive video frames → consecutive **audio frames** (or spectrogram frames)
- latent actions → discrete latent **articulatory gestures**
- unlabeled internet video → your **7.7 GB of Café Claude recordings** (excluding the 06-25 / 07-01 heldout)
- the small fine-tune head → maps latent gesture → your synth / `mouth.py` parameters

You get a syllable-scale action vocabulary **discovered from Hebrew audio, with no labels and no phonetician**. That is the same shape as your 22-syllable inventory, except learned rather than declared. It runs on one Spark. It is a weekend, not a quarter.

**② Emit chunks, not frames. And make the chunk longer, not the denoiser deeper.**
Every frontier policy emits an **action chunk** — H future timesteps at once — because single-step policies jitter. GR00T went from horizon 16 to **horizon 40** between N1.6 and N1.7. If `mouth.py` emits one frame at a time, it will jitter for the same reason a robot arm does.

And VLA-Perf (arXiv 2602.18397) gives you the tuning rule for free `[MEASURED]`: **the action expert is memory-bound** (54 FLOPs/byte) while the backbone is compute-bound (543). Therefore *more action tokens are nearly free; more denoise steps are not* — going 10→50 steps costs 5× in the action head and 2.15× end-to-end. **Longer chunks: cheap. Deeper denoising: expensive.** Spend your budget on horizon.

**③ Relative action space, shared between human and ERAN.**
GR00T N1.6→N1.7's biggest single change was moving to a **relative end-effector action space shared across robot and human embodiments**. That is what let them train on human video at all. NVIDIA states relative actions produce smoother and more accurate motion than absolute targets.

For ERAN: predict **deltas** in articulatory/formant space, not absolute targets. That does two things — it smooths babble, and it puts *your* voice and *ERAN's* synth in the same coordinate system, which is the precondition for ERAN learning from recordings of humans at all. Without a shared relative space, human audio is not training data for him; it is just noise with the right statistics.

**④ The EgoScale method — not the law.**
Ignore the scaling law (§4.2, it is broken). Steal the pipeline. EgoScale's actual contribution is: *take cheap unlabeled human data, manufacture action labels with off-the-shelf estimators, then **retarget into your embodiment's coordinate space by constrained optimisation***. They used SLAM + hand-pose estimation + CasADi/IPOPT into a 22-DoF hand, enforcing joint limits and kinematics.

ERAN's analogue: forced aligner / formant tracker / articulatory-inversion model on Hebrew speech → constrained retargeting into ERAN's synth parameter space under his own limits. Same three stages, different physics.

**Blunt caveat**: their curve *starts* at 1,000 hours and 1,000 hours gave only 0.30 task completion. You do not have 1,000 hours of clean Hebrew. Expect to live at the bottom of that curve. The method is sound; the payoff at your data scale is unknown and probably modest.

**⑤ Don't decode. Predict in the representation.**
V-JEPA 2-AC is the cleanest result in the brief: **plans in 16 seconds where pixel-generating world models take 4 minutes**, and beats them on manipulation **60–80% vs 0–20%**, after post-training on only **62 hours** of robot data `[MEASURED]`.

For ERAN and for the optical loop, same lesson: **if ERAN needs a world model of sound, it should predict the next embedding, not the next waveform.** Cheaper, and on the only head-to-head evidence available, better. Reconstruction is a tax you pay for interpretability, not for capability.

**⑥ RECAP — the cheapest possible way to let ERAN learn from his own attempts.**
π*0.6's RECAP converts RL into supervised learning, which is why it works at home:
1. Train a value head predicting **steps-to-success** from observation+instruction, supervised on binary episode outcomes.
2. Advantage = outcome − V(state), **binarised** so ~30% of actions get labelled "positive".
3. Train the policy **conditioned on that label**; at inference, always condition on "positive".
4. **Human corrections are forced to "positive"** regardless of computed advantage.

Step 4 is you. When you correct ERAN's pronunciation, that correction enters the positive-advantage distribution and teaches recovery. No RL infrastructure, no reward shaping, no policy gradients. This is the single most implementable "learns from experience" recipe published in 2026.

**⑦ A cheap detector for "is it learning or memorising?" — you specifically need this.**
Your measured scar: nothing unsupervised beats the 79.55% no-learning control, and the depth/width winner turned out to be **reading TIME**. arXiv 2603.19183 built exactly the tool for that class of self-deception — an SAE over residual activations plus **four cheap statistics** (episode coverage, mean onset count, mean activation magnitude, relative run length) that classify each feature as *general* vs *memorised* **without running any rollouts**.

They found **97.37% memorised features on LIBERO, 89.19% on DROID** — and the whole difference was dataset diversity. Run this on ERAN's activations. It is a diagnostic, it is cheap, it needs no robot, and it is designed to catch precisely the failure you already got burned by once.

**⑧ The Beit Din neuron is defensible — the median part.**
Robust aggregation via **median statistics and Talwar's m-estimator** is established practice in dendritic neuron models, specifically to stop outliers dominating. And DendSN (arXiv 2412.06355) shows that **nonlinear dendritic aggregation gives measurably higher expressivity than point neurons** in deep SNNs. So "output = median of 3 seats" is a known-good robust estimator with a literature, not a metaphor you have to defend from scratch. Frame it as *nonlinear dendritic aggregation* when you write it up and it lands in an existing conversation.

Be honest about the other half: **the dissent channel has no analogue anywhere I found.** That part is yours, unvalidated, and nobody in Physical AI is doing anything like it. That is not a reason to drop it — it is a reason to measure it against a plain median before claiming it does something.

**⑨ One real equation for the optical loop.**
Ozcan's group at UCLA (Li et al., *Light: Science & Applications* **11**:153, 2022) established that a **single** free-space diffractive platform can implement a *group* of arbitrarily-chosen complex-valued linear transformations in parallel through **polarisation-encoded channels**, with negligible error, provided the number of trainable diffractive features/neurons N approaches

```
N  ≥  Np · Ni · No
```

Ni = pixels in the input field of view, No = pixels in the output field, **Np = number of distinct linear transforms assigned to different input/output polarisation combinations**. Equivalently: two orthogonal polarisation states multiply the platform's information capacity by exactly Np.

That is a sizing rule for your loop. It tells you how many optical degrees of freedom you must physically have to get Np parallel channels out of one pass — and it is the constraint your 7.1 bits / 64-cell vector should be measured against. Your Malus cos² "free multiply" intuition is correct; this is the price of admission for doing several multiplies at once instead of one.
<https://www.nature.com/articles/s41377-022-00849-x> · preprint: <https://arxiv.org/pdf/2203.13482>

### 9.2 DOES NOT TRANSFER — no hedging

**✗ Running GR00T on LIBERO would teach you almost nothing.** You *can* — it is an officially supported platform on DGX Spark, N1.6-3B is 6.15 GB, batch 32 fine-tuning fits on one box. And it would be a waste of a week. §7.3 just established that **97.37% of SAE features on LIBERO are memorised training sequences**. LIBERO measures how well a model memorises LIBERO. With no robot you cannot escape that. Download GR00T to *read its action head*, not to score it.

**✗ The scaling law. Do not build a plan on it.** The published equation `L = 0.024 − 0.003·ln(D)` produces a **negative MSE for three of the five points it was fitted to**. R²=0.9983 on 5 points with 2 free parameters is not evidence. And the whole effect is measured from 1k to 20k hours of data you do not have. The *pipeline* transfers (§9.1④); the *law* does not.

**✗ Cosmos 3 and Genie 3 as tools.** Cosmos3-Super is 64B bf16 ≈ 128 GB — **it does not fit one Spark's 121 GB**. Cosmos3-Nano (16B) probably fits but is **never validated on GB10**, and Cosmos Transfer1 is on Isaac Lab's explicit unsupported-on-Spark list. Genie 3 has **no weights at all** — US research preview only. And fundamentally these are *video* world models. ERAN is not a video system. You would be spending 4 GPUs generating pictures of warehouses.

**✗ Everything requiring teleoperation.** π*0.6, Helix, Gemini Robotics 2, AgiBot GO-1 — all of them rest on hundreds to millions of teleoperated demonstrations collected by paid human operators on real hardware. No leader arm, no operators, no budget, no path. Read them for method; ignore their numbers.

**✗ Neuromorphic hardware as a build target.** Read §6 in full before ever spending money here. Short form:
- **Loihi 3 does not exist** — every spec circulating for it is AI-generated content-farm fabrication. If a plan of yours depends on it, the plan depends on a hallucination.
- **Innatera's "500× lower energy" has no baseline, no methodology and no third-party measurement**, and Innatera does not publish Pulsar's neuron or synapse count. Pulsar is real and good, and it is aimed at smart home and wearables — it has **zero** robotics deployments.
- **Intel Loihi 2 is not a product.** Access needs INRC membership plus an executed licence and confidentiality agreement; most members get shared SSH to a cloud vLab, not silicon. The 2026 flagship robotics paper — *with Intel co-authors and vLab access* — still could not close a chip-to-robot loop and ran its robot results in software simulation. That is the ceiling for an outsider.
- **The only neuromorphic silicon you can actually order is BrainChip AKD1000** ($289 PCIe / $249 M.2). Blunt: on-chip learning is **final layer only, binary weights** — it is not a substrate for growing a learning organism — and **a DGX Spark has no PCIe slot for it**, so it needs an x86 host or the $995 Raspberry Pi bundle.
- And the direction of the peer-reviewed evidence is *against* the premise: pruned SNNs use **1.61× more** energy than pruned ANNs once memory access is counted (ACM TACO 2026), and the best real embodied win is **~3× at system level**, from 2024, on last-generation silicon.

**What to take instead:** the *architectural* idea from arXiv:2602.13747 — a spiking **neural state machine** that orchestrates heterogeneous components on one substrate, replacing off-chip control logic. That is software, it reproduces in PyTorch or LAVA on your Sparks at zero hardware cost, and it is very close in spirit to what your Beit Din neuron and ALMIDO worm are already doing. Their own conclusion is that the blocker is not silicon — it is that **~104 hand-tuned parameters must be replaced by self-regulation**. That is a homeostasis problem, which is your kind of problem.

**✗ The SAPIEN ecosystem, permanently.** ManiSkill3, SimplerEnv — **no Linux aarch64 wheels exist**, and SimplerEnv additionally requires CUDA <13 while GB10 requires ≥13. That is a contradiction, not a packaging problem. Build on MuJoCo / Newton / LIBERO instead. Newton 1.0's install docs name DGX Spark explicitly; that is your physics engine if you ever want one.

**✗ The optical loop has no Physical AI analogue at all.** Nothing in the 2026 robot-learning literature touches free-space optical computing. The photonic-neuromorphic community exists and is active, but it is a different field with different benchmarks, and your 7.1 bits / 6 Hz is not comparable to anything in this brief. Do not expect this crawl to have found you a peer. It did find you a sizing equation (§9.1⑨) and that is all.

### 9.3 If you only do one thing

**Latent action pretraining on Café Claude audio (§9.1①), with the memorised-vs-general SAE diagnostic (§9.1⑦) as the acceptance check.**

It is one build, it uses data you already have, it runs on one Spark, it needs no robot, it produces a learned syllable-scale action vocabulary instead of a declared one — and it comes with a built-in test for whether ERAN learned anything or just memorised the tape. Given the 79.55% no-learning-control scar, shipping the diagnostic *with* the experiment is the whole point.

The rest of this brief is context. That is the item.
---

## 10. METHOD, AND WHAT I GOT WRONG OR COULD NOT VERIFY

**Method.** ~60 web searches and ~35 direct fetches, run 2026-08-23. Primary sources preferred: arXiv abstracts and HTML full text, HuggingFace model cards, GitHub READMEs, vendor newsrooms and standards documents. Press was used only to locate primaries or where no primary exists. Three parallel crawls covered data economics, neuromorphic hardware, and the open-source stack.

**Negative findings, collected in one place** — these are the highest-value output of this crawl:

1. **EgoScale's published scaling equation is arithmetically impossible.** `L = 0.024 − 0.003·ln(D)` yields a negative MSE for D > 2,981 h, i.e. for three of the five points it was fitted to. Almost certainly a log₁₀/ln typo. R² = 0.9983 on 5 points with 2 parameters is not evidence of a law. (§4.2)
2. **"Robots fail 88% of real household tasks" is misframed.** Both halves of the famous comparison — RLBench 89.4% and BEHAVIOR-1K 12.4% — are **simulator** results. It is a sim-to-sim gap, not a sim-to-real one. (§7.1)
3. **"Intel Loihi 3" is fabricated.** Every circulating spec traces to AI-generated content farms, one of which contradicts itself and another of which predates the alleged announcement. Loihi 2 remains Intel's only shipping neuromorphic processor. (§6.1)
4. **Innatera's "100× lower latency, 500× lower energy"** has no published benchmark, no named baseline, no methodology and no third-party measurement. (§6.2)
5. **No official pJ/SOP exists for Loihi 2.** The widely-quoted ~10–12 pJ figure has no traceable primary source. (§6.6)
6. **The 2026 flagship neuromorphic-robotics paper's chip never controlled the robot.** Its headline 68%/70% success figures came from software SNN simulation on conventional hardware. The authors say so plainly. (§6.3)
7. **IBM NorthPole is not neuromorphic** — no spikes, no neuromorphic dynamics. Widely miscategorised in market reports. (§6.7)
8. **LIBERO scores are close to meaningless as capability measures** — 97.37% of learned features on LIBERO are memorised training sequences. (§7.3)
9. **Physics-IQ rankings are unstable** — Kendall's τ = 0.46 under artifact correction, and prompt rewording alone moved Sora 2 from 12.7 to 25.3. NVIDIA's "leads Physics-IQ" claim ships with no number. (§7.7)
10. **The 2026 BEHAVIOR Challenge had not concluded** at time of writing (winners 2026-11-04). Anything labelled "2026 BEHAVIOR results" is the 2025 run.

**Could not verify — open items, flagged rather than guessed:**
- Per-factor effect sizes in arXiv 2603.22876 (which of domain randomisation / photorealism / physics realism / RL updates matters most for sim-to-real). Abstract only; the full paper has them.
- Cosmos 3's actual numeric scores on Physics-IQ, PAI-Bench, RoboLab, RoboArena. NVIDIA claims leadership on all of them and publishes numbers on none, in either the press release or the developer blog.
- GR00T N1.7 vs N1.6 vs N1.5 head-to-head benchmark table. Not published in the HF blog or the GitHub README.
- π*0.6's parameter count and training-data hours from a primary source. The Gemma-3-4B + 860M action expert figures are from a secondary analysis, not the paper.
- Whether openpi runs at all on aarch64 / GB10. No reports exist anywhere; he would be first.
- Whether snnTorch / Norse / SpikingJelly / GeNN build cleanly on GB10 aarch64.
- The per-source breakdown of EgoScale's 20,854 h. **Resolved otherwise:** the corpus itself is confirmed NVIDIA-internal and unreleased (§5.3) — only the 829 h EgoDex slice is obtainable, and the paper names no other component.
- Whether Lightwheel's claimed 100,000-hour "EgoSuite-Open100K" open release exists. No matching HuggingFace dataset was found; their own product page advertises the hours as a B2B service. Treat as unsupported until a repo appears.

**A standing caution.** Two of the most-repeated numbers in the neuromorphic literature turned out to be marketing and fabrication respectively, and the single most-cited robotics statistic of 2026 turned out to describe a simulator. In this field, **check whether the benchmark is a simulator, and check whether the number has a baseline.** Those two questions caught every error in this brief.
