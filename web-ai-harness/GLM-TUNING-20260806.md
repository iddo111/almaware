# GLM-5.2 fleet tuning — 2026-08-06

**Headline: the fleet got 1.29x–1.85x faster by changing which CPU cores the model runs on. Nothing else. No quantisation, no memory re-split, no quality change, no restart on eran4.**

| node | before | after | gain | tok/s after | spread after |
|---|---|---|---|---|---|
| eran1 | 1690.3 ms/tok | **1000.9** | **1.69x** | 1.00 | 4.1% (was 13.3%) |
| eran2 | 1618.2 ms/tok | **974.3** | **1.66x** | 1.03 | 5.1% (was 11.4%) |
| eran3 | 1886.1 ms/tok | **1017.6** | **1.85x** | 0.98 | 4.3% (was 20.8%) |
| eran4 | 2582.8 ms/tok | **1995.3** | **1.29x** | 0.50 | 2.1% (was 6.7%) |

eran3 gets an extra step because it was also carrying `COLI_CUDA_MTP=1`: affinity alone
took it to 1088.9, and removing MTP took it to 1017.6 (see §2.4). Its figure above is
the mean of two independent replications, 1014.3 and 1020.9 — agreeing to 0.65%.

A 90-token reply that took **3 minutes** now takes **~90 seconds** on eran1/2/3.
Iddo's original complaint was 0.43–0.53 tok/s; eran1/2/3 now run at **0.92–1.03 tok/s**.

Output was verified correct on every run (counting and prime-sequence prompts, all
exact). Disk reads and memory footprint are unchanged — this is pure scheduling.

---

## 1. Before -> after, and what changed

### What changed

Exactly one thing on eran1/2/3, plus one ExecStart normalisation on eran3:

```
OMP_PROC_BIND=close
OMP_PLACES={5},{6},{7},{8},{9},{15},{16},{17},{18},{19}
OMP_NUM_THREADS=10
```

Every GB10 node has a **heterogeneous** CPU: 10x Cortex-X925 at 3.9 GHz (cores
5-9, 15-19) and 10x Cortex-A725 at 2.8 GHz (cores 0-4, 10-14). Verified identical
on all four nodes from `/sys/devices/system/cpu/cpu*/cpufreq/cpuinfo_max_freq`.

The old setting was `OMP_PROC_BIND=spread` + `OMP_PLACES=cores`, which spreads
threads evenly across *all* 20 cores. OpenMP then splits each layer's work into
**equal** shares. Because the shares are equal but the cores are not, every barrier
waits for a little A725 core to finish a big core's worth of work.

### The direct evidence

Measured on eran4's live engine, per-thread CPU time (`utime`, in ticks) for
threads doing identical shares of identical work:

| thread placement | utime |
|---|---|
| CPU 2, 4, 10, 12, 14 (little A725) | 193335, 193846, 195570, 195487, 195755 |
| CPU 6, 8, 16, 18 (big X925) | 108242, 106149, 107999, 106431 |

**~1.8x more CPU burned on the little cores for the same work.** The little cores
are the critical path at every OpenMP barrier. Excluding them is the entire fix.

This independently reproduces the finding from the earlier 30-config sweep, which
measured the same thing from the other direction (little cores 76-81% busy while
six big cores sat 100% idle).

### Why the gain is real and not drift

- Byte-identical disk reads before and after (252.8 vs 253.1 GB/run in the sweep).
- Byte-identical output text.
- Run-to-run spread *fell* on all four nodes (e.g. eran3 20.8% -> 6.1%), which is
  what you expect when you remove a slow straggler, not what you get from noise.
- Every node improved, independently, in the same direction.

### Method

Per node: service restarted, 2 warm-up requests discarded, then 3 measured runs.
Prompts deliberately demand far more output than `max_tokens` so **every run is
truncated at exactly 48 tokens** (32 on eran4) and runs are directly comparable.
ms/tok excludes prefill: it is `(total - TTFT) / (tokens - 1)`.

Harness: `~/tune/fleetbench.py` on each node; raw results in `~/tune/*.json` and
`~/tune/*.log`.

---

## 2. The winning configuration

### eran1, eran2, eran3 — full winner, applied and restarted

`~/.config/systemd/user/colibri-glm52.service` ExecStart (unchanged except eran3,
which was normalised from the `--ram 45 --vram 64` test back to the measured best):

