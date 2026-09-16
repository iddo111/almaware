<!-- לזכרה של עלמה ז"ל -->
# MODEH — the Master Modeler's corpus-teachability organ

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

> **מאסטר-מודלר → מודיליאני → מודה אני.** The conductor over all the models carries
> thanksgiving in its name. This is the part of it that decides what ERAN is
> allowed to be grateful **for**.

Status **VERIFIED** (2026-09-05). Built, run, and graded against the human
record: **9/9**, including **3/3 on corpora the thresholds were frozen before
seeing**.

---

## 1. Why this and not a better teacher-picker

The Master Modeler was specified (Iddo, 2026-07-02) as ERAN's built-in faculty
for **sampling and learning from the best available models**. In the same breath
Iddo attached the condition: ***what you train on decides*** — so learn-from-the-
best must be paired with **forgetting and unlearning**
([[project_eran_forgetting_unlearning]]).

2026-09-03 showed why the condition is the hard half. ERAN ate
`facebook/mms-tts-heb` output for a month believing it was a human mouth. Iddo
listened to ten clips blind: **0 of 10 matched their labels.** Every accuracy
number in the estate stood on that corpus.

So the organ's first job is not *pick the best teacher*. It is
**detect a teacher with nothing to teach.**

## 2. What it measures

Six probes, each against ERAN's own frozen ear (`eran-brain/body/ears.py`,
cochlea, 24 bands × 8 slices = 192 dims, loudest60). Nothing is reimplemented —
if a corpus is unteachable to that ear it is unteachable to ERAN, which is the
only question worth asking.

| # | probe | question | fires when |
|---|---|---|---|
| 1 | **PROVENANCE** | does the corpus's own paperwork name a generator? | any TTS/VITS/seed marker in a record beside it or above it |
| 2 | **REDUNDANCY** | how many *independent* examples per unit, not how many files? | `n_eff = k / (1 + (k−1)·w_excess)` below 3 |
| 3 | **ARTEFACT** | can labels that are the **same sound** be told apart? | separates above the measured drift floor, p<0.01 |
| 4 | **SIGNAL** | is anything learnable under an honest split? | leave-group-out accuracy not above chance, p≥0.01 |
| 5 | **LEAKAGE** | how much of the reported number was memorising a sitting? | random-split minus leave-group-out > 15 points |
| 6 | **DRIFT FLOOR** | *(the control)* can early clips of ONE unit be told from late clips of the **same** unit? | reported, and probe 3 is scored against it |

Two design choices carry most of the weight:

**`w_excess`, not raw cosine.** Within-unit similarity is subtracted from the
corpus's own **between**-unit similarity and renormalised, so redundancy numbers
compare across corpora instead of riding on whatever that corpus's overall
variance happens to be.

**The drift floor is a param-matched control** (`feedback_clean_experiments`).
Take one unit, sort its own clips by time, call the first half *early* and the
second half *late*, and try to separate those. Same syllable, same mouth, same
label — only the clock differs. Whatever that reaches is the score any pair of
units recorded back-to-back gets for free. An identical-phone pair proves a
nuisance channel only if it beats **that**, not if it beats a coin flip.

## 3. Verdicts

`REJECT` · `STARVED` · `WEAK` · `ACCEPT` / `ACCEPT-UNVERIFIED` · `UNKNOWN`,
each with the numbers that produced it and a prescription. On
`REJECT + NO-SIGNAL` the prescription is the 2026-09-05 growth finding applied:
*don't size a fixed wide model on a corpus with nothing in it — grow on underfit
instead; measured, the fixed wide model lands 0.1429 below the floor the grown
one sits on.*

## 4. Forgetting — what is built and what is not

**Built (data-level unlearning, provenance-keyed):**

- `forget <corpus>` emits a revocation list: every file of a rejected corpus,
  its verdict, its reasons, and its **derived cascade** — the artefacts built
  from it (`food/words` from `food/train`, `state/curriculum.json` and the
  "13 syllables mastered" gate from a DEV split of the same train,
  `state/metrics.jsonl` from the vault).
- The cascade also runs **inside `judge`**: a corpus built from a rejected
  corpus inherits the rejection. Without that, revoking a source leaves every
  dish cooked from it on the table. This is what caught `food/words`.
- `contamination` answers the question that would have caught the fraud a month
  early: *is a rejected clip sitting in the food?* — separating "this food dir
  **is** a rejected corpus" from "someone copied rejected clips in".

**Already built, and more than I first credited.** ERAN has *three* live
forgetting mechanisms, and DARWISH has a fourth thing ERAN lacks:

| # | mechanism | where | keyed to |
|---|---|---|---|
| 1 | disuse pruning — `mass < 3.0` **and** unused `4000` beats → deleted | `body/sleep.py::_prune` | **disuse** |
| 2 | homeostatic decay — `SHY_FACTOR 0.98`, `SCAR_DECAY 0.90` each sleep | `body/sleep.py::cycle` | **time** |
| 3 | trace-keyed valence unlearning — a 👎 scars exactly the prototypes that produced the output, weighted by eligibility `e`; `att = sims − scars`, so a scarred prototype pulls less | `body/brain.py::pay_trace` (down) | **the output** |
| 4 | *the measurement of #3* — re-emission probability before/after the 👎 **plus heldout collateral damage** | `darwish-midi/proof/measure.py::unlearning_smoke` (PASS-4) | DARWISH only |

