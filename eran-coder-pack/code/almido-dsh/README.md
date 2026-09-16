> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working).

# AlmIdo dsh plugins — עברית אחרי האנגלית

**EN:** Two zero-dependency plugins for the DeepSeek Harness (dsh v0.1) trial on eran3, giving the harness AlmIdo's organs and AlmIdo's policy gate. Source of truth lives here (PC, git-visible); the deployed copy lives at `~/dsh-almido` on eran3, wired through `~/.dsh/profiles/web/cordis.patch.yml` (see `cordis.patch.snippet.yml` for the exact rows).

**HE:** שני תוספים ל-DeepSeek Harness על eran3 — האיברים של אלמעידו ושער המדיניות שלו. המקור כאן במחשב, הפריסה ב-`~/dsh-almido` על eran3.

| plugin | what it does |
|---|---|
| `almido-organs` | Registers the `shamash_weave(note)` agent tool — read-only fetch of one knot from SHAMASH on eran2:8850 (LAN <lan-ip> first, fabric <fabric-ip> fallback; both measured reachable from eran3, 2026-08-31). |
| `almido-gate` | `tools/pre-execute` deny waterfall + `ctx.tools.guard` monotonic final deny for `bash`/`pwsh`, driven by `policy.json` (trimmed from `~/.iddo-harness/policy.yaml`, ported from `almido_gate.py`). Verdicts ALLOW/CONFIRM/BLOCK; CONFIRM ⇒ deny with "needs Iddo" (no push channel on eran3). One JSON audit line per decision → `~/dsh-almido/audit.log` (`src: "almido/dsh"`). STOP-file kill switch: `touch ~/dsh-almido/STOP` denies everything. |

**Deliberately absent / חסר בכוונה:**
- `alma_recall` — the PC recall server listens on 127.0.0.1:8794 only; eran3 cannot reach it. Re-add when it is rebound to LAN.
- `ramchat_read` — no clean HTTP path from eran3 to the council; not inventing one.
- Policy is **JSON not YAML** — the gate imports nothing, and node stdlib has no YAML parser.

**Smoke / בדיקת עשן:** `node ~/dsh-almido/smoke.mjs` on eran3 — live SHAMASH fetch + gate decisions + kill switch, no dsh needed.
**Deploy check / בדיקת פריסה:** `cd ~/dsh-trial && export PATH=~/dsh-trial/node/bin:$PATH && npx -y @deepseek-ai/dsh web --dump-config | grep -n almido`