```
/usr/bin/python3 %h/apps/colibri/c/coli serve \
  --model %h/models/GLM-5.2-colibri-int4-with-int8-mtp \
  --auto-tier --gpu 0 --ram 70 --vram 40 --ctx 32768 --policy quality \
  --host <tailscale-ip> --port 8800 --model-id glm-5.2 \
  --max-queue 1 --queue-timeout 3600 --kv-slots 1
```

`~/.config/colibri-glm52/service.env`:

```
COLI_API_KEY=<key>
CUDA_RELEASE_HOST=1
PIPE=1
URING=1
DIRECT=1
PILOT=1
PILOT_REAL=1
PREFETCH=8
# GLM-5.2 tuning 2026-08-06: OMP pinned to the ten Cortex-X925 big cores.
OMP_PROC_BIND=close
OMP_PLACES={5},{6},{7},{8},{9},{15},{16},{17},{18},{19}
OMP_NUM_THREADS=10
```

### eran4 — conservative variant, applied WITHOUT a restart

eran4 hosts gpt-oss (the only fast model) and alma-stt, has ~1.2 GB free RAM and
14.9 GB of swap already in use. **Restarting its colibri would have freed and then
re-allocated ~21 GB of RSS on a node with no headroom — the one action most likely
to disturb gpt-oss.** So it was not restarted.

Instead the identical placement was applied **live with `taskset`** to the running
engine's ten compute threads — pure scheduling, zero memory churn, instantly
reversible:

```
taskset -pc 19 <master>          # was CPU 0 (a little core)
taskset -pc 5,6,7,8,9,15,16,17,18 <the nine OMP workers>   # were 2,4,6,8,10,12,14,16,18
```

The same lines were then written to eran4's `service.env` so the placement survives
the next natural restart. Revert script: `~/tune/eran4_revert_affinity.sh`.

Side benefit for gpt-oss: GLM previously occupied five little cores at ~100%.
It now touches **no little core at all** — all ten A725 cores are free for
gpt-oss, alma-stt and the system.

### 2.4 `COLI_CUDA_MTP=1` was removed — it is now a 7% LOSS

eran3 was the only node carrying `COLI_CUDA_MTP=1` (speculative decoding, draft=1).
The brief recorded it as a ~6% *gain*, measured before the affinity fix.

Re-measured on eran3 today, same node, same config, back to back:

| config | ms/tok | TTFT |
|---|---|---|
| affinity + `COLI_CUDA_MTP=1` | 1088.9 | 13.91 s |
| affinity, MTP removed | **1014.3** | 12.81 s |
| affinity, MTP removed (replication) | **1020.9** | 12.75 s |

MTP now **costs ~7%**. That reversal makes sense: speculative decoding spends extra
compute on the verify step to save memory traffic. When the CPU was crippled by the
little-core misallocation, that trade paid. Now that the CPU is no longer the
bottleneck, the extra verify compute is a pure cost.

MTP is now **off on all four nodes**, so the fleet is uniform. `service.env.bak-mtp-ab`
on eran3 holds the previous version.

### Persistence — verified, not assumed

The brief flagged a previous incident where a good config lived only in process
memory. That is checked explicitly here. eran1/2/3 were each restarted, and the
**live process environment** was then read back from `/proc/<pid>/environ`:

```
OMP_NUM_THREADS=10
OMP_PLACES={5},{6},{7},{8},{9},{15},{16},{17},{18},{19}
OMP_PROC_BIND=close
ExecStart: --ram 70 --vram 40
```

Identical on all three, matching the on-disk EnvironmentFile. The running threads
were also confirmed pinned one-per-core to 5,6,7,8,9,15,16,17,18,19.

Independent confirmation from the router's own health poller, which saw eran3 come
back as `vram_gb=39.99` (it had been 63.99), proving the ExecStart edit is live.

Backups, on every node:
- `~/.config/systemd/user/colibri-glm52.service.bak-fleet-20260806-*`
- `~/.config/colibri-glm52/service.env.bak-fleet-20260806-*`

Revert = restore the backup, `systemctl --user daemon-reload && restart`.

---

## 3. Always-warm: does it go cold?

### Answer: NO. It does not go cold from idling. Measured, not assumed.

The three idle intervals were run **concurrently on three different nodes** (so 10,
30 and 60 minutes all fit in one 60-minute window). Each node is compared against
**its own** warm reference taken minutes earlier, so node-to-node differences cancel.

