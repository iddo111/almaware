# ALMA-MESH — Protocol & Scaling: from 200 nodes to 120,000+

לזכרה של עלמה ז"ל · ALMAWARE — 100% from-scratch, zero vendor code (no Meshtastic,
no RadioLib). Builds on the working v0 in `src/mesh.h` (16 B header, single-hop,
dedupe cache) and the radio in `src/radio_sx1262.cpp` (868/915 MHz, SF9/125k).

## 1. Why flooding dies — the math, not the vibe

Meshtastic's "managed flood" (every node rebroadcasts once, TTL≤3, dedupe by
packet-ID) works because LoRa airtime is brutally scarce and flooding burns it
combinatorially. Using our own numbers from `03-voice-lora.md`: a 216 B frame
at SF9/125k/CR4:7 = **~1.5 s time-on-air**. The channel is half-duplex and
shared — one transmission blocks every node in radio range for its full ToA.

**Flood cost model.** In a flood, one message from one origin causes
(N_in_range − 1) rebroadcasts per hop, up to TTL hops. Total airtime consumed
network-wide for a single message:

```
airtime_total ≈ ToA × Σ(hop=1..TTL) [avg_neighbors_reached_at_hop]
```

For a dense mesh (avg 8 neighbors/node, TTL=3): one message → ~8+64+512 ≈ 584
rebroadcast events in the worst case before dedupe saturates local caches — and
dedupe only stops a node hearing the *same* packet-ID twice, it does not stop
the *first* rebroadcast from every node that heard it. Real deployments settle
lower (dedupe + collisions cap it), but Meshtastic's own field data and forum
consensus put practical ceilings at:

| Nodes | Flood behavior |
|---|---|
| ≤80 | Fine — channel utilization <10%, ACKs land, low collision rate |
| 80–200 | Degraded — perceptible latency (10s of seconds), rising duplicate/collision rate |
| >200 | Congestion collapse — channel utilization saturates, retries flood the retries, effective throughput can go *negative* (more collisions than delivered packets) |

**Root causes, concretely:**
1. **Airtime is O(1.5 s/frame)**, not milliseconds — a flood at even 300 nodes
   sending one message/minute each = 300 msg/min × up to N-hop rebroadcasts,
   already exceeding 1 channel-second-per-second budget.
2. **No frequency reuse in a flood** — every node uses the same channel, so
   there's no spatial multiplexing; growing the mesh geographically doesn't
   help because a flood is *designed* to reach everyone, defeating locality.
3. **Duty-cycle law (EU868-style, and our own conservatism)** — if we honor a
   1% duty cycle, each node gets ~36 s of *transmit* budget per hour, shared
   across its own traffic *and* every rebroadcast it performs for others. Flood
   rebroadcast obligations eat first, starving the node's own messages.
4. **ACK storms** — naive per-hop ACK in a broadcast medium means N nodes all
   try to ACK the same packet, colliding with each other.
5. **Collision math**: LoRa has no CSMA in the 802.11 sense (no clear-channel
   assessment that reliably prevents overlap across all SF/CR combos in the
   same slot), so overlapping transmissions from hidden nodes are simply lost —
   collision probability grows as O(n²) pairs of simultaneous transmitters.

**Conclusion**: flooding is O(N) or worse in per-message network cost; it must
be replaced by something O(log N) or O(1) local for the network to hit 120k+.

## 2. Architecture: hierarchical clusters + backbone, not flat flood

```
                         ┌─────────────────────────┐
                         │   REGION 0x02 (backbone) │
                         │  gateway mesh, LoRa+other │
                         └────────────┬─────────────┘
                    ┌──────────────────┼──────────────────┐
             ┌──────┴──────┐    ┌──────┴──────┐    ┌──────┴──────┐
             │ CLUSTER 0x02.11 │ │ CLUSTER 0x02.12 │ │ CLUSTER 0x02.13 │
             │  gateway node   │ │  gateway node   │ │  gateway node   │
             └──────┬──────┘    └──────┬──────┘    └──────┬──────┘
          ┌──────────┼──────────┐      │
     ┌────┴───┐  ┌────┴───┐ ┌────┴───┐  ...
     │ leaf   │  │ leaf   │ │ leaf   │   (≤ ~40 leaves per cluster,
     │ node A │  │ node B │ │ node C │    single-hop or 2-hop to gateway)
     └────────┘  └────────┘ └────────┘
```

