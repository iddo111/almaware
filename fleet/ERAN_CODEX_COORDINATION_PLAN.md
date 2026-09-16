# Eran Codex Coordination — Guarded Plan

## Fresh inventory — 2026-07-27 13:00 IDT

| Node | Configured access result | Codex evidence | Status |
|---|---|---|---|
| Local Windows | Local Codex CLI is present | `codex.exe` available locally | ACTIVE |
| Eran1 / `<lan-ip>` | SSH accepted | Process PID 32990, user `eran1`, binary `~/.codex/.../0.145.0-aarch64.../codex`, cwd `/home/eran1` | ACTIVE, session purpose UNKNOWN |
| Eran2 / `<lan-ip>` | SSH accepted | No `codex` command/process found | ABSENT |
| Eran3 / `<fabric-ip>` | SSH timed out | Cannot inspect | BLOCKED — configured-address failure |
| Eran4 / `<tailnet-host>` | SSH accepted | Process PID 51884, user `eran4`, binary `~/.codex/.../0.145.0-aarch64.../codex`, cwd `/home/eran4` | ACTIVE, session purpose UNKNOWN |

Fresh Tailscale control-plane state reports the known DGX peers online. This is carrier evidence only; it is not acceptance of an agent, RAMCHAT, model endpoint, or shared-memory service.

## Coordination design: bounded, not always-on chatter

The safe first architecture is a versioned **coordination ledger** plus bounded work packets—not agents continuously talking, sharing private context, or auto-starting work.

```text
approved project packet -> shared Git/worktree artifact -> task lease -> evidence artifact -> human review
                                      ^                    |
                         RAMCHAT/MQTT adapter (later) <----+
```

## Required approval gates before implementation

1. **Identity and ownership:** approved account/key per node, including whether Eran2 may receive Codex and how Eran3 address drift is resolved.
2. **Shared state:** named repository/path, permitted data classes, retention policy, conflict handling, and secret-exclusion rule.
3. **Messaging:** one primary channel only (RAMCHAT *or* MQTT *or* Slack), authenticated identities, ACLs, topic/schema, audit trail, rate limits, and kill switch. Do not bridge every channel by default.
4. **Agent policy:** allowed commands, per-task workspace, budget/time limits, model source, human approval points, and prohibited actions.
5. **Cloud:** named provider/account/project, spending ceiling, region, credentials owner, workloads, shutdown policy, and data boundary. No cloud worker or ant-farm is authorized until these are explicitly approved.

## Sequenced next work

1. Preserve and identify the existing Eran1/Eran4 Codex sessions without interrupting them.
2. Define the coordination ledger and one read-only task-packet schema.
3. Validate one selected local channel end-to-end with a synthetic non-secret message and audit record.
4. Only then decide on Eran2 installation and Eran3 remediation.
5. Treat cloud workers as a separate controlled deployment after local acceptance.

## Hard boundaries

- No credentials copied into shared memory, RAMCHAT, MQTT, Slack, Git, or prompts.
- No automatic remote command execution, agent spawning, package install, firewall change, cloud provisioning, or continuous messaging.
- Existing model services and Codex sessions are not stopped or restarted by this plan.
