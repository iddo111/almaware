# AI Fleet No-Idle Supervisor — 2026-07-28 12:38 IDT

## Status

- **ACTIVE (local control plane):** Ollama service process is running (PID 12752); local coordination/worker processes are also present. Process presence and cumulative CPU do not prove a current assigned workload.
- **VERIFIED (authorized local model endpoint):** `http://127.0.0.1:11434` returned HTTP 200 from `/api/version` (`0.32.5`) and `/api/tags`; `qwen3:4b-instruct` returned the non-empty deterministic smoke response `fleet-smoke-ok` from `/api/generate`.
- **UNVERIFIED / UNAVAILABLE:** authorized local DGX tunnel `127.0.0.1:7801` refused `/health` and `/v1/models`; local Alma harness `127.0.0.1:8095` also refused both checks. Neither endpoint was eligible for a generation test.
- **STALE WATCHDOG:** `dgx_watchdog_status.json` was last updated 2026-07-21 15:14:43 UTC and reported 3/4 reachable, with dgx3 (<fabric-ip> through dgx1) timing out. It is not current acceptance evidence.

## Idle-worker task queue

1. **BLOCKED — assign a pre-authorized local task:** no current task manifest, project owner, input, output location, or acceptance criterion maps to the idle/low-utilization local workers. No work was invented or started.
2. **NEXT — restore/verify DGX endpoint only when authorized:** provide the intended local tunnel/harness owner and a safe restart or repair authorization; then require health, model listing, and a real non-empty generation.
3. **NEXT — refresh fleet reachability:** an authorized operator may rerun the watchdog after validating the configured `dispatch_nodes.json` identities, especially dgx3's fabric route.

No services, network/firewall policy, cloud resources, packages, or external accounts were changed.