- **Leaf tier**: ordinary handhelds/sensors, ≤40 per cluster, 1–2 hops to their
  cluster's gateway. Flooding is *allowed* but scoped: TTL≤2, only inside the
  cluster. This keeps the "flood works fine" regime (§1: ≤80 nodes) true by
  construction — a cluster never grows past the size where flooding is safe.
- **Gateway tier**: one elected/fixed node per cluster (better antenna, mains
  or solar power — matches the rooftop relay design in `LORA_RF_DEEP_GUIDE`).
  Aggregates cluster traffic, deduplicates, and forwards *summaries* upward —
  not every leaf packet, see §4 store-and-forward.
- **Backbone tier**: gateways talk to each other over a **separate channel/
  frequency plan** (different SF or sub-band, or a non-LoRa backhaul — WiFi
  mesh, cellular, or a second LoRa radio on 433 MHz while leaves use 915 MHz)
  so backbone traffic never contends with leaf-cluster airtime. This is the
  single biggest scaling lever: **the backbone is not flooded, it's routed.**
- **Regional tier**: backbone segments group into regions for address
  aggregation (§3) and for bounding routing-table size (§5).

Capacity arithmetic: 40 leaves/cluster × 40 clusters/region × 80 regions =
**128,000 nodes** — comfortably over the 120k target — with every leaf-tier
flood domain kept at ≤40 nodes, deep inside the safe flooding regime.

## 3. Addressing — hierarchical, geography-friendly

24-bit flat IDs (efuse MAC truncation, as in v0) don't scale to routing at
120k nodes — there's no structure to route on. New scheme, **backward
compatible in spirit** (still fits in the existing 4-byte src/dst fields):

```
 Address (32 bits):
 ┌────────────┬────────────┬────────────┬────────────┐
 │ region (8b)│cluster(10b)│  leaf (12b) │  reserved  │
 │  0–255     │  0–1023    │   0–4095    │  (2b flags)│
 └────────────┴────────────┴────────────┴────────────┘
     0x02          0x011         0x1A3

 Human/text form:  0x02.011.1A3   (dotted like an IP, for logs/UI)
```

- **region**: assigned at deployment (e.g. one per city/country cell) — 256
  regions × 1024 clusters × 4096 leaves = 1.07 billion address space, we use
  ~128k of it. Room to grow 10,000x without a redesign.
- **cluster 0**: reserved for "unassigned / new node broadcasting for a
  gateway" (bootstrap state, see §7).
- **leaf 0xFFF within a cluster**: cluster-local broadcast (replaces the old
  flat 0xFFFFFFFF broadcast, now scoped).
- **Gateways** get a well-known leaf number (e.g. `.000`) inside their own
  cluster, so "route toward my gateway" = "route toward `region.cluster.000`" —
  no separate discovery needed once cluster ID is known.
- Address is assigned by the **cluster's gateway** at join time (like DHCP but
  offline-capable — gateway keeps a simple bitmap of the 4096 leaf slots) and
  persisted in flash so the same handheld doesn't renumber every boot.

## 4. Routing — reactive locally, proactive on the backbone, geographic as fallback

Three regimes, matched to each tier's traffic pattern and hardware:

