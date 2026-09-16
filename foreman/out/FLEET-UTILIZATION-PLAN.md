# FLEET‑UTILIZATION‑PLAN.md  
**Four DGX‑Spark GB10 boxes (121 GB unified memory each)**  

| Box | Hostname | Primary Services (standing load) | Approx. Memory / GPU usage* |
|-----|----------|----------------------------------|-----------------------------|
| 1   | **eran1**| • `qwen3‑coder` (LLM inference)  <br>• STT server (Whisper‑large‑v2)  <br>• API router (NGINX + Envoy) | 30 GB RAM / 1 GPU (qwen3‑coder)  <br>12 GB RAM / 0.5 GPU (STT)  <br>4 GB RAM / 0 GPU (router) |
| 2   | **eran2**| • `glm` (GLM‑130B chat) | 45 GB RAM / 1 GPU |
| 3   | **eran3**| • `nemotron` (Nemotron‑3‑8B) | 20 GB RAM / 0.5 GPU |
| 4   | **eran4**| • `gpt‑oss` (open‑source GPT‑NeoX 20B)  <br>• Training jobs (LoRA/full‑fine‑tune) | 35 GB RAM / 1 GPU (gpt‑oss)  <br>Remaining ≈ 50 GB RAM / 0‑2 GPU for training |

\*Numbers are steady‑state averages observed under typical request rates (≈ 15 req/s per LLM, 8 req/s STT). Peaks can add ~10‑15 % overhead; we keep a **20 % safety margin** on each box for burst traffic.

---

## 1. Inventory of Standing Loads & Their Appetites  

| Service | Memory (GB) | GPU Fraction | CPU cores (approx.) | Notes |
|---------|-------------|--------------|---------------------|-------|
| qwen3‑coder | 30 | 1.0 | 8 | Serves code‑completion API; latency‑sensitive (< 200 ms p95). |
| STT server | 12 | 0.5 | 4 | Real‑time transcription; must stay < 100 ms end‑to‑end. |
| Router | 4 | 0 | 2 | Terminates TLS, does load‑balancing; zero‑tolerance for packet loss. |
| glm | 45 | 1.0 | 12 | Chat‑oriented LLM; can tolerate higher latency (≤ 500 ms). |
| nemotron | 20 | 0.5 | 6 | Multimodal vision‑language model; used for occasional image‑captioning. |
| gpt‑oss | 35 | 1.0 | 10 | General‑purpose LLM; shares box with training workloads. |
| Training (LoRA/full) | ≤ 50 (dynamic) | 0‑2 | 8‑16 | Runs only when box is idle; can be pre‑empted. |

**Key constraint:** The STT server **and** the router on **eran1** must never be starved; they are the live‑mic pipeline. Any extra workload on eran1 must leave **≥ 20 GB RAM** and **≥ 0.5 GPU** free for them at all times.

---

## 2. Day vs. Night Windows – Where to Put Flux / LTX  

| Time window (UTC) | Typical load pattern | Boxes with spare capacity | Suitable workloads |
|-------------------|----------------------|---------------------------|--------------------|
| **00:00‑06:00** (night) | Low inbound API traffic (≈ 30 % of peak) | eran1 (≈ 70 GB free), eran2 (≈ 60 GB free), eran3 (≈ 80 GB free), eran4 (≈ 50 GB free) | **Flux** (image‑gen, ~17 GB) **or** **LTX** (video, ~26 GB) can run **any** box, but we prefer eran3/eran4 because they have no live services. |
| **06:00‑12:00** (morning ramp‑up) | Traffic rising to ~60 % peak | eran1 (still safe if we keep ≤ 10 GB extra), eran2 (≈ 40 GB free), eran3 (≈ 60 GB free), eran4 (≈ 30 GB free) | Flux OK on eran2/eran3/eran4; **avoid LTX** on eran1 (router/STT safety). |
| **12:00‑18:00** (day peak) | Traffic ~80‑90 % peak | eran1 (≤ 5 GB free – **no** extra workload), eran2 (≈ 20 GB free), eran3 (≈ 40 GB free), eran4 (≈ 10 GB free) | Only **light** inference (e.g., small LoRA adapters) on eran2/eran3; **no** Flux/LTX. |
| **18:00‑00:00** (evening) | Traffic declines to ~50 % | eran1 (≈ 30 GB free), eran2 (≈ 40 GB free), eran3 (≈ 60 GB free), eran4 (≈ 40 GB free) | Flux/LTX can resume; prefer eran3/eran4 for video (LTX) because they have more GPU headroom. |

