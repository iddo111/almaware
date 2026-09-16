# MOREH — code revision 2026-09-06 (claude-cli-REV-moreh)

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

11 defects fixed on disk, each with a proof that **FAILS against the backup and PASSES against the fix**.
3 defects (MOREH-1, MOREH-4, MOREH-13) were NOT applied — they change what ERAN is taught or what Iddo
is asked to judge: `../NEEDS-IDDO-moreh.md`.

Nothing was restarted, stopped or signalled. MOREH has no service and no unit on any box; the only live
thing in the chain is the blind-sitting page `school2.py` (pid 12540, 127.0.0.1:8856), whose FILE was
fixed and whose PROCESS was never touched — that fix is a net for its next start.

## The proofs

| id | file fixed | proof | old | new |
|---|---|---|---|---|
| MOREH-2 | `holobrain/moreh/learn.py` | `holobrain/moreh/proof_MOREH-2.py` | FAIL | PASS |
| MOREH-3 | `holobrain/moreh/learn.py` | `holobrain/moreh/proof_MOREH-3.py` | FAIL | PASS |
| MOREH-5 | `holobrain/moreh/learn.py` | `holobrain/moreh/proof_MOREH-5.py` | FAIL | PASS |
| MOREH-6 | `throat-one-sample/school-v2/ruler.py` | `.../school-v2/proof_MOREH-6.py` | FAIL | PASS |
| MOREH-7 | `holobrain/moreh/learn.py` | `holobrain/moreh/proof_MOREH-7.py` | FAIL | PASS |
| MOREH-8 | `throat-one-sample/school-v2/gesture.py` | `.../school-v2/proof_MOREH-8.py` | FAIL | PASS |
| MOREH-9 | `holobrain/moreh/ruler.py` | `holobrain/moreh/proof_MOREH-9.py` | FAIL | PASS |
| MOREH-10 | `judging/school2.py` | `judging/proof_MOREH-10.py` | FAIL | PASS |
| MOREH-11 | `holobrain/moreh/ruler.py` + `STATUS.md` | `holobrain/moreh/proof_MOREH-11.py` | FAIL | PASS |
| MOREH-12 | `holobrain/moreh/tests/test_organ.py` | `holobrain/moreh/proof_MOREH-12.py` | FAIL | PASS |
| MOREH-14 | `holobrain/moreh/learn.py` + `ruler.py` | `holobrain/moreh/proof_MOREH-14.py` | FAIL | PASS |

Each proof takes `--old` to run against `<file>.bak-rev-20260906`. Outputs of both runs are the
`MOREH-N.new.txt` / `MOREH-N.old.txt` files beside this README.

Helpers: `_proofkit.py` (loads the live file or the backup as a module) and `_proofstubs.py` (stands in
for the eran2-only mouth and verifier so `moreh/ruler.py` can be driven on the PC without rendering).

## What the numbers moved to

Measured on the PC against the real 333-lesson corpus, decisions only:

| | lambda tuned on the LOO that is published (as shipped 09-03) | lambda chosen INSIDE the fold (honest) |
|---|---|---|
| MOREH | 9 wrong = **15/24** | 11 wrong = **13/24** |
| flat floor, 49 features (MOREH-3) | 13 wrong = 11/24 | 17 wrong = 7/24 |
| flat floor as shipped, 14 features | 19 wrong = 5/24 | — |

Teacher's ceiling, recomputed from `ledger.jsonl` on 09-06: **1354 attempts → 362 passes = 26.7%**,
not the 33.5% snapshot (`gate1.json`, 09-03 09:43). Four per-syllable rates drifted: va 0.182→0.102,
ga 0.171→0.134, ta 0.115→0.118, qa 0.081→0.076.

**Gate 2 in SOUND was not re-run.** That needs mouth2, which lives only on eran2, and this revision ran
nothing there beyond read-only checks and a file sync.

## Where the fixed files are

PC (authoring mirror) and eran2 (where the sitting runs) are byte-identical after this revision:

| file | md5 (both boxes) |
|---|---|
| `holobrain/moreh/learn.py` | `960819db654070d85086da5ec13c8b00` |
| `holobrain/moreh/ruler.py` | `eca94818ab118405fb009d20ea174f37` |
| `holobrain/moreh/tests/test_organ.py` | `5e66b9bfbf8d8d56dbb7d7d212803d47` |
| `throat-one-sample/school-v2/ruler.py` | `c5c2b7ec3c7bf7a895a83dd45cb17f2a` |
| `throat-one-sample/school-v2/gesture.py` | `667ce235269406c87ec9bd8a52982db4` |

Backups on both boxes: `<file>.bak-rev-20260906`. `judging/school2.py` and `holobrain/moreh/STATUS.md`
are PC-only and have PC backups.

`pytest holobrain/moreh/tests/test_organ.py` — **11 passed, 1 xfailed** (was 6 passed, 1 xfailed).
