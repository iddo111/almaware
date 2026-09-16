#!/usr/bin/env bash
# =============================================================================
# launch.sh — gpt-oss-120b FULL-WEIGHT ZeRO-3 + NVMe-offload launcher
#             targets: eran1 + eran2 + eran3 (GB10 DGX Spark, 1 GPU/node,
#             unified 121 GiB pool per node — the pool IS the GPU memory)
#
#   DEFAULTS TO DRY-RUN. EXECUTE=0 unless explicitly EXECUTE=1.
#   Even with EXECUTE=1 it refuses unless EVERY gate passes AND
#   I_HAVE_READ_GO_NO_GO=YES — because GO_NO_GO.md's verdict for this job
#   is NOT VIABLE on this fleet as cabled.
#
#   Every number printed below traces to the 2026-08-05 qualification reports
#   (DeepSpeed install / NCCL-RoCE fabric / memory-NVMe reality).
#   UNKNOWN means the measurement was not obtained; it is never an estimate.
#
#   Dry-run performs READ-ONLY remote checks (free, pgrep, find, df,
#   ip route get, python import). It allocates nothing, loads nothing.
# =============================================================================
set -uo pipefail   # deliberately NOT -e: gates are collected, then judged

EXECUTE="${EXECUTE:-0}"
ACK="${I_HAVE_READ_GO_NO_GO:-NO}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DS_CONFIG="$SCRIPT_DIR/ds_config_zero3_nvme.json"
DATASET_MANIFEST="${DATASET_MANIFEST:-$SCRIPT_DIR/dataset_manifest.json}"
TRAIN_SCRIPT_REL="gptoss-training/train_full_zero3.py"   # relative to $HOME on each node — DOES NOT EXIST YET (gated)
MASTER_ADDR="${MASTER_ADDR:-eran2}"    # UNVERIFIED: must resolve from BOTH eran1 and eran3 (mgmt net).
                                       # No single RoCE /30 address is reachable from both spokes.
MASTER_PORT="${MASTER_PORT:-29500}"
NODES=(eran1 eran2 eran3)
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=6)

# ---------------- Gates (justifications printed in the plan) ----------------
REQUIRED_FREE_GIB=100      # measured idle baseline was 114-115 GiB available (5-6 GiB used).
                           # <100 GiB available means another tenant (GLM replica) is resident.
REQUIRED_NVME_GIB=400      # derived per-node NVMe footprint ~312 GB (77.9 param shard +
                           # 155.8 fp32 master + 77.9 grad spill + 0.2 Adafactor) + headroom.
MODEL_DIR_REMOTE='models/gpt-oss-120b'
MODEL_BYTES_EXPECTED=65248893184   # verified byte-identical on all nodes
MODEL_SHARDS_EXPECTED=15
DS_VER_EXPECTED="0.19.3"           # verified installed on all three nodes

# --- NCCL env: the ONLY proven-working 3-node configuration (fabric report §4) ---
# The fabric is a LINE (eran1<->eran2<->eran3, no eran1<->eran3 wire). A 3-node
# RoCE ring is topologically impossible as cabled: NCCL binds one NIC per channel
# per rank, and transit RDMA through eran2 dies with IBV_WC_RETRY_EXC_ERR.
# Proven 3-node transport: TCP sockets, 4.53 GB/s algbw @ 2 GB messages.
NCCL_COMMON="NCCL_IB_DISABLE=1 NCCL_SOCKET_NTHREADS=4 NCCL_NSOCKS_PERTHREAD=4 NCCL_DEBUG=INFO"
declare -A IFNAME=(
  [eran1]="enp1s0f0np0,enP2p1s0f0np0"
  [eran2]="enp1s0f1np1,enP2p1s0f1np1,enp1s0f0np0,enP2p1s0f0np0"
  [eran3]="enp1s0f1np1,enP2p1s0f1np1"
)
# 2-node RoCE reference env — PROVEN at 22.63 GB/s all-reduce (for the QLoRA /
# pipeline-parallel alternative, NOT used by this 3-node launcher):
#   eran1: NCCL_IB_DISABLE=0 NCCL_IB_GID_INDEX=3 NCCL_IB_HCA="=rocep1s0f0:1,roceP2p1s0f0:1" NCCL_SOCKET_IFNAME=enp1s0f0np0
#   eran2: NCCL_IB_DISABLE=0 NCCL_IB_GID_INDEX=3 NCCL_IB_HCA="=rocep1s0f1:1,roceP2p1s0f1:1" NCCL_SOCKET_IFNAME=enp1s0f1np1

