# RECON 1 — FLEET (DGX 1-4)

> 🪟 **BROKEN WINDOWS LAW** — if it's not working, fix it IMMEDIATELY. Test real output, not proxies.

**Ground truth captured 2026-07-11.** All 4 nodes UP.

## Traffic-light

| Node | Reach | GPU °C / util | Load1 | Mem G | Disk / | QSFP fabric | Key procs |
|------|-------|---------------|-------|-------|--------|-------------|-----------|
| 🟢 eran1 | LAN <lan-ip> | 52 / 9% | 0.36 | 95/121 | 1.8T/3.6T 51% | enp1s0f0np0 UP <fabric-ip> (→eran2); enp1s0f1np1 DOWN | **llama-server** |
| 🟢 eran2 | LAN <lan-ip> | 54 / 0% | 0.71 | 100/121 | 796G/3.6T 23% | ALL 4 UP: <fabric-ip> + <fabric-ip> + 2 link-local — **fabric hub** | **rpc-server** |
| 🟡 eran3 | fabric ONLY (<fabric-ip> via eran1 ProxyJump; **LAN/WiFi DOWN**) | 48 / 0% | 0.77 | 68/121 | 919G/3.6T 27% | enp1s0f1np1 UP <fabric-ip>; others DOWN. Extra enP7s7 UP <fabric-ip> → eran4 | **dnsmasq + rpc-server** |
| 🟡 eran4 | via eran3 direct-link <fabric-ip> ONLY (**LAN <lan-ip> DOWN**) | **77 / 92%** | 1.01 | 5/121 | 956G/3.6T 28% | no QSFP up; enP7s7 UP <fabric-ip> (wired to eran3) | **none** (see note) |

Uptimes: eran1 ~157h (~6.5 d), eran2/3/4 ~49h (~2 d).

## Fabric topology (verified)

```
  eran1 ─── <fabric-ip>/30 ─── eran2 ─── <fabric-ip>/24 ─── eran3
                                       (hub, all 4 up)   │
                                                         │ enP7s7 wired
                                                         │ <fabric-ip>/24
                                                         │
                                                       eran4
```

- eran1 fabric link: only enp1s0f0np0 (to eran2). enp1s0f1np1 DOWN. Half of eran1's fabric NICs are cold.
- eran2 is the full fabric hub — all 4 QSFP interfaces UP.
- eran3 reaches the fabric on ONE port (enp1s0f1np1 <fabric-ip>). LAN/WiFi is dead → SSH must ProxyJump through eran1. Confirmed still fabric-only, as SSH config comment predicted.
- eran4 has NO QSFP up. It's on the fleet ONLY through the wired direct-link enP7s7 to eran3 (<fabric-ip>/24). LAN <lan-ip> timed out. eran3's dnsmasq serves this segment.

## Findings needing eyes

- 🟡 **eran4 GPU 92% at 77 °C with ZERO userspace llama-server / rpc-server / dnsmasq processes.** Something IS driving the GPU (only kernel `kworker/R-rpciod` matched grep — not a workload). Verify what's actually training/inferring on eran4 before assuming idle.
- 🟡 **eran1 has one dead QSFP port** (enp1s0f1np1 DOWN). Not blocking (link to eran2 is up), but half the fabric NICs are cold.
- 🟡 **eran3 LAN is still dead** (matches SSH config note). Only fabric reachability.
- 🟡 **eran4 LAN is still dead** (<lan-ip> timed out). Only reachable via eran3's wired link — a single point of failure.
- 🟢 llama.cpp cluster present: eran1=coordinator (llama-server), eran2/eran3=workers (rpc-server). eran4 is NOT in the rpc cluster.
- 🟢 Disks healthy on all four (23–51% used).

## Reachability recipes (working)

```bash
ssh eran1                  # LAN
ssh eran2                  # LAN
ssh eran3                  # fabric via eran1 ProxyJump (as configured)
ssh -o ProxyCommand="ssh -F ~/.ssh/eran.ssh_config -W %h:%p eran3" \
    -o StrictHostKeyChecking=accept-new eran4@<fabric-ip>   # via eran3 wired link
```

Files:
- `D:\CLAUDE\almaware-hud\recon\fleet.json` — structured
- `D:\CLAUDE\almaware-hud\recon\fleet.md` — this file
