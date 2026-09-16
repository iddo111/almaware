# KESHEV-6 — a second STT decode path for the mic, on 127.0.0.1:8738

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

Built overnight 2026-09-03/04 on Iddo's order: *"if you think you can make a
SIGNIFICANT improvement to the microphone — do it."*

**It runs BESIDE the live server, never instead of it.** `mic-rebuild`'s :8737
and `keshev-next`'s mic engine were not edited, restarted or configured all
night. Switching is one environment variable, and so is rolling back.

The measured result is in `D:\CLAUDE\_status-reports-archive\KESHEV-6-20260904.md`.

## What it is

One process. `ivrit-ai/whisper-large-v3-turbo-ct2` (a Hebrew fine-tune) at
int8_float16 on the RTX 3070 Ti — 818 MiB, which is what is left once :8737 has
its two models. Same HTTP contract as :8737, field for field, so the client
needs no code change.

Three things it does differently:

1. **The model.** :8737 decodes every segment on `iddo-lora-run2-ct2`, a
   personal fine-tune. This decodes on the public Hebrew model that read Iddo's
   own clips 5/5 on eran2 (`eran-brain/hebrew-ref/HEBREW-JUDGE-20260903.md`).
2. **A lexicon `initial_prompt`** (`lexicon.py`) carrying his project names.
   Names are what the old path fails on: Chinchilla came out "צ'רלי וחצי".
3. **No language routing.** The client already forces `he`; routing a
   code-switched sentence to `en` is the historic wall (08-19 inquiry), so
   Latin words the model emits stay where they are. Measured: Latin words kept
   inside Hebrew sentences went 8 → 22 over 209 segments.

It also **reports** `speech_ratio` on every reply so the client's hallucination
stop-list can stop firing on loud speech — proposed, not applied, in
`PROPOSED-textguard-v2.diff`.

## Run it

    RUN-KESHEV6-SERVER.cmd          (or run_hidden.vbs, no console window)

Not in startup. It dies on the next reboot until Iddo says otherwise.

## Point the mic at it

    ADD-TO-STARTUP.cmd                                          # FIRST - see the warning
    setx KESHEV_STT_URL http://127.0.0.1:8738/v1/transcribe    # switch
    setx KESHEV_STT_URL ""                                      # roll back

Restart the KESHEV window either way.

**The order matters.** `main.py` calls `decoder.wait_until_ready()`, which blocks
FOREVER by design (a mic listening into a server that cannot answer is a
shredder). So if `KESHEV_STT_URL` points at :8738 and :8738 is not running after
a reboot, **the mic never opens** — it logs `waiting for the decoder:
UNREACHABLE` and waits. Register the server for boot and switch together, or do
neither. `tests/test_switch_e2e.py` proves this
works by importing `keshev-next/app/decoder.py` itself and running a real
segment through both servers.

## Layout

| file | what it is |
|---|---|
| `keshev6_server.py` | the server. stdlib HTTP + numpy + faster-whisper |
| `lexicon.py` | the prompt sentence and the (narrow, audited) repair map |
| `server-6.json` | model, port, walls, `use_prompt` / `use_repair` switches |
| `tools/pair_night.py` | pairs dumped WAVs with the old system's verdict in `trial.log` |
| `tools/ab.py` | sends the same WAVs to :8737 and :8738 |
| `tools/ablate.py` | model vs +prompt vs +repair, one model load |
| `tools/score.py` | WER/CER vs the reference, the name table, the diff table |
| `tools/frontend_gate.py` | what a `speech_ratio` gate would save, and cost |
| `tools/soak.py` | 30-minute real-time replay |
| `tools/join_test.py` | does joining a sub-second fragment recover real words? |
| `tools/empties_sweep.py` | is real speech hiding in the LOUD "empty" segments? |
| `ADD-TO-STARTUP.cmd` | registers the server for boot — **run it BEFORE switching**, see below |
| `tests/` | contract parity with `mic-rebuild/common/protocol.py`, and the switch |

## Rules it was built under

- Never restart, stop or reconfigure :8737 or the live mic. Never open an audio
  device. (It has no audio-device code at all.)
- HIGH priority for the serving process only; batch tools run below normal.
- Privacy is structural: audio lives only in RAM, and `status_line()` raises
  `TypeError` on a `text`/`transcript`/`title` field, so a transcript cannot
  reach the log even by accident. `tests/test_contract_parity.py` asserts the
  source has no path that writes audio to disk.

## What it does NOT fix

The 85.8% of tonight's segments that came back empty. Those are laughter,
breath and room — 30 of 30 gave no Hebrew sentence from three independent
decoders (`_status-reports-archive/KESHEV-EMPTY-20260903.md`). No model here
recovers them, and this server does not pretend to.

## Which copy is the source? (K6-04, 2026-09-06)

**`eran1:/home/eran1/keshev6/lexicon.py` is the truth. This tree is the copy.**

That is not a preference, it is where the live decoder reads from — and since
K6-05 it re-reads it within 30 s of an edit (or immediately on `SIGHUP`), with
no restart of the microphone's decoder.

It cost something to learn. On 2026-09-06 `keshev6_server.py` was byte-identical
in both places, so the deploy looked clean, while `lexicon.py` was 4,943 B here
(09-04 00:04) against 5,779 B on eran1 (09-06 04:30). The 04:30 edit added
*Assassin's Creed*, *Meshtastic* and *Kropotkin* — put there because Iddo
demonstrated the failure himself at 02:41: the mic could not hear the first of
them, and could hear "hi". A redeploy from this tree would have reverted his fix
and nothing in the repo could have told you.

```
python tools/lexicon_parity.py --check           # offline, against the record
python tools/lexicon_parity.py --fetch           # ssh eran1, real diff, who is ahead
python tools/lexicon_parity.py --fetch --record  # after you have made them agree
```

`LEXICON-DEPLOYED.json` holds the fingerprint of the deployed prompt-and-repair
maps, and `tests/test_contract_parity.py` asserts this tree still matches it —
so drift now breaks a test instead of breaking his dictation. The fingerprint
covers the DATA only (prompt + both maps), so a comment edit is not mistaken for
a behaviour change and a behaviour change cannot hide behind an unchanged size.