hr(){ printf '%s\n' "--------------------------------------------------------------------------------"; }

MODE="DRY-RUN (default, EXECUTE=0)"; [ "$EXECUTE" = "1" ] && MODE="EXECUTE (armed)"
hr
echo "gpt-oss-120b full-weight ZeRO-3+NVMe launcher   MODE: $MODE"
hr
cat <<'PLANEOF'
PLAN
  Job ............... full-weight fine-tune, gpt-oss-120b (116,829,156,672 params,
                      count independently re-derived from the 15 shard headers)
  Nodes ............. eran1, eran2, eran3   (eran4 EXCLUDED: no RDMA hardware)
  World ............. 3 nodes x 1 GPU = 3 ranks (torchrun --nnodes=3 --nproc_per_node=1)
  Sharding .......... DeepSpeed 0.19.3 ZeRO-3, params+optimizer offloaded to NVMe
                      (config: ds_config_zero3_nvme.json; per-node __NVME_PATH__
                      templated to /home/<node>/gptoss_ds_offload)
  Optimizer ......... client-side Adafactor (transformers 5.12.1), factored state
                      ~0.5 GB fp32 — Adam m,v would be ~934 GB and is ruled out
  Precision ......... MXFP4 checkpoint upcast to BF16 (233.66 GB weights)
  Transport ......... NCCL over TCP sockets — the ONLY proven 3-node config:
                        NCCL_IB_DISABLE=1 NCCL_SOCKET_NTHREADS=4 NCCL_NSOCKS_PERTHREAD=4
                        eran1: NCCL_SOCKET_IFNAME=enp1s0f0np0,enP2p1s0f0np0
                        eran2: NCCL_SOCKET_IFNAME=enp1s0f1np1,enP2p1s0f1np1,enp1s0f0np0,enP2p1s0f0np0
                        eran3: NCCL_SOCKET_IFNAME=enp1s0f1np1,enP2p1s0f1np1
                      Measured: 4.53 GB/s algbw / 6.04 GB/s busbw @ 2 GB (5.0x slower
                      than the 22.63 GB/s 2-node RoCE reference). 3-node RoCE ring:
                      IMPOSSIBLE as cabled (line topology, transit RDMA dead).
  PATH on nodes ..... $HOME/.local/bin:/usr/local/cuda/bin prepended (ninja + nvcc,
                      required for DeepSpeed JIT ops — proven in qualification)

MEMORY BUDGET PER NODE (measured pool: 121 GiB total; 114-115 GiB available at the
2026-08-05 snapshot, SHRINKING under concurrent GLM-5.2 bring-up on eran1/eran3):
  sharded bf16 weights+grads ......... 155.8 GB/node  [derived 467.3/3] -> DOES NOT FIT
                                       => NVMe offload is mandatory, not optional
  resident with full NVMe offload:
    live param window (1e9 elem bf16)     2.0 GB   [config]
    prefetch buckets (2 x 2e8 elem)       0.8 GB   [config]
    pinned param buffers (5 x 7.2e8)      7.2 GB   [config; sized to largest tensor
                                                    2,123,366,400 elem / 3 ranks]
    reduce buckets (2 x 5e8 elem bf16)    2.0 GB   [config]
    pinned optimizer swap buffers       ~16.0 GB   [derived: 4 x 1e9 fp32 subgroups]
    activations (micro_bs=1, grad ckpt)  UNKNOWN   [no dataset -> no seq len measured]
    CUDA ctx + NCCL TCP buffers          UNKNOWN
  NVMe per node ...................... ~312 GB [77.9 param shard + 155.8 fp32 master
                                       + 77.9 grad spill + 0.2 Adafactor]
                                       measured free: eran1 840G, eran2 1.5T, eran3 1.6T

