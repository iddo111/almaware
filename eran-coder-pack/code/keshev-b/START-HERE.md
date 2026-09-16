# 🪟 KESHEV B — START HERE

> 🪟 **BROKEN WINDOWS LAW:** if it's not working, fix it IMMEDIATELY. Test the REAL output, not a proxy (`health: ok` ≠ working).

**You are Qwen, or you are gpt-oss. You are building KESHEV B together, as a QUORUM.**
One app. Not two. There is no KESHEV C. Iddo's order, 2026-08-15.

---

## 1. READ THIS FIRST, COMPLETELY

```
D:\CLAUDE\HANDOUT-KESHEV-B-QWEN.md
```

That is the full brief: ALMAWARE laws, RAMCHAT protocol, the verified fleet
routes, the STT server you must REUSE rather than rebuild, the 57-scar
ledger, the presence scar of 2026-08-15 09:46, and the always-on LoRA +
from-scratch training tracks over the Café Claude corpus.

**Do not skip it. Do not skim it. Everything below assumes you have read it.**

---

## 2. CLAIM YOUR WORK BEFORE YOU BUILD

Several AIs share this machine. This is not optional.

```bash
cd D:\CLAUDE\RAMCHAT
python ramlink.py read --tail 20
python ramlink.py post qwen "starting KESHEV B - reading the handout"
```

Set `PYTHONIOENCODING=utf-8` — the files are full of Hebrew and cp1252 crashes.

---

## 3. RUN THE QUORUM BEFORE YOU WRITE CODE

Qwen and gpt-oss argue the design in the Talmudic form (see the QUORUM
section of `D:\CLAUDE\CLAUDE.md`). Each states ONE contestable claim,
challenges the other **by name**, defends, brings one proof, and either
rejects explicitly or **concedes**. Conceding is a win condition.

**Write the verdict to `D:\CLAUDE\keshev-b\QUORUM-VERDICT.md` before any code.**

The two questions worth arguing hardest:

1. **How does B know Iddo is in the room?** On 2026-08-15 09:46, KESHEV A
   typed the ROOM into his live chat as him — eight messages in nine seconds
   from a video playing near the mic. Every guard passed and was right to.
   None of them asked whether the man whose name goes on the message was
   there. **Do not copy A's answer. Find yours.**
2. **How does the mic get better every day without ever getting worse?**
   Capture, nightly training, and a promotion gate that refuses to deploy a
   model that did not win. A model trained on its own output grows more
   confident and more wrong while the loss curve looks beautiful the whole
   way down.

---

## 4. WHAT YOU MAY AND MAY NOT TOUCH

| | |
|---|---|
| **Build here** | `D:\CLAUDE\keshev-b\` — yours |
| **Never write** | `D:\CLAUDE\mic-rebuild\` — that is KESHEV A |
| **May read from A** | `PHASE1-INQUIRY.md` (the 57 scars) and `state\stt-token` — nothing else |
| **Must not read** | A's `PHASE2-DESIGN.md` and A's source. Inherit the scars, invent the architecture — otherwise B is a copy and the comparison is worthless |
| **Never start automatically** | KESHEV A currently holds the microphone. ONE-MIC LAW: detect another live dictation client and refuse to start, with an honest message |

---

## 5. THE FIRST THING THAT MUST WORK

Before any UI, any polish, any architecture diagram:

**Iddo speaks Hebrew at the BRIO, and the words appear in his window.**

Verify the STT server answers you before building anything on top:

```
http://<lan-ip>:8737/v1/transcribe
Authorization: Bearer <D:\CLAUDE\mic-rebuild\state\stt-token>
Content-Type: audio/pcm;rate=16000;encoding=s16le;channels=1
X-Request-Id: <8hex>-<6+digits>      X-Audio-Duration-Ms: <ms>
X-Lang-Hint: auto | he | en
```

⚠️ **Measured 2026-08-15, and it will bite you:** with `X-Lang-Hint: auto`
the server sometimes decides Hebrew speech is English and returns fluent
nonsense — *"Give me a car! A fascism would have been!"* for
*"גריקה! הפאשיזם לא יעבור"* — and can spiral into a repeated phrase 70 times.
The same audio with `he` decodes perfectly. **Language routing is an open
problem, not a solved one. Treat it as a first-class design question.**

---

## 6. HOW "WORKS WELL" IS JUDGED

Section 6 of the handout. The short version: 20 real Hebrew utterances,
≥19 correct in the right window; p50 under 700 ms; **the Bluetooth headset is
never opened as a microphone, ever**; ten minutes of empty room types nothing;
a video playing near the mic types nothing as him; nothing is ever silently
dropped; it survives the night or alarms loudly; and **any "typed ok" that did
not reach the screen fails the whole build.**

---

**Speak to Iddo in Hebrew AND English, short, like to a ten-year-old.**
**Never hand him a `D:\` path as something to click — serve it on `http://127.0.0.1:PORT/`.**

בהצלחה.
