> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# CODER code revision — patches for eran3 (NOT APPLIED)

**2026-09-06 · claude-cli-REV-coder · model `coder` on box eran3**

`eran3` holds `coder-train.service` and is **off limits for writes**. Everything
here was produced read-only (`ssh` + `cat/ls/stat/grep/systemctl show` + `scp` of
files *out*). **Nothing on eran3 was written, restarted, stopped or signalled.**

Verified after the work (same as before it):

```
coder-train.service  ActiveState=active  MainPID=1594129
                     ExecMainStartTimestamp=Sun 2026-09-06 05:20:09 IDT  NRestarts=0
train.py / watchdog.py / paired_compare.py / train.config.json / coder-train.service
                     mtimes unchanged (2026-09-05 14:22 / 2026-09-06 05:25 /
                     2026-09-05 16:18 / 2026-09-05 14:36 / 2026-09-06 00:04)
eran1 PID 120630     lstart Fri Aug 21 17:19:00 2026   (ERAN himself, untouched)
```

## Layout

```
orig/        the six files exactly as they are on eran3 right now
new/         the same files, patched
diff/        unified diffs, paths rooted at /  (ALL-coder-eran3.patch = all six)
proof/       proof_CODER-NN.py -- each takes a target and exits 0=PASS 1=FAIL
proof-out/   every proof run twice: .OLD.txt (must FAIL) .NEW.txt (must PASS)
```

## The 11 patched defects

| id | file | one line |
|---|---|---|
| CODER-01 | watchdog.py | `deactivating` mapped to DEAD, and `systemctl restart` was waited on with a 15 s timeout while a graceful stop takes 7-8 min → one real restart booked twice, two real events per hour escalated a healthy run to BROKEN |
| CODER-02 | watchdog.py + unit | exit codes 1/3/5 ("investigate", "never restart") were restarted every 60 s; the watchdog's status classifier lives inside `if alive:` so a dead crash was never even read |
| CODER-03 | watchdog.py | a run that reached step 1600 and exited 0 was restart-looped (47 GB reload to run `range(1600,1600)`) until the crash-loop cap called a *completed* run BROKEN. **What comes after 1600 is Iddo's — see NEEDS-IDDO-coder.md** |
| CODER-04 | train.py + config + **new eval_ckpt.py** | nothing the training produces ever returns: no export, no consumer, and the held-out set never re-scored since the BASE model, 12 h before training began |
| CODER-05 | paired_compare.py | the only "the weights improved" number (-16 σ) is on data the warm-start weights had already trained on; now split into CONTAMINATED / CLEAN halves and it refuses to quote a clean number before step 65 |
| CODER-06 | watchdog.py | loss trend = two single-step samples with a 0.1% threshold against sd 0.085 → it said "increasing" on 30+ passes while the block means fell; now OLS over block means with an SE, and "underpowered" when it cannot tell |
| CODER-07 | train.py | a SIGTERM on a save step wrote the same 47 GB checkpoint twice (measured: 01:25:09 and 01:32:04, both step 20) |
| CODER-08 | unit drop-in | `StartLimitIntervalSec` sat in `[Service]`, where systemd ignores it — the file claimed a guard it did not have |
| CODER-09 | watchdog.py | `train.pid` has named a non-existent process since 2026-09-04 19:36; WATCHDOG.md still lists it as a liveness source |
| CODER-10 | watchdog.py | `restarts_last_hour` was `len(restart_history)` unfiltered — it reported 4 at 12:03 for restarts that happened at 04:23-05:16 |
| CODER-11 | watchdog.py + train.py + drop-in | the 50 GB disk floor was below the cost of one checkpoint cycle (~94 GB); orphaned `.tmp_step_*` dirs were counted as checkpoints and never swept; a failed save had no exit code of its own |
| CODER-12 | train.py | a resume compared only precision/seq_len/block_size — lr, warmup, max-steps, clip **and the corpus paths** could change between two watchdog restarts in silence |

(CODER-13's non-Iddo half — `--ckpt-dir` no longer defaults to the abandoned
run's directory — ships inside the train.py patch and is proved by
`proof_CODER-12.py`. The 98 GB deletion and CODER-14's policy question are in
`..\NEEDS-IDDO-coder.md`.)

## Verify the proofs yourself (runs on the PC, touches nothing)

```powershell
cd D:\CLAUDE\_deliverables\code-revision\eran3-patches\proof
python proof_CODER-01.py ..\orig\watchdog.py   # expect FAIL, exit 1
python proof_CODER-01.py ..\new\watchdog.py    # expect PASS, exit 0
```

All twelve were run both ways; the outputs are in `proof-out\`. They are pure
stdlib: `watchdog.py` is imported for real, and `train.py`'s helpers are lifted
out by AST and executed on their own (train.py needs torch, and **no training or
inference runs on the PC**).

## To apply (a human decision, at a chosen moment — NOT by this workflow)

The patch is **a net for the next restart**, not a live change. `train.py` and
`train.config.json` are read only at process start, and `watchdog.py` is re-read
on every 5-minute timer pass, so:

| file | when it takes effect |
|---|---|
| `watchdog.py` | **next watchdog pass (≤5 min)** — no restart needed |
| `30-exit-codes.conf` | after `systemctl --user daemon-reload` — no restart needed |
| `train.py`, `train.config.json`, `paired_compare.py`, `eval_ckpt.py` | **next restart of coder-train** — do not restart it for this |

```bash
# on eran3, when a human decides to:
cd ~/coder-train
for f in train.py watchdog.py paired_compare.py train.config.json; do
  cp -a "$f" "$f.bak-rev-20260906"          # back up FIRST
done
# then copy new/* over from the PC and:
mkdir -p ~/.config/systemd/user/coder-train.service.d      # already exists
#   (holds 10-checkpoint-timeout.conf and 20-who-stopped-me.conf; 30- sorts last
#    and shares no keys with either)
systemctl --user daemon-reload             # does NOT restart the unit
```

`diff/ALL-coder-eran3.patch` applies cleanly with `patch -p1` from `/`
(verified: all six output files came out byte-identical to `new/`).

**Does the new drift guard block the next resume? No — measured, not assumed.**
`save-hf-every` is deliberately **not** in `CONFIG_DRIFT_KEYS`, so the 0 → 200
change is invisible to it. Checked against the live checkpoint:
`config_drift(ckpt2/step_00000040 train_state args, patched train.config.json)`
returns `[]` — all twelve watched keys (lr 4e-05, warmup 20, max_steps 1600,
grad_accum 128, micro_batch 1, seed 1337, replay '0.10', clip 1.0, wd 0.1,
min_lr_ratio 0.1, both corpus paths) match exactly. Output in
`proof-out\live_drift_check.txt`. The guard is a no-op today and only speaks if
someone later edits the schedule or the food between two restarts.

**And `eval_ckpt.py` must never run on a timer.** eran3 holds one model at a time
in 121 GB and the trainer already reserves ~84 GB. Measure with `--dry-run 5`
first, never run it while Qwen3-Coder-480B is resident, and never let it become a
cron job.
