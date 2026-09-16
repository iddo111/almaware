# Nemotron 3 Super 120B - DGX1-3 production verification

Verified live on 2026-07-20 (Asia/Jerusalem).

## Outcome

- One distributed `nvidia/nemotron-3-super` model runs across DGX1, DGX2,
  and DGX3 with pipeline parallelism 3 and tensor parallelism 1.
- Production API: DGX1 port 8000.
- `/health`: HTTP 200.
- `/v1/models`: HTTP 200 in 0.290270 seconds; exact model ID
  `nvidia/nemotron-3-super`; `max_model_len=131072`.
- Real patched generation with the model-card-supported
  `chat_template_kwargs.enable_thinking=false`: HTTP 200 in 4.187389 seconds;
  content `NEMOTRON_PATCHED_OK`; finish reason `stop`; 31 prompt tokens,
  10 completion tokens, 41 total tokens.

The preceding default-thinking request also returned HTTP 200, but consumed
all 128 completion tokens in reasoning and returned null final content. It was
not counted as the success gate.

## Cluster topology

- DGX1 / Ray head: `<fabric-ip>`, one GB10 GPU.
- DGX2 / Ray worker: `<fabric-ip>`, one GB10 GPU.
- DGX3 / Ray worker: `<fabric-ip>`, one GB10 GPU.
- Ray status: exactly three ALIVE nodes, exactly 3.0 GPUs, no pending nodes,
  no recent failures.
- Network runtime: `enp1s0f1np1` only, `NCCL_IB_DISABLE=1`, one NCCL channel,
  `RAY_memory_usage_threshold=0.98`.

## Persistent rank fix

The derived image `vllm-ray-nemotron-pp:v0.20.0-rankfix` is built on all
three nodes. Its vLLM worker source was verified at line 308 on all nodes:

```python
kv_cache_config = kv_cache_configs[self.worker.rank]
```

This selects the KV-cache configuration by the effective Ray worker rank after
placement ordering, instead of the stale pre-sort global rank.

Production containers use that derived image:

- DGX1: `nemotron-ray-head`, `nemotron-cluster`.
- DGX2: `nemotron-ray-worker`.
- DGX3: `nemotron-ray-worker`.

All have restart policy `unless-stopped`.

## Load evidence

- 17/17 checkpoint shards loaded.
- Pipeline stage model allocations: 23.91 GiB, 24.29 GiB, 25.34 GiB.
- Available KV-cache memory: approximately 80.1 GiB on DGX1 and 79.55 GiB
  on the worker stages.
- Engine profile/KV/warmup: 22.12 seconds.
- Production API container: OOM false, restart count zero at verification.

## Important accuracy warning

vLLM reported checkpoint `k_scale` and `v_scale` names that did not match the
expected attention names, so those scales were not loaded. vLLM also warns
that FP8 KV cache without proper scaling can reduce accuracy. Service health
and generation passed, but this remains a model-quality limitation to measure.

## Watchdog

- End-to-end generation check targets the actual `nemotron-cluster` container.
- It uses reasoning-off mode and requires HTTP 200 plus `NEMOTRON_OK` content.
- Policy: restart only after three consecutive failures; 1800-second cooldown;
  API launcher fallback if the canonical container is absent.
- Manual run: healthy, HTTP 200, failures 0, action none.
- First automatic timer run at 07:59:56 IDT: healthy, HTTP 200,
  `NEMOTRON_OK`, service result success, exit status 0.
- Next run was scheduled for 08:05:12 IDT; cadence is five minutes.

## Rollback and preservation

Nothing was deleted. Retained stopped rollback containers:

- DGX1: `nemotron-ray-head-unpatched`,
  `nemotron-cluster-triton-pre-rankfix`, and earlier trial containers.
- DGX2: `nemotron-ray-worker-unpatched`.
- DGX3: `nemotron-ray-worker-unpatched`.

Launchers and rollback notes are in `D:\CLAUDE\fleet\nemotron-rankfix` and
installed under `/usr/local/sbin` on the applicable nodes.

Competing services remain disabled and inactive: Qwen/Comfy on DGX1, Grok RPC
on DGX2 and DGX3, and Eran Gist on DGX3. Their files were not deleted.

## Boot identity audit

- DGX1: `fe512620-59e9-42f1-adc6-54d40cf4e447`.
- DGX2: `83731048-d107-440f-b6f1-7dc78e867153`.
- DGX3: `24ab2384-792e-4c2e-8cf7-c1f01f9248a4`.
- DGX4 remained `d147ca84-4c2c-424d-9514-ed05db785956`;
  `alma-gpt-oss-120b.service` and `alma-harness.service` were active/running
  during the final audit.