STEP-TIME FLOOR (from measurements — this is why GO_NO_GO.md says NOT VIABLE):
  NVMe:    234-467 GB/node/step at measured 4.2-4.6 GB/s  =  53-106 s/step
  Network: ZeRO-3 all-gathers ~311 GB inbound/node/step; at the measured 4.53 GB/s
           3-node TCP rate                                 =  30-60+ s/step
  Combined floor: ~2-4 MINUTES PER OPTIMIZER STEP before any compute.
  1,000 steps ~= 1.5-3 days of pure byte-moving overhead.

GATES CHECKED BEFORE ANY LAUNCH (all read-only):
  per node:  ssh reachable | no GLM/Colibri/inference procs | >=100 GiB avail RAM
             model present (15 shards, 65,248,893,184 B) | deepspeed==0.19.3
             >=400 GiB free NVMe at $HOME fs | static route present (eran1/eran3;
             runtime-only routes, lost on reboot) | training script present
  local:     ds_config_zero3_nvme.json exists | dataset manifest exists
  execute:   EXECUTE=1 AND I_HAVE_READ_GO_NO_GO=YES AND zero failed gates
PLANEOF
hr
echo "PRE-FLIGHT CHECKS (read-only; ssh BatchMode, 6 s connect timeout per node)"
hr

declare -a RESULTS=()
FAILS=0
check(){ # status name detail
  local st="$1" name="$2" detail="$3"
  RESULTS+=("$(printf '%-4s | %-46s | %s' "$st" "$name" "$detail")")
  [ "$st" = "FAIL" ] && FAILS=$((FAILS+1))
}
gib(){ awk -v b="${1:-0}" 'BEGIN{printf "%.1f", b/1073741824}'; }
val(){ printf '%s\n' "$2" | sed -n "s/^$1=//p" | head -1; }

# --- remote probe script (read-only), shipped over ssh stdin ---
PROBE_FILE="$(mktemp)"
cat > "$PROBE_FILE" <<'PROBE'
node="$1"
echo "MEM_AVAIL_B=$(free -b | awk '/^Mem:/{print $7}')"
GLMPAT='[gG][lL][mM]|[cC]oli[b]ri|vl[l]m|sgl[a]ng|trit[o]nserver|llama[-_]server'
echo "GLM_PROCS=$(pgrep -af "$GLMPAT" | wc -l)"
echo "GLM_SAMPLE=$(pgrep -af "$GLMPAT" | head -1 | cut -c1-70)"
echo "MODEL_SHARDS=$(find "$HOME/models/gpt-oss-120b" -maxdepth 1 -name '*.safetensors' 2>/dev/null | wc -l)"
echo "MODEL_BYTES=$(find "$HOME/models/gpt-oss-120b" -maxdepth 1 -name '*.safetensors' -printf '%s\n' 2>/dev/null | awk '{s+=$1} END {printf "%d", s+0}')"
echo "DS_VER=$(python3 -c 'import deepspeed; print(deepspeed.__version__)' 2>/dev/null || echo MISSING)"
echo "NVME_AVAIL_B=$(df -B1 --output=avail "$HOME" 2>/dev/null | tail -1 | tr -d ' ')"
if [ -f "$HOME/gptoss-training/train_full_zero3.py" ]; then echo TRAIN_SCRIPT=present; else echo TRAIN_SCRIPT=absent; fi
case "$node" in
  eran1) ip route get <fabric-ip> 2>/dev/null | grep -q 'via <fabric-ip>' && echo ROUTE=ok || echo ROUTE=missing ;;
  eran3) ip route get <fabric-ip> 2>/dev/null | grep -q 'via <fabric-ip>' && echo ROUTE=ok || echo ROUTE=missing ;;
  *)     echo ROUTE=direct ;;
