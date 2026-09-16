# ALMAWARE Cockpit UI — Design Spec

> 🪟 **BROKEN WINDOWS LAW:** if the cockpit shows stale data, a dead service, or a wrong colour → fix it IMMEDIATELY. `health: ok` is not proof; the tile must reflect the REAL last-updated file and REAL probe. Test the real output.

**Deliverable:** single self-contained `D:\CLAUDE\almaware-hud\cockpit.html`.
**Reads:** `D:\CLAUDE\almaware-hud\status.json` (published by the collector every 5 s).
**Refresh:** `fetch()` every 3 s; render diff-only.
**Target viewport:** 1920×1080, zero scrollbars. Degrades gracefully to 1366×768.
**Theme:** ALMA dark, gold accent, cream text.

---

## 1. Wireframe (1920×1080)

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│  ⬢  ALMAWARE COCKPIT      swarm/alma-language-4 · 3558b95                    16:07:39  🟢    │  ← HEADER  h=56
│                                                                    last status 4s ago       │
├────────────────────────────────────┬────────────────────────────────────────────────────────┤
│  🧠  ERAN — byte-LM (live)         │  🖧  FLEET                                             │
│                                    │  ┌──────────┬──────────┬──────────┬──────────┐        │
│  step  506,280       loss 0.4345   │  │  eran1   │  eran2   │  eran3   │  eran4   │        │  ← ROW A  h=280
│  ema   0.4371        sps  5.1      │  │  🟢 UP   │  🟢 UP   │  🟢 UP   │  🟠 GPU  │        │
│  tps   10k           vram 285 MB   │  │ 52°C 9%  │ 54°C 0%  │ 48°C 0%  │ 77°C 92% │        │
│  🟢 chat online (:8792)            │  │ up 157h  │ up  49h  │ up  49h  │ up  49h  │        │
│  ─── LATEST BABBLE ───             │  │llama-svr │rpc-server│rpc+dns   │  (none)  │        │
│  ▸ אבא… → "…תסדר את                │  │          │ HUB      │          │ orphan?  │        │
│    האפליקציה של המיקרופון…"        │  └──────────┴──────────┴──────────┴──────────┘        │
│                        step 505,100│  click any card → SSH shortcut copy                    │
├────────────────────────────────────┼────────────────────────────────────────────────────────┤
│  🕸  QSFP FABRIC                   │  🛠  SERVICES                                          │
│                                    │                                                        │
│    eran1 ═══200G═══ [eran2] ══200G ═╡  ● grok-1 head   :8080  <tailnet-ip>   🟢 4 slots   │  ← ROW B  h=260
│      ║               HUB              │  ● grok-1 shim   :8899                🟢 up         │
│      · (spare 200G)  ║                │  ● eran-chat     :8792                🟢 200        │
│                      · (spare 200G)   │  ● rpc eran2     :50052               🟢 pid 2094… │
│                     eran3 ─10G─ eran4 │  ● rpc eran3     :50052               🟢 pid 2964… │
│                     ▲               ▲ │  ● chrome CDP    :9222                🔴 down       │
│    green=UP+IP  grey=UP+no-IP  red=DN │                                                     │
├────────────────────────────────────┴────────────────────────────────────────────────────────┤
│  🧩  PROJECTS  (sort: status · priority · touched)     [active 20] [dormant 12] [plan 10]   │
│                                                                                             │
│  ┌──────────┬──────────┬──────────┬──────────┬──────────┬──────────┬──────────┬──────────┐ │
│  │🟢 eran-  │🌟 eran-  │🟢 shisha │🟢 percept│🟢 physic │🟢 alma-  │🟢 alma-  │🟢 grok1- │ │  ← ROW C  h=280
│  │  live    │  charter │  brain   │  n-movie │  al-wgts │  language│  govern  │  private │ │
│  │north-star│ shipped  │north-star│ high  0d │ high  0d │ high  0d │ high  1d │ high  0d │ │
│  ├──────────┼──────────┼──────────┼──────────┼──────────┼──────────┼──────────┼──────────┤ │
│  │🟢 grok-  │🟢 grok-  │🟢 memri- │🟢 alma-  │🟢 alma-  │🟢 iddo-  │🟢 fleet  │🟢 alma-  │ │
│  │  web…    │  coder   │  st-pedal│  mic     │  fed.    │  perez   │          │  hud     │ │
│  ├──────────┼──────────┼──────────┼──────────┼──────────┼──────────┼──────────┼──────────┤ │
│  │🟡 eran-  │🟡 alma-  │🟡 lora-  │🟡 quorum │🟡 wa-mcp │🟡 alma-  │🟡 memri- │🟡 cave-  │ │
│  │  robot   │  talmud  │  mesh    │          │          │  ozen    │  st-brain│  wall    │ │
│  ├──────────┼──────────┼──────────┼──────────┼──────────┼──────────┼──────────┼──────────┤ │
│  │⚪ eran-  │⚪ eran-  │⚪ eran-  │⚪ alma-  │⚪ alma-  │⚪ ram-   │⚪ noam   │⚪ misc-  │ │
│  │  grid    │  cloud   │  play    │  linux   │  iff     │  tri-chat│          │  dormant │ │
│  └──────────┴──────────┴──────────┴──────────┴──────────┴──────────┴──────────┴──────────┘ │
│  click tile → open project.path in Explorer                                                 │
├─────────────────────────────────────┬────────────────────────────┬──────────────────────────┤
│  ✅ TODO / NEXT ACTIONS             │  📁 GIT STATUS             │  🔄 WORKFLOW              │
│                                     │                            │                          │
│  □ commit fleet_health_check.sh 🔴  │  branch swarm/alma-lang-4  │  wf_b4ff0d78-647          │  ← ROW D  h=224
│  □ commit standard-site-en.html 🔴  │  ahead — · main main       │  peretz-inquiry…         │
│  □ verify eran-audio config edit    │  ● 7 modified              │                          │
│  □ audit shim swap grok1_shim.py    │  ● 1 submodule dirty       │  ▓▓▓▓▓▓▓▓░░  4 / 5 done  │
│  □ decide memristor-pedal weave     │  ● 1,476 untracked  ⚠      │                          │
│  □ eran4 GPU 92% — whose workload?  │  ● 0 staged                │  ✓ perceptron-movie      │
│  □ QSFP spare → wire eran1↔eran3    │                            │  ✓ links reconciliation  │
│                                     │  recent:                   │  ✓ eran babble audio     │
│                                     │  3558b95 grid-dashboard…   │  ✓ psytrance v3 plan     │
│                                     │  a925099 shisha 3x3 grid…  │  ⟳ grok-1 memory inject  │
│                                     │  508a4f3 9-memristor …     │     (running · 16:08)    │
└─────────────────────────────────────┴────────────────────────────┴──────────────────────────┘
```

Grid: `header (56) → A (280) → B (260) → C (280) → D (224)` sums to 1100 → padding 20+20 = 1140, i.e. designed for 1080 with a 60px scroll safety margin. If viewport < 1080, D collapses to `h=180` and its three columns get an internal `overflow-y: auto`.

---

## 2. Data contract — `status.json`

The collector merges the seven `recon/*.json` files (already present) plus a live probe pass into ONE object. Field names below are what the UI reads. Any missing field must render as the string `"—"` and a grey dot; the UI never throws.

```jsonc
{
  "meta": {
    "generated_at": "2026-07-11T16:07:39+03:00", // ISO8601 with tz
    "generated_at_epoch_ms": 1783041859000,      // for age computation
    "collector_version": "1.0.0",
    "collector_uptime_s": 12345,
    "stale_after_s": 30                          // UI paints header red past this
  },

  "eran": {
    "step": 506280,
    "loss": 0.4345,
    "ema": 0.4371,
    "sps": 5.1,
    "tps_k": 10,                                 // 10k tok/s
    "vram_mb": 285,
    "lr": 3.0e-5,
    "alive": true,                               // training process still logging
    "last_log_ts": "2026-07-11T16:06:01",
    "chat_up": true,                             // :8792 200 OK
    "chat_url": "http://127.0.0.1:8792/",
    "chat_port": 8792,
    "checkpoint": {
      "path": "D:\\CLAUDE\\eran-live\\checkpoints\\latest.pt",
      "mtime": "2026-07-11T16:06:32",
      "size_mb": 37.36
    },
    "babble": {
      "text": "…תסדר את האפליקציה של המיקרופון הקדוש ש",   // latest sample, may be Hebrew/English/mixed
      "step": 505100,
      "ts": "2026-07-11T16:03:17",
      "age_s": 262
    }
  },

  "fleet": {
    "nodes": [                                    // ALWAYS length 4, in order eran1..eran4
      {
        "id": "eran1",
        "hostname": "eran1",
        "up": true,
        "role": "compute + LAN gateway",
        "reachable_via": "LAN <lan-ip>",
        "uptime_h": 157,
        "gpu_temp_c": 52,
        "gpu_util_pct": 9,
        "load1": 0.36,
        "mem_used_g": 95,
        "mem_total_g": 121,
        "disk_root": "1.8T/3.6T 51%",
        "procs": ["llama-server"],
        "warning": null                           // string if UI should paint orange
      },
      // eran2..eran4 identical shape
    ]
  },

  "fabric": {
    "edges": [                                    // canonical L2/L3 links
      {
        "from": "eran1",
        "to": "eran2",
        "speed_mbps": 200000,
        "medium": "QSFP DAC",
        "ip_configured": true,
        "carrier": true,                          // link light
        "role": "active",                         // "active" | "spare" | "uplink"
        "kind": "qsfp"                            // "qsfp" | "rj45"
      }
      // ... 5 edges total per recon/fabric.json
    ],
    "hub": "eran2"                                // rendered larger, centred
  },

  "services": [
    {
      "id": "grok1_head",
      "label": "grok-1 head",
      "url": "http://<tailnet-ip>:8080",
      "port": 8080,
      "up": true,
      "state_text": "4 slots",
      "click_url": "http://<tailnet-ip>:8080/"   // what to open on tile click
    },
    { "id": "grok1_shim",  "label": "grok-1 shim",  "port": 8899, "url": "http://127.0.0.1:8899", "up": true, "state_text": "up",             "click_url": "http://127.0.0.1:8899/" },
    { "id": "eran_chat",   "label": "eran-chat",    "port": 8792, "url": "http://127.0.0.1:8792", "up": true, "state_text": "200",            "click_url": "http://127.0.0.1:8792/" },
    { "id": "rpc_eran2",   "label": "rpc eran2",    "port": 50052,"host": "eran2", "up": true, "state_text": "pid 2094466", "click_url": null },
    { "id": "rpc_eran3",   "label": "rpc eran3",    "port": 50052,"host": "eran3", "up": true, "state_text": "pid 2964180", "click_url": null },
    { "id": "chrome_cdp",  "label": "chrome CDP",   "port": 9222, "url": "http://127.0.0.1:9222/json", "up": false, "state_text": "run CHROME-DEBUG.bat", "click_url": null }
  ],

  "projects": [
    {
      "id": "eran-live",
      "name": "Eran (byte LM, live)",              // WITHOUT leading emoji — UI picks emoji by status
      "emoji": "🟢",                                // optional override
      "status": "active",                           // "active" | "dormant" | "planning" | "shipped"
      "priority": "north-star",                     // "north-star" | "high" | "medium" | "low"
      "last_touched_days": 0,
      "path": "D:\\CLAUDE\\eran-live",              // click opens this in Explorer via file:// link
      "next_action": "keep training on DGX + wire Grok-1 to know his current step/loss",
      "notes": "44 files, logs/metrics.jsonl updated today"
    }
    // ... ~45 projects per recon/projects.json
  ],

  "todo": [                                        // synthesized from projects[].next_action + git.recommendations
    { "text": "commit alma-govern/fleet_health_check.sh (stale IP fix)", "severity": "critical", "source": "git" },
    { "text": "commit almaware-standard-site-en/index.html (broken HTML fix)", "severity": "critical", "source": "git" },
    { "text": "verify eran-audio config.json edit (0.95→0.65 temperature)", "severity": "review", "source": "git" },
    { "text": "audit grok1_shim.py swap (.bak-20260711 alongside)", "severity": "review", "source": "git" },
    { "text": "decide memristor-pedal — standalone or in alma-language weave", "severity": "decide", "source": "project" },
    { "text": "eran4 GPU 92% at 77°C — identify workload", "severity": "warn", "source": "fleet" },
    { "text": "wire QSFP spare eran1↔eran3 (mesh fragility fix)", "severity": "warn", "source": "fabric" }
  ],

  "git": {
    "branch": "swarm/alma-language-4",
    "main_branch": "main",
    "commits_ahead_of_main": null,                 // rendered as "—" if null
    "modified_unstaged": 7,
    "staged": 0,
    "submodule_dirty": 1,
    "untracked": 1476,
    "untracked_warn_threshold": 500,               // UI paints orange if exceeded
    "recent_commits": [
      { "sha": "3558b95", "subject": "grid-dashboard: reservoir training layer…" }
      // ... 3–5 entries
    ]
  },

  "workflow": {
    "id": "wf_b4ff0d78-647",
    "name": "peretz-inquiry-and-deliver",
    "phases_total": 5,
    "phases_done": 4,
    "phases_running": 1,
    "recon_at": "2026-07-11T16:09:00+03:00",
    "agents": [
      { "id": "a1a248d0…", "role": "Perceptron movie / Grok Imagine prompts",   "status": "completed" },
      { "id": "a73728fc…", "role": "Clickable-links memory + Stop-hook",        "status": "completed" },
      { "id": "acade4cd…", "role": "Eran authentic byte-to-tone babble",        "status": "completed" },
      { "id": "a3e688dd…", "role": "Psytrance music v3 post-mortem + plan",     "status": "completed" },
      { "id": "a969b00e…", "role": "Commissioner 5 — Grok-1 memory injection",  "status": "running",  "started_ts": "2026-07-11T16:08" }
    ]
  }
}
```

**Invariants the UI relies on:**
- `fleet.nodes` is length 4, order `eran1..eran4`.
- `fabric.edges` includes both active AND spare links (spare = `ip_configured:false, carrier:true`).
- `projects` items are safe to sort by `(status_rank, priority_rank, last_touched_days)` where status_rank = `active=0, shipped=0, planning=2, dormant=3` and priority_rank = `north-star=0, high=1, medium=2, low=3`.
- All timestamps carry timezone offsets; the UI never assumes UTC.
- Any field can be `null`/missing; UI renders `"—"` with the muted colour.

**Stale check:** if `(Date.now() - meta.generated_at_epoch_ms) / 1000 > meta.stale_after_s`, the header dot goes RED and the last-updated string paints `--red`.

---

## 3. CSS design tokens

```css
:root {
  /* palette */
  --bg:          #0d0a1a;
  --panel:       #141028;
  --panel-2:     #1a1533;   /* elevated card */
  --panel-edge:  #221a3a;
  --text:        #e8edf4;   /* cream */
  --muted:       #8a8172;
  --gold:        #f4d06a;   /* ALMA */
  --gold-dim:    #b89b4c;
  --green:       #3ad07a;
  --orange:      #ffb43a;
  --red:         #ff5a5a;
  --purple:      #8e44ad;
  --blue:        #4aa8ff;
  --link-hover:  #ffd680;

  /* status → colour */
  --status-active:    var(--green);
  --status-shipped:   var(--gold);
  --status-planning:  var(--blue);
  --status-dormant:   var(--muted);
  --status-critical:  var(--red);
  --status-warn:      var(--orange);

  /* type */
  --font-ui:   "Segoe UI", system-ui, -apple-system, sans-serif;
  --font-mono: "Consolas", "JetBrains Mono", ui-monospace, monospace;

  /* type scale */
  --fs-hd:  20px;   /* header title */
  --fs-h1:  15px;   /* row title (🧠 ERAN…) */
  --fs-h2:  11px;   /* small section title */
  --fs-body:13px;
  --fs-mono:12px;
  --fs-tile:10.5px; /* project tile label */
  --fs-num: 22px;   /* big number (loss, step) */

  /* geometry */
  --radius:    10px;
  --radius-sm: 6px;
  --pad-panel: 14px;
  --gap:       12px;
  --row-gap:   12px;
  --header-h:  56px;

  /* motion */
  --pulse: pulse 2s ease-in-out infinite;
}