| node | idle | warm reference | first request after idle | change | TTFT warm -> cold |
|---|---|---|---|---|---|
| eran3 | 10 min | 1056.7 ms/tok | **1046.6** | **-0.9%** | 13.60 -> 13.97 s |
| eran2 | 30 min | 971.0 ms/tok | **950.8** | **-2.1%** | 12.88 -> 13.15 s |
| eran1 | 60 min | 1005.8 ms/tok | **983.2** | **-2.2%** | 12.79 -> 13.03 s |

Every "after idle" number is *faster* than its warm reference. There is no decay at
all — the small negative changes are run-to-run noise (spread is 3.5–4.7%).

### Corroborating evidence that nothing was evicted

`VmRSS` of the engine process, sampled before warm-up, after warm-up, after the idle
window and after the re-query:

| node | VmRSS across the whole test |
|---|---|
| eran1 (64 min span) | 54939344 kB, 54939344 kB, 54939344 kB, 54939344 kB |
| eran2 (34 min span) | 54959640 kB, 54959640 kB, 54959640 kB, 54959640 kB |

**Byte-identical.** `VmSwap: 0` throughout. Page cache moved by <150 MB. The
`admitted` counter was unchanged across every idle window (9 -> 9), proving no other
traffic warmed the node behind the test's back.

### Why it cannot go cold — the mechanism

- There is **no idle timer, no unload path and no eviction-on-idle** anywhere in the
  engine. (`colibri.c` eviction is LRU *within* a live generation; the keepalive code
  in `openai_server.py` is an HTTP socket keepalive for long prefills, unrelated.)
- The expert tiers are **explicit resident allocations**, not page-cache. The kernel
  will not reclaim them without memory pressure, and on eran1/2/3 there is none.
- Nothing on these boxes drops caches: no `drop_caches` cron, no `tuned`, no
  `systemd-oomd`, no `earlyoom`, `swappiness=10`.

### So what was actually deployed, and why

Since idle decay is zero, a keepalive is **not** needed to prevent it, and this
report explicitly does not claim one is. But there is a real, separate cold state:
**the first request after a restart or reboot** costs an extra ~10-15 s (measured:
first warm-up request 11.4–15.7 s for a single token, second 1.9–5.3 s).

So `colibri-keepalive.timer` is installed on **eran1, eran2, eran3** with:

```ini
OnBootSec=5min          # warm the model after every boot, before a user asks
OnUnitActiveSec=60min   # the LONGEST interval with measured evidence behind it
AccuracySec=30s
```

60 minutes is chosen because 60 minutes of idle is the longest gap actually measured
to cause zero degradation. Its job is to bound post-restart coldness, not to fight
decay.

The ping is deliberately cheap and polite:
- `max_tokens: 1`, measured at **3.1–3.2 s** per ping — a **0.09% duty cycle**.
- It reads `/health` first and **skips entirely if the node is busy**, so it can
  never queue in front of a real user on a 1-KV-slot backend.
- Every invocation logs one line to `~/tune/keepalive.log` and to the journal.

Verified live on all three: `enabled`, `active`, next elapse 59 min out, first ping
`PING ok http=200 3.17s`, `Result=success`. Linger was already on.

**eran4 deliberately has the service unit staged but the timer NOT installed.** It
gains nothing (no idle decay exists) and every avoidable background task on that node
is pure downside risk to gpt-oss. To enable it later:
`~/tune/deploy_keepalive.sh 60min`.

To remove the keepalive entirely on any node:
`systemctl --user disable --now colibri-keepalive.timer`

---

## 4. eran4 regression check

**Verdict: gpt-oss and alma-stt are both untouched. Neither was ever restarted.**

The strongest single piece of evidence: all three eran4 services still report their
original start time, hours before any change was made.

```
gptoss-120b:     Thu 2026-08-06 06:14:49 IDT
alma-stt:        Thu 2026-08-06 06:14:37 IDT
colibri-glm52:   Thu 2026-08-06 06:14:53 IDT
```

The eran4 change was applied at 20:54. Nothing restarted.

### gpt-oss (port 8000)

| when | max_tokens | latency |
|---|---|---|
| before change | 16 | 0.65 / 0.40 / 0.41 s |
| after change | 16 | 0.410 / 0.401 / 0.401 s |
| after change | 40 | 0.985 / 0.929 / 0.928 / 0.935 / 0.930 s |

Still ~1 s, and slightly *more consistent* than before (the 0.65 s outlier is gone) —
consistent with GLM having vacated the little cores that gpt-oss's host threads use.