**Rule of thumb:**  
- **Flux (≈ 17 GB)** can be placed on any box **as long as** the box retains **≥ 20 GB RAM** and **≥ 0.5 GPU** for its standing services.  
- **LTX (≈ 26 GB video)** needs **≥ 30 GB RAM** and **≥ 1 GPU** free; therefore it is restricted to **eran2, eran3, eran4** during night/evening windows, and never to eran1.

---

## 3. Protection Rules for STT Server & Router (Live Mic)

1. **Hard reservation** – On **eran1**, reserve **20 GB RAM** and **0.5 GPU** exclusively for the STT‑router pair. The reservation is enforced via cgroups/virtual‑memory limits (`Memory=20G`, `MemorySwap=0`, `cpus=0.5`).  
2. **No pre‑emptive training** – Training jobs on eran1 are **disallowed**; they may only run on eran2‑4.  
3. **Throttle inference spill‑over** – If qwen3‑coder exceeds its 30 GB baseline, it must first **swap to CPU** (using `torch.cuda.empty_cache()` and `model.to('cpu')`) before touching the reserved pool.  
4. **Health‑check gating** – A lightweight side‑car runs every 30 s:  
   - `curl -s http://localhost:8010/health` (router)  
   - `ffmpeg -f lavfi -i anullsrc -t 1 -ar 16000 -ac 1 -f wav - | curl -s -X POST -data-binary @- http://localhost:8011/stt` (STT)  
   If latency > 150 ms (router) or > 200 ms (STT), the orchestrator **pauses** any non‑essential workload on eran1 until latency recovers.  
5. **Network isolation** – The router’s NIC is placed in a dedicated VLAN with QoS guaranteeing ≥ 100 Mbps upstream for the mic stream; other containers share the remaining bandwidth via `tc` shaping.

---

## 4. Concrete Weekly Schedule (UTC)

| Day | Time Slot | Box | Assigned Workload | Notes |
|-----|-----------|-----|-------------------|-------|
| Mon | 00:00‑06:00 | eran1 | **Idle** (reserve for STT/router) | – |
| Mon | 00:00‑06:00 | eran2 | Flux (batch 4) | 17 GB each, GPU = 1 |
| Mon | 00:00‑06:00 | eran3 | LTX (video 2‑clip) | 26 GB, GPU = 1 |
| Mon | 00:00‑06:00 | eran4 | Training LoRA (gpt‑oss) | ≤ 50 GB, GPU = 2 |
| Mon | 06:00‑12:00 | eran1 | qwen3‑coder + STT + router (baseline) | – |
| Mon | 06:00‑12:00 | eran2 | Flux (batch 2) | – |
| Mon | 06:00‑12:00 | eran3 | **Idle** (reserve for possible burst) | – |
| Mon | 06:00‑12:00 | eran4 | gpt‑oss inference (low‑priority) | – |
| Mon | 12:00‑18:00 | All boxes | **Standing loads only** (no extra) | Peak traffic window |
| Mon | 18:00‑00:00 | eran1 | qwen3‑coder + STT + router (baseline) | – |
| Mon | 18:00‑00:00 | eran2 | Flux (batch 3) | – |
| Mon | 18:00‑00:00 | eran3 | LTX (video 1‑clip) | – |
| Mon | 18:00‑00:00 | eran4 | Training full‑fine‑tune (gpt‑oss) | GPU = 2 |
| … | … | … | … | **Repeat same pattern** for Tue‑Sun, swapping Flux/LTX boxes to balance GPU usage (see table below). |

### Weekly Rotation (to even out wear)

| Day | Flux Box | LTX Box |
|-----|----------|---------|
| Mon | eran2 | eran3 |
| Tue | eran3 | eran4 |
| Wed | eran4 | eran2 |
| Thu | eran2 | eran3 |
| Fri | eran3 | eran4 |
| Sat | eran4 | eran2 |
| Sun | eran2 | eran3 |

