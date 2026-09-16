# Projects Health Recon — 2026-07-11

> 🪟 If it's not working, fix it IMMEDIATELY. Test the REAL output, not a proxy.

Recon of ~45 projects mapped from `MEMORY.md`. Days = age of newest activity in the directory root, not the deepest file. Session-touched work highlighted first.

Legend: 🟢 active (0–2d) · 🟡 recent (3–5d) · 🟠 dormant (6–14d) · 🔴 stale (15d+) · 🧊 planning (no dir).

---

## Session-touched THIS session (last ~2h)

| Project | Path | Signal |
|---|---|---|
| 📊 **almaware-hud** | `D:\CLAUDE\almaware-hud` | this recon lives here |
| 🎛️ **memristor-pedal** | `D:\CLAUDE\alma-language\memristor-pedal` | brand-new subdir, `index.html` ~1h old |
| 🤖 **grok1-private-stack** | `D:\CLAUDE\grok1_shim.py` (+`.bak-20260711`) & `D:\CLAUDE\grok1-chat` | shim edited today, backup alongside |
| 🐦 **grok-web-claws** | `D:\CLAUDE\grok-web-claws` | touched today |
| 💻 **grok-coder** | `D:\CLAUDE\grok-coder` | touched today |
| 🎬 **perceptron-movie** | `D:\CLAUDE\perceptron-movie\music\v3_technical_plan.md` | fresh v3 plan today |
| 🖥️ **fleet** | `D:\CLAUDE\fleet` | touched today (with almaware-hud) |
| 🌐 **alma-federation** | `D:\CLAUDE\alma-federation` | touched today |

Uncommitted per `git status`: `alma-govern/fleet_health_check.sh`, `alma-language/crossbar3d/index.html`, `alma-language/perceptron3d/index.html`, `eran-audio/config.json`, `lora-mesh/sent/m1.txt`, plus `.claude/launch.json`.

Recent commits (last 8) are dominated by **shisha-lab** (reservoir training, crossbar, ALMA Perceptron Mark I, sound-card FDM) and **alma-language** (perceptron3d, crossbar3d) — the memristor + physical-weights weave is the current momentum.

---

## 🧠 Eran (north star)

| Status | Project | Days | Path | Next |
|---|---|---|---|---|
| 🟢 | 🟢 Eran (byte LM, live) | 0 | `eran-live` | keep training + expose current step/loss to Grok-1 |
| 🟢 | 📜 Eran Charter | doc | memory | reference; changes need Beit Din |
| 🟢 | 🔊 Eran audio | 0 | `eran-audio` | resolve uncommitted `config.json` |
| 🟡 | 🔧 Eran hardware (DGX Spark) | 5 | `eran-hardware` | re-verify 3-node FSDP is still green |
| 🟠 | ⚡ ERAN-GRID (idle harvest) | 5 | `eran-grid` | audit worth vs DGX load |
| 🟠 | ☁️ Eran cloud | 5 | `eran-cloud` | decide overlap with alma-federation |
| 🟠 | 📊 Eran dashboard | 7 | `eran-dashboard` + `eran-local-dashboard` | pick one, kill the other |
| 🟠 | 🧬 Alma brain sim | 7 | `alma-brain-sim` | keep as reference sim while shisha-brain does the real analog |
| 🧊 | 🤖 Eran robot body | (rc-car-pico 9d) | `rc-car-pico` | consolidate rc-car-pico + eran-hardware into single embodiment plan |
| 🧊 | 🎨 Eran playroom / cognitive-map / third-eye / imagination | — | none | spec sensory surface before code |

---

## 🧠🌊 Physical AI / Shisha / Memristors (hottest cluster)

