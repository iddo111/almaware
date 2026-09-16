#!/usr/bin/env python3
"""
NCCL 3-node triangle test — verify the QSFP fabric all-reduce before training ProtoEran.
3 DGX Spark (GB10, 1 GPU each) wired in a triangle (each node -> both others).
Checks: (1) correctness of all-reduce, (2) bandwidth (algbw + ring busbw).

RUN (fleet must be UP; run the SAME command on each node, changing --node_rank):
  # on each of eran1(rank0) / eran2(rank1) / eran3(rank2):
  NCCL_DEBUG=INFO NCCL_SOCKET_IFNAME=<qsfp_iface> \
  torchrun --nnodes=3 --nproc_per_node=1 --node_rank=<0|1|2> \
           --master_addr=<eran2_qsfp_ip> --master_port=29500 nccl_triangle_test.py

  NOTE: set NCCL_SOCKET_IFNAME to the QSFP interface name (check `ip a` on each node).
        NCCL_DEBUG=INFO prints the transport NCCL picked (RoCE/IB vs TCP) — read it to
        confirm it's using the 200G QSFP links, not the slow management LAN.
"""
import os, time, torch
import torch.distributed as dist


def human(b):
    return f"{b/1e6:.0f} MB" if b < 1e9 else f"{b/1e9:.2f} GB"


def main():
    dist.init_process_group(backend="nccl")            # reads env:// from torchrun
    rank = dist.get_rank()
    world = dist.get_world_size()
    local_rank = int(os.environ.get("LOCAL_RANK", 0))
    torch.cuda.set_device(local_rank)
    dev = torch.device(f"cuda:{local_rank}")
    name = torch.cuda.get_device_name(local_rank)
    print(f"[rank {rank}/{world}] up on {name} (local_rank={local_rank})", flush=True)

    # ---- (1) correctness: each rank contributes a distinct value; SUM must match ----
    t = torch.full((1024, 1024), float(rank + 1), device=dev)
    dist.all_reduce(t, op=dist.ReduceOp.SUM)
    expected = float(sum(range(1, world + 1)))
    ok = torch.allclose(t, torch.full_like(t, expected))

    # ---- (2) bandwidth: repeated all-reduce of a big buffer ----
    N = (256 * 1024 * 1024) // 4                        # 256 MB of float32
    buf = torch.ones(N, device=dev)
    torch.cuda.synchronize(); dist.barrier()

    # warmup
    for _ in range(5):
        dist.all_reduce(buf, op=dist.ReduceOp.SUM)
    torch.cuda.synchronize()

    iters = 20
    t0 = time.perf_counter()
    for _ in range(iters):
        dist.all_reduce(buf, op=dist.ReduceOp.SUM)
    torch.cuda.synchronize()
    dt = (time.perf_counter() - t0) / iters

    size_bytes = buf.numel() * buf.element_size()
    algbw = size_bytes / dt / 1e9                        # GB/s
    busbw = algbw * 2 * (world - 1) / world              # ring all-reduce bus bandwidth

    if rank == 0:
        print("=" * 56, flush=True)
        print(f"[nccl] world_size = {world}", flush=True)
        print(f"[nccl] correctness = {'PASS ✅' if ok else 'FAIL ❌'} "
              f"(each cell should equal {expected:.0f})", flush=True)
        print(f"[nccl] all-reduce {human(size_bytes)} : {dt*1e3:.2f} ms/iter", flush=True)
        print(f"[nccl] algbw = {algbw:.1f} GB/s   busbw = {busbw:.1f} GB/s", flush=True)
        print(f"[nccl] (QSFP ~200Gb/s ≈ 25 GB/s/link; healthy busbw ~ tens of GB/s)", flush=True)
        print("=" * 56, flush=True)

    dist.barrier()
    dist.destroy_process_group()


if __name__ == "__main__":
    main()
