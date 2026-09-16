# לזכרה של עלמה ז״ל

# QUORUM — SPEC (what it is, precisely)

## Purpose
QUORUM lets Iddo **watch AI minds argue a question in the Talmudic form** —
שקלא וטריא (give-and-take). Not one answer, not brainstorming: an *adversarial
dialectic* made visible, truth refined by challenge and defense among different minds.

## The form (canonical)
```
Round 0 — עמדות        each model states its דעה (a clear, contestable claim)
Round 1..N — שקלא וטריא each model faces ONE named opponent and responds:
                         קושיא  (challenge the opponent's weakest point)
                         תירוץ  (defend one's own position)
                         ראיה   (bring one strong proof)
                         דחייה  (say explicitly where the opponent is rejected —
                                 or where one concedes)
Closing — מסקנה         one strong model names: where all AGREE, where the
                         מחלוקת stands (who disputes whom, on what), the strongest
                         position, ending in a single 'מסקנה:' line.
```
Like אביי vs רבא: each speaker is answerable to a specific opponent by name, so the
argument is real give-and-take, not parallel monologues.

## Participants
Any 2+ real responders: first-class private Alma routes (`alma:nemotron` and
`alma:gptoss120b`), first-class local 4D-fleet routes
(`qwen3-coder-next-fp8` on eran1, `glm-4.7-flash` on eran2, `nemotron-3-super`
on eran3, `gpt-oss-120b` on eran4 — all through the ONE alma-router on eran1
:8010, OpenAI-compatible; the model name selects the box; the URL lives in
`state\settings.json` / env `QUORUM_FLEET_ROUTER_URL`, never baked in), callable Claude/Grok/Gemini
CLIs, and local ollama specialists.
Executable presence is discovery only; a provider joins the debate after a real,
non-empty first turn. Alma routes must also return the exact intended model and
Harness route identity; fleet routes must list and echo the exact model asked for. The closing מסקנה is written by the best responding model
(`config.SYNTH_PREFERENCE`).

## Non-negotiable contracts
- **Born inert.** `config.ENABLED=False` → no model is contacted until deliberately enabled.
- **failure-is-a-value.** No exception crosses a public boundary; failures are
  `Reply(ok=False,…)` values and `error`/`done` events.
- **Injection defense.** Cross-model text is fenced `<untrusted-model-output>` = DATA.
- **100% ours.** stdlib only; orchestration is ours; the trained models are the rock.
- **Bright RTL** UI + PDF/HTML transcripts (standing delivery rules).
- **Loopback-only** by default; Tailscale/token gate for anything wider.

## In vs out of scope (v0.1)
IN: the שקלא-וטריא engine, live model detection, SSE web arena, HTML transcript.
OUT (roadmap): true per-token streaming, PDF export, other modes (chat/courtroom),
always-on supervisor, public `iddoperez-quorum` publishing.

## Event protocol (server ↔ browser, SSE)
`plan` (roster + rounds) · `status` (round-start / per-turn writing·done·note) ·
`delta` (streamed tokens; `agent:"synth"` = the closing מסקנה) · `error` · `done`
(carries `topic`, `synth_model`, `synthesis`, full `transcript`).
