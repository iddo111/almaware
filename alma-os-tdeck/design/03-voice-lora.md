# ALMA-MESH — Voice over LoRa: honest design & math

לזכרה של עלמה ז"ל · ALMAWARE — zero external libraries; Codec2 only (open, patent-free)

Hardware: LILYGO T-Deck — ESP32-S3, SX1262 LoRa, MAX98357A I2S speaker
(`PIN_I2S_BCK/WS/DOUT` = 7/5/6), ES7210 I2S mic ADC (`PIN_ES7210_*` = 48/21/47/14).
Radio defaults from `board_tdeck.h`: 868 MHz, **SF9 / 125 kHz / CR 4:7**, 17 dBm.
ALMA-MESH frame (`mesh.h`): 16 B header + payload ≤ 200 B → max LoRa payload 216 B.

## 1. The bandwidth reality — do the math, not the vibe

LoRa is not a data pipe; it's a very slow, very robust radio link. Time-on-air
(Semtech AN1200.13 formula) for our actual frame size at our actual radio config:

| Payload (incl. 16 B mesh header) | Time-on-Air @ SF9/125k/CR4:7 |
|---|---|
| 36 B  (small text msg) | 341 ms |
| 66 B  | 513 ms |
| 116 B | 828 ms |
| **216 B (max frame)**  | **1488 ms (~1.5 s)** |

A max-size 216 B frame takes 1.5 seconds of airtime, one-way, single hop, and
that's the *entire* channel for that time (SX1262 is half-duplex — it can't
send and receive at once, and neither can any other node within earshot;
LoRa's near–far problem and lack of CSMA in our v0 design make this worse
in a crowded mesh). Physical raw rate at this config is only **~1.16 kbps**,
and that's before any regulatory duty-cycle limit (EU868-style 1% sub-band
limits, if honored, cap *usable* channel time to 36 s/hour — this is the
"~0.3–5 kbps effective" range mesh people quote, and it is real). Bottom
line: **we are budgeting bytes like it's 1985 dial-up, not 2026 Wi-Fi.**

## 2. CODEC2 — the only honest choice, and it fits ALMAWARE purity