So targeted weight-level unlearning **exists and runs**, in both organisms. It
is credit-assigned suppression of a named artefact — the right shape.

**What is actually missing, precisely:**

1. **Nothing is keyed to PROVENANCE.** A prototype is
   `{vec, mass, birth_step, last_used, scar}` — **there is no source field.**
   Scars come from a 👎 on an *output*, never from "this input was a lie". So
   *"revoke everything ERAN learned from `food/train`"* is unexpressible: no
   record says which prototype came from which corpus. This is the exact seam
   where MODEH stops — MODEH's revocation list is keyed by **source**, ERAN's
   unlearning is keyed by **output**, and nothing joins them.
2. **Scars fade.** `SCAR_DECAY = 0.90` per sleep, so even a scar you did apply
   is ~gone within a few dozen sleeps. Correct for pain ("a teacher, not a life
   sentence"); wrong for a revoked source, which must stay revoked.
3. **ERAN has no PASS-4.** DARWISH measures whether a down-tap actually removes
   the target and what it costs elsewhere. ERAN has the mechanism with no such
   gate, so nobody knows how well it works or how much collateral it does.

4. **Mechanism #3 has a documented failure mode, in ERAN's own arena.**
   `eran-brain/arena/bimodal.py` states two hypotheses about the same channel
   ("ERAN's own eligibility trace... the same channel the parent's thumb-tap
   uses"): (a) `TauCapAgent` — `trace_tau` decodes to as much as 121 trials, so
   on a task whose rule turns over every ~10 trials the tap "pays reward earned
   under the new rule to the prototypes that encoded the dead one", i.e. the
   👎 scars the **wrong** prototypes; (b) `AttritionAgent` — "prototypes spawned
   under rule A are **never unlearned**, the code saturates at the cap, and the
   new rule has nowhere to live." Both fixes are coded. **No result file for
   this arena is on disk — UNKNOWN which hypothesis won.**

### The prototype that no mechanism can reach

Put 1–4 together and there is a clean hole. A prototype built from the TTS
corpus and used often enough to carry mass is immune to **every** forgetting
mechanism ERAN has:

- **disuse pruning** won't take it — it is used, and `mass ≥ 3.0`;
- **SHY decay** won't take it — it downscales everything equally, so rank is
  preserved;
- **the thumb-tap** can only reach it if someone happens to 👎 an output it
  produced, may scar the wrong prototypes anyway (failure (a)), and whatever
  scar lands fades at `0.90` per sleep;
- **and at `MAX_PROTOTYPES = 4096` it occupies a slot the truth needs** (failure
  (b)).

That is the whole argument for provenance-keyed unlearning in one paragraph, and
it is why "he forgets already" is not an answer to Iddo's condition.

The next gate is therefore small and concrete, not a research programme: **put a
source tag on the prototype, add a non-decaying revocation scar, and port
DARWISH's `unlearning_smoke` to ERAN.** Then MODEH's forget-set becomes
executable instead of advisory.

So the honest state of Iddo's condition is: **forgetting yes; unlearning yes but
output-keyed, unmeasured in ERAN, and never joined to provenance.**

## 5. Safety — unchanged from the rest of this control plane

Read-only. It opens `.wav` and `.json` and nothing else; its only writes are
under `master-modeler/runs/`. It never kills or starts a trainer, never opens a
microphone, never touches `eranb-life` on eran1. On Windows it sets itself to
`BELOW_NORMAL` priority so it cannot starve the mic
(`feedback_pc_heavy_work_below_normal`). The FLEURS corpus was read from eran2
by a `nice -n 19` tar and measured on the PC; nothing on the fleet was started,
stopped or evicted.

## 6. Honest accounting of the thresholds

The builder does not grade himself, so this has to be written down:

- **Tuned set (6 corpora).** After the first run, `n_eff_starved` was raised
  `1.5 → 3.0`, and the drift-floor control was added because `t07-iddo`
  disagreed with the record. Both changes are defensible on their own
  (a variance needs 3 points to estimate; a claim needs a control) but they were
  made *after seeing results*, so those six prove nothing by themselves.
- **Held-out set (3 corpora).** `words-derived`, `antfarm-source` and
  `human-dictation` were added and run **only after the thresholds were frozen**.
  **3/3.**
- **Not tested:** whether the verdicts survive a different ear; whether the
  identical-phone list is right for every pair (`aa/ah` in `t07` is flagged
  CONFOUNDED, not resolved — only Iddo's ear can settle it); whether the
  provenance marker list generalises beyond this estate.

## 7. Files

| file | what |
|---|---|
| `teachability.py` | the organ — six probes, verdicts, forget-set, contamination |
| `corpora.json` | the corpus registry; `expect` is the human record, never read by the scorer |
| `acceptance_teachability.py` | grades the organ against `expect`; tuned vs held-out declared |
| `runs/` | every judgement, timestamped, plus `forget-set.json` and `acceptance.json` |
| `master_modeler.py teach` | the organ reachable from the control plane |

## 8. Commands

```
python teachability.py judge --all
python teachability.py judge tts-vault t06-rich
python teachability.py units t06-starved
python teachability.py forget tts-food-train
python teachability.py contamination
python acceptance_teachability.py --heldout
python master_modeler.py teach --scratch <dir>
```
