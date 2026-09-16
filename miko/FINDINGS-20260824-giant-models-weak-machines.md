> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# מיקו · MIKO ruling — giant models on weak machines, and federation across clouds

**Question (Iddo, 2026-08-24 05:26):** open-source ways to run giant models on simple computers
(an old 8 GB Pavilion laptop), or to federate across clouds.
**Seven lenses searched. Two judges (Pavilion, ARM64) ruled. This is the ruling seat.**
**לזכרה של עלמה ז״ל.**

---

## 1. מסקנה · THE RULING

**עברית —** התשובה הכי טובה כבר אצלך ביד, וקוראים לה **colibri**. שום דבר שנמצא בחיפוש הזה לא
מריץ מודל ענק על חומרה פשוטה יותר טוב ממנה, ושום דבר לא הכה את המספרים שכבר מדדת בעצמך על
הצי (10 טוקן/שנייה בזרם יחיד, 28 בארבעה). על **הלפטופ הישן — התשובה היא לא**: אין שום פרויקט
בעולם, נכון להיום, שמריץ מודל ענק על 8 ג'יגה בלי כרטיס מסך במהירות שאפשר לחיות איתה. התקרה
האמיתית שלו היא מודל 3–4B ב־Q4 (15–40 טוקן/שנייה) — או, ההצעה החזקה יותר, **מודל מזוקק**
(DeepSeek-R1-Distill / Qwen3-distill): לא לדחוס ענק, אלא להריץ ילד שלמד מענק. על **פדרציה בין
עננים**: הרכבה של שכבות חינם (Kaggle+Colab+ZeroGPU+Oracle) **אינה קיימת כפרויקט ואינה מסתדרת
במספרים** — הדרך האמיתית והיחידה שנמצאה חיה היא Hivemind/PRIME-RL, והיא דורשת GPU אמיתיים
בתשלום. **כלל ה־4-bit שלך עומד** — הוא רק התחדד: זה לא כלל של מספר ביטים אלא של **מצב כשל שקט**.
מה לעשות עכשיו: לא לגעת ב־colibri, לא לחפש מודל גדול יותר ללפטופ, ולהריץ ניסוי אחד זול (§6).

**English —** The best answer to this question is already on your disk and it is called
**colibri**. Nothing this search found runs a giant model on modest hardware better than it,
and nothing found beats the fleet numbers you already measured yourself (10 tok/s single
stream, 28 tok/s at 4-way). For the **Pavilion the honest answer is no**: as of today no
open-source project runs a giant model on 8 GB with no GPU at a speed a human would tolerate.
Its real ceiling is a 3–4B model at Q4 (15–40 tok/s) — or, the stronger move, a **distilled
model** (DeepSeek-R1-Distill / Qwen3-distill family): don't compress a giant, run a child that
learned from one. For **federation across clouds**: stitching free tiers
(Kaggle + Colab + ZeroGPU + Oracle) **does not exist as a project and the arithmetic does not
close** — the only live, real path found is Hivemind / PRIME-RL, and it assumes real paid or
donated GPUs. **Your "never below 4-bit" rule holds**, sharpened: it is not a bit-count rule,
it is a *silent-failure-mode* rule. So: leave colibri alone, stop hunting a bigger model for
the laptop, and run the one cheap experiment in §6.

---

## 2. THE THREE TABLES

**How a row was earned.** A project gets a row only if it **survived the judge whose scope that
table covers** and was **not killed by the other judge in that same scope**. Colibri is a
worked example: killed for the Pavilion (its own RAM floor is ~25 GB), survived for the fleet —
so it appears in table (a) and not in (b). Rows marked **†** were surfaced late by the
gap-lens and were **never put through either hardware judge** — treat them as leads, not
verdicts.

