# ALMA-OS T-Deck — Design Overview
### A from-scratch, ALMAWARE-pure, Hebrew-native, AI-native handheld mesh — better than Meshtastic

*Synthesis of a 5-agent design swarm (2026-07-06). Full detail in the sibling docs 01–05. Built ON the existing `alma-os-tdeck` v0.1 base, not from zero.*

## What it is
A LilyGO T-Deck (ESP32-S3 + SX1262 LoRa + screen + keyboard + mic/speaker) running **our own OS**: Hebrew-native UI, a from-scratch LoRa mesh (**ALMA-Mesh**) designed to scale to ~128k nodes, voice-over-LoRa, and an on-device personal assistant (**עלמא**) that falls back to the wider ALMA/Eran network. 100% ours, offline-first, owner-gated.

## The five layers

| # | Layer | What we designed | Honest verdict |
|---|---|---|---|
| 01 | **Mesh protocol** | Hierarchical leaf(≤40)→gateway→backbone→region; 32-bit hierarchical address; reactive+proactive+geographic routing; DTN store-and-forward; X25519 + ChaCha20-Poly1305 E2E, Ed25519 anti-Sybil certs | **128k by construction (40×40×80)** — architected on paper, not field-tested. Flooding dies past ~200. |
| 02 | **RF / PHY** | SF7–SF12 data-rate table; FDM (3–4 ch) + FHSS-lite + TDMA-lite + SF-orthogonality; **micro-CFO concurrent decoding at gateways** (Iddo's idea) | Real multiplexing = **scheduling, not magic**. True multi-freq needs a 2nd radio. Micro-CFO is a gateway superpower (~2–8×). |
| 03 | **Voice over LoRa** | Codec2 700–1200 bps pipeline; store-and-forward voice notes; PTT walkie-talkie mode | **Voice messages: YES.** PTT: ~3 s/hop latency, usable for "over". **Live conversation: NO** (half-duplex physics). |
| 04 | **Firmware / OS + Hebrew** | Arduino-ESP32/FreeRTOS 5-task split; RTL bidi renderer on ST7789; lightweight card-UI (not LVGL, purity); SD flat-binary storage; power mgmt; `firmware/` scaffold | Solid, buildable path on the existing v0.1 base. |
| 05 | **Assistant (עלמא)** | 3-tier ladder: on-device intent-classifier → mesh-relay to a strong ALMA/Eran node → offline queue; Hebrew commands; SOS hardcoded above ML | On-device = intents+templates only (honest — no big LLM on ESP32-S3). Real intelligence comes via the mesh relay. |

## 🔴 Critical must-fix before ANY field test
The existing `src/board_tdeck.h` **hardcodes 868 MHz @ 17 dBm** — EU-only, and **not legal in Israel** (caps: 10 dBm@433 MHz, 14 dBm@917–920 MHz). Must become **region-gated presets** (default Israel-legal) + a EULA/antenna-declaration gate before family use. This is the #1 next action.

## How it beats Meshtastic
- **Hebrew-native** RTL UI + Hebrew assistant (Meshtastic has neither).
- **E2E encryption by default** per-pair (Meshtastic defaults to a shared channel key).
- **Hierarchical scale** to ~128k (Meshtastic's flood mesh caps ~80–200).
- **Voice messages** over LoRa (Meshtastic is text-only).
- **On-device + mesh-relayed assistant.**
- **100% ALMAWARE-pure**, owner-gated, offline-first.

## Build roadmap (honest, phased)
1. **Legal fix** — region-gated freq/power presets + EULA gate. *(small, do first)*
2. **Mesh v0.2** — implement hierarchical addressing + gateway join + intra-cluster routing on the existing `mesh.h`; test 3–10 nodes.
3. **Voice notes** — Codec2 1200bps store-and-forward (reuses mesh chunking).
4. **Assistant tier-1** — tiny Hebrew intent classifier + template replies; tier-2 relay to a home ALMA/Eran node.
5. **Gateway prototype** — SDR-class gateway with micro-CFO concurrent decoding; measure real cluster capacity.
6. **Field pilot** — family cluster, honest range/latency/uptime numbers (ALMA standard: works >1hr, real-not-demo).

## Files
`design/01-mesh-protocol.md` · `02-rf-phy.md` · `02b-micro-cfo-addendum.md` · `03-voice-lora.md` · `04-firmware-os.md` · `05-assistant.md` · `firmware/` scaffold.