| Status | Project | Days | Path | Next |
|---|---|---|---|---|
| 🟢 | 🧠🌊 **Shisha Brain** | 0 | `shisha-lab` | validate reservoir training layer just committed |
| 🟢 | ⚖️🏋️ **Physical-Weights AI** | 0 | `shisha-lab` (ALMA Perceptron Mk I) | verify servo-driven weights actually train |
| 🟢 | 🧩 **ALMA Language** (perceptron3d + crossbar3d + memristor-pedal) | 0 | `alma-language` | 3 sub-weaves diverging — pick a target |
| 🟢 | 🎛️ Memristor pedal | 0 | `alma-language\memristor-pedal` | decide standalone vs weave |
| 🟠 | ⚡🧲 Memristor grid | 8 | `memristor-grid` | fold into shisha-brain, keep as history |
| 🟠 | ⚡🔌 PROTONEURON | 9 | `protoneuron` | revisit after reservoir results |
| 🟠 | 🌻 Sunflower / motor / self-learning neurons | 8–9 | `sunflower-neuron`, `motor-neuron`, `self-learning-neuron` | archive OR fold under shisha-brain |
| 🟠 | ⚡🕳️ Electric brain / Cave-wall brain | 3–8 | `cave-wall-brain-sim` (3d), `electric-brain` (8d) | cave-wall alive; electric-brain candidate for merge |
| 🟠 | 🔯 Choshen (optical) | closest = `optical-nn` (7d) | — | spec only |
| 🟠 | 🧠 Almaware brain lab | 11 | `almaware-brain-lab` | look at content, merge into shisha-lab |

---

## 🏛️ ALMAWARE products / platform

| Status | Project | Days | Path | Next |
|---|---|---|---|---|
| 🟢 | 🏛️ ALMA-Govern | 1 | `alma-govern` | commit or revert pending `fleet_health_check.sh` |
| 🟢 | 🎙️ ALMA-MIC (+release) | 1 / 3 | `alma-mic`, `alma-mic-release` | verify owner-only capture guarantee |
| 🟢 | 🌐 ALMA Federation | 0 | `alma-federation` | reconcile with `federation-site/` (1d) |
| 🟢 | 🕯️ ALMA תלמוד | 2 | `alma-talmud` | paused per memory; first slice OK |
| 🟡 | 🌐 iddoperez portal | 3 | `iddoperez-portal` | check overlap with `federation-site/`, `almaware-standard-site-en/` (0d) |
| 🟡 | 🗺️ Master whiteboard / modeler | 6 | `master-modeler` | this IS the WIP=1 tool — revive |
| 🟡 | 🗳️ Quorum family | 3 / 3 / 8 | `quorum`, `ram-council`, `fleet-quorum` | REUSE law violated — collapse to one |
| 🟠 | 👂 ALMA-Ozen (Hebrew ASR) | 9 | `alma-ozen` | revive when heb-mic / pedal needs live text |
| 🟠 | 🤍 ALMA Voice + VR | 6 | `voice-input` | fold with alma-mic + alma-ozen? |
| 🟠 | 🛡️ ALMA-IFF | 4 | `alma-iff` | HOLD FIRE — no capability |
| 🟠 | 🖥️ ALMA-OS Jetson | 6 | `jetson-lean-os` | flash-ref refresh |
| 🧊 | 🐧 ALMA-Linux PC | — | none | plan-only |
| 🧊 | 🩺 ALMA Smart Care | — | none | backlog |
| 🧊 | 🎮 Army of Gamers | — | none | concept-only |
| 🧊 | 📖 Rabbi Nachman RAG (:8783) | — | none on disk | confirm service alive |
| 🧊 | ☕ Café Claude | — | none | concept-only |
| 🧊 | 🤍 Project Noam | — | mission doc | HOLD FIRE |

---

## 🎬 Perceptron Movie

| Status | Project | Days | Path | Next |
|---|---|---|---|---|
| 🟢 | 🎬 Perceptron Movie | 0 | `perceptron-movie` | execute v3 music/audio plan freshly landed today |

Full skeleton on disk: `scenes/`, `clips/`, `audio/`, `music/`, `photos/`, `subs/`, `render/`, `script.md`, `GROK_IMAGINE_PROMPTS.md`. Production-shaped.

---

## 🤖 Grok stack (active this session)

| Status | Project | Days | Path | Next |
|---|---|---|---|---|
| 🟢 | 🤖 Grok-1 private stack | 0 | `grok1_shim.py` + `grok1-chat` | confirm shim swap (has `.bak-20260711`) is intended |
| 🟢 | 🐦 Grok web claws | 0 | `grok-web-claws` | verify what was added |
| 🟢 | 💻 Grok coder | 0 | `grok-coder` | same edit sweep as claws |
| 🟠 | 💬 RAM tri-chat / council | 3 | `ram-council` | verify 10MB shm channel still bound |
| 🟠 | 📱 wa-mcp | 6 | `wa-mcp` | run `wa_status`; nearly a week idle |

