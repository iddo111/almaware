# 05 — עלמא: the on-device Hebrew assistant

לזכרה של עלמה ז"ל · ALMAWARE — 100% ours, offline-first, owner-only.

This doc designs the assistant honestly for the hardware it actually runs on:
an ESP32-S3 with ~320 KB usable SRAM and 8 MB OPI PSRAM, no MMU, no filesystem
beyond microSD, sharing that PSRAM and CPU with the display, LoRa radio, and
mesh stack. It is **not** a phone and it is **not** a DGX Spark. The design
below is a three-tier fallback ladder — each tier honest about what it can
and cannot do — plus how it composes with ALMA-MESH and the existing
`alma-ozen` (Hebrew ASR) and `shiri` (Hebrew WhatsApp assistant) work already
built for PC-class hardware.

## 1. The fallback ladder

```
 user query (typed Hebrew, or ASR text from a paired phone/PC)
        │
        ▼
 Tier 0 — rule matcher (✅ shipped, src/assistant.h)
   instant, deterministic, zero battery cost, zero RAM beyond ~1 KB strings
        │  not handled
        ▼
 Tier 1 — on-device tiny intent model (⬜ next, this doc's main design)
   int8 byte/intent model resident in PSRAM, <2s reply, still fully offline
        │  low confidence / open-ended question
        ▼
 Tier 2 — mesh-relay to a stronger ALMA node (⬜ path exists, gateway ⬜)
   forwarded over LoRa to a phone/PC/Eran node running a real model;
   answer comes back as a normal mesh text message, shown when it arrives
        │  no node reachable
        ▼
 Offline degradation — clear "not reachable, saved for later" banner,
   query is queued and retried on next mesh contact (store-and-forward),
   never a silent failure or a fake/hallucinated confident answer
```

The contract point is `almaAssistantReply()` in `src/assistant.h`: every tier
answers through the *same* call signature, so upgrading Tier 0 → Tier 1 is an
internal swap, not a rewrite of the Chat card or the mesh plumbing.

## 2. Tier 0 — rule matcher (shipped today)

Substring match on decoded Hebrew UTF-8 against ~6 known commands (`עזרה`,
`שעה`, `סוללה`, `מי אתה`, `שלום`), returning canned Hebrew strings built from
live device state (uptime, battery voltage). No ML, no ambiguity, no cost.
This is deliberately not "smart" — it is the reliable floor: it will *never*
misfire, hallucinate, or need PSRAM. Every higher tier degrades to this one
if it fails, times out, or isn't built yet.

## 3. Tier 1 — on-device tiny model: what's actually realistic

**Be honest about the ceiling.** An ESP32-S3 cannot run a transformer LLM in
any useful sense — no attention-over-context, no multi-turn reasoning, no
open-domain generation worth trusting. What *is* realistic on this chip:

- **An intent classifier, not a generator.** A small model maps an utterance
  to one of N known intents (send-message, find-contact, navigate, SOS,
  translate-word, time/battery/status, "unknown/uplink") plus slot values
  (a name, a short phrase). The *reply text* comes from templates filled with
  device state — the same pattern Tier 0 already uses — not from token-by-
  token generation. This is the same shape as `eran-live`'s byte-level model
  philosophy (`eran-live/model.py`, `tokenizer.py`) but at a drastically
  smaller scale and a classification/slot-fill head instead of open decode.
- **Sizing budget.** PSRAM is 8 MB shared with display buffers (none needed —
  the ST7789 driver is framebuffer-less, see `ARCHITECTURE.md` §4), mesh
  dedupe tables, and card state. A realistic budget for the assistant is
  **≤1.5 MB of int8 weights** (leave headroom for growth and the rest of the
  OS). For comparison, `alma-ozen`'s *smallest* acoustic model tier is ~5 M
  params (`alma-ozen/model.py` `SIZES["small"]`, 256×3 BiLSTM) — already too
  big at fp32 (~20 MB) and still large at int8 (~5 MB). The T-Deck assistant
  model must be roughly **3-5x smaller than alma-ozen's smallest tier**: a
  tiny GRU/RNN (not LSTM-stacked) or a depthwise-separable tinyCNN over
  character n-grams, ~300K-800K params, quantized int8, greedy/argmax decode
  only (no beam search — no budget for it).
- **What it buys over Tier 0:** typo/inflection tolerance (Hebrew has heavy
  morphology — a rule matcher on raw substrings misses `הסוללה`, `לסוללה`,
  `סוללתי`), a handful more intents (navigate-to-card, "read me my last
  message"), and slot extraction (a contact name, a word to translate)
  instead of exact-phrase matching. It does **not** buy: open Q&A, world
  knowledge, multi-turn memory, or anything resembling a chat LLM. Any query
  that doesn't map cleanly to a known intent falls through to Tier 2 (or the
  offline queue) rather than guessing — this is the same "handled=false ⇒
  caller may uplink" contract already in `assistant.h`.
