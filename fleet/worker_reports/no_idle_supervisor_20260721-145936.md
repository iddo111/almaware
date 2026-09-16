# AI Fleet No-Idle Supervisor — 2026-07-21 14:59 IDT

Mode: read-first; no resources started, stopped, or reconfigured.

## Fresh evidence

- `dgx_watchdog_status.json` was refreshed at 14:58 IDT: 3/4 nodes reachable.
- `dgx1` (eran1), `dgx2`, and `dgx4` report 0% GPU utilization (44/39/43 C), so they appear idle from the watchdog snapshot.
- `dgx3` is unverified: SSH through dgx1 to `<fabric-ip>:22` timed out.
- No local active relevant worker/model processes were found.
- No listener was present on loopback ports 11434, 7800, 7801, 8080, 8081, or 8084. GET checks for local health/model routes were refused; therefore no configured endpoint is generation-verified.

## Local task queue

Status: blocked; do not dispatch.

Exact missing authorization: one bounded, read-only review task naming the target project files and the intended verified local worker/model. Before any later dispatch, reconcile the stale worker addresses in `project_workers.py` with `dispatch_nodes.json`, then require health, model listing, and an actual generation from the selected endpoint.