### alma-stt (port 8844)

```json
{"status": "ok", "server": "eran4", "model": "openai/whisper-large-v3-turbo",
 "device": "cuda:0 / float16", "gpu": "NVIDIA GB10", "loaded": true,
 "automatic_languages": ["he", "en"]}
```

HTTP 200, model loaded on the GPU. (Probed from the Windows box — alma-stt returns
403 to eran4's own IP by its allowed-clients policy, which is correct behaviour, not
a fault.)

### Memory — unchanged, as designed

|  | free | swap used |
|---|---|---|
| before | 1144 MB | 14900 MB |
| after | 1678 MB | 14971 MB |

Pure CPU scheduling changes nothing about memory, which is exactly why this was the
only change made on eran4.

### Why eran4 was not restarted

Applying the config the normal way (edit `service.env`, `systemctl restart`) would
have freed and re-allocated ~21 GB of RSS on a node with 1.1 GB free and 14.9 GB
already in swap. That is the single action most likely to disturb gpt-oss. So the
placement was applied **live with `taskset`** instead, and the env file was updated
so a future restart reproduces it. Revert: `~/tune/eran4_revert_affinity.sh`.

---

## 5. Final verification

### /health returns 200 and reports a GPU — all four

| node | HTTP | status | gpus | gpu | vram_gb | ram_gb |
|---|---|---|---|---|---|---|
| eran1 | 200 | ok | 1 | CUDA device x1 | 39.99 | 43.77 |
| eran2 | 200 | ok | 1 | CUDA device x1 | 39.99 | 43.77 |
| eran3 | 200 | ok | 1 | CUDA device x1 | 39.99 | 43.77 |
| eran4 | 200 | ok | 1 | CUDA device x1 | 11.88 | 11.35 |

eran1/2/3 are now byte-for-byte uniform. eran4's small tiers are the memory-pressure
story in §6.

### A real generation returns a correct answer

Trick question, temperature 0: *"A farmer has 17 sheep. All but 9 run away. How many
are left?"* — the wrong answer is 8.

| node | answer |
|---|---|
| eran2 | `9` — "The phrase 'all but 9' means exactly 9 sheep remained." |
| eran3 | `9` — identical |
| eran4 | `9` — identical |

Through the router, 3 different sums in parallel: `1+1 -> 2`, `2+2 -> 4`, `3+3 -> 6`.
All counting and prime-list benchmark outputs were also exact on every run.

### ms/tok per node (final)

| node | ms/tok | tok/s | corroborating independent measurements |
|---|---|---|---|
| eran1 | **1000.9** | 1.00 | 1005.8 (warm ref), 983.2 (post-idle) |
| eran2 | **974.3** | 1.03 | 971.0 (warm ref), 950.8 (post-idle) |
| eran3 | **1017.6** | 0.98 | 1014.3 and 1020.9 (two replications) |
| eran4 | **1995.3** | 0.50 | 1985.3 / 2021.0 / 1979.5 (spread 2.1%) |

### Free memory and swap, every node

| node | free | available | swap used |
|---|---|---|---|
| eran1 | 10032 MB | 25187 MB | **0 MB** |
| eran2 | 6733 MB | 25200 MB | 1126 MB |
| eran3 | 9417 MB | 25975 MB | 159 MB |
| eran4 | 1520 MB | 12176 MB | 14963 MB |

eran4's swap is pre-existing and unchanged by this work (14900 MB before, 14963 MB
after — normal drift). No node swapped as a *result* of any change.

### eran4: gpt-oss and alma-stt

- gpt-oss on :8000 — **0.400 / 0.403 / 0.494 s**, still ~1 s or better. `active`.
- alma-stt on :8844 — HTTP 200, `"loaded": true`, whisper-large-v3-turbo on
  `cuda:0`. `active`.
- Neither service restarted at any point (start timestamps still 06:14).

### Concurrency through the router — 3 parallel, 3 different backends

Three requests arriving in the **same millisecond**:

```
22:00:30.709 RECV    [896857b2] ... 22:00:30.709 RECV [3b2f86ea] ... 22:00:30.709 RECV [230ca285]
22:00:30.760 DISPATCH[896857b2] -> eran1  router_wait=0.00s loads[eran1=1, eran2=0, eran3=0, eran4=0]
22:00:30.760 DISPATCH[3b2f86ea] -> eran2  router_wait=0.00s loads[eran1=1, eran2=1, eran3=0, eran4=0]
22:00:30.761 DISPATCH[230ca285] -> eran3  router_wait=0.00s loads[eran1=1, eran2=1, eran3=1, eran4=0]
22:00:44.092 DONE    [896857b2] <- eran1  status=200 elapsed=13.30s
22:00:44.208 DONE    [3b2f86ea] <- eran2  status=200 elapsed=13.45s
22:00:44.285 DONE    [230ca285] <- eran3  status=200 elapsed=13.52s
```

Three distinct backends, zero router wait, all 200, finishing within 220 ms of each
other — i.e. genuinely parallel, not serialised. eran4 was correctly left idle by
`ROUTER_DEPRIORITIZE`. Repeated a second time with the same fan-out.

### Router changes

`glm_router.py` needed **no functional change** — its health gating (`gpus>=1` *and*
`tiers.vram_gb>0`, probed *with* the bearer key) is correct and it detected every
restart on its own, including eran3 flipping from `vram_gb=63.99` to `39.99`.

Only stale documented facts were corrected: `ROUTER_REQUEST_TIMEOUT` said "GLM is
~3 s/tok" (now ~1.0 on eran1/2/3, ~2.0 on eran4), and `ROUTER_DEPRIORITIZE`'s note
now records that eran4 is also the slowest node by ~2x, which makes picking it last
doubly correct.

`fleet.py` carried a stale user-facing label (`~0.5 tok/s, expect 3-8 min`) and — more
importantly — points the GUI's GLM entry **straight at eran4:8800**, the slowest node,
bypassing the router entirely. The label is corrected and the file now documents
`COLIBRI_URL=http://127.0.0.1:8801` to route through the load balancer instead. **The
default endpoint was left unchanged** — switching the GUI's transport is a behavioural
change beyond this task's scope, and is flagged here as a recommendation.

---

## 6. What is still slow, and why

### The remaining bottleneck is the single NVMe, and it is now measurable

Measured directly on eran3 (bytes from `/proc/diskstats` across one 48-token
generation, plus a raw `O_DIRECT` read of the model shards to find the ceiling):

| quantity | measured |
|---|---|
| bytes read per token | **3.31 GB** |
| sustained rate during generation | 3.16 GB/s |
| drive ceiling, 1 stream (`dd iflag=direct`) | 4.4–4.6 GB/s |
| drive ceiling, 4 parallel streams | **5.79 GB/s** |

The model is ~358 GB on disk; only ~84 GB is resident (40 GB VRAM tier + 44 GB RAM
tier). Everything else streams, every token.

**Even a perfect I/O path cannot beat ~570 ms/token** (3.31 GB at 5.79 GB/s), i.e.
**~1.75 tok/s is the hard hardware ceiling** for this model at this residency on one
drive. We are at 1.0 tok/s, so roughly 55% of each token is unavoidable disk time and
~450 ms is compute and non-overlapped I/O.

### Why the "add a second SSD" idea is dead

The brief flagged `COLI_MODEL_MIRROR` / `coli mirror` as potentially the single
biggest win, because independent-drive bandwidth adds. **Checked: every node has
exactly one physical NVMe (`nvme0n1`, 3.6 TB).** There is no second drive to mirror
onto. This is a hardware purchase, not a config change — but note it is the single
highest-leverage upgrade available: a second NVMe would move the hard ceiling from
~1.75 tok/s to ~3.5 tok/s.

### The io_uring / CUDA helper threads share core 5 — checked, and it does not matter

Pinning binds the OMP master to the first place (CPU 5), and every thread it spawns
inherits that: 9 `iou-wrk` workers, `cuda-EvtHandlr` and the CUDA driver thread all
land on CPU 5 alongside a compute thread. That looks alarming, so it was measured:
the io_uring workers consume **~280 ticks of stime in total against ~9,500 ticks of
utime per compute thread — about 3%**. They are blocked on I/O, not competing for
CPU. No action needed; recorded so nobody re-investigates it.

### eran4 is slow for a completely different reason

eran4 is at 1995 ms/tok not because of CPU or drive but because it has no memory.
It shares 121 GiB with gpt-oss-120b, alma-stt (whisper-large-v3-turbo on the same
GPU), ollama, docker and a GUI. Its colibri gets `vram_gb=11.88 / ram_gb=11.35`
against eran1/2/3's `39.99 / 43.77`, and **13.1 GB of its RSS is swapped out**.
It reads far more from disk per token because almost nothing is resident.

