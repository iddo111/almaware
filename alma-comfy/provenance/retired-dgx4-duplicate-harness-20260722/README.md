# Retired DGX4 duplicate assistant harness

Fresh evidence before removal on 2026-07-22:

- `/home/eran4/alma-harness` was 5.6 MiB.
- `alma-harness.service` was disabled but still active as PID-backed Python on
  `127.0.0.1:8095`.
- It routed four conflicting backends: local GPT-OSS, remote Nemotron, remote
  Grok-1, and local Gemma 4.
- Tailscale Serve exposed it at HTTPS 8446. A second stale 8445 mapping targeted
  absent port 8094.

This door contradicted the accepted topology. The service, source directory,
and both stale Serve mappings were removed. The canonical workstation gateway
at `http://127.0.0.1:8095` was not changed.
