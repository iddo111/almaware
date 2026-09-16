# ALMAWARE — Master Dashboard (web)

Iddo's whole AI world in one browser page: **see** the fleet + training live, and
**hear** Eran's and Yigael's latest babble. ALMAWARE-pure — one small Python web
server (stdlib `http.server` only, no Flask / no frameworks).

Lives inside the existing `eran-dashboard` project (reuse, not duplicate). The
older `eran_dashboard.py` is the always-on-top **desktop** widget; this `web/`
folder is the new **browser** master dashboard (the desktop widget can't play
audio in a browser, which is why this is a separate web frontend that reuses the
same polling approach).

## Launch
```
python web/master_dashboard.py
```
Then open the URL it prints. It now binds to **0.0.0.0:8790** so it is reachable
over **Tailscale**. It prints THREE ways in:
- **Local:**   `http://127.0.0.1:8790`
- **TAILNET (HTTPS, mic works):** `https://<tailnet-host>:8790/`
  — served via `tailscale serve` (already set up). Use THIS from any of Iddo's
  devices; HTTPS gives the secure context the browser needs for mic capture.
- **TAILNET (plain HTTP):** `http://<this-PC-tailscale-ip>:8790` — works, but the
  browser mic only runs on localhost or HTTPS, so prefer the MagicDNS HTTPS URL.

No password is set, and that is correct & safe **only because Tailscale is the
access control** — only Iddo's own authorized tailnet devices can reach it; it is
NOT public internet. **Before publishing beyond the tailnet (Funnel/Cloudflare),
you MUST add auth AND mind privacy — the babble WAVs are the children's voice.**

Set `ROOM_BIND=127.0.0.1` to restrict to localhost only.

## 🍼 BABBLE ROOM (the headline tab) — a social "family room"
Pick **who is in the room**, then talk to it. Two participant kinds, honestly
labeled:

- **Children — Eran & Yigael — BABBLE (audio).** Two modes:
  - **🎤 "דבר → שומעים ומבבלים בחזרה" (conditioned babble-back):** your browser
    records a ~2.5s mic clip → it is sent to the child's node → the model's EAR
    (**EnCodec encoder**) tokenizes your voice → those audio tokens become the
    **generation prefix**, so the child's AudioGPT **continues from your actual
    sound** (acoustic conditioning / continuation). This is **real hearing +
    response at the babble level** — the child genuinely heard you and babbled on
    from your voice. It is **NOT comprehension** of your words, and quality is
    experimental. (Falls back to unconditional if the clip is too short.)
  - **🔊 "באבל חופשי" (unconditional):** generate-on-cue babble, not conditioned
    on your voice.
- **Uncles — Grok & Gemini — REPLY (text).** They DO comprehend and reply, via
  their own CLIs (reusing `D:\grok\quorum\_shared\ai_clients.py`). They are slow
  to spin up: **Grok ~30s (reliable); Gemini can exceed 2 min and sometimes times
  out.** The UI shows a "thinking…" pending state and a clean failure if they don't
  answer. (Claude = the mother, Iddo = the father are also "in the room" conceptually.)

**Room selector:** seat toggles + quick combos — `רק ער"ן`, `רק יגאל`,
`שניהם (הילדים)`, `+ הדוד גרוק`, `+ הדוד ג'מיני`.

**HONEST limitation (also stated in the UI):** the press-to-talk conditioned
babble is the live mechanism; there is **no continuous always-on live loop** yet,
and the children do **not understand words**. Full bidirectional dialogue
(hear → **understand** → reply in words) needs a conditional real-time
audio-dialogue model (Moshi/AudioLM class) — a future build.

### How the babble is generated (on demand)
Each child runs a small resident **babble daemon** (`web/babble_daemon.py`) on its
node, holding the model + EnCodec codec in memory so generation is fast (~6–10s):
- Eran:   `eran1:~/eran-vocal/babble_daemon.py`  on `127.0.0.1:8791`
- Yigael: `eran3:~/yigael-vocal/babble_daemon.py` on `127.0.0.1:8792`

