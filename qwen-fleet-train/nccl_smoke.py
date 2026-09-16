#!/usr/bin/env python3
"""Minimal NCCL all-reduce smoke test. No DeepSpeed, no model -- just proves the
NCCL collective data-plane works across the given ranks. Launched by torchrun.
Prints START, does a CUDA all_reduce, prints the result + elapsed. If it hangs,
the collective data-plane is the problem (not train.py/DeepSpeed)."""
import os, time, torch, torch.distributed as dist

rank = int(os.environ["RANK"]); world = int(os.environ["WORLD_SIZE"])
print(f"[rank {rank}/{world}] START pid={os.getpid()}", flush=True)
dist.init_process_group("nccl")
print(f"[rank {rank}] init_process_group OK", flush=True)
torch.cuda.set_device(0)
x = torch.ones(1024, 1024, device="cuda") * (rank + 1)   # 4 MB
torch.cuda.synchronize()
t0 = time.time()
dist.all_reduce(x)                                       # sum across ranks
torch.cuda.synchronize()
dt = time.time() - t0
expected = sum(range(1, world + 1))
got = x[0, 0].item()
print(f"[rank {rank}] all_reduce DONE in {dt*1000:.1f} ms  value={got} expected={expected} "
      f"{'OK' if abs(got-expected) < 1e-3 else 'WRONG'}", flush=True)
# a few more to measure steady-state
t0 = time.time()
for _ in range(10):
    dist.all_reduce(x)
torch.cuda.synchronize()
print(f"[rank {rank}] 10x all_reduce (4MB) avg {(time.time()-t0)/10*1000:.1f} ms", flush=True)
dist.barrier()
print(f"[rank {rank}] BARRIER passed -- SMOKE OK", flush=True)
dist.destroy_process_group()
