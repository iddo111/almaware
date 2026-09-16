# 🪟 HANDOUT — KESHEV B, built by Qwen

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait to be told. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

**You are Qwen and gpt-oss, working together. You are building KESHEV B — a microphone dictation app for Iddo Perez, from scratch.**

Author of this handout: `claude-cli` (which built KESHEV A). Date: 2026-08-15.

**Iddo's order, revised 2026-08-15:** *"i will instruct them to make a quorum together on the mic app — so keshev b only not c"*. There is no KESHEV C. **Qwen and gpt-oss form a QUORUM and produce ONE build, B.**

### How the quorum works — this is not optional decoration

QUORUM is Iddo's Talmudic-debate harness (`D:\CLAUDE\quorum`, live at http://127.0.0.1:8099/). Read the QUORUM section of `D:\CLAUDE\CLAUDE.md` for the full form. The short version, applied to this build:

```
Round 0     עמדות      each model states ONE clear, CONTESTABLE design claim
Round 1..N  שקלא וטריא  facing ONE named opponent:
              קושיא   challenge their weakest point, BY NAME
              תירוץ   defend your own
              ראיה    bring ONE strong proof
              דחייה   reject explicitly — or CONCEDE
Closing     מסקנה      one model writes the verdict, ending in a line
                       beginning `מסקנה:`
```

**Conceding is a win condition, not a loss.** A concession that admits the opponent was right is worth more than a defended error.

Debate the architecture decisions — especially section 7 (how B knows Iddo is present) and section 9 (the training loop). **Write the מסקנה down in `D:\CLAUDE\keshev-b\QUORUM-VERDICT.md` before you write code.** Then build the verdict, not your own losing position.

---

## 0. THE ONE-PARAGRAPH BRIEF

Iddo speaks Hebrew and English at a USB microphone. The app must hear him, transcribe accurately and fast, and **type the text into whatever window he is working in**, optionally pressing Enter. It runs on his Windows 11 PC. Transcription happens on a remote DGX box that is already built and running — you do not build a speech model. The hard part is not the AI. **The hard part is the twenty years of Windows edge cases between a microphone and a text box, and never lying about whether it worked.**

---

## 1. YOUR BOUNDARIES — read before touching anything

| Rule | Meaning |
|---|---|
| **Build in `D:\CLAUDE\keshev-b\`** | Create it. It is yours. |
| **NEVER write inside `D:\CLAUDE\mic-rebuild\`** | That is KESHEV A. Read-only to you, and only the files section 4 permits. |
| **Do not import from A** | Not one module. B must run with A deleted. |
| **Claude will not interfere** | Iddo's explicit instruction. Claude's only role is to verify B works. Do not wait for Claude's approval on design. |
| **Claim your work in RAMCHAT before you start** | Section 2. Non-negotiable — several AIs share this machine. |

---

## 2. ALMAWARE — locate it and use it, ALWAYS

**ALMAWARE** is Iddo's software ecosystem and its engineering ethos. You are joining a team of AIs (Claude, Claude CLI, Codex, Grok, Gemini, Cursor, and you) working the same machine in parallel.

### 2.1 The standing laws — `D:\CLAUDE\CLAUDE.md`

**Read this file first, every session.** It is the workspace's law header. The laws that bind YOUR build:

- **🪟 Broken Windows** — fix it now, test the real output.
- **⭐ ALMA Standard / Reliability Reset** — one thing that WORKS beats many demos. Real, not demo. Proof, honest.
- **🗣️ Say-When-Beyond-Me** — if it is not working or beyond your reach, say so plainly and early (🟢🟡🔴). Do not flail, do not fake.
- **🚫📢 No Overselling** — never report a feature as working that you have not measured working.
- **⭐ Bilingual Law** — every user-facing message to Iddo is written in **both Hebrew and English**. Cut content hard to compensate.
- **🧒 Talk short and simple** — explain like he is ten. He asks for "eli10". Respect it.
- **🔗 Clickable-Access Law** — **never hand Iddo a `C:\...` or `D:\...` path as something to click.** They do not click in his app. Give him ACCESS: open the file for him with `Start-Process`, drop a Desktop shortcut, or serve it on `http://127.0.0.1:PORT/` (those DO click). Deliverables for Iddo are **JPEG + PDF on the Desktop**, never a raw `.html`.
- **🚫🔥 No AI torch on the PC** — anything that does `import torch` + `torch.load()` runs on the DGX fleet, never the PC. A "just a chat server" that quietly does local inference has been caught before. Remote-API clients are fine.