- **Leaf → gateway (intra-cluster)**: **reactive** (AODV-flavored, our own,
  not IETF RFC text reused verbatim — just the same well-proven idea: no
  routes are held until needed). A leaf that doesn't already know a 1-hop
  path to its gateway sends a scoped Route-Request (TTL≤2); the gateway or
  a relaying leaf answers with a Route-Reply. Cheap because clusters are
  small (§1's safe-flood regime) — the "discovery flood" is bounded to ≤40
  nodes, nothing like a network-wide flood.
- **Gateway ↔ gateway (backbone)**: **proactive distance-vector**, refreshed
  on a slow heartbeat (minutes, not seconds — backbone nodes are mains/solar
  powered, not battery-anxious). Each gateway keeps a table of
  `{region.cluster → next-hop gateway, hop-count, last-seen}`, gossiped
  between neighboring gateways only (not flooded network-wide) — classic
  distance-vector with split-horizon to avoid count-to-infinity. At ~40
  clusters/region this table is trivially small (≤1024 rows region-wide,
  <10 KB), fits in the T-Deck's PSRAM or a Pi-class gateway easily.
- **Cross-region / long haul**: **geographic (gradient) routing** as the
  fallback when the backbone link is thin or the destination region is
  unknown to the proactive table — packets carry a coarse lat/lon or
  region-vector "gradient" hint and each backbone hop forwards toward
  whichever neighbor gateway reports being closer (via periodic beacon that
  includes GPS or manually-configured fixed coordinates for rooftop relays).
  This degrades gracefully (progress-not-guaranteed, but no routing-table
  explosion) exactly where Meshtastic has nothing at all today.

This is the honest core of "why this beats Meshtastic at scale": Meshtastic
has **one** regime (flood, everywhere, always) which is fine at 80 nodes and
collapses at 300. We have **three** regimes, each sized to the traffic
locality that actually exists at that tier.

## 5. Store-and-forward / DTN — because rural LoRa is a disruption-tolerant network, not a LAN

A gateway may be offline (solar node at night, relay walked out of range).
Borrowing the right *idea* from Delay-Tolerant Networking (Bundle Protocol
concepts, not the IETF bytes) without adopting its full stack:

- Every message is a **bundle**: payload + TTL-in-seconds (not just hop-count)
  + a `custody` flag.
- A gateway that accepts custody of a bundle for a not-currently-reachable
  destination **stores it** (SD card / flash — T-Deck already has microSD;
  gateways are Pi-class with real storage) and retries on a backoff schedule
  when its neighbor-table shows the path is live again.
- This turns "gateway is asleep" from a dropped-message failure into a
  bounded-latency delay — critical for solar/intermittent nodes at 120k scale,
  where *some* fraction of gateways are always transiently down.
- Custody transfer is single-hop and acked (§6) so bundles don't get
  duplicated across multiple standby custodians.

## 6. Channel/airtime management, congestion control, fairness, dedup, TTL, ACK

- **Frequency/SF plan**: leaves use one SF (SF9, matches v0 default) on one
  sub-band; gateways additionally use a second radio or a reserved slot at a
  different SF (SF7, shorter ToA, backbone traffic is smaller/more frequent
  control messages) so leaf and backbone airtime don't compete.
- **Duty-cycle budget enforced in firmware**, not just assumed: each node
  tracks its own rolling 1-hour TX-seconds and refuses to transmit
  non-critical traffic past a configurable cap (default matches whatever the
  regulatory doc for the deployment region says — see
  `LORA_ISRAEL_RESEARCH_2026-04-29.md` for the IL numbers already researched).
  Rebroadcast-for-others is budgeted *separately and capped lower* than a
  node's own traffic, so a busy cluster can't starve a leaf's own messages
  (direct fix for the flood-ACK-storm failure mode in §1).
- **CSMA-with-backoff, our own**: before any TX, listen (CAD — Channel
  Activity Detection, an SX1262 hardware feature) for a random backoff window
  scaled by estimated local node density (a node that hears many neighbors in
  its beacon window backs off more) — cheap collision avoidance without full
  slot synchronization.
- **Congestion control**: a gateway broadcasts a lightweight "cluster busy"
  flag (1 bit in the periodic beacon) when its own channel utilization
  crosses a threshold (e.g. 30%); leaves hearing it apply exponential backoff
  to non-urgent traffic — simple, no per-flow state, scales to any cluster
  size because it's a broadcast bit, not per-node signaling.
- **Dedup**: v0's (src, msgid) cache generalizes to (full 32-bit address,
  msgid, **originator-timestamp**) with a bloom-filter-style cache (not a
  linear array) once cluster sizes exceed the ~16-slot v0 cache — O(1) memory
  regardless of cluster size, false-positive rate tunable.
