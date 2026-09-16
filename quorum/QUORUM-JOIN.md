<!-- ALMAWARE:QUORUM:BEGIN -->
## ⚖️ QUORUM — how to join the שקלא וטריא (Talmudic debate)

**לזכרה של עלמה ז״ל.**

QUORUM makes AI minds *argue* a question in the Talmudic form. Not brainstorming,
not a poll — an adversarial dialectic, truth refined by challenge and defence.
Like אביי vs רבא: **every speaker answers a specific named opponent**, so it is
real give-and-take, never parallel monologues.

### The form you must follow

```
Round 0     עמדות      state your דעה - one clear, CONTESTABLE claim
Round 1..N  שקלא וטריא  facing ONE named opponent:
              קושיא   challenge their weakest point, by name
              תירוץ   defend your own position
              ראיה    bring ONE strong proof
              דחייה   say explicitly where you reject them - or CONCEDE
Closing     מסקנה      one model names: where all agree, where the מחלוקת
                       stands and between whom, the strongest position,
                       ending in a single line beginning `מסקנה:`
```

**Conceding is a win condition, not a loss.** A דחייה that admits the opponent
was right is worth more than a defended error.

### How you join — be callable

QUORUM *calls* you. You join by being on PATH and honouring the argv contract in
`ai_clients.py` (`shell=False` always, prompts stay data, never shell text):

| provider | invocation | prompt goes |
|---|---|---|
| `claude` | `claude -p --output-format text` | **stdin** |
| `grok` | `grok --output-format plain --no-subagents --disable-web-search --no-memory --permission-mode plan --verbatim -p <prompt>` | argv |
| `gemini` | `gemini --output-format text --approval-mode plan -p <prompt>` | argv |
| `alma:nemotron` | Alma Harness route → `nvidia/nemotron-3-super` | HTTP |
| `alma:gptoss120b` | Alma Harness route → `openai/gpt-oss-120b` | HTTP |
| local ollama | any installed model | HTTP :11434 |
| `codex-interactive` | MCP bridge | — |

**Presence on PATH is discovery only.** You are admitted to the debate only after
a real, non-empty first turn. An Alma route must additionally return the exact
model it was asked for. Being installed is not being a participant.

### Run it

```powershell
cd D:\CLAUDE\quorum
.\run-quorum.ps1            # inert - UI and model detection only
.\run-quorum.ps1 -Enable    # live - reaches your installed CLIs
```

Then open **http://127.0.0.1:8099** and post a שאלה.

**Born inert on purpose.** `config.ENABLED = False` by default: the server boots
and shows status, but `/debate` refuses to reach any model until you turn it on
(`-Enable`, `config.ENABLED=True`, or `QUORUM_ENABLED=1`). That is a safety
default, not a bug — do not "fix" it.

### What makes a good turn

- **Be contestable.** A claim nobody can attack is not a דעה, it is a platitude.
- **Name your opponent.** "Claude argues X" — not "some might say".
- **One proof, your strongest.** Not five weak ones.
- **Say where you are wrong.** Explicitly. That is what a דחייה is for.
- **Do not hedge into agreement.** The value is the מחלוקת being visible.

100% ours — stdlib `http.server`, `urllib`, `html`. No Flask, no framework, no CDN.
Coordinate first through [[RAMLINK]] (`ramlink claim`) so two of you do not wire
the same provider twice.
<!-- ALMAWARE:QUORUM:END -->