### 2.2 RAMCHAT — the shared memory. **Claim before you build.**

Location: `D:\CLAUDE\RAMCHAT`. Rules: `RULES.md`. Onboarding: `HANDOUT-ramchat-join-20260808.md`.

```bash
cd D:\CLAUDE\RAMCHAT && python ramlink.py read --tail 20
```

Then, before you write a line of code:

```bash
python ramlink.py post qwen "starting KESHEV B at D:\CLAUDE\keshev-b - independent mic app, per Iddo 2026-08-15"
```

- Always set `PYTHONIOENCODING=utf-8` — the files are full of Hebrew and cp1252 crashes.
- **Claim ports in RAMCHAT before binding anything.** A is not using a local port; if B needs one, claim it.
- `claim` is **atomic**. If it refuses, someone else holds the task — stop and pick another.
- Post negative results too. They save the most time.
- Post when you finish something substantial: `python ramlink.py post qwen "<what changed, where, warnings>"`

### 2.3 The fleet — where transcription happens

Four DGX Spark (GB10) boxes. **The SSH routes written in `CLAUDE.md` for eran3/eran4 are STALE as of 2026-08-15** — measured today, the documented jump times out. Working routes:

| node | reach | role |
|---|---|---|
| eran1 | `ssh eran1` (<lan-ip>) | **your STT server** + Qwen head |
| eran2 | `ssh eran2` (<lan-ip>) | RPC worker, fabric hub |
| eran3 | `ssh dgx3` ✅ (tailnet — **not** the `-J eran2` jump) | RPC worker |
| eran4 | `ssh eran4@<lan-ip>` ✅ | **Eran voice training — DO NOT TOUCH** |

**eran4 is off limits.** It trains Iddo's child-model "Eran". Nothing of yours goes near it.

---

## 3. THE STT SERVER IS ALREADY BUILT — REUSE IT, DO NOT REBUILD IT

This is the single biggest thing you get for free. **Do not build a speech model. Do not run Whisper on the PC.**

```
URL      http://<lan-ip>:8737/
State    READY (verified 2026-08-15 11:31, uptime 45479 s)
Models   large-v3-turbo-ct2  ·  iddo-lora-run2-ct2   ← LoRA fine-tuned on Iddo's own voice
Auth     Bearer token. WITHOUT it every request is 401.
Token    read from D:\CLAUDE\mic-rebuild\state\stt-token   ← the ONE file you may read from A
Service  systemctl --user is-active keshev-stt   (user unit, NOT system — `systemctl is-active` lies "inactive")
Health   GET /health with the Bearer header
```

Verify it yourself before building anything on top:

```bash
curl -H "Authorization: Bearer $(cat /path/to/stt-token)" http://<lan-ip>:8737/health
```

**⚠️ A measured trap, paid for in Iddo's real speech:** the server's language policy must decode Hebrew with **`vad=False`**. On 2026-08-14 an inner Silero VAD was eating **37% of his real Hebrew** (measured: 3 of 8 archived speech WAVs returned EMPTY with `vad=True` and decoded perfectly with `vad=False`). One dropped word was `הק!` — a real thing he said, shown as nothing, while he was talking about his father. If you see Hebrew coming back empty while English works, this is why. **Protect against silence-hallucination on the CLIENT, never by re-enabling that flag.**

If you prefer your own server contract, you may write your own service on eran1 — but claim the port in RAMCHAT first and **do not disturb `keshev-stt` on 8737**, which is A's live dependency.

---

## 4. THE SCAR LEDGER — the most valuable thing in this handout

`D:\CLAUDE\mic-rebuild\PHASE1-INQUIRY.md` — **57 scars and 23 acceptance criteria.** Read it completely. Twice.

**READ THIS FILE. Do NOT read A's `PHASE2-DESIGN.md` or A's source code.**

That split is deliberate, and here is the reasoning so you can judge it yourself:

- The **scars** are empirical facts about Windows, about audio hardware, and about Iddo's specific machine. They were paid for with months of his broken workdays. A "from scratch" build that re-bleeds every one of them is not independent — it is just slower.
- The **design** is the thing that should differ between A, B and C. If you read A's design, B becomes a copy and the comparison is worthless.

So: inherit the *facts*, invent the *architecture*. If Iddo overrules this and wants you fully blind, obey him — his word beats this document.

**A sample of what is in there**, so you know it is worth your time:

- Per-character `SendInput` silently LOSES characters when the receiving app cannot drain its queue — a 79-character utterance arrived with every space stripped. Clipboard paste is 4 events regardless of length.
- Terminals **discard** `KEYEVENTF_UNICODE` entirely. `SendInput` returns success, the log says typed, nothing appears. This lied for weeks.
- Restoring the clipboard after a paste pasted his PREVIOUS clipboard for an entire night — Ctrl+V is only a *request*.
- Window identity must be HWND + PID + image path, **never the caption** — a terminal spinner rewrites its title every tick.
- `SetForegroundWindow` fails silently; you must verify the change took.
- Typing into a title-less window (the desktop) **renames his files**.
- Clipboard handles must be `c_void_p` — the default int return truncates a 64-bit HANDLE.

---

## 5. THE LAWS OF THE MICROPHONE — these are Iddo's, not engineering taste

### 🎧 SACRED AUDIO LAW — חוק השמע הקדוש

**Iddo's music is his flow state. Never touch his audio.** No process may claim, duck, mute, pause or degrade his output devices.

**The WH-1000XM4 — or ANY Bluetooth headset — is NEVER a microphone.** Opening a BT headset mic flips it to HFP telephone quality and wrecks his sound. This happened. Never again.

- Microphone input = **USB mics ONLY** (Logitech BRIO is primary, then Scarlett, then wired USB).
- If no authorized USB mic is alive, the app states `IDLE_NO_MIC` and **stops**. There is **no fallback** to Bluetooth, headset or virtual devices. Ever.
- **Enforce this structurally, in code — not as a config setting a bug can flip.**
- Any video your app opens in a browser: muted before play.

### 🎤 ONE-MIC LAW

Only one dictation client may hold the microphone. **KESHEV A currently holds it.** Two clients sharing a mic is a documented failure. B must:

- detect that another dictation client is alive and **refuse to start** with an honest message, and
- never start automatically. Iddo decides which mic app runs.

### 🔒 Privacy

Log **executable names, never window titles**. His window titles contain his private life. Audio is his; do not upload it anywhere except the STT server described above, and do not retain a corpus without his explicit say-so.

---

## 6. WHAT "WORKS WELL" MEANS — how Claude will judge B

Claude's only role is verification. These are the checks. Nothing here is graded on code beauty.

| # | Check | Pass condition |
|---|---|---|
| 1 | **He speaks Hebrew, it appears** | 20 consecutive real Hebrew utterances → ≥19 appear, correct, in the right window |
| 2 | **He speaks English, it appears** | same |
| 3 | **Latency** | p50 under 700 ms speech-end → text-on-screen |
| 4 | **No Bluetooth mic, ever** | with the WH-1000XM4 connected and the BRIO unplugged, the app goes idle. It does not open the headset. Verified by device enumeration, not by hope. |
| 5 | **Silence types nothing** | 10 minutes of empty room → zero characters typed |
| 6 | **A video playing near the mic types nothing as him** | ← this is the scar of 2026-08-15 09:46, section 7 |
| 7 | **Nothing is ever silently dropped** | every refusal is journaled and the text is recoverable from a file |
| 8 | **It survives the night** | 8 hours running → still transcribing, or it alarmed loudly when it stopped |
| 9 | **Honest status** | when it is deaf, the UI says DEAF. A green light while deaf is an automatic fail. |
| 10 | **Nothing it reports is untrue** | any "typed ok" that did not reach the screen fails the whole build |

Iddo will judge on one thing beyond these: **does it feel like it hears him.**

---

## 7. THE NEWEST SCAR — 2026-08-15 09:46, hours before this handout

With Iddo out of the room, KESHEV A typed **the room** into his live chat, as him, with Enter:

> *"Welcome to Art Racer."* · *"Hola, saludos."* · *"Let's go."* · *"That's it."* · *"So this is a lot of fun."*

Eight messages in nine seconds. A video was playing near the microphone.

**Every guard worked.** The device guard proved it was an authorized USB mic. The energy gate, blip guard and VAD proved it was speech. The text guard proved it was not a hallucination. The focus guard proved the destination window was allowed.

**Not one of them asked whether the man whose name goes on the message was in the room.**

Design B so that it *cannot* speak as him when he is not there. Do not solve it by tightening the audio gates — the audio gates were correct; that really was speech. It is a different question and it needs its own answer. Candidate answers: presence via the OS idle clock, push-to-talk, an arming hotkey with decay, a wake word, or voice identity against his own enrolled voice.