esac
PROBE

for n in "${NODES[@]}"; do
  OUT="$(ssh "${SSH_OPTS[@]}" "$n" bash -s -- "$n" < "$PROBE_FILE" 2>/dev/null)"
  if [ -z "$OUT" ]; then
    check FAIL "$n: ssh reachable (BatchMode)" "unreachable — ALL $n gates fail"
    continue
  fi
  check PASS "$n: ssh reachable (BatchMode)" "ok"

  glm="$(val GLM_PROCS "$OUT")"
  if [ "${glm:-0}" -eq 0 ] 2>/dev/null; then
    check PASS "$n: no GLM/Colibri/inference procs" "0 matches"
  else
    check FAIL "$n: no GLM/Colibri/inference procs" "$glm match(es): $(val GLM_SAMPLE "$OUT")"
  fi

  memb="$(val MEM_AVAIL_B "$OUT")"
  if awk -v b="${memb:-0}" -v r="$REQUIRED_FREE_GIB" 'BEGIN{exit !(b/1073741824 >= r)}'; then
    check PASS "$n: >=${REQUIRED_FREE_GIB} GiB RAM available" "$(gib "$memb") GiB available"
  else
    check FAIL "$n: >=${REQUIRED_FREE_GIB} GiB RAM available" "$(gib "$memb") GiB available (another tenant is resident)"
  fi

  shards="$(val MODEL_SHARDS "$OUT")"; mbytes="$(val MODEL_BYTES "$OUT")"
  if [ "${shards:-0}" = "$MODEL_SHARDS_EXPECTED" ] && [ "${mbytes:-0}" = "$MODEL_BYTES_EXPECTED" ]; then
    check PASS "$n: model verified (~/$MODEL_DIR_REMOTE)" "$shards shards, $mbytes B"
  else
    check FAIL "$n: model verified (~/$MODEL_DIR_REMOTE)" "got $shards shards / ${mbytes:-0} B, want $MODEL_SHARDS_EXPECTED / $MODEL_BYTES_EXPECTED"
  fi

  dsv="$(val DS_VER "$OUT")"
  if [ "$dsv" = "$DS_VER_EXPECTED" ]; then
    check PASS "$n: deepspeed==$DS_VER_EXPECTED importable" "$dsv"
  else
    check FAIL "$n: deepspeed==$DS_VER_EXPECTED importable" "got '$dsv'"
  fi

  nvb="$(val NVME_AVAIL_B "$OUT")"
  if awk -v b="${nvb:-0}" -v r="$REQUIRED_NVME_GIB" 'BEGIN{exit !(b/1073741824 >= r)}'; then
    check PASS "$n: >=${REQUIRED_NVME_GIB} GiB NVMe free (\$HOME fs)" "$(gib "$nvb") GiB free"
  else
    check FAIL "$n: >=${REQUIRED_NVME_GIB} GiB NVMe free (\$HOME fs)" "$(gib "$nvb") GiB free (need ~312 GB + headroom)"
  fi

  rt="$(val ROUTE "$OUT")"
  case "$rt" in
    ok)      check PASS "$n: static cross-rail route present" "runtime route ok (LOST ON REBOOT)";;
    direct)  check PASS "$n: static cross-rail route present" "hub node, directly connected both /30 pairs";;
    *)       check FAIL "$n: static cross-rail route present" "missing — reapply: eran1 'ip route add <fabric-ip>/30 via <fabric-ip> dev enP2p1s0f0np0' / eran3 'ip route replace <fabric-ip>/30 via <fabric-ip> dev enP2p1s0f1np1'";;
  esac

  ts="$(val TRAIN_SCRIPT "$OUT")"
  if [ "$ts" = "present" ]; then
    check PASS "$n: training script ~/$TRAIN_SCRIPT_REL" "present"
  else
    check FAIL "$n: training script ~/$TRAIN_SCRIPT_REL" "absent — never written (unmet precondition)"
  fi
