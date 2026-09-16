# AI Fleet Idle Worker Queue

**Run:** 2026-08-18T07:49:39+03:00 (Asia/Jerusalem)  
**Mode:** Read-first; no dispatch, resource start/stop, or policy/network change.

## Dispatch state: BLOCKED

No safe, pre-authorized task packet attributes bounded work to the active local `coordinator.py` and `worker.py` processes. RAMLINK currently has open work items, but none supplies all dispatch controls below.

## Exact missing task packet

1. Project/repository path and bounded deliverable.
2. Named worker or endpoint, allowed runtime/model, and resource/time cap.
3. Input and expected artifact path.
4. Acceptance test, owner, and stop condition.
5. Explicit execution authorization.

## Endpoint eligibility

| Endpoint | Fresh evidence | Eligibility |
|---|---|---|
| Ollama `127.0.0.1:11434` | Listener PID 9352 and version `0.32.5`; `/api/tags` timed out after 8 s; fresh nonce generation did not complete within 30 s. | BLOCKED |
| `127.0.0.1:7800` | No listener; health/model probes refused. | BLOCKED |
| `127.0.0.1:7801` | No listener; health/model probes refused. | BLOCKED |

## Watchdog / workers

- `dgx_watchdog_status.json` says 4/4 only as of `2026-08-05T05:26:52Z`; historical, not current DGX acceptance.
- Active `coordinator.py` PID 5552 and `worker.py` PID 16420 are unattributed, with no observed lease, task packet, or output evidence.
