# Retired Nemotron container experiments

At 2026-07-22 14:50 IDT, the following stopped experimental containers were
inventoried before removal. Their shared image and model weights were retained.
The live production containers `nemotron2-ray-head`, `nemotron2-api`, and
`nemotron2-ray-worker` were excluded.

DGX1:

- `nemotron-cluster` — exited 137
- `nemotron-cluster-cudaop-20260721` — exited 0
- `nemotron-ray-head` — exited 1
- `nemotron-cluster-wrongif-20260721-3node-ifacefix` — exited 137
- `nemotron-ray-head-wrongif-20260721-3node-ifacefix` — exited 1
- `nemotron-cluster-triton-pre-rankfix` — exited 0
- `nemotron-cluster-prod` — exited 137
- `nemotron-ray-head-unpatched` — exited 1
- `nemotron-ray-head-bad-entrypoint` — exited 2
- `nemotron-cluster-single-nic` — exited 1
- `nemotron-cluster-debug` — exited 1
- `nemotron-cluster-trial-pre-rankfix` — exited 1
- `nemotron-ray-head-pre98` — exited 1

DGX2:

- `nemotron-ray-worker` — exited 137
- `nemotron-ray-worker-wrongif-20260721-3node-ifacefix` — exited 1
- `nemotron-ray-worker-unpatched` — exited 1
- `nemotron-ray-worker-pre98` — exited 1

DGX3:

- `nemotron-ray-worker` — exited 137
- `nemotron-ray-worker-wrongif-20260721-3node-ifacefix` — exited 1
- `nemotron-ray-worker-unpatched` — exited 1
- `nemotron-ray-worker-pre98` — exited 1