- **TTL**: dual TTL — hop-count TTL (small integer, prevents routing loops,
  matches v0's existing `ttl` byte) **and** wall-clock TTL in the DTN bundle
  header (§5) for store-and-forward expiry. Hop TTL defaults: 2 intra-cluster,
  8 cross-backbone (regions are ≤3–4 gateway-hops apart by design).
- **ACK strategy**: unicast-only ACKs (never ACK a broadcast — this is exactly
  Meshtastic's/naive-flood's ACK-storm bug). Cluster-local hop-by-hop ACK for
  leaf→gateway reliability; backbone uses end-to-end ACK only (per-hop ACKing
  8 backbone hops would multiply airtime for no benefit since backbone links
  are provisioned to be reliable/mains-powered).

## 7. Security — our own primitives, named honestly

ALMAWARE purity = we write the protocol, but we do **not** roll our own crypto
primitives — X25519 and AES-GCM/ChaCha20-Poly1305 are public, audited,
patent-free algorithms (not "vendor code" in the sense the purity law
targets — the law is about not depending on Meshtastic/RadioLib-style
*frameworks*; using a standard, public-domain cipher construction the way
everyone from Signal to WireGuard does is the responsible engineering choice,
not a purity violation — this is called out explicitly so it isn't re-litigated
by a future agent).

- **Identity**: every node generates an X25519 keypair at first boot (hardware
  RNG on the ESP32-S3), stored in flash. The public key, **not the 32-bit
  mesh address**, is the durable identity — addresses are reassigned by
  gateways (§3) and can collide across regions if misconfigured; the pubkey
  cannot.
- **Key distribution**: cluster gateways run a lightweight local CA — when a
  leaf joins (§3 bootstrap), it exchanges pubkeys with its gateway over a
  short-range, low-power "pairing" exchange (ideally requiring a physical
  action — QR code scan or button press — to prevent silent remote pairing).
  The gateway signs the leaf's pubkey + assigned address into a small
  certificate (Ed25519 signature, same key family) that other nodes can
  verify without contacting the gateway again.
- **End-to-end encryption**: X25519 ECDH between sender and recipient pubkeys
  → derived symmetric key → ChaCha20-Poly1305 AEAD over the payload. Routing
  headers (addresses, TTL, msgid) stay in the clear (routers need them);
  payload is opaque to every relay, including gateways — gateways route
  ciphertext, they don't decrypt it. This is a real improvement over
  Meshtastic's default (which historically shipped a shared-network-key AES
  mode where any node on the channel can decrypt any message — fine for a
  campsite, not for 120k strangers).
- **Group/broadcast messages**: symmetric per-cluster channel key (like
  Meshtastic's model) for the *cluster-broadcast* traffic class only (public
  announcements), while direct/unicast messages always use the pairwise
  E2E scheme above — so "私 messages are E2E, public channel chat is
  shared-key" is an explicit, documented split, not an accident.
- **Sybil/spam resistance at 120k scale**: address assignment is gated by the
  gateway's signed certificate (§ above) — an attacker can't mint unlimited
  addresses without a gateway signing them, and a gateway can rate-limit new
  joins (physical pairing requirement makes mass-Sybil expensive: you need
  physical proximity to a gateway per fake identity). Per-node rate limiting
  (msgs/hour) enforced by neighbors who see repeated traffic from one pubkey
  well past the announced duty-cycle budget (§6) — a misbehaving/compromised
  node's neighbors can locally downrank/ignore it (soft reputation, no global
  consensus needed, no blockchain silliness).
