# Addendum to 02-rf-phy — Micro Frequency Offsets (CFO) as a Capacity Multiplier

*Iddo's idea ("micro changes to freq"), folded into the RF layer. This is a real, researched technique — not the same as sub-channelizing within a band.*

## The idea
Deliberately assign each node a **tiny, distinct carrier-frequency offset (CFO)** — micro-Hz to low-kHz — so that when several nodes transmit **at the same time on the same nominal channel**, a capable gateway can **separate and decode the colliding transmissions in parallel** by their differing CFOs (and timing offsets). Collisions become concurrent channels.

## Why it's physically real
- SX1262 tunes with **FSTEP ≈ 0.9537 Hz** resolution (32 MHz / 2²⁵) — micro-offset assignment is trivially within reach.
- LoRa's chirp-spread-spectrum (CSS) means concurrent signals with distinct CFO/time offsets leave separable traces in the de-chirped spectrum. Published systems exploit exactly this: **Choir** (per-node CFO fingerprints), **FTrack**, **NScale**, **mLoRa** — decoding many colliding LoRa frames at one receiver.

## Where it fits ALMA-Mesh
- This is a **gateway superpower**, not a node feature. Cheap SX1262 **leaf nodes** keep transmitting normally; the **cluster gateway** (the "smart ear") uses oversampling + DSP to swallow many simultaneous leaf transmissions.
- Directly boosts the **intra-cluster concurrency** that the hierarchical 128k design (see `01-mesh-protocol.md`) depends on — more nodes per cluster before airtime saturates.

## Honest caveats
- **Separation happens at the gateway**, needing oversampling / SDR-class front-end + DSP. A plain SX1262-to-SX1262 link cannot do this — it is not independent point-to-point micro-channels.
- **CFO drift**: cheap crystals drift with temperature; the gateway must **track** each node's offset, not assume it's fixed. TCXO on gateways helps.
- Assigned micro-offsets must stay **within the occupied channel bandwidth** and within the legal channel — this does not create new spectrum, it disentangles shared spectrum.
- Gain is real but bounded (papers show ~2–8× concurrency, not unlimited).

**Verdict:** a genuine, frontier-grade capacity multiplier for the cluster gateways — worth prototyping on an SDR gateway, keep leaf nodes dumb and cheap.