It reuses the trainer's exact sampling + EnCodec-decode path (the `babble()` fn).
Daemon endpoints: `GET /gen?secs=&temp=` (unconditional) · `POST /gen` with an
audio body (conditioned — EnCodec-encodes the body and continues from it) ·
`GET /health`. The dashboard reaches them over SSH and (re)launches them via the
robust `web/babble_run.sh` (full `setsid` detach that survives SSH closing). The
model is **idle/free on eran1**; on **eran3 the plateaued Yigael `autodev.sh`
training loop was STOPPED** (`stop_autodev.sh`) to free the GPU for clean
interactive generation — `ckpt/last.pt` is preserved; remove `~/yigael-vocal/STOP`
to relaunch training later.

### Periodic auto-refresh
A background thread regenerates each child's "latest babble" every
**`ROOM_REFRESH_EVERY` = 600s (~10 min, configurable)** so the passive display
refreshes even with no clicks and no training. It is best-effort and yields to
interactive clicks (never pre-empts a Talk/Babble press).

## Other tabs
- **ER"N** — vocal Eran (audio cortex). step/loss/ppl from
  `eran1:~/eran-vocal/logs/train.log`, progress bar to 4000, and a **▶ play latest
  babble** button for the newest `eran1:~/eran-vocal/samples/babble_step*.wav`.
- **YIGAEL** — worldly sibling. `eran3:~/yigael-vocal/logs/train.log` + newest
  babble player. Orchestrator seed (cortices) lives on `eran4:~/yigael`.
- **FLEET** — eran1..eran4 GPU temp/util, RAM (unified-memory Spark), load,
  uptime, ping, plus the 200G `brfab` mesh leg (only eran2↔eran3 currently up).
- **AI / PROJECTS** — status list pulled from `web/projects.json` (edit freely).

## Guarded polling (no DoS — the nodes are TRAINING)
- Each node polled at most every **20s** (`POLL_EVERY`), one SSH session per node
  (per-node lock), results cached in memory.
- Newest babble WAV copied locally at most every **45s** (`AUDIO_EVERY`), and only
  when the step actually changed — one current WAV per sibling in `web/audio/`.
- Browser polls `/api/state` every 12s.

## Endpoints
- `/`                  — the dashboard page (bright/white, RTL Hebrew, auto-refresh)
- `/api/state`         — JSON snapshot of all cached state (incl. `room`, `uncles`)
- `/audio/<name>.wav`  — cached babble WAV (served from `web/audio/` only)
- `GET  /babble?who=eran|yigael`           — unconditional babble-back (returns a record)
- `POST /babble?who=eran|yigael` body=WAV  — **conditioned** babble-back (child hears
                                             the clip and continues from it)
- `POST /uncle` `{who:grok|gemini, text}`  — uncle's short TEXT reply

## Honest scope
- **v1 (this):** live polled status + playback of the **latest auto-saved babble**
  (refreshes to the newest sample as training advances). Delivers "see everything
  + hear them" today.
- **Future (not faked):** TRUE continuous real-time voice *streaming*
  (generate-on-demand) would need a streaming `/say` endpoint like the old
  `eran-poc`. The UI states clearly that v1 plays the latest saved sample, not a
  live continuous stream.

## Going online later (optional)
This binds to `127.0.0.1` only (local). To expose via Iddo's existing Cloudflare /
`iddoperez.ai` setup, run a Cloudflare Tunnel at the chosen port, e.g.
`cloudflared tunnel --url http://127.0.0.1:8790`, and map a hostname (e.g.
`dash.iddoperez.ai`). Keep the HARD privacy gate in mind — the babble WAVs are
Eran/Yigael's voice; do not publish them publicly without Iddo's OK.