[Codec2](http://www.rowetel.com/codec2.html) (David Rowe, GPL/LGPL, patent-free)
is *the* open low-bitrate speech codec — already the standard for HF digital
voice (FreeDV) and ham LoRa handhelds (`sh123/esp32_loradv`, Meshtastic's
`ESP32_Codec2`). No proprietary IP, no patent royalties (unlike AMR/EVS/Opus-SILK
lineage concerns some vendors raise) — clean fit for the ALMAWARE purity law.

Quality vs bitrate (well characterized, Rowe's own MOS testing + community use):

| Mode | Bitrate | Subjective quality | Frame size we can afford |
|---|---|---|---|
| 3200 | 3200 bps | Good, close to toll quality | 0.49 s audio / 216 B frame |
| 1600 | 1600 bps | Communicable, slightly robotic | 0.98 s audio / frame |
| 1200 | 1200 bps | Understandable, noticeably synthetic | 1.31 s audio / frame |
| 700C | 700 bps  | Marginal but *words are recoverable* | 2.24 s audio / frame |

(196 B usable per frame after a 4 B voice sub-header inside the 200 B mesh
payload; bytes/sec = bitrate/8.)

### Store-and-forward voice messages: genuinely feasible

Sending N seconds of recorded speech, back-to-back frames, no other mesh
traffic competing (best case):

| Message length | 1200 bps (frames, airtime, × realtime) | 700 bps (frames, airtime, × realtime) |
|---|---|---|
| 5 s  | 4 frames, 6.0 s (1.19×) | 3 frames, 4.5 s (0.89×) |
| 10 s | 8 frames, 11.9 s (1.19×) | 5 frames, 7.4 s (0.74×) |
| 30 s | 23 frames, 34.2 s (1.14×) | 14 frames, 20.8 s (0.69×) |

**700–1200 bps Codec2 pushes a voice message over LoRa at roughly real-time
or faster** (0.7×–1.2× the clip's own length, single hop, channel free).
Compare 3200 bps: 3.1× real-time — it *falls behind* and only gets worse
with hops or contention. **This is the actual case for store-and-forward
voice notes**: record, compress at 700–1200 bps, queue as a chunked mesh
transfer, deliver over the next many seconds while the sender walks away.
Totally practical, same shape as an SMS-slow voice memo. Multi-hop obviously
multiplies airtime by hop count and adds queuing delay — fine for
async messages, a real cost for anything expecting a reply soon.

Under a strict 1%-duty-cycle regulatory ceiling (if we choose to honor
EU868-style limits even though ALMA-MESH runs a private syncword outside
LoRaWAN), one link is capped near 24 max-size frames/hour — **~30–55
seconds of deliverable Codec2 voice per hour, per link**. That is a hard
real ceiling for a chatty multi-user mesh; it is not a ceiling for
"send one 10-second voice note now and then," which is the actual use case.

## 3. Live conversation — honest assessment: hard, and here's why

SX1262 is **half-duplex**: it cannot transmit while receiving. Real
full-duplex two-way voice (like a phone call) is off the table on this
radio, full stop — not a firmware limitation, a physics-of-the-chip one.

What's realistically achievable is **push-to-talk (PTT) half-duplex,
walkie-talkie style**: press a button, speak, release, the other side's
speaker plays it back after a hop. Expected latency, one hop, single Codec2
frame per LoRa packet:

- **1200 bps**: 1.31 s of audio buffered per packet + 1.49 s time-on-air
  ≈ **~2.8 s mic-to-ear latency**, before ESP32 encode/decode compute time
  (small — Codec2 1200 encodes/decodes well under real-time on ESP32-S3;
  measured ~17 ms encode / ~15 ms decode per 40 ms frame in community
  benchmarks) and before any retry.
- **700 bps**: larger audio-per-packet (2.24 s) actually **increases**
  latency to **~3.7 s** because each packet carries more buffered speech
  before it can be sent — a real tradeoff: lower bitrate helps throughput,
  hurts latency, unless frames are shortened (more, smaller packets = more
  fixed preamble overhead each time; a genuine engineering tension, not
  free to fix).

So: **PTT walkie-talkie is the realistic middle ground** — **2.5–4 seconds
of one-way latency per hop**, "over" discipline required (can't interrupt,
no back-channel "mhm"), multi-hop adds ~1.5 s per additional hop. This is
usable for short exchanges ("copy, moving to checkpoint 2") the way real
LoRa-voice hobbyist projects (`esp32_loradv`) already demonstrate — but it
is a **radio, not a phone call**.

**Full duplex live conversation: marginal-to-no.** Even ignoring the
half-duplex hardware limit, a real conversation needs sub-300 ms round-trip
to feel natural; we are 10-15× that on a good single hop before accounting
for jitter, retries, or a second hop. Framing this as "live conversation"
would be dishonest. Framing it as "PTT radio" is accurate and still useful.

## 4. Pipeline design

```
 mic (ES7210, I2S, 8 kHz native OK) 
   -> Codec2 encode (700/1200 bps, 40ms frames)
   -> packetize: [voice-hdr: seq(2B) flags(1B) codec-mode(1B)] + up to 196B Codec2 payload
   -> wrap in ALMA-MESH frame (mesh.h: 16B header, type=VOICE, ttl)
   -> FEC: interleave + simple parity/repeat on the MOST-significant Codec2
      bits (LSPs/pitch) — Codec2 already degrades gracefully bit-for-bit,
      so cheap unequal error protection (protect the first ~30% of bits,
      let the rest ride bare) beats full-frame Reed-Solomon for our CPU
      budget. Pure ALMAWARE code, no external FEC library.
   -> SX1262 TX (half-duplex; PTT gates this)
   -> [mesh: single-hop v0.1/v0.2; TTL-flood rebroadcast for multi-hop is
      already the mesh.h roadmap item, reused as-is for voice]
   -> receiver: dedupe cache (already in AlmaMesh) -> jitter buffer
      (2-3 frames deep, ~restores 40ms Codec2 cadence even with LoRa's
      bursty per-packet delivery) -> Codec2 decode -> I2S speaker (MAX98357A)
```

**Packet loss handling — FEC vs retransmit, and why FEC wins here:**
Retransmit (ACK+resend) is what mesh.h already plans for text (v0.2) but it
is the *wrong* default for voice: a resend arrives 1.5 s+ late, useless for
PTT, and for store-and-forward it just adds airtime we've already shown is
tight. **Voice should prefer FEC + graceful degradation**: a dropped Codec2
frame becomes a lost 40 ms of speech (frame-repeat/mute conceal, cheap to
implement) rather than a stall-and-wait. Reserve retransmit for the voice
sub-header (seq/flags) only if it's corrupted, since losing that misorders
playback worse than losing one frame of audio.

**Buffering:** record into a ring buffer while encoding continues in the
background (Codec2 1200 encode ~17 ms per 40 ms frame — comfortable
headroom on ESP32-S3 at 240 MHz); a small transmit queue (4-8 frames) lets
PTT start sending before the whole utterance is captured, cutting the
"buffer a whole clip then send" latency tax.

## 5. Purity & feasibility

- **Purity**: Codec2 is GPL/LGPL C, no patents, already ported bare-metal to
  ESP32/ESP32-S3 by multiple independent projects (`sh123/esp32_codec2_arduino`,
  Meshtastic's own `ESP32_Codec2`, `sh123/esp32_loradv` — a working
  Codec2-over-LoRa walkie-talkie). We'd vendor/port the codec source itself
  (small, a few thousand lines of C, no dynamic deps) — consistent with
  "our driver, our mesh, our font" but Codec2 the *algorithm* is the one
  place "zero external libraries" should bend to "one small, audited,
  patent-free C library," same spirit as using the Espressif Arduino core
  as a toolchain foundation.
- **On-device feasibility, ESP32-S3**: confirmed by community benchmarks —
  Codec2 1200 bps runs real-time with margin (single-digit-ms encode/decode
  per 40 ms frame) on ESP32/ESP32-S3-class cores; ezDV and esp32_loradv both
  ship Codec2 on ESP32-S3 in real products. RAM footprint is small (codebook
  + short history buffers, low tens of KB) — trivial against the T-Deck's
  8 MB PSRAM and fine even in internal SRAM. **700C mode is real but is the
  most CPU-expensive Codec2 mode and the most degraded-sounding**; community
  reports flag 700-family quality as "words recoverable, not pleasant" —
  usable for store-and-forward text-like voice notes, marginal for PTT
  conversation where naturalness matters more.

## 6. Honest verdict

- **Voice messages (store-and-forward): YES.** 700-1200 bps Codec2 delivers
  a voice note at roughly real-time-or-better airtime, single hop, using
  the mesh we already have. Build this first.
- **PTT walkie-talkie: PROBABLY, with caveats.** Half-duplex "over"-style
  exchanges work at **~2.8-3.7 s one-way latency per hop** — usable for
  short tactical/status exchanges, not for natural back-and-forth banter.
  Multi-hop stacks ~1.5 s per additional hop.
  **Full live conversation (natural full-duplex chat): MARGINAL-TO-NO** —
  SX1262 half-duplex physics plus ~3 s one-hop latency (10-15× what
  full-duplex speech needs) make it dishonest to promise. Say so plainly:
  ALMA-MESH gives you a radio, not a phone.