Evidence grades: **MEASURED-INDEPENDENT** (someone other than the authors published a number) ·
**CLAIMED-BY-AUTHOR** (the authors' own number, including peer-reviewed papers) ·
**INFERRED** (reasoning, no number).

### (a) GIANT MODEL ON HIS OWN 4 BOXES — what beats 10 / 28 tok/s?

**Short answer: nothing verified does.** One vendor number is higher, on a different model.

| project | what it actually does | number found | grade | verdict vs his 10/28 |
|---|---|---|---|---|
| **vLLM in `nvcr.io/nvidia/vllm` (NGC)** | the only vLLM that builds for sm_121 aarch64 | his own 10 tok/s single / 28 at 4-way | MEASURED-INDEPENDENT | **this IS the baseline.** vLLM issues #36821 + #31128 (no sm_121 on aarch64) are **still open** — the pip gap is real and unfixed, not user error. Needs `--attention-backend=TRITON_ATTN`; FlashInfer unusable on sm_121 |
| **NVIDIA 3-Spark switchless ring** (`sparkrun`, `spark-vllm-docker`) | 3 boxes in a full triangle, **no switch** — GB10's ConnectX-7 is **dual-port** | Qwen3.5-397B-A17B **17.86 ±0.16 tok/s decode** (NVIDIA's own guide) | CLAIMED-BY-AUTHOR (vendor); topology corroborated by 3 independent repos + NVIDIA forum | **the only candidate that beats 10 tok/s** — but a different model, vendor-published. **Corrects CLAUDE.md:** "3+ nodes need a switch" is false for *cabling*, true for *TP scaling* |
| **llama.cpp `--rpc`** | pipeline layer split | his own 2.93 tok/s | MEASURED-INDEPENDENT | **worse, permanently.** Independently confirmed 2026: RPC "doesn't support tensor parallelism and never will"; adding nodes makes generation ~2× *slower* — it buys capacity only |
| **colibri / coli** | NVMe expert streaming, 744B on one box | 0.4–2.06 tok/s across four independent rigs | MEASURED-INDEPENDENT | **far slower, and that is fine** — it is a *capacity* tool, not a speed tool. See §3 |
| **distributed-llama** | **true tensor parallel** over plain Ethernet, ARM-optimized, MIT | 1.77 tok/s on 1× Pi5 8 GB → 3.01 on 4× Pi5; Qwen3-30B-A3B-Q40 15.14 tok/s on 4× Pi5 | MEASURED-INDEPENDENT (ARM CPU); **INFERRED** for GB10 — nobody has reported running it on a DGX Spark | structurally the right idea (speed, not just memory) but **CPU-only, no CUDA path** — on a DGX it would use Grace's ARM cores and ignore the Blackwell GPU. Cluster size skews power-of-2 |
| **prima.cpp** | pipelined-ring for *heterogeneous weak* devices; a Halda solver assigns layers by measured device capability | 70B at 674 ms/token (~1.5 tok/s); 32B + spec-decode 26 tok/s; claims 5–17× lower TPOT vs llama.cpp/exo/dllama | CLAIMED-BY-AUTHOR (**ICLR 2026 accepted** — real review, not a README) | **the only project whose design target is his exact fleet shape** (4 strong boxes + 1 weak laptop). **Zero independent reproduction found. 82 GitHub stars** after a year — that gap is itself data. CPU/pipeline only |
| **GGUF dynamic quants** (Unsloth UD; `ik_llama.cpp` IQ_K/IQ_KS merged to mainline Mar 2026) | keeps important layers at 8-bit, drops the rest lower | Aider Pass-2 ladder, DeepSeek-V3.1: 5-bit 70.7% · 4-bit 69.7% · 3-bit 65.6–68.4% · 2-bit 64.3–65.8% · **1-bit 50.7–55.7%** | MEASURED-INDEPENDENT (third-party Aider harness) | same binary he already runs. **This is where the quant frontier actually moved** — mixed precision, not flat sub-2-bit |
| **† `--n-cpu-moe N` (mainline llama.cpp) + `ik_llama.cpp` fused MoE kernels** | keeps attention/KV/router on GPU, parks the routed-expert FFNs of the first N layers in CPU RAM | Qwen3.6-35B-A3B ~50 tok/s hybrid on one RTX 3060 12 GB + 32 GB DDR5 | MEASURED-INDEPENDENT (community), **INFERRED** for GB10 | **a flag in software he already has.** Big untested caveat: on GB10 unified memory "CPU RAM" and "GPU RAM" are one pool — the flag may be a no-op there. Cheap to find out |
| **† Mooncake** (kvcache-ai) | pools a **KV cache** across a fleet's DRAM+SSD; the scheduler places by cache cost, not weight placement | FAST 2025 **Best Paper**; joined the PyTorch Ecosystem Feb 2026; vLLM-Omni connectors Feb 2026 | MEASURED-INDEPENDENT | **an axis nobody else in this search named** — federate the *cache*, not the weights. Built for high request volume, not one interactive user; the benefit size for his usage is untested |
| **† CPU-only many-core precedent** | DeepSeek-R1 671B, **zero GPU**, llama.cpp on dual-EPYC | 1.9 tok/s (FP16, 256 threads) · 2–4 (1.58-bit, 192 GB) · 5–8 (IQ4_XS, 384 GB) · 6.2 (Q8, single EPYC 9654) | MEASURED-INDEPENDENT — four unrelated sources converge | proves a giant MoE runs on RAM+cores alone. Note: the **1.58-bit run was slower than several 4-bit runs** — going lower-bit did not even buy speed |