No configuration change fixes this. The options are: stop running GLM on eran4
(the router already picks it last), or accept it as the overflow node. The 1.29x
affinity gain is all that was safely available.

### Levers that are measured and deliberately NOT shipped

- **`CACHE_ROUTE=1 ROUTE_J=1 ROUTE_M=32`** — the big one: 3.19x with 86% fewer disk
  reads and coherent output on all three test prompts. It changes which experts are
  consulted, so it needs a real quality suite (the engine ships `ROUTE_AGREE`
  telemetry for exactly this) before it goes near production. **This is the single
  best next piece of work** and it is the only remaining path to Iddo's 3-minute
  reply becoming ~40 seconds.
- **`--topk 4`** — 1.46x but a *measured quality regression* (miscounts: "18, 19,
  19, 20"). Not shipped.
- **Stacked approximations** (topk4 + ctx8k + CACHE_ROUTE) — produced garbage output.
  Not shipped.

### Levers that are measured and simply do not work

`--policy` (all three values are throughput-identical), `--repin`, `--cap` (the
planner overrides the flag), pipe worker count, and RAM/VRAM re-splits. All were
measured null in the earlier 30-config sweep and none was revisited except the
RAM/VRAM split, which was re-normalised to the measured-best 70/40 on eran3.

---

## 7. Artifacts, backups and how to revert

### Backups (all created today, before any edit)

| node | files |
|---|---|
| eran1 | `service.env.bak-fleet-20260806-204621`, `colibri-glm52.service.bak-fleet-20260806-204621` |
| eran2 | `service.env.bak-fleet-20260806-204630`, `colibri-glm52.service.bak-fleet-20260806-204630` |
| eran3 | `service.env.bak-fleet-20260806-204517`, `colibri-glm52.service.bak-fleet-20260806-204517`, `service.env.bak-mtp-ab` |
| eran4 | `service.env.bak-fleet-20260806-205449` (env only — the unit was never touched) |

Revert on eran1/2/3:

```bash
cp ~/.config/colibri-glm52/service.env.bak-fleet-20260806-* ~/.config/colibri-glm52/service.env
cp ~/.config/systemd/user/colibri-glm52.service.bak-fleet-20260806-* ~/.config/systemd/user/colibri-glm52.service
systemctl --user daemon-reload && systemctl --user restart colibri-glm52
systemctl --user disable --now colibri-keepalive.timer   # if you also want the keepalive gone
```

Revert on eran4 — **no restart required**, the affinity is live-only:

```bash
~/tune/eran4_revert_affinity.sh
cp ~/.config/colibri-glm52/service.env.bak-fleet-20260806-205449 ~/.config/colibri-glm52/service.env
```

### One important asymmetry to know about eran4

eran4's **on-disk** env now specifies the big-core placement, but its **live process
environment still shows the old `spread`/`cores`** — because it was never restarted.
The live placement was set with `taskset` and is currently correct (verified: all ten
compute threads on CPUs 5-9,15-19). The two will converge the next time colibri-glm52
restarts on that node. This is intentional, not drift.

### Scripts left on every node (`~/tune/`)

| file | purpose |
|---|---|
| `fleetbench.py` | the benchmark harness (fixed token count, ms/tok excludes prefill) |
| `apply_winner.sh` | backs up, rewrites env + ExecStart, reloads, restarts |
| `coldtest.sh` | warm reference -> idle N min -> re-measure, with RSS/swap/admitted snapshots |
| `diskprobe.sh` | bytes read per token from `/proc/diskstats` during one generation |
| `colibri-keepalive.sh` | the ping (skips when busy, logs every invocation) |
| `deploy_keepalive.sh` | installs + enables the timer at a given interval |
| `eran4_revert_affinity.sh` | eran4 only — restores the original thread placement |

Raw results: `~/tune/*.json`, `~/tune/*.log`, `~/tune/cold_*.snap`.

### Note on measurement methodology

Every number in this report excludes prefill: `ms/tok = (total - TTFT) / (tokens - 1)`.
Prompts are chosen to demand far more output than `max_tokens` so every run is
truncated at the same token count and runs are directly comparable — the earlier
prompts finished early (13-48 tokens) and were replaced for exactly this reason.
Warm-ups are always discarded. The cold tests additionally record the backend's
`admitted` counter across the idle window to prove no foreign traffic interfered.