- **Training path:** intents distilled from the same Hebrew text pipeline
  behind `alma-ozen` (its `gold/manifest.jsonl` transcripts are a natural seed
  corpus for command-like utterances) and `eran-live`'s tokenizer conventions,
  but trained as a tiny classifier/CTC-slot model, exported to a flat int8
  weight blob (reuse `alma-ozen/export.py`'s int8 pattern) and loaded from
  microSD at boot into a PSRAM arena — never re-flashed with firmware, so the
  model can be updated independently by dropping a new file on the SD card.
- **Cost on the loop:** must run inside the existing cooperative single-
  threaded event loop (`ARCHITECTURE.md` §6) without blocking LoRa RX polling
  or keyboard scanning for more than ~50 ms per tick — so inference is
  chunked across ticks if it can't complete in one, the same discipline
  already applied to display blitting and radio polling.

## 4. Hebrew NLU + TTS specifics

- **Input paths into the assistant:** (a) typed Hebrew from the on-device
  Q10 keyboard via `src/keyboard.h`'s Israeli layout (already logical-order
  UTF-8, no ASR needed), and (b) spoken Hebrew, which this device **cannot
  transcribe itself** — there is no realistic on-device ASR budget here (the
  T-Deck has a mic ADC per `board_tdeck.h` PIN_ES7210_*, but running even
  `alma-ozen`'s smallest CTC model, ~5 M params plus mel-spectrogram
  front-end, is out of reach for the same PSRAM/CPU-budget reasons as §3).
  Voice input is therefore a **mesh/paired-device feature**: audio (or a
  pre-transcribed text) comes from a phone or PC running the real
  `alma-ozen` engine (`alma-ozen/app/engine.py`, `app/live.py`) and arrives
  at the T-Deck as plain UTF-8 text over the same channel Tier 2 uses. The
  T-Deck's own mic is reserved for a possible future low-rate voice-note
  capture-and-forward (record → send raw/compressed PCM over mesh → remote
  ASR), not on-device transcription.
- **Command set (v1 target):** `שלח הודעה ל<שם>` (send message to contact,
  relayed as an AlmaMessage), `מצא <שם>` (find contact — looks up a local
  contacts list on SD), `נווט ל<כרטיס>` (navigate to card — Settings/Files/
  Chat), `SOS` / `מצוקה` (SOS — highest priority: broadcasts an
  `ALMA_MSG` with a reserved urgent flag and the node's last known
  status, bypassing normal send-cooldown), `תרגם <מילה>` (translate word —
  Tier 1 for a tiny built-in dictionary of common words, Tier 2 uplink for
  anything else), plus the existing `עזרה/שעה/סוללה/מי אתה` status commands.
  SOS is deliberately handled *before* the normal intent classifier — a
  hardcoded highest-priority check, same "never make the safety path depend
  on the ML path" principle as `alma-iff`'s HOLD FIRE design.
- **TTS for replies:** full neural TTS is out of budget for the same reasons
  as ASR. Realistic on-device options, cheapest first:
  1. **Text-only replies on screen** (v1 default) — the RTL Hebrew renderer
     already exists (`display_st7789.cpp` `drawTextRTL`); this is free and
     should be the actual default for the assistant.
  2. **A handful of pre-recorded Hebrew phrase clips** (system sounds: "שלום",
     "הודעה נשלחה", "SOS נשלח") as short PCM/ADPCM samples played over the
     MAX98357A I2S DAC — a fixed phrase table, not TTS.
  3. **Simple concatenative TTS** (diphone or syllable splicing) is the
     honest ceiling if audio-out replies for arbitrary text are wanted later:
     stitch pre-recorded Hebrew phoneme/syllable units, no prosody model, no
     neural vocoder. This is a v2+ stretch, not committed here — Codec2-style
     compression only helps storage size, it does not add synthesis
     capability, so it's an optimization on top of concatenative TTS, not a
     TTS method itself. Marked ⬜, honestly deprioritized behind text-first.

## 5. Assistant capabilities over the mesh (Tier 2)

An unhandled `?`-prefixed query (existing convention in `assistant.h`) is
wrapped in an `AlmaMessage` (`src/mesh.h`) and broadcast/routed toward a
**gateway node** — a phone, PC, or the Eran/DGX box — running a real model.
This reuses, rather than reinvents, work already built:

- The gateway is the natural evolution of `lora-mesh/lora_autoresponder.py`
  (referenced already in `ARCHITECTURE.md` §8) paired with a local LLM (an
  Eran checkpoint, or any ALMA-approved local model) — **not a cloud API
  call**, keeping the ALMAWARE purity law intact end-to-end.