### (b) BIG MODEL ON THE 8 GB PAVILION — what genuinely works

| project | what it actually does | real tokens/sec | grade | verdict |
|---|---|---|---|---|
| **3–4B dense at Q4_K_M, plain llama.cpp** | just fits in RAM | **15–40 tok/s** CPU-only; a 7B (Mistral-Q4) drops to **low single digits** | MEASURED-INDEPENDENT (several 2026 "best LLM for 8 GB" benchmarks converge) | **this is the real ceiling.** The only category that clears the usable bar with no GPU |
| **† Distilled models** (DeepSeek-R1-Distill-Qwen 1.5B/7B/14B/32B; the Qwen3-distill line) | a small model trained on a giant model's outputs | runs at the row above's speed | MEASURED-INDEPENDENT (published HF benchmarks) | **the honest answer to what he actually asked.** Don't compress a giant — run its child. A 2026 refinement (T3S) reports a distilled Qwen3-8B beating DeepSeek-R1 on AIME24/25 (80.6/74.0 vs 79.8/70.0) — but that is CLAIMED-BY-AUTHOR on **two narrow math benchmarks**, not coding breadth |
| **llamafile** | one portable binary, hand-tuned `tinyBLAS` CPU kernels spanning ~20 years of CPUs | **no independent tok/s figure found** — do not repeat a multiplier | INFERRED | best way to get the most out of what already fits. **Raises no ceiling.** Honestly scoped, unlike AirLLM |
| **distributed-llama** (as a cluster *member*) | the Pavilion contributes ~4–6 GB to a pooled cluster | 1.77 → 3.01 tok/s across 4× 8 GB ARM nodes | MEASURED-INDEPENDENT | the Pavilion alone still holds nothing useful; it only helps as one ring member, and its pipeline slot makes it **the node everyone else waits on** |
| **prima.cpp** | its own test devices are **4.1 GB and 1.9 GB RAM, no GPU** | 674 ms/token for 70B across 4 consumer devices | CLAIMED-BY-AUTHOR (ICLR 2026) | the only project that *designed for* a machine this weak. Hard dependency on a source-built HiGHS solver. Nobody outside the authors has published a number |
| **† T-MAC** (Microsoft, EuroSys 2025) | CPU **lookup-table** matmul for low-bit weights instead of dequantize-then-multiply; ARM + x86 | 20 tok/s 1-core / 48 tok/s 4-core for a 3B BitNet model on a Surface Laptop 7 (4–5× over llama.cpp); 11 tok/s on a Pi 5 | CLAIMED-BY-AUTHOR | the only **CPU-kernel-level** (not memory-hierarchy) answer found anywhere. No independent reproduction. Its flagship numbers are for BitNet-native ternary models — capped at ~2–4B (see graveyard) |
| **† MNN** (Alibaba, arXiv:2506.10443) | multi-backend edge engine (Vulkan / QNN / MUSA / CPU); 3.5.0 added Vulkan LLM inference + TQ3/TQ4 KV quant | none published outside Alibaba | CLAIMED-BY-AUTHOR | the Chinese-ecosystem blind spot no lens had searched. Demonstrated on *small* edge models, not giants |

### (c) FEDERATION ACROSS CLOUDS — free/cheap and legitimate

