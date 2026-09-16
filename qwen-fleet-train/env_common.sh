# env_common.sh -- shared NCCL / rendezvous env for the 3-node FSDP/ZeRO-3 run.
# Sourced by launch_node.sh on every node. Do NOT run standalone.
#
# THE CRITICAL LINE: NCCL_NET=Socket.
# The routed eran1<->eran3 hop hairpins through eran2 (10.0.2.x -> 10.0.3.x). The
# spcx RDMA/IB plugin HANGS on that routed hop on this fleet (documented in
# project_eran_mesh). TCP-Socket transport works every time. It is slower than
# RDMA -- that is the #1 throughput risk, mitigated by large gradient accumulation.

export NCCL_NET=Socket
export NCCL_IB_DISABLE=1
export NCCL_SOCKET_FAMILY=AF_INET
# Boost Socket transport throughput (multiple TCP streams per peer).
# GATED: only on when TUNE_SOCKETS=1 -- aggressive multi-socket may deadlock the
# routed eran1<->eran3 hop, so default OFF (NCCL picks defaults).
if [ "${TUNE_SOCKETS:-0}" = "1" ]; then
  export NCCL_NSOCKS_PERTHREAD=4
  export NCCL_SOCKET_NTHREADS=2
fi
# First bring-up: set INFO to watch the ring form; drop to WARN once stable.
export NCCL_DEBUG=${NCCL_DEBUG:-WARN}

# Rendezvous master = eran1 (rank 0), where the weights are staged.
export MASTER_ADDR=${MASTER_ADDR:-<fabric-ip>}
export MASTER_PORT=${MASTER_PORT:-29500}

export OMP_NUM_THREADS=${OMP_NUM_THREADS:-8}
export TOKENIZERS_PARALLELISM=false
# Fail fast instead of hanging forever if a node never joins the ring:
export NCCL_ASYNC_ERROR_HANDLING=1
export TORCH_NCCL_ASYNC_ERROR_HANDLING=1