@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.55} }

/* dot */
.dot { width:8px; height:8px; border-radius:50%; display:inline-block; vertical-align:middle; }
.dot--green  { background: var(--green);  box-shadow: 0 0 6px var(--green); }
.dot--red    { background: var(--red);    box-shadow: 0 0 6px var(--red); animation: var(--pulse); }
.dot--orange { background: var(--orange); box-shadow: 0 0 6px var(--orange); }
.dot--muted  { background: var(--muted); }
```

Font sizes were picked so the whole page fits 1920×1080 without a scrollbar and stays legible from a 65-inch TV two metres away (Iddo's viewing distance).

---

## 4. Layout system

- Root: `body { display: grid; grid-template-rows: var(--header-h) 280px 260px 280px 224px; grid-gap: var(--row-gap); padding: 20px; height:100vh; overflow:hidden; }`
- Row A: `grid-template-columns: 480px 1fr;`
- Row B: `grid-template-columns: 1fr 460px;`
- Row C: full-width panel, inner `grid-template-columns: repeat(8, 1fr); grid-auto-rows: 60px;`  (4 rows × 8 cols = 32 tile slots; overflow tiles collapse into a "+N more" pill in slot 32).
- Row D: `grid-template-columns: 1.2fr 1fr 1fr;`

Every panel: `background: var(--panel); border-radius: var(--radius); padding: var(--pad-panel);` with a 1-px `--panel-edge` inner border.

Panel title: uppercased, `letter-spacing:.08em; color: var(--muted); font-size: var(--fs-h2);` sits at the top-left, no border.

---

## 5. Component list (implementation checklist)

Each component is a plain function returning an HTML string (or DOM node). No framework; vanilla JS module. All components accept a slice of `status.json` and return a rendered panel. Names below are the exported symbols the implementer must define.

| # | Component | Reads | Emits | Interaction |
|---|-----------|-------|-------|-------------|
| 1 | `Header(meta, git)` | `meta.generated_at`, `git.branch`, `git.recent_commits[0].sha`, staleness | title + branch + last-updated + running clock + status dot | none |
| 2 | `EranTile(eran)` | full `eran` object | step/loss/ema/sps/tps/vram + chat pill + babble box with Hebrew RTL detection | click → `window.open(eran.chat_url)` |
| 3 | `FleetCard(node)` × 4 | one `fleet.nodes[i]` | up/down dot, temp with orange >70°C / red >80°C, util bar, uptime, procs | click → copies `ssh <node.id>` to clipboard, toast "SSH copied" |
| 4 | `FleetRow(fleet)` | `fleet.nodes` | flex row of 4 `FleetCard` | — |
| 5 | `FabricMap(fabric)` | `fabric.edges`, `fabric.hub` | inline SVG 700×220, nodes as rounded rects, edges as lines (green=active+IP, gold-dim=spare, red=down, dashed=RJ45) | hover edge → tooltip `speed / medium / role` |
| 6 | `ServicesList(services)` | `services[]` | flat rows: dot + label + port + state text | click row (if `click_url`) → `window.open` |
| 7 | `ProjectTile(project)` | one project | emoji by status, name (truncated), priority + `Xd` since touch, tooltip = `next_action` | click → open `file:///` + `project.path` |
| 8 | `ProjectsGrid(projects)` | `projects[]` | sorted grid of 32 `ProjectTile` + tab filters `[active][dormant][planning] [all]` and overflow "+N more" pill | click filter → re-renders grid |
| 9 | `TodoList(todo)` | `todo[]` | checkbox list; severity dot before each row | click checkbox → strikethrough only (client-only, no persistence in v1) |
| 10 | `GitPanel(git)` | full `git` | branch line, counters (red pulse if `modified_unstaged>0`, orange if `untracked > untracked_warn_threshold`), 3 most-recent commits | click sha → `navigator.clipboard.writeText(sha)` |
| 11 | `WorkflowPanel(workflow)` | full `workflow` | id + name + progress bar (`phases_done/phases_total`) + agent list w/ ✓ / ⟳ | ⟳ rows pulse gold |
| 12 | `App(status)` | root | grid layout + all children | own the fetch loop |

