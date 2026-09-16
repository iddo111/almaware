# ALMAWARE fleet onboarding — for Muse Code

You are running inside Iddo's ALMAWARE fleet (WSL on his PC). Here is what already exists so you don't rebuild it.

## The one harness
ALMAWARE Coder desktop app (`D:\CLAUDE\qwen480-taste\coder_desktop.py`) is the ONE approved chat/coder UI. You are being run alongside it as a second CLI tool, per Iddo's explicit choice — not a replacement. Never build another chat UI, IDE, or launcher; if you have a capability worth adding, it goes into ALMAWARE Coder as a Brain-menu model option or a Tools-menu entry.

## The second brain (durable knowledge)
- Door: `http://127.0.0.1:8897` (local) or `https://<tailnet-host>:8897` (any machine on the tailnet)
- Read: `GET /search?q=...`, `GET /page?id=...`
- Write: you PROPOSE (`POST /propose` with `page`, `change`, `author`, needs `X-Brain2-Token` — ask Iddo or another agent for it, never invent one); a separate maintainer process applies proposals and writes real pages. One writer, no races.
- `laws/` pages are read-only to agents — only Iddo's own word changes a law.
- Full handout: `D:\CLAUDE\alma-brain2\HANDOUT-brain2-join-20260912.md`

## RAMCHAT (the fast "now")
Shared agent council / work queue, separate from brain2 (brain2 is durable facts, RAMCHAT is live coordination).
```
cd D:\CLAUDE\RAMCHAT
python ramlink.py read --tail 20
python ramlink.py post <your-name> "what you're doing"
python ramlink.py queue --open
```
Always `read` before starting something, and `post` after anything substantial — other agents (Claude Code sessions, Codex, Grok, Gemini) are working the same tree in parallel.

## Ezra HaSofer (transcript memory)
`D:\CLAUDE\ezra-hasofer\log.jsonl` — every Claude Code conversation in this workspace, timestamped, text-only. Search it before re-deriving something already discussed.

## The fleet (4 DGX Spark boxes)
- eran1 (spark-dgx): runs Maverick 400B router at `:8010` (also serves free NVIDIA-hosted Kimi-K3, Nemotron-3-Super, GLM-5.3-Flash through the same door)
- eran2 (dgx2): gpt-oss-120b at `:8000`
- eran3: behind eran2's NAT, no direct LAN
- eran4 (dgx4): `qwen-coder-dgx4` at `:8450`
- Tailnet addresses and the full topology: `D:\CLAUDE\fleet_inventory.json` (read via `fleet_inventory.py`, don't hardcode addresses — they drift on router changes)

## Our projects (top few, ask brain2/RAMCHAT for the rest)
- **DJ ALMIDO**: an ALMA-language MIDI composer ("Chai") performing live into Ableton via `D:\CLAUDE\dj-alma\`. Currently monophonic (poly=1) — cannot write harmony/chords yet, that's an open gap.
- **KESHEV**: the live mic/STT pipeline. Audio rules used to be very strict; Iddo repealed the whole AUDIO PROTECTION LAW on 2026-09-12 (see brain2 `laws/feedback_audio_law_repealed_20260912`) — but still be thoughtful around his mic/music by default.
- **ERAN**: a separate long-running "holobrain" project on eran1, currently disabled/archived per Iddo's 2026-09-11 order — do not restart it.

## Standing rules that apply to you too
- Broken Windows Law: if something's broken, fix it now, don't wait to be told.
- Token economy: prefer the free fleet over any paid API for bulk work; check `D:\CLAUDE\tokensave\` (`ask.py`, `web.py`, `peek.py`) before reading whole files or spending a model turn.
- Claim before you build (RAMCHAT `claim <task-id>`) — several agents work this tree at once.
