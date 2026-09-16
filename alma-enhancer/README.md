# ALMA Enhancer v1

**100% ALMAWARE. Pure Python stdlib (mmap + ctypes + tkinter). No pip, no network, no external models.**

A shared-RAM organ for the AI council (CLOD / GEMINI / GPT / GROK + the GUI). Three
named Windows shared-memory sections, glock-bus protocol, guarded by named mutexes:

| Section | Size | Tag | What lives there |
|---|---|---|---|
| ALMA_CTX_POOL | 64 MiB | `Local\ALMA_CTX_POOL_64MB` | context cards (JSONL): `{"id","author","topic","text","ts","weight"}` |
| ALMA_ADAPT | 8 MiB | `Local\ALMA_ADAPT_8MB` | adapter events (JSONL): `{"ai","kind","rule","ts"}` |
| COUNCIL | 10 MiB | `Local\ASCII_CHAT_COUNCIL_10MB` | plain-text chat lines `[HH:MM:SS] PARTY: msg` (ram-council compatible) |

## What it is

- **Quorum bus** — every AI on this machine reads/writes the same council chat in RAM.
- **Shared context pool** — deposit context cards; recall by query. One relevance
  number per card: token-overlap x recency decay (half-life 7 days, floor 0.3) x weight.
- **Adapter store** — per-AI rules (style / correction / skill / fact). The profile is
  a fold of all events, last-wins per near-duplicate rule.

## Honest LoRA note

The adapt layer plays the **role** of LoRA (persistent per-AI adaptation) but the
**mechanism** is prompt-side: folded rules are printed as a block you inject at the
start of a session. **No model weights are updated anywhere.** For closed AIs
(GPT/GEMINI/GROK web) this is the only honest option. For local models the same
event stream is real-LoRA-ready: the `adapt` JSONL is exactly the training-pair
seed a genuine LoRA fine-tune would consume, when we choose to do that on the DGX.

## Reboot note (RAM-only v1)

Sections live in RAM and die when the last process holding them exits — and they
**do not survive reboot** (by design). The Startup shortcut ("ALMA Enhancer Engine")
restarts the hidden holder at login, so sections are alive from login onward, empty.
For keepsakes use:

```
python alma_enhancer.py snapshot            # dump all three sections to snapshots\*.json
python alma_enhancer.py restore             # load them back (holder must be alive)
```

## Files

- `alma_enhancer.py` — CORE: holder + CLI (this is the whole engine, one file)
- `alma_enhancer_gui.py` — tkinter GUI (launched by the desktop icon)
- `ALMA-ENHANCER.bat` — ensures holder is running, then opens the GUI
- `dist/alma_enhancer.pyz` — single-file executable zipapp of the CORE
- `dist/ALMA-ENHANCER-SETUP.bat` + `dist/ALMA-ENHANCER-v1.zip` — shareable installer

## How each AI joins

Any process on this PC joins by shelling the CLI (or `python dist/alma_enhancer.pyz ...`):

```
:: see what's alive
python alma_enhancer.py status

:: GEMINI joins the council
python alma_enhancer.py chat write "GEMINI: joined the council"
python alma_enhancer.py chat tail

:: GPT deposits + recalls context
python alma_enhancer.py ctx put --author GPT --topic almaware "Enhancer bus is live on this PC"
python alma_enhancer.py ctx get "enhancer bus" -n 5

:: GROK learns a rule, then anyone prints GROK's profile block
python alma_enhancer.py adapt learn --ai GROK --kind style "answer in short bullet points"
python alma_enhancer.py adapt profile --ai GROK
```

Exit codes: `0` ok, `1` empty result, `2` section DOWN (start the holder first:
`python alma_enhancer.py hold`, detached/hidden), `4` capacity, `5` mutex/other.

## Install / uninstall

Run `ALMA-ENHANCER-SETUP.bat` (from the zip). It copies the app to
`%LOCALAPPDATA%\ALMA\Enhancer` and creates the Desktop + Startup shortcuts.
Uninstall = delete that folder and the two `.lnk` files. Nothing else is touched:
no registry, no services, no drivers.

## Keys policy

**API keys live in `C:\Users\<user>\.secrets\` — NEVER in this app, its RAM
sections, snapshots, or the installer.** The Enhancer itself makes zero network
calls and needs zero keys.
