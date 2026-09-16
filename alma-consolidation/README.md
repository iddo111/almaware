# ALMA CONSOLIDATION — the private hub on :8896

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

Iddo's private master dashboard. 100% stdlib, no framework, no CDN.
Bound to `0.0.0.0:8896`, gated by a token (`?key=` → HttpOnly cookie), published to the
tailnet only. Started at logon by `Startup\ALMA-MasterDashboard-8896.lnk`
(`pythonw.exe private_hub.py`, hidden, BELOW_NORMAL).

| file | what |
|---|---|
| `private_hub.py` | the server: token gate, the catalogue page, `/media/<id>` range streaming, POST routing |
| `control.py` | the CONTROL page + state + the whole action space + the background prober |
| `one_place.py` | devices · models · ask-any-model · the RAMCHAT work queue |
| `fleet_models.py` | the model ledger and the MONOLITH/COUNCIL/GIANTS switch |
| `hub_token.txt` | the access token. Never copy it into a document, a post or a commit. |
| `control-audit.jsonl` | one line per action, forever |

Pages: `/` the catalogue · `/control` the dashboard.
APIs: `GET /control/api/state` · `GET /control/api/audit` ·
`POST /control/api/action` · `POST /control/api/ask` · `POST /control/api/queue`.

---

## 2026-09-11 — WAVE B3: CONTROL becomes THE ONE PLACE

Iddo, 04:52: one page, from the phone, in Thailand — all the devices, all the work,
any model. 08:29 "do all 13 upgrades in your order", 08:34 "לאט ובטוח, בנייה חזקה".

### 0. The broken window found on the way in
**The whole page script had been ONE SyntaxError since 2026-09-09** — a raw newline
inside the JS string of the coder-train confirm text. The server could not see it: the
HTML was valid, the response was 200, `curl` looked perfect, and every tile on the page
was frozen on its static `…` placeholder with every button dead. Found by actually
rendering the page in a browser at 375 px instead of trusting the HTTP code.

Two guards so it cannot come back silently:
* `control.check_page_js()` parses every `<script>` block with `node --check`;
  `private_hub.py` runs it at every start and writes the verdict to the audit log
  (`action: "page.js.check"`).
* A **separate** tiny `<script>` before the main one installs a `window.onerror`
  handler, so a syntax error in the big block paints a red banner on the page itself.

### 1. Fast render — probing moved off the request path
Before: **5.0 s** on a cold open (11 HTTP door probes + 3 SSH round trips to eran2/3/4
+ the 480B health check, all inside the GET; the internal 20–25 s caches always expired
between phone visits). After: **0.009–0.021 s, every time**, including `?force=1`.

A daemon thread owns freshness in two tiers, because they cost very different things:

| tier | what | while he is looking | while nobody is |
|---|---|---|---|
| FAST | door tiles, the 33 inventory doors, the model list, `tailscale status` | every 25 s | every 300 s |
| SLOW | SSH into eran2/3/4, the 480B health, the model ledger | every 60 s | **never** |

"Looking" = a `/control` or `/control/api/state` in the last 3 minutes. The page states
its own measurement age in the header, so stale is visible, never pretended.
The cheap half (KESHEV's state files, `status.json`, the RAMCHAT tail, the queue) is
still read per request — local files, under 20 ms, and PAUSE/LISTEN must answer instantly.

### 2. המכשירים — DEVICES
All 10 hosts of `D:\CLAUDE\fleet_inventory.json` (pc, s26, quest, a70, eran1-4,
hp-laptop, printer): online/offline from `tailscale status --json` (cached 60 s), last
seen in Hebrew, LAN + tailnet address + MagicDNS, the one-line role, and every door that
host owns as a live pill. Loopback-only doors are greyed and labelled **PC only** —
honest about what the phone cannot reach. Measured now: 7/10 online, 31/33 doors.

### 3. Models — ONE list
The union, 26 seats, each with a live pill from a probe-per-BASE (not per model):
the fleet's OpenAI-compatible doors from the inventory, every resident ollama model on
eran4 and on the PC, `claude` sonnet/opus/haiku, `openai:gpt-*` (only when
`OPENAI_API_KEY` is in the environment), and anything in QUORUM's hot-reloadable
registry. The choice is remembered in a cookie.

**Keys never reach the browser.** The page sends an opaque id; the server looks the
endpoint up in its own table and adds the `Authorization` header itself.

**A seat never vanishes because a door was slow.** Every enumerating source keeps its
last good answer and is backed off for 120 s after a failure, so the dropdown does not
reshuffle under his thumb — the seats stay and go red instead. Proven by simulating a
total network outage: 26 seats before, 26 during (3 live — the local Claude CLI seats,
presence-based and labelled as such), 26 after.

### 4. Chat — `POST /control/api/ask`
`{model, text}` → the server calls the chosen door: OpenAI-compatible
`/v1/chat/completions` for fleet/ollama/openai/nvidia, and for Claude the pattern
`wa-chat-agent\claude_brain.py` uses — `claude -p --model X --output-format text
--safe-mode --tools "" --strict-mcp-config`, prompt on stdin, BELOW_NORMAL, no tools at all.

Gates, all measured: the HttpOnly cookie, the token in the body, **and** a per-process
`X-CSRF-Token` (the `:8941` pattern); 4 KB per question; 20 questions per minute.
The audit row carries the model and the character counts — **never the question text,
never a key**.

### 5. העבודה — the work queue
The RAMCHAT tail (12) plus the open queue, with קח / סיימתי buttons that shell out to
`ramlink.py` itself — that is where the atomic lock lives — as
`iddo (control page)`. Task ids are validated against `^task-[...]$` before anything runs.

### 6. Phone-first
`dir=rtl`, `viewport-fit=cover`, 46 px minimum buttons that go full-width under 520 px,
`<details>` sections so the long panels fold away, bright/white per Iddo's rule.
Verified by rendering at 375×812, not by reading the CSS.

### What is deliberately still absent
No endpoint starts, stops or restarts ERAN (eran1 `eranb-life`) or DARWISH
(eran4 `dmidi-life`/`dmidi-tap`). Not hidden — absent. Every SSH target is a literal in
`FLEET_ALIASES = ("eran2","eran3","eran4")`; no function takes a hostname from a request.
The KESHEV pause/listen code is byte-identical to what it was before this wave.

### The URL Iddo opens on the phone
`https://<tailnet-host>:8896/control` — with the `?key=` from the Desktop
shortcut *MASTER DASHBOARD (remote).url*. It answers in 22 ms from a remote tailnet node.