done
rm -f "$PROBE_FILE"

# --- local gates ---
if [ -s "$DS_CONFIG" ]; then
  check PASS "local: ds_config_zero3_nvme.json exists" "$DS_CONFIG"
else
  check FAIL "local: ds_config_zero3_nvme.json exists" "missing: $DS_CONFIG"
fi
if [ -s "$DATASET_MANIFEST" ]; then
  check PASS "local: dataset manifest exists" "$DATASET_MANIFEST"
else
  check FAIL "local: dataset manifest exists" "missing: $DATASET_MANIFEST — no dataset was ever provided"
fi

hr
TOTAL=${#RESULTS[@]}
echo "GATE RESULTS: $((TOTAL-FAILS))/$TOTAL passed, $FAILS FAILED"
hr
for r in "${RESULTS[@]}"; do echo "  $r"; done
hr

if [ "$EXECUTE" != "1" ]; then
  echo "DRY-RUN COMPLETE. Nothing was launched. No model loaded, no GPU/unified"
  echo "memory allocated, no process started on any node (checks were read-only)."
  echo ""
  echo "To arm:  EXECUTE=1 I_HAVE_READ_GO_NO_GO=YES bash launch.sh"
  echo "It will still REFUSE while any gate above is FAIL."
  echo "Read GO_NO_GO.md first — the verdict for this job is NOT VIABLE."
  exit 0
fi

if [ "$FAILS" -gt 0 ]; then
  echo "REFUSING TO LAUNCH: $FAILS gate(s) FAILED (see table above)."
  exit 1
fi
if [ "$ACK" != "YES" ]; then
  echo "REFUSING TO LAUNCH: GO_NO_GO.md verdict is NOT VIABLE for 3-node full-weight"
  echo "training. If you have read it and insist: set I_HAVE_READ_GO_NO_GO=YES."
  exit 1
fi

# ---------------- actual launch (reachable ONLY with EXECUTE=1, zero failed ----
# ---------------- gates, and explicit GO_NO_GO acknowledgement) ----------------
echo "ALL GATES PASSED + ACK GIVEN — launching."
for i in "${!NODES[@]}"; do
  n="${NODES[$i]}"
  ssh "${SSH_OPTS[@]}" "$n" "mkdir -p ~/gptoss-training ~/gptoss_ds_offload/param ~/gptoss_ds_offload/optimizer"
  sed "s|__NVME_PATH__|/home/$n/gptoss_ds_offload|g" "$DS_CONFIG" | \
    ssh "${SSH_OPTS[@]}" "$n" "cat > ~/gptoss-training/ds_config_zero3_nvme.json"
  scp -o BatchMode=yes "$DATASET_MANIFEST" "$n:gptoss-training/dataset_manifest.json"
  ssh "${SSH_OPTS[@]}" "$n" "export PATH=\$HOME/.local/bin:/usr/local/cuda/bin:\$PATH; \
    cd ~/gptoss-training && nohup env $NCCL_COMMON NCCL_SOCKET_IFNAME=${IFNAME[$n]} \
    torchrun --nnodes=3 --nproc_per_node=1 --node_rank=$i \
      --master_addr=$MASTER_ADDR --master_port=$MASTER_PORT \
      \$HOME/$TRAIN_SCRIPT_REL \
      --deepspeed ds_config_zero3_nvme.json \
      --model-path \$HOME/models/gpt-oss-120b \
      --dataset-manifest ~/gptoss-training/dataset_manifest.json \
      > train_rank$i.log 2>&1 & echo launched rank $i on $n"
done
echo "Launched. Logs: ~/gptoss-training/train_rank<N>.log on each node."
