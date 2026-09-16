# RECON 6 — Git + Workspace

> 🪟 BROKEN WINDOWS LAW — חוק החלונות השבורים: if it's not working, fix it IMMEDIATELY.

**Branch:** `swarm/alma-language-4` (not `main`)
**Head:** `3558b95` — grid-dashboard reservoir training layer

## Counts

| category                  | count |
| ------------------------- | ----- |
| modified (unstaged)       | 7     |
| staged                    | 0     |
| submodule dirty           | 1 (`dispatch-fix`) |
| untracked                 | **1476** |
| total status entries      | 1484  |
| stderr warnings (broken symlinks / permission-denied dirs) | 4 |

## Worktrees (9 total)

- `D:/CLAUDE` — primary, on `swarm/alma-language-4`
- `C:/Users/<user>/.grok/worktrees/claude/2026-07-02-e4787b3c` — detached
- `C:/Users/<user>/AppData/Local/Temp/iff-verify` — `swarm/alma-iff-3`
- `D:/CLAUDE/.claude/worktrees/dreamy-robinson-d29c66` — detached
- `D:/CLAUDE/.claude/worktrees/fresh-20260704` — `claude/fresh-20260704`
- `D:/CLAUDE/.claude/worktrees/fresh-start` — `fresh-start`
- `D:/CLAUDE/.claude/worktrees/laughing-mendeleev-6d303d` — detached
- `D:/CLAUDE/.claude/worktrees/nostalgic-gates-b1935a` — `claude/nostalgic-gates-b1935a`
- `D:/CLAUDE/.claude/worktrees/wf_4df10cda-309-21` — `swarm/alma-meta-selector-5`

## Modified files (7) — one-line verdicts

| file | change | verdict |
| ---- | ------ | ------- |
| `.claude/launch.json` | moved eran-voice to `archive/`, added `shisha-grid9-3d` (:4321) and `eran-babble-audio` (:8784) | **commit** |
| `alma-govern/fleet_health_check.sh` | `eran4@<lan-ip>` → SSH alias `eran4` (DHCP-drift; .12 was stale, now .163) | **commit — critical, health-check was pointing at a dead IP** |
| `alma-language/crossbar3d/index.html` | +2 SEO/theme meta tags | **commit** |
| `alma-language/perceptron3d/index.html` | +2 SEO/theme meta tags | **commit** |
| `almaware-standard-site-en/index.html` | escaped a raw `"` inside a `<meta>` description | **commit — was actually malformed HTML** |
| `eran-audio/config.json` | listen temperature 0.95→0.65, top_k 100→30 | **hold — live tuning knob for Eran, ask Iddo** |
| `lora-mesh/sent/m1.txt` | rewrote a sent-message log entry | **leave — runtime artifact, not source** |

## Session deliverables (cross-referenced)

| directory | state | verdict |
| --------- | ----- | ------- |
| `almaware-hud/` | THIS session's own recon output, `hud.py` + `recon/` + `__pycache__` | **do NOT commit yet** — still receiving data from this recon workflow |
| `perceptron-movie/` | `script.md` + `GROK_IMAGINE_PROMPTS.md` + 7 asset folders | **commit only the two .md files** — `render/ music/ clips/ audio/ photos/ scenes/ subs/` are almost certainly binaries and don't belong in the repo without `.gitignore` review or LFS |
| `alma-language/memristor-pedal/` | one 12 KB `index.html` | **commit** — clean standalone weave, matches crossbar3d/perceptron3d pattern |
| `grok-coder/` | `grok1_tk.py`, `grok_coder.html`, `Grok-1 Coder.url` | **commit** — small, self-contained, matches the "Grok-1 Private Stack" memory line |
| `grok1_shim.py` + `start_grok1_shim.cmd` | Grok-1 shim + launcher | **commit** |
| `grok1_shim.py.bak-20260711` | timestamped backup | **do NOT commit** — add `*.bak-*` to .gitignore |

## Honest bottom line

The workspace has **1,476 untracked entries at the repo root**. That's not a git problem — that's a workspace-hygiene problem. `D:\CLAUDE` has drifted from "repo" toward "scratchpad." Broken-Windows Law says: this is the broken window. Two moves:

1. **Land the small correctness fixes today, as their own tight commit** so they aren't lost in the noise:
   - `alma-govern/fleet_health_check.sh` (dead IP)
   - `almaware-standard-site-en/index.html` (malformed HTML)
   - `.claude/launch.json` (new launch configs)
   - `alma-language/crossbar3d/index.html` + `perceptron3d/index.html` (meta tags)

2. **Second commit for this session's real deliverables:**
   - `alma-language/memristor-pedal/`
   - `grok-coder/`
   - `grok1_shim.py` + `start_grok1_shim.cmd`
   - `perceptron-movie/script.md` + `perceptron-movie/GROK_IMAGINE_PROMPTS.md`

3. **Do NOT commit:**
   - `almaware-hud/` (still in-flight this session)
   - `perceptron-movie/{audio,clips,music,photos,render,scenes,subs}/` (binaries — audit first)
   - `eran-audio/config.json` (live tuning; confirm with Iddo)
   - `lora-mesh/sent/m1.txt` (runtime log)
   - `grok1_shim.py.bak-20260711` (backup)

4. **Never** run `git add -A` or `git add .` in this tree — the untracked list is too polluted. Every commit should name files explicitly.

5. **Follow-up worth spawning:** a proper `.gitignore` audit — `*.bak-*`, `__pycache__/`, big loose files at repo root, and probably a decision on whether `perceptron-movie/` binaries live in the repo at all.