*Training slots* on eran4 alternate between **LoRA (night)** and **full‑fine‑tune (evening)**; eran2/eran3 run lightweight inference or idle when not hosting Flux/LTX.

---

## 5. Failure Etiquette – What a Job Must Do When Memory Runs Short  

1. **Detect early** – Each container runs a watchdog that polls `/proc/meminfo` and `nvidia-smi` every 5 s. If **free RAM < 5 GB** *or* **GPU memory utilization > 95 %**, the watchdog triggers.  
2. **Graceful step‑down** –  
   - **Inference jobs** (qwen3‑coder, glm, nemotron, gpt‑oss) first attempt to offload a fraction of the batch to CPU (`model.to('cpu')`) and continue with reduced throughput.  
   - If after offload the pressure persists, the job **rejects new requests** (returns HTTP 429) and finishes processing in‑flight requests.  
3. **Training jobs** – Must checkpoint every N steps (default N = 500). On memory pressure they:  
   - Save checkpoint to `/var/checkpoints/<job-id>/`.  
   - Send SIGTERM to the main training process.  
   - The orchestrator (Kubernetes or Slack‑based scheduler) then **requeues** the job for the next available slot.  
4. **Never OOM a sibling** – The watchdog **never** kills another container. If the pressure originates from a *neighbor* (e.g., a noisy training job on eran4 trying to use the GPU that also serves gpt‑oss), the offending job is the one that steps down or checkpoints.  
5. **Alert & log** – On any step‑down event, emit a structured log line:  
   ```json
   {"ts":"2025-09-26T03:14:12Z","box":"eran4","event":"mem_pressure","action":"cpu_offload","free_mem_gb":3.2,"gpu_util_pct":97}
   ```  
   The central monitoring stack (Prometheus + Grafana) raises a **warning** if the same box experiences > 3 such events within 10 min.

---

## 6. Measurement – Metrics to Log Per Box  

| Metric | Source | Sampling | Why it matters |
|--------|--------|----------|----------------|
| `mem_used_bytes` | `/proc/meminfo` | 10 s | Tracks overall RAM pressure; ensures reservation stays intact. |
| `mem_available_bytes` | `/proc/meminfo` | 10 s | Directly used for the 20 GB safety check on eran1. |
| `gpu_mem_used_bytes` | `nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits` | 5 s | Detects GPU memory saturation before OOM. |
| `gpu_utilization_percent` | `nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits` | 5 s | Shows compute headroom for Flux/LTX. |
| `process_cpu_seconds_total` (per container) | cgroup `cpuacct.usage` | 10 s | Helps spot runaway inference loops. |
| `network_rx_bytes` / `network_tx_bytes` | `/proc/net/dev` | 10 s | Verifies router QoS and mic‑stream bandwidth. |
| `stt_latency_ms` (custom) | STT server side‑car (time from audio chunk to transcript) | 1 s | SLA guard – must stay < 200 ms p95. |
| `router_latency_ms` (custom) | Router side‑car (time from SYN to SYN‑ACK) | 1 s | SLA guard – must stay < 150 ms p95. |
| `job_checkpoint_count` | Training wrapper | per checkpoint | Measures training progress; used to compute effective utilization. |
| `job_preempt_count` | Orchestrator | per pre‑empt event | Tracks how often we had to yield for live services – should stay low. |
| `flux_batch_size` / `ltx_clip_len` | Workload launcher | per job start | Correlates with actual memory/GPU consumption for capacity planning. |

All metrics are exported via a **node‑exporter** side‑car on each box and scraped by a central Prometheus instance. Grafana dashboards display:

- **Utilization heatmap** (RAM + GPU) per box over the week.  
- **Live‑service latency** STT/router with threshold bands.  
- **Job throughput** (flux batches/hr, LTX clips/hr, training steps/hr).  
- **Pre‑empt/OOM events** (should be zero).  

A successful plan will show **average RAM usage climbing from ~45 GB to ~80 GB** on non‑eran1 boxes during night/evening windows, while **eran1 stays flat at ~30 GB** (reserved + baseline). GPU utilization on eran2‑4 should rise from ~30 % (day) to ~70‑80 % (night) without ever hitting 95 %+ on any box.

---  

*End of document.*  
*Prepared for the Fleet Operations Team – 2025‑09‑26.*