| project | what it actually does | evidence | grade | verdict |
|---|---|---|---|---|
| **Hivemind** (learning-at-home) | the actual library under DiLoCo and Petals: DHT, no master, fault-tolerant backprop, decentralized averaging | maintained, Jan 2026 release | MEASURED-INDEPENDENT (it demonstrably underpins shipped systems) | **the honest starting block** if he ever hand-rolls a 4-DGX + rented-node federation. A library that needs real engineering, not a product |
| **DiLoCo** (method) / **PRIME-RL** (implementation) | ~500× less communication via local SGD; PRIME-RL adds TOPLOC (verify untrusted workers) + SHARDCAST (broadcast weights) | a real run: 4 nodes × 8 H100 across Canada/Finland/USA at **90–95% utilization**; INTELLECT-2 (32B) then INTELLECT-3 (106B MoE) trained over a permissionless GPU market | MEASURED-INDEPENDENT | **shipped, not vaporware — decentralized training across clouds now works at 100B+ scale.** Caveat: that is **RL post-training on an existing base**, not pretraining, and it assumes 32 real H100s, not notebook scraps. ⚠️ **OpenDiLoCo is dead** (its maintainers' own words) — the successor is prime-rl |
| **SWARM Parallelism** | pipeline training over unreliable, poorly-connected, heterogeneous, preemptible devices at <200 Mb/s | the closest paper to "train on whatever cloud scraps exist" | CLAIMED-BY-AUTHOR | a research reference implementation; no confirmed 2026 maintenance cadence. Read it, don't deploy it |
| **Parallax** (GradientHQ) | pipeline sharding over a P2P layer ("Lattica"), Apache-2.0, arXiv 2509.26182 | 1.4k ★ | INFERRED | ARM64 support, WAN/NAT behaviour, and RAM floor are **all unconfirmed**. "Sovereign AI Operating System" is a slogan, not a measurement. Install-and-test before believing anything |

---

## 3. COLIBRI — he already owned the answer

**What it is.** A dense resident core (~17B params, **9.9 GB at int4**) stays in RAM, while
**21,504 routed experts (~370 GB)** stream from NVMe on demand. MLA attention gives a
**~57× smaller KV cache**. MTP speculative decoding (an int8 draft head) yields
**2.2–2.8 tokens per forward pass at 39–59% acceptance**. That is how a 744B model fits behind
`--vram 28`: at any moment only a handful of experts are live, and the KV cache — normally the
thing that eats a giant model's memory — has been shrunk by two orders of magnitude.

**Why it works on his hardware specifically.** ARM64/aarch64 is **explicitly tested on Grace**,
the exact CPU family in his DGX boxes. His eran4 deployment is not a fluke; it is a supported
configuration. Unified memory is a genuine structural advantage here, not a workaround: there
is no host↔device copy to orchestrate — the whole 121 GB is one addressable pool for the
resident core and the expert cache alike.

**What it costs, honestly.** Independent community benchmarks span 0.05–0.11 tok/s (WSL2, cold
disk) · ~1.00 tok/s (EPYC, 430 GB RAM, 98% cache hit) · 1.06–2.06 tok/s (M5 Max, warm Metal
cache) · 0.40 tok/s (Ryzen AI Max+ 395). **Speed tracks almost entirely with how much of the
370 GB expert set sits in fast RAM.** At `--vram 28` he is near the bottom of that band. On
quality, the project self-reports int4 MMLU/ARC/HellaSwag 0-shot at 62.5% while its own README
admits "protocol confounds remain" — CLAIMED, and not trusted even by its own authors.

**Is it the answer to his whole question? One third of it, completely.**
It is the best single-box giant-model runner found anywhere in this search, and he already runs
it. But its own documentation states: **"No GPU sharding; single expert cannot span multiple
devices."** It will **never** spread across the 4-DGX fabric — so it does not answer the
federation half. And its RAM floor (~25 GB for the resident core alone) means it will **never**
touch the Pavilion.

**Two warnings on colibri specifically:**
1. **Repo identity is unresolved.** One lens cited `uv-genai/colibri`; another cited
   `JustVugg/colibri` + `justvugg.github.io/colibri`. Both cannot be the canonical upstream.
   **Confirm which repo `~/apps/colibri` actually tracks before pulling any update.**
2. **Do not repeat the "11.1+ tok/s on GB10" number.** A search-result *title* on colibri
   issue #161 claims 11.1+ tok/s full-k8 CUDA, but fetching the issue body shows only
   2.39 → 3.33 tok/s from a routing-cache experiment, with no 11.1 anywhere in the visible
   content. **This is MIKO's second founding scar, in the wild** — a headline the body does not
   support. Open the issue yourself before quoting it.

---

## 4. THE MACHLOKET — where the evidence genuinely conflicts

### מחלוקת א׳ — does "never below 4-bit" still hold in 2026?

**דעת המחמירים (the rule holds).**
- Unsloth's own bit-ladder on the **third-party Aider** harness: 4-bit **69.7%** → 1-bit
  **50.7–55.7%**. A real 15–19 point collapse, measured on a benchmark they did not invent.
- An independent 2026 **KL-divergence** benchmark on a 27B model found *every* IQ1 quant worse
  than *both* published IQ2 options — the size saving "buys nothing practical."
- `howtospark.com`'s 2-bit GLM-5.2 recipe across 2 DGX Sparks scores 92% on GSM8K-50, but the
  authors themselves report it **degenerated on 2 of 6 long-prose prompts** where the
  full-precision build degenerated on **0 of 6** — and they warn that passing GSM8K is not
  sufficient validation. **This is Iddo's GLM-4.7 scar, re-discovered independently, one model
  generation later.**
- The CPU-only EPYC data adds a blunt point: **the 1.58-bit run (2–4 tok/s) was slower than
  several 4-bit runs (5–8 tok/s)**. Going lower did not even buy speed.
- Orthogonal but decisive on the general principle: Dong et al. (arXiv:2508.16712) found
  **W8A8-INT8 destroyed 92% of HumanEval pass rate** on a 13B model, while weight-only 4-bit
  lost at most 22%. **Bit count alone does not predict the cliff — the operation being
  quantized does.**

**דעת המקילים (the frontier moved).**
- A 2026 NVIDIA developer-forum post ran **GLM-5.2 UD-IQ1_S on 2× DGX Spark — his exact
  hardware class** — at 8 tok/s with 256K context, scoring 88/100 on a tool-eval bench,
  answering riddles coherently, and producing an 8,000-word physics essay with no logical
  errors. **In thinking mode.**
- Unsloth's own documentation supplies the reconciliation: *"For UD-IQ1_S and other 1-bit
  quantizations, empty responses can occur… always enable thinking/low reasoning mode, as
  non-reasoning modes cause the model to not output anything."*
- Separately, a GLM-5.1-GGUF IQ4_NL "gibberish" bug was **filed and fixed in llama.cpp build
  b8808** — proof that some "low quant is broken" reports are runtime bugs, not information
  loss.

**פסק · The ruling, carrying both sides forward.** The rule **stands, and gets sharper**. It is
not "1-bit is dumb." It is: **1-bit has a documented silent-failure mode — empty completions
while still billing tokens — that fires in non-reasoning mode.** That is an annoyance for a
human chatting interactively and a landmine in an unattended agentic pipeline. His fibonacci
prompt almost certainly hit exactly that trigger. So: **never below 4-bit for unattended or
agentic code work.** If he ever goes sub-2-bit deliberately, **force thinking mode and never run
it unattended.** And note where the frontier *did* move: **dynamic mixed precision** (important
layers at 8-bit, unimportant ones low), already supported in the llama.cpp/GGUF stack he runs.

### מחלוקת ב׳ — did NVIDIA say 3 nodes need a switch?

CLAUDE.md records "NVIDIA says 3+ nodes need a switch." **That is now half wrong.** GB10's
ConnectX-7 is **dual-port**, and NVIDIA publishes an official switchless three-Spark ring guide
(`build.nvidia.com/spark/connect-three-sparks/three-sparks-ring`), corroborated by three
independent community repos and NVIDIA's own forum. **But it changes nothing about tensor
parallelism** — TP still needs power-of-2 node counts / attention-head divisibility, so 3 nodes
stay pipeline-only regardless of cabling. **His conclusion was right; his stated reason was
wrong.** Practical note: he already owns four 200G links, and fabric B duplicates the same two
chain hops. **Re-terminating one fabric-B pair as a direct eran1↔eran3 link would complete the
triangle using cable and ports he already has** — and would buy routing, not TP.

### מחלוקת ג׳ — README versus reality (three cases, same shape)

- **AirLLM**: the README says "70B on 4 GB, it just works." Independently measured community
  speed: **0.07–0.3 tok/s** (24 tokens in 80.9 s). *Both are true at once* — it runs, and it is
  not usable.
- **exo**: its README claims a **3.2× speedup on 4 devices**. Jeff Geerling, an independent
  reviewer, measured **1.5×** running DeepSeek V3.1 671B across 4 M3 Ultra Studios. The vendor
  and independent numbers disagree by more than 2×. Geerling's framing matches Iddo's own rule:
  the cluster's real job is *fitting* the model; the speed bump is a bonus.
- **KTransformers (~16 tok/s) vs colibri (<2 tok/s)**: **not a contest.** The same idea under
  two different hardware assumptions — KTransformers assumes a real 24 GB discrete GPU exists;
  colibri deliberately assumes it does not. Do not compare them as rivals for one slot.

---

## 5. THE GRAVEYARD — killed, and why (this section saves the most time)

**Killed for the Pavilion (no GPU, 8 GB):**
- **AirLLM** — the whole mechanism is streaming layers *through a GPU*. No GPU, no AirLLM. And
  where it does run: 0.07–0.3 tok/s.
- **DeepSpeed ZeRO-Inference** — the same GPU/CPU/NVMe hierarchy trick; its CPU-only tier is
  documented as the slowest one. Datacenter batch throughput, not a laptop answer.
- **KTransformers** — needs a 24 GB discrete GPU for hot experts, and its fast path is **Intel
  AMX** kernels, x86-only silicon. Grace has no AMX either, so it is dead on the DGX fleet too.
- **PowerInfer / PowerInfer-2** — its 13.2 avg / 29.08 peak tok/s were measured on an
  **RTX 4090**.
- **Petals** — its own FAQ states the client needs **~12 GB RAM before hosting a single
  transformer block**. A clean, explicit no for 8 GB. Its 2026 swarm liveness is also
  unverifiable: the "~100 active nodes" and "still thriving" claims trace to promotional copy
  with no sourceable number. **Weakest-sourced item in the whole search.**
- **colibri** — Pavilion scope only: ~25 GB RAM floor for the resident core. **Not killed as a
  project**; see §3.
- **AWQ / GPTQ / HQQ / QuIP# / AQLM / QTIP** — all GPU/PyTorch-calibrated. No ARM-CPU path found
  for any of them. QuIP# and AQLM show **no 2026 activity at all**. Irony worth noting: HQQ's
  own authors recommend starting at `nbits=4` despite supporting lower — the 4-bit floor,
  independently confirmed by a tool that *could* go lower and chooses not to.

**Killed for the fleet:**
- **exo** — three GitHub issues on the live repo, **all still open**: #923 ARM64 unsupported,
  #913 Linux CUDA still a tracking issue, #907 Debian-arm64 unanswered. Its one working CUDA
  fork is verified only on Tesla V100 and M40 (Volta/Maxwell) — architecturally nothing like
  Blackwell sm_121. On his DGX boxes today, exo would run CPU-only and ignore the GPUs entirely.
  **47k stars, and it cannot touch his hardware.**
- **GPUStack / Kalavai** — **wrong category.** They orchestrate *full replicas*: every node must
  independently hold the whole model. Kalavai's low-RAM fallback is llama.cpp RPC underneath,
  inheriting RPC's "capacity, not speed" ceiling.
- **cake** — 3.1k stars; the **largest model ever demonstrated on it is Qwen3-0.6B**. Also a
  non-commercial FAIR license, not open source as its framing implies.
- **Mesh LLM** (iroh/QUIC) — architecturally the most honest federation answer found (true
  NAT-traversing P2P, an 18 MB Rust binary, 40+ models up to 235B). Launched 2026-07-11, with
  **zero tokens/sec published anywhere**. Nothing to judge. Watch it; don't build on it.
- **SharedLLM** — a thin wrapper over llama.cpp RPC. Not a new mechanism.

**Killed on quantization:**
- **Sub-2-bit for unattended/agentic code** — see §4 מחלוקת א׳. Killed, with the dissent
  recorded rather than averaged away.
- **BitNet / bitnet.cpp native ternary** — the only natively-trained ternary model found is
  **2B parameters**. The widely-quoted "100B on a CPU at 5–7 tok/s" is a **different technique**
  (PT-BitNet, *post-training* ternarization). **Nobody has natively trained a ≥30B ternary model
  as of this search.** Treat "1-bit LLMs are here at scale" as false until that changes.

**Killed on federation:**
- **OpenDiLoCo** — its maintainers state plainly that it is **"no longer maintained."** A clean,
  documented death. Successor: prime-rl.
- **Free-tier stitching (Kaggle + Colab + HF ZeroGPU + Cloudflare Workers)** — **no dedicated
  open-source project doing this as real distributed training exists.** What exists is the
  manual pattern: checkpoint to Drive/Kaggle Datasets, the session dies at the time limit,
  resume by hand elsewhere. That is file relay, not federation, and pushing it risks both
  platforms' ToS. Even combined, the numbers don't close: 30 GPU-hr/week in 9-hour chunks,
  3.5 min/day, a halved Oracle ARM tier, and Workers whose terms forbid training outright.
  **Stop looking. It isn't there.**
- **"EAGLE-3 speculative decoding is now available in llama.cpp"** — one blog asserts it; the
  primary GitHub source does not support the claim. Do not plan around it.

**Unjudged, flagged for honesty:** the lens record for **Nous Research / Psyche network** was
truncated before its verdict was written. It is neither endorsed nor killed here. If it matters,
it needs its own look.

---

## 6. THE ONE EXPERIMENT

**The biggest open question in this whole ruling:** *is his fleet permanently pipeline-shaped,
or does real tensor parallelism buy speed on hardware he already owns?* Every downstream
decision hangs on the answer — whether to recable a triangle, whether to spend days on
prima.cpp or distributed-llama, whether adding boxes is ever worth it.

**The test: vLLM `--tensor-parallel-size 2` on eran1↔eran2 over the direct 200G fabric-A link,
against his existing PP×3 baseline.**

Why this and not something else: it uses the NGC container that **already works** on his boxes,
two boxes **already cabled** directly to each other, and **zero new software**. TP=2 is
power-of-2, so it is the one tensor-parallel configuration his fabric can legally run — and he
has never measured it. Every number he owns is pipeline.

**The control, which MIKO's second scar demands:** pick **one** model + quant that fits *both*
TP=2 across two boxes *and* PP=3 across three. Same model, same quant, same prompt set, same
context length, same sampler. TP halves the memory per box, so a model that only fits across
three in pipeline will not fit in two — choose the model to make the comparison honest, or the
result means nothing.

**Pass / fail:**
- **PASS** — TP=2 single-stream decode **> 10 tok/s** on the same model his PP×3 run measured.
  Meaning: real tensor parallelism does buy speed here; two boxes beat three; completing the
  triangle and pursuing TP-shaped tooling becomes worth real effort.
- **FAIL** — TP=2 **≤ 10 tok/s**. Meaning: the fleet is pipeline-shaped for good on this fabric.
  Stop optimizing topology, stop evaluating cluster tools, and put the effort into single-box
  levers instead (colibri, dynamic quants, `--n-cpu-moe`).
- **INVALID** — if the model does not fit identically in both configurations, throw the result
  away. No control, no finding. That is the rule this organ exists to enforce.

**Second-cheapest test, if he wants two:** one flag, one box —
`llama.cpp --n-cpu-moe N` on a GLM/Qwen3-MoE at Q4 on a single DGX Spark. Pass = **> 10 tok/s
single-stream on one box**, which would mean the fabric was never the right lever for MoE models
at all. Honest caveat: on GB10's unified memory "CPU RAM" and "GPU RAM" are one pool, so the
flag may do nothing there. Finding *that* out costs one command.

---

*Judged 2026-08-24 by MIKO's ruling seat. Seven lenses searched; two hardware judges ruled; this
seat did not argue in the search. Where the evidence conflicted it is named on both sides, not
averaged. Every claim above carries its grade — and the most valuable lines in this document are
in §5.*