- Reply comes back as a normal `ALMA_MSG` — the T-Deck doesn't need to know
  it asked a "hard" question versus receiving any other mesh text; the Chat
  card just displays it when it arrives, with the query shown as "pending"
  in the interim (never a spinner promising an instant answer over a
  multi-second LoRa round-trip).
- **Voice-capable stretch:** if a paired phone/PC is reachable over
  Bluetooth/WiFi rather than pure LoRa (out of scope for `board_tdeck.h`'s
  current radio-only design, but architecturally compatible), the same relay
  could carry short voice notes to `alma-ozen`'s live engine and back — this
  is future work, explicitly not committed in this design.
- **Latency honesty:** LoRa at SF9/125 kHz (current `board_tdeck.h` default)
  gives on the order of hundreds of ms to a few seconds airtime per ~200 B
  frame, plus gateway inference time. Tier 2 answers are a "get back to you"
  channel, not a chat-latency one — the UI must say so, not imply real-time.

## 6. Offline graceful degradation

No node in range and Tier 1 doesn't have an answer: the query is not
dropped. It is written to a small on-SD queue (reusing the SD card already
wired for CS39, `board_tdeck.h`) with a timestamp, the UI shows "אין קשר —
נשמר לשליחה" (no contact — saved for sending), and the mesh layer retries it
opportunistically whenever a BEACON or any traffic from a candidate gateway
node is seen (`mesh.h`'s existing `ALMA_BEACON` type is the natural presence
signal). This mirrors `shiri`'s "never spam, never fake success" ethos
(`shiri/README.md` §1) transplanted to a radio-silence scenario instead of a
rate-limit one: honest about not having reached anyone yet, never a
fabricated Tier-1 answer dressed up as if it were an informed one.

## 7. Privacy, ownership, and ALMAWARE purity

- **Owner-gated by construction, not by policy alone.** The assistant only
  ever answers the person holding the keyboard — there is no multi-user
  concept on this firmware (single event loop, no accounts). The risk is
  the *mesh* side: SOS and message-send intents must only be triggerable
  from local input, never remotely re-triggered by a crafted mesh payload
  addressed to this node — Tier 2 relay is strictly outbound-query /
  inbound-answer, and any inbound `AlmaMessage` is displayed as *received
  text*, never executed as a command (same untrusted-input discipline as
  `shiri`'s `wa_recent`/`wa_search`: inbound mesh data is data, not
  instructions).
- **Local keys, no cloud identity.** Node identity is the efuse MAC
  (`mesh.h` `_self`), not an account or token. If message content ever needs
  confidentiality beyond "shared LoRa channel," that's the roadmap AES-CTR
  payload encryption already flagged in `ARCHITECTURE.md` §7 (⬜) — a
  pre-shared key local to the owner's devices, not a cloud KMS.
- **Zero cloud dependency for core function.** Tiers 0 and 1 need nothing
  beyond the device itself. Tier 2's gateway is the owner's own hardware
  (phone/PC/Eran) — never a third-party API — preserving the same "100%
  ours" rule already governing `alma-ozen` (pure PyTorch/stdlib, CPU-only,
  no cloud STT) and `shiri` (credential-free MCP, local WhatsApp bridge).
- **Contacts/SOS data stays on-device.** A local contacts list (for
  `מצא`/`שלח הודעה ל`) lives on the SD card next to the offline query queue,
  not synced anywhere by default — sync-to-phone, if ever wanted, is an
  explicit future opt-in, not silent background behavior.

## 8. Summary table

| Tier | Runs on | Capability | Cost | Honest limit |
|---|---|---|---|---|
| 0 | ESP32-S3, always | ~6 fixed Hebrew commands | ~0 (rules) | no tolerance for phrasing variation |
| 1 | ESP32-S3, PSRAM | intent+slot classify, templated reply | <2s, ≤1.5MB weights | no open Q&A, no generation, no world knowledge |
| 2 | mesh gateway (phone/PC/Eran) | real model, open questions | seconds, needs a reachable node | not always available; not instant |
| offline | SD queue | never silently fails | ~0 | answer arrives late or never, always says so |

## 9. What this doc does not commit to (roadmap, marked ⬜)

- Concatenative Hebrew TTS for arbitrary text (§4.3) — text-first is the
  actual v1 plan.
- On-device voice transcription — architecturally out of budget; voice stays
  a paired-device/mesh feature.
- AES-CTR mesh payload encryption — flagged in `ARCHITECTURE.md`, assumed
  but not re-specified here.
- A trained Tier-1 model — this doc specifies the budget and shape; training
  data collection and the actual int8 export are follow-up work, analogous
  to `alma-ozen/export.py`'s existing int8 pipeline.