- **Replay protection**: msgid is a monotonic per-sender counter (already in
  v0's header) bound into the AEAD associated-data, so a replayed ciphertext
  fails the nonce/counter check at the recipient.

## 8. Packet/frame sketch (v0.2, extends `mesh.h` — not a breaking rewrite)

```
Byte:  0   1   2    3     4-7      8-11     12-13   14   15   16..
     ['A']['M'][ver][type][ src:32 ][ dst:32 ][msgid:16][ttl][len][ payload ]
       magic     |     hierarchical addr (region.cluster.leaf packed 8/10/12+2)
                 |
                 └─ v0.2 adds type values:
                      4 = ROUTE_REQ   5 = ROUTE_REPLY   6 = GW_BEACON
                      7 = DV_GOSSIP   8 = BUNDLE (DTN, adds wall-clock TTL +
                                                   custody flag in payload[0])
                      9 = JOIN_REQ    10 = JOIN_CERT (gateway-signed pairing)

Payload for type=MSG when encrypted (v0.2):
  [0]      key-epoch / cluster-key-id (for group messages) OR 0xFF = E2E unicast
  [1..32]  sender X25519 ephemeral pubkey (E2E case only; omitted for group)
  [..]     ChaCha20-Poly1305 ciphertext + 16 B auth tag
```

Header stays 16 bytes — **v0 firmware and v0.2 firmware agree on the header
layout**, only the address bit-packing inside src/dst and the new `type`
values are new, so existing v0 single-hop MSG/ACK/BEACON traffic keeps
working unmodified during a mixed-firmware rollout.

## 9. What's genuinely novel vs. hard vs. still honest-limits

**Novel / real improvement over Meshtastic:**
- Bounded flood domains by construction (cluster ≤40) instead of "flood
  everywhere and hope collapse doesn't happen" — this is the actual scaling
  answer, not a bigger radio or cleverer dedupe.
- Per-pair E2E encryption as the default for unicast (Meshtastic's default
  channel-key model is weaker at large-N).
- Explicit three-regime routing (reactive/proactive/geographic) matched to
  where each traffic pattern actually lives, vs. one mechanism for everything.

**Hard, and honestly still hard:**
- **Gateway placement/election** is a real logistics problem, not just a
  protocol one — 3,200 gateways (128k/40) need physical siting, power, and
  antennas; the protocol assumes they exist, it doesn't make them appear.
- **Distance-vector count-to-infinity and route flap** at region scale need
  real tuning (split-horizon helps, doesn't eliminate every pathological
  topology) — this needs simulation before field trust, not just this doc.
- **Clock sync for wall-clock DTN TTL** across nodes with no GPS and no
  network time is an open detail — likely solved with "relative TTL since
  last-seen-fresh gateway beacon" rather than true wall-clock, needs a v0.3
  design pass.
- **120k nodes has never been field-tested by us** — this document is a
  from-scratch architecture that scales *on paper* by construction (bounded
  flood domains + hierarchical routing tables), not a claim that we've run it.
  The honest path is: ship v0.2 (single cluster, ≤40 nodes, E2E crypto,
  reactive routing) first, prove it, then add the backbone tier for
  multi-cluster, then prove *that*, before ever claiming six-figure capacity
  in the field.

## 10. Interop note

We do not implement Meshtastic's wire protocol. A T-Deck on ALMA-MESH cannot
talk to a T-Deck on stock Meshtastic firmware — same honest limit v0 already
states. What we *do* take from Meshtastic is the lesson embedded in its scaling
ceiling: flat managed-flood is the wrong shape past ~200 nodes, and no amount
of dedupe/backoff tuning fixes a design that has only one routing regime. We
learn that lesson and write our own protocol, per the ALMAWARE purity law.
