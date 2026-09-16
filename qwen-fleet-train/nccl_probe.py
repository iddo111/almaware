#!/usr/bin/env python3
"""Pinpoint which collective+size hangs on the 3-node routed topology.
Tests all_reduce, all_gather_into_tensor, reduce_scatter_tensor at escalating
sizes, printing after EACH so the last printed line = the one that hung."""
import os, time, torch, torch.distributed as dist

rank = int(os.environ["RANK"]); world = int(os.environ["WORLD_SIZE"])
dist.init_process_group("nccl"); torch.cuda.set_device(0)
print(f"[rank {rank}] init OK world={world}", flush=True)

def bench(name, fn, mb):
    torch.cuda.synchronize(); t0 = time.time()
    fn(); torch.cuda.synchronize()
    if rank == 0:
        print(f"  {name:22s} {mb:6d}MB  {(time.time()-t0)*1000:8.0f} ms", flush=True)

for mb in [4, 64, 256, 1024, 2048]:
    n = mb * 1024 * 1024 // 4
    # all_reduce
    x = torch.ones(n, device="cuda")
    bench("all_reduce", lambda: dist.all_reduce(x), mb)
    del x; torch.cuda.empty_cache()
    # all_gather_into_tensor  (ZeRO-3 param gather)
    shard = torch.ones(n, device="cuda")
    out = torch.empty(n * world, device="cuda")
    bench("all_gather_into", lambda: dist.all_gather_into_tensor(out, shard), mb)
    del shard, out; torch.cuda.empty_cache()
    # reduce_scatter_tensor  (ZeRO-3 grad reduce)
    inp = torch.ones(n * world, device="cuda")
    rout = torch.empty(n, device="cuda")
    bench("reduce_scatter", lambda: dist.reduce_scatter_tensor(rout, inp), mb)
    del inp, rout; torch.cuda.empty_cache()
    if rank == 0:
        print(f"  --- {mb}MB tier PASSED ---", flush=True)

dist.barrier()
print(f"[rank {rank}] ALL COLLECTIVES x ALL SIZES OK", flush=True)
dist.destroy_process_group()
