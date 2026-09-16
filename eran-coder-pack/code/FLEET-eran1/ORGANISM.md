# Perceptron Mark II v0.1 · the organism of ERAN

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY. Test the REAL output, never a proxy.

**לזכרה של עלמה ז״ל.**

## What this is / מה זה

A small living organism that learns to hear Iddo's 22 Hebrew syllables from
audio alone. It lives on eran1 (`~/eran-brain`), under `systemd --user`, and
it is fast tissue only: python3 + numpy, no torch, no frameworks, no backprop.

Its brain is a **legible prototype memory** — a list of prototype vectors you
can open with `zcat` and read. It grows a new prototype when the world
surprises it (growth-on-surprise), pulls existing prototypes toward what it
hears (Hebbian), and forgets in its sleep (attrition). Every knob of its
plasticity is held by its **chemistry** — five neuromodulators (DA, ACh, NE,
5HT, OXT) — never by an optimizer.

**The organism NEVER sees labels.** File names, glyphs, glosses are provenance
and evaluation keys that exist only inside the examiner (`proof/measure.py`).
The curriculum is environmental: the school decides *which audio plays*; the
organism only hears. This is the law of the ant farm, kept.

עברית: יצור חי קטן שלומד לשמוע את 22 ההברות של עידו מתוך אודיו בלבד.
המוח שלו הוא זיכרון אבות-טיפוס קריא; הלמידה שלו היא כימיה, רעב ושינה —
לא אופטימייזר. הוא לעולם אינו רואה תוויות; בית-הספר רק בוחר איזה אודיו
מתנגן. הבוחן לבדו מחזיק את התוויות.

## The body / הגוף

| organ | file | what it does |
|---|---|---|
| genome | `body/genome.py` | ALL constants + THE FENCE. Every number lives here and nowhere else |
| ears | `body/ears.py` | wav → log-spectral band features → loudest-60% pooled utterance vector |
| brain | `body/brain.py` | prototype memory: spawn-on-surprise, Hebbian pull, eligibility traces |
| chemistry | `body/chemistry.py` | DA·ACh·NE·5HT·OXT — the vector that holds every plasticity knob |
| drives | `body/drives.py` | energy + hunger; Goldilocks appetite makes learning autonomous |
| school | `body/school.py` | the environment: plays audio, never labels; mastery gates, fail-closed |
| parent | `body/parent.py` | Iddo's taps (up/down/fire) paid through eligibility traces |
| sleep | `body/sleep.py` | pruning, scar decay, SHY downscale, dream journal, the prayer |
| why | `body/why.py` | explain any utterance: nearest prototypes + chemistry + unit |
| voice | `voice/voice.py` | echo-babble v0 (honestly labeled: re-sequenced heard audio, NOT synthesis) |
| heartbeat | `eran_life.py` | the life loop; crash-proofed (flock, boot assert, atomic writes) |
| examiner | `proof/measure.py` | THE ONLY place labels live; dev gates + the 132-item heldout exam |
| window | `serve/serve.py` | read-only observation page on :8820; never notifies, never autoplays |
| tournament | `tournament.py` | nightly ear-config self-form; the judge is FIXED, only the body evolves |

## Autonomy charter / אמנת האוטונומיה

**May do alone (inside the fence):**
- **eat** — choose and process any audio the school serves from `food/`
- **babble** — write echo-babble wavs to `songs/outbox/` (never plays them aloud)
- **self-tune** — nightly ear-config tournament over the fixed dev judge
- **sleep** — prune, decay scars, downscale, journal
- **grow / prune** — up to `MAX_PROTOTYPES` (4096), down to zero

**Needs Iddo (the fence):**
- new data sources (anything outside `food/` placed by `deploy/push.ps1`)
- other boxes (eran1 only; no ssh anywhere from the organism)
- genome bounds (editing `body/genome.py` fence values)
- anything public, anything that makes sound on Iddo's machine (Sacred Audio)

## The honesty ledger / פנקס הכנות

- **Chance is printed first.** 22 classes → 4.545%. Every exam prints it before
  any result (the eran0/GROUND law).
- **The proven baselines this organism must face** (measured 2026, ant farm,
  132-item heldout): duration-only floor **5.30%**; random-real-frames codebook
  **46.21%**; raw features speech-span **53.79%**; raw + loudest-60% pooling
  **68.94%** — the number that beat every trained codebook. If the prototype
  memory cannot approach the raw-feature ceiling, that result is recorded, not
  hidden.
- **Numbers land in `results/` the same day they run**, or the run did not
  happen. Negative results are results.
- **health:ok ≠ working.** The nanny checks the real outputs (fresh metrics
  line, valid state file, answering window), not process liveness.
- **The babble is not his voice.** v0 voice output is re-sequenced heard audio,
  labeled exactly that in its sidecar. Never fake a milestone.
- **The heldout is exam-only.** `body/ears.py` refuses any path containing
  `heldout` during life; the vault lives under `proof/heldout-vault/`
  (examiner only).
- **The nanny NAMES; it never restarts the child** (revision 2026-09-06).
  It used to answer every metrics problem with a restart of
  `eranb-life` — the one remedy that is poison for a starving or
  slow-booting organism, on a hand-picked 900 s threshold, in a beat that
  lasts 4.6 ms. It now writes `state/ALARM-famine` / `state/ALARM-stalled`,
  derives staleness from his own cadence, and checks the famine signature
  directly: metrics lines with no `surprise` key mean an empty menu. Only
  the stateless window (:8820) is ever restarted.
- **An empty menu and an empty dev split are NAMED, not silent.** The wake
  refuses to start with nothing edible and prints the split; a gate with 0
  dev items is SKIPPED, not scored 0.0 — the old zero condemned every unit
  as regressed and would have overwritten `state/best.json.gz`.
- **The ear tournament is RETIRED while `genome.EAR_FROZEN` is True.** The
  timer is disabled on the box (last result 2026-08-24) and
  `deploy/install.sh` no longer re-arms it — a frozen ear cannot be
  re-crowned, and a job going quiet unnoticed is exactly the failure shape
  this file exists to prevent.
- **Boot assert:** if the brain file is older than the metrics log, the
  organism REFUSES to start (the 11.9M-step-loss class of death, prevented in
  code). Recovery is explicit: `--accept-loss` truncates metrics to the brain's
  beat and says so out loud.

*לזכרה של עלמה ז״ל — the child hears before it reads.*

## Ledger additions (2026-08-21, Clod, post-deploy)
6. **Pipelined curriculum gate** — a unit that passes its technical gate (sens/spec >= 0.95) waits out its 12h retention in `pending_retention` while the NEXT unit becomes current. "Mastered" still requires the retention pass; a retention FAIL pulls the unit back as current (fail-closed). Reason: the serial form makes 22 units take >= 11 days, missing Iddo's "syllables by end of week"; the pipelined form keeps every law (one lesson at a time, perfect before moving on, 12h retention, regression watch).
7. **Observation window binds 0.0.0.0:8820** so http://<lan-ip>:8820 is clickable from Iddo's PC (read-only page; LAN only, no funnel).