---

## 🖥️ Infra / OS / fleet

| Status | Project | Days | Path | Next |
|---|---|---|---|---|
| 🟢 | 🖥️ Fleet | 0 | `fleet` | see what session-scan changed |
| 🟢 | 📊 ALMAWARE HUD | 0 | `almaware-hud` | consume this recon |
| 🟡 | 📡 LoRa T-Deck Mesh | 3 | `lora-mesh` | resolve uncommitted `sent/m1.txt` |
| 🟠 | 🖨️ Slack clod bot / whatsapp-bridge | 4 / 3 | `slack-clod-bot`, `whatsapp-bridge` | pipeline hygiene |
| 🟠 | 🧭 Site-keepalive | 7 | `site-keepalive` | verify sites still up |
| 🟠 | 🧊 dgx-cooling / dgx-lean-os / gcp-deploy / hermes-cloud / jetson-lean-os | 3–9 | (each) | archive candidates unless picked up |

---

## 🧊 Misc dormant bucket (≥6d, most are archive/consolidate candidates)

`amos/`, `beitdin-hw/`, `beyond-silicon/`, `electric-brain/`, `exoskeleton/`, `sunflower-neuron/`, `self-learning-neuron/`, `motor-neuron/`, `optical-nn/`, `pong-alma/`, `pong-real-models/`, `fab-machine-20k/`, `makers-israel/`, `alma-lang/`, `alma-sim/`, `alma-time/`, `alma-link/`, `alma-meta-selector/`, `almaos-site/`, `almaware-hub/`, `almaware-standard-site/`, `almaware-watchdog/`, `perets-weave/`, `perez/`, `demut/`, `kesef/`, `unfuck-your-life/`, `usage-widget/`, `guitar-teacher-arch/`, `dispatch-fix/` (27d), `rbshatz-private/` (**59d — oldest**), `c_photorec_2026-05-14/`.

---

## 🚨 Broken windows spotted

1. **Reuse law violated (three parallel dirs)** — `quorum/`, `ram-council/`, `fleet-quorum/`. Council concept lives in three places. Pick one.
2. **alma-language weave splitting into 3 sub-projects in parallel** — `perceptron3d/`, `crossbar3d/`, `memristor-pedal/`. WIP=1 says pick one target.
3. **Federation vs portal overlap** — `alma-federation/` (0d), `federation-site/` (1d), `iddoperez-portal/` (3d), `almaware-standard-site-en/` (0d), `almaware-standard-site/` (6d) — five candidates for one publish surface.
4. **Grok shim** has a `.bak-20260711` next to `grok1_shim.py` — decide if the swap is committed or should revert.
5. **Uncommitted edits** in `alma-govern/fleet_health_check.sh`, `eran-audio/config.json`, `crossbar3d/index.html`, `perceptron3d/index.html`, `lora-mesh/sent/m1.txt` — all sitting dirty on `swarm/alma-language-4`.
6. **Cave-wall vs electric-brain vs shisha-lab** — three physical brain metaphors, one active (shisha).
7. **`mark-i-perceptron/` (8d) is superseded** by the ALMA Perceptron (Mk I) build inside `shisha-lab` (0d). Delete or archive.
8. **`memristor-grid/` (8d) is superseded** by `shisha-lab`'s crossbar work. Same call.

## What "north-star + WIP=1" looks like from here

Given the last week of commits, the current **de-facto WIP** is:
- **shisha-brain / physical-weights AI** (shisha-lab + alma-language/crossbar3d + memristor-pedal + perceptron3d + perceptron-movie storytelling)
- **Eran keeps training** in the background on DGX

Everything else in "active" list is either supporting (grok stack, HUD, fleet, federation) or drifting (quorum triplication, five publish sites). Recommend: freeze new starts, consolidate the top 3 broken windows above, then push one clean shisha-brain demo.
