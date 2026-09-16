> BROKEN WINDOWS LAW — if it's not working, fix it IMMEDIATELY.

# QSFP FABRIC MAP — Eran mesh recon (2026-07-11)

Verified with `sudo ethtool <iface>` (real link speed + carrier) and `sudo lldpctl <iface>` (peer chassis/port MAC) across eran1, eran2, eran3. All four historical claims held; two extra physical cables were discovered.

## Node identities

| Node  | Hostname          | Chassis MAC          | Role                                                    |
|-------|-------------------|----------------------|---------------------------------------------------------|
| eran1 | eran1             | fc:9d:05:13:02:49    | compute + LAN gateway (enP7s7 -> <lan-ip>/24)     |
| eran2 | edgexpert-041d    | fc:9d:05:13:04:1d    | MESH HUB — all cross-node QSFP paths transit here      |
| eran3 | edgexpert-01e6    | fc:9d:05:13:01:e6    | compute + eran4 uplink (enP7s7 -> <fabric-ip>/24)         |
| eran4 | edgexpert-3636    | fc:9d:05:13:36:36    | leaf, single-homed via eran3 enP7s7                    |

## Physical edges (5 total)

```
                          200G QSFP (<fabric-ip>/30)     200G QSFP (<fabric-ip>/24)
  eran1 ================================= eran2 ================================= eran3
        enp1s0f0np0      enp1s0f0np0            enp1s0f1np1     enp1s0f1np1
        <fabric-ip>                <fabric-ip>               <fabric-ip>         <fabric-ip>

  eran1 - - - - - - - - - - - - - - - - eran2 - - - - - - - - - - - - - - - - eran3
        enP2p1s0f0np0    enP2p1s0f0np0          enP2p1s0f1np1   enP2p1s0f1np1
        (no IP - SPARE 200G)                   (no IP - SPARE 200G)

                                                                   10G RJ45
                                                       eran3 ================= eran4
                                                       enP7s7            (<fabric-ip>)
                                                       <fabric-ip>
```

| # | From                        | To                          | Speed  | Medium   | IP? | Notes |
|---|-----------------------------|------------------------------|--------|----------|-----|-------|
| 1 | eran1 enp1s0f0np0 (<fabric-ip>/30) | eran2 enp1s0f0np0 (<fabric-ip>/30) | 200 Gb/s | QSFP DAC | yes | active routed link |
| 2 | eran1 enP2p1s0f0np0 (no IP)     | eran2 enP2p1s0f0np0 (no IP)     | 200 Gb/s | QSFP DAC | no  | SPARE — physically cabled, unused |
| 3 | eran2 enp1s0f1np1 (<fabric-ip>/24) | eran3 enp1s0f1np1 (<fabric-ip>/24) | 200 Gb/s | QSFP DAC | yes | active routed link |
| 4 | eran2 enP2p1s0f1np1 (no IP)     | eran3 enP2p1s0f1np1 (no IP)     | 200 Gb/s | QSFP DAC | no  | SPARE — physically cabled, unused |
| 5 | eran3 enP7s7 (<fabric-ip>/24)       | eran4 enP7s7 (<fabric-ip>)         | 10 Gb/s  | RJ45     | yes | only path to eran4 |

## Down ports (no cable)

- eran1 enp1s0f1np1, enP2p1s0f1np1
- eran3 enp1s0f0np0, enP2p1s0f0np0

## Historical claims — all VERIFIED

| Claim | Verdict |
|-------|---------|
| eran1 enp1s0f0np0 <fabric-ip>/30 <-> eran2 enp1s0f0np0 <fabric-ip>/30 direct QSFP | ✅ TRUE (200 Gb/s ethtool + LLDP peer MAC match) |
| eran2 enp1s0f1np1 <fabric-ip>/24 <-> eran3 enp1s0f1np1 <fabric-ip>/24 direct QSFP | ✅ TRUE (200 Gb/s ethtool + LLDP peer MAC match) |
| eran1 <-> eran3: NO direct cable, forwards via eran2 | ✅ TRUE (`ip route get`: eran1-><fabric-ip> via <fabric-ip>; eran3-><fabric-ip> via <fabric-ip>; ping 2ms via eran2) |
| eran3 enP7s7 (10 Gb RJ45) <-> eran4 (Iddo confirmed) | ✅ TRUE (10 Gb linked, ARP peer MAC fc:9d:05:13:36:36 = edgexpert-3636 = eran4) |

## Discovered beyond history

- 🆕 **eran1<->eran2 has a SECOND 200G cable** on `enP2p1s0f0np0` — linked at 200 Gb/s, LLDP confirms peer, but no IP. Silent 200G of latent capacity.
- 🆕 **eran2<->eran3 has a SECOND 200G cable** on `enP2p1s0f1np1` — linked at 200 Gb/s, LLDP confirms peer, no IP. Silent 200G of latent capacity.

Both together = 400 Gb/s available east-west if bonded (LACP) or activated as backup routes.

## Fragility flags

🟡 **eran2 = single point of failure for eran1<->eran3.** No direct QSFP between eran1 and eran3; all cross-talk transits eran2. If eran2 goes down, mesh splits into `{eran1}` and `{eran3, eran4}`. Both nodes have 2 unused QSFP ports — one DAC cable directly between eran1 and eran3 would remove this SPOF.

🟡 **eran4 = single-homed via eran3 enP7s7 (10G RJ45).** Loss of eran3 OR that one RJ45 cable takes eran4 offline. Also caps aggregate eran4 throughput at 10 Gb/s vs the 200 Gb/s mesh. Second cable from eran4 to eran2 would fix.

🟢 **Latent 400G east-west redundancy** already cabled. Zero hardware cost to activate — just needs IPs on the spare pair (or a bond) on both ends.

## Verify commands (rerun to re-check)

```bash
for h in eran1 eran2 eran3; do
  ssh $h "hostname; for i in enp1s0f0np0 enp1s0f1np1 enP2p1s0f0np0 enP2p1s0f1np1 enP7s7; do
    printf '%s: ' \$i
    sudo ethtool \$i 2>/dev/null | grep -E 'Speed|Link detected' | tr '\n' ' '
    echo
  done
  ip -4 -br addr show | grep -E 'enp|enP'"
done
```
