# AI Fleet No-Idle Supervisor — 2026-07-22 15:02 IDT

## VERIFIED

- Read-only sweep completed. No services were started, stopped, changed, authenticated, or contacted externally.
- `dgx_watchdog_status.json` is stale: written 2026-07-21 18:14:43 IDT. Its last snapshot reports 3/4 reachable: `dgx1`, `dgx2`, and `dgx4` at 0% GPU; `dgx3` timed out via `<fabric-ip>`.
- Active local processes relevant to fleet work: `coordinator.py` (PID 7996) and `D:\CLAUDE\dgx4-dual-model-harness\alma_harness.py` (PID 35856). Their active task/model state is not established by process presence alone.
- No listener exists on authorized local ports 11434, 7800, 7801, 8080, 8081, or 8084.
- Explicit loopback model-listing probes to 11434, 7800, 7801, 8081, and 8084 were actively refused. Therefore no model listing or real generation is verified, and no generation was attempted.

## ACTIVE / IDLE ASSESSMENT

- Fleet worker availability is **UNVERIFIED**. The old watchdog indicates formerly reachable but idle GPUs; it is not current enough to dispatch against.
- `project_workers.py` remains non-dispatchable: it hard-codes `eran1@<lan-ip>` / `eran4@<lan-ip>`, conflicting with canonical `dispatch_nodes.json` addresses.

## LOCAL TASK QUEUE

| Status | Task | Acceptance gate |
|---|---|---|
| BLOCKED | Refresh a pre-authorized local worker endpoint | health + model listing + one real local generation |
| BLOCKED | Reconcile `project_workers.py` addresses with `dispatch_nodes.json` | source/config addresses match and a bounded review prompt is supplied |
| BLOCKED | Dispatch idle worker work | explicit bounded read-only prompt and target files |

## EXACT MISSING TASK

Provide an explicit bounded read-only review prompt with target files, plus one verified local worker/model. Do not dispatch the existing project worker until its endpoint addresses are reconciled with the canonical configuration.