**Do not copy A's answer.** Find yours. This is exactly the kind of place where three independent builds are worth the cost.

---

## 9. THE VOICE THAT LEARNS HIM — always-on LoRA + a from-scratch model

**Iddo's order, 2026-08-15:** *"add to the app here and in the qwen oss — the from scratch weight model and lora auto training always on my voice — and cafe clod"*.

This is not a side feature. It is the point: **the microphone should get better at Iddo every day it is used.**

Two tracks, different risk, different timelines. **Do not let the slow one block the fast one.**

### 9.1 The seed corpus — Café Claude

```
D:\קפה-קלוד\        7.67 GB, 173 files — VERIFIED 2026-08-15
  67 .WAV + 32 .mp3   Iddo's own voice
  48 .txt + 14 .srt   transcripts, already paired
  subdirs: cleaned\  transcripts\  dgx_compare\  handouts\
```

Paired audio and text — exactly what fine-tuning needs, already on disk. Start here, not from zero.

**⛔ HELD OUT — never train on these:** `2026-06-25` and `2026-07-01`. They are the evaluation set (shared with the Voice Ant Farm). Training on them destroys your only honest measurement and you will not notice.

### 9.2 Track A (fast, real) — always-on LoRA on eran1

The flywheel: every segment KESHEV decodes becomes a candidate training pair (audio + text). Nightly, a LoRA trains on the accumulated pairs and — **only if it wins** — replaces the live one.

`iddo-lora-run2-ct2` is already loaded on the eran1 server. You are extending a working thing.

**Four traps that kill this exact design. Iddo has authorized the build; these are yours to solve, and the quorum should argue them:**

1. **Pseudo-label collapse.** Training a model on its own outputs makes it more confident and more wrong, forever, and the loss curve looks beautiful the whole way down. Never train on raw decodes alone.
2. **Corrections are the gold.** When Iddo *fixes* a word KESHEV got wrong, that correction is worth a hundred confident decodes. **Capture corrections as first-class training data** — this is the single highest-value signal in the whole system, and it is free.
3. **Promotion must be earned.** A new LoRA replaces the live one **only** when it beats the current one on the held-out set. Never promote on training loss. Log both numbers every run. A promotion with no measurement is how the mic silently gets worse.
4. **Honest WER, every run.** One fixed held-out set, never touched, WER reported and kept. If you cannot say what the WER is, the training loop is decoration.

**Where it runs:** eran1. **NEVER eran4** — that is Eran's voice training and is off limits. **Never the PC** — no `torch` on Iddo's machine, ever.

### 9.3 Track B (slow, purist) — the from-scratch weight model

An ASR model trained from zero on Iddo's voice, no pretrained weights. This is the ALMAWARE-purist line, the same spirit as the Eran project.

**Say this plainly to him and keep saying it: for a long time it will be far worse than Whisper.** That is expected and it is not failure — a from-scratch model on ~8 GB of one speaker is a research track, not a product track. Its honest job is to get measurably better each week on the same held-out set.

**It must never be in the live dictation path until it beats the LoRA on that set.** Track A stays his working microphone the whole time.

### 9.4 Privacy — he has now authorized capture

Recording his dictation for training is a real consent boundary and **Iddo crossed it deliberately on 2026-08-15** with the order above. So:

- Store the corpus **locally and on the fleet only**. It never leaves his machines.
- Keep it separable and deletable — one command wipes it if he changes his mind.
- Corpus capture is **his voice for his model.** Not for evaluation dashboards, not for anyone else's training, not uploaded anywhere.
- Log what you captured, in counts, where he can see it.

---

## 8. START HERE

1. `cd D:\CLAUDE\RAMCHAT && python ramlink.py read --tail 20` — see what the team is doing.
2. `python ramlink.py post qwen "claiming KESHEV B, building at D:\CLAUDE\keshev-b"`
3. Read `D:\CLAUDE\CLAUDE.md` — the laws.
4. Read `D:\CLAUDE\mic-rebuild\PHASE1-INQUIRY.md` — all 57 scars, completely.
5. Verify the STT server answers you (section 3).
6. **Write your design down before you write code.** One page. What is your answer to section 7?
7. Build. Test against section 6 with REAL speech, not synthetic audio.
8. Post to RAMCHAT when it works — and when it does not.

**Speak to Iddo in Hebrew and English, short, like to a ten-year-old. Never hand him a `D:\` path as something to click.**

בהצלחה. / Good luck.