**Fetch loop (in `App`):**
```js
async function tick() {
  try {
    const r = await fetch('status.json?t=' + Date.now(), { cache: 'no-store' });
    if (!r.ok) throw new Error(r.status);
    const s = await r.json();
    render(s);
    lastOk = Date.now();
  } catch (e) {
    markHeaderStale(e);
  } finally {
    setTimeout(tick, 3000);
  }
}
```
- The UI keeps rendering the last good `status` if a fetch fails; the header dot goes RED after `meta.stale_after_s`.
- `render(s)` diffs by JSON.stringify per component slice (cheap enough for this size); components only re-render if their slice changed.

**Wall clock:** independent 1 s `setInterval` updates the `HH:MM:SS` in the header; no fetch coupling.

---

## 6. Interaction contract (opens & clipboards)

| Target | Action | Notes |
|--------|--------|-------|
| Eran tile | opens `http://127.0.0.1:8792/` | new tab |
| Fleet card | copies `ssh <id>` to clipboard, shows toast for 1200 ms | no auto-connect |
| Fabric edge | tooltip on hover | no click |
| Service row w/ `click_url` | opens URL in new tab | otherwise cursor stays default |
| Project tile | opens `file:///D:/CLAUDE/...` in a new tab | Chrome will prompt to open Explorer — acceptable |
| Git sha | copies sha to clipboard, toast | |
| Todo checkbox | strikes through the row | session-only; no writes |

Toast component: fixed bottom-centre, `background: var(--panel-2); color: var(--gold);` 1200 ms fade.

---

## 7. Colour rules (single source of truth)

```
status = active     → 🟢 green
status = shipped    → 🟡 gold
status = planning   → 🔵 blue
status = dormant    → ⚪ muted grey

fleet up            → green
fleet up, gpu >70°C → orange
fleet up, gpu >80°C → red pulse
fleet down          → red pulse

fabric edge:
  carrier + ip      → green solid
  carrier + no-ip   → gold-dim dashed  (spare)
  no carrier        → red dashed
  RJ45 medium       → thinner stroke   (0.5x)

service up          → green
service down        → red pulse

todo severity:
  critical          → red
  warn              → orange
  review            → gold
  decide            → blue
```

---

## 8. Rendering rules

- **Hebrew:** any node in `.babble-text`, `.project-name`, `.todo-text` gets `dir="auto"` so RTL is auto-detected per string.
- **No horizontal scroll ever.** Text overflow uses `text-overflow: ellipsis` with `title=` for full text.
- **No emoji-only signals:** every emoji is paired with a colour or word. Colour-blind rule.
- **Reduced motion:** `@media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation: none !important; } }` — pulse becomes solid.
- **Zero external assets.** No CDN, no web fonts, no images. Emoji from system font.
- **CSP-safe self-contained HTML:** all CSS in one `<style>`, all JS in one `<script>`. No `eval`, no dynamic script tags.

---

## 9. Fallbacks & failure modes

| Situation | Behaviour |
|-----------|-----------|
| `status.json` missing | header dot red, all panels show `"—"`, banner: `waiting for collector…` |
| `status.json` malformed JSON | keep previous state, header banner: `stale — parse error at HH:MM:SS` |
| Individual key missing | `"—"` in that field only; component still renders |
| Clock skew (generated_at in the future) | render as-is; do not throw |
| `projects.length > 32` | show first 31 tiles + `+N more` tile that expands the projects panel into a scrollable modal on click |
| `fabric.edges` empty | show text `"no fabric data"` in the SVG area |

---

## 10. File layout the implementer must produce

```
D:\CLAUDE\almaware-hud\
├── cockpit.html          (this design — single file, self-contained)
├── status.json           (produced by collector every 5 s — NOT this task)
└── design\
    └── cockpit_design.md (this document)
```

Implementer must NOT touch `hud.py` (the Tk widget) or `recon/*.json` (collector inputs). This build phase is UI only.

---

## 11. Acceptance criteria (for verification phase)

1. Open `cockpit.html` locally at 1920×1080 — no scrollbars, no console errors.
2. Panels populate from a hand-written `status.json` that matches §2.
3. Fetch fails once → header goes red within `stale_after_s`; next successful fetch clears it.
4. Every clickable target does what §6 says (verified with mock).
5. All 32 project tiles fit; overflow pill shows a real count.
6. Renders correctly at 1366×768 (row D collapses, everything else stays visible).
7. Hebrew babble sample renders RTL without mangling adjacent English.
8. `@media (prefers-reduced-motion)` kills all pulses.
9. `.html` file size < 60 KB (single file, self-contained, hand-authored).
10. Zero network requests other than `status.json?t=...`.

---

## 12. Explicit non-goals (v1)

- No auth. Local-only file, opened directly.
- No write actions. Todo checkboxes are session-only.
- No history / trend graphs. That is a v2 tile.
- No mobile layout.
- No dark/light toggle — always dark ALMA.
- No SSE / websockets — 3 s polling is enough at this scale.

---

**Signed off as spec.** Next phase: build `cockpit.html` from this doc alone. If the implementer needs a field not in §2, they extend §2 and update the collector spec — they do not invent fields silently.
