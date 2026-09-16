> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# eran3 voice-ant-farm — patch, NOT applied / תיקון שלא הופעל
**2026-09-06 · claude-cli-REV-voice_ant_farm**

eran3 is write-locked for this workflow, so nothing here was applied to it.
The identical change **is live on eran2** and every proof below was run there.

## Why the patch fits eran3 exactly
Verified 2026-09-06: eran3's five target files are **byte-identical** to eran2's
pre-revision originals (md5 `9dac8868…` acoustic_units.py, `38943bba…` colony.py,
`c4680cd3…` fire.py, `b41d5a5c…` run_loop.sh, `9094d5ba…` status.sh).
`patch -p1 --dry-run` against those originals is clean.

**One correction to the trace:** `train_loop.sh` does **not** exist on eran3
(`md5sum: train_loop.sh: No such file or directory`). The stale-second-loop race
in VAF-10 can only happen on eran1/eran2/eran4. The flock in this patch is still
worth having on eran3 — it is what stops a second `run_loop.sh` too.

## To apply (someone with the eran3 write mandate)
```bash
scp voice-ant-farm-rev-20260906.diff lanes.py eran3:~/          # via eran2, eran3 has no LAN
ssh eran3 'cd ~/voice-ant-farm
  for f in acoustic_units.py colony.py fire.py run_loop.sh status.sh; do
    cp -p "$f" "$f.bak-rev-20260906"; done
  patch -p1 --dry-run < ~/voice-ant-farm-rev-20260906.diff   # must be clean first
  patch -p1            < ~/voice-ant-farm-rev-20260906.diff
  mv ~/lanes.py .; bash -n run_loop.sh; python3 -c "import fire,colony,acoustic_units,lanes"'
```
Then copy `proofs/*.py` next to the code and run every proof against the backup
directory and against the tree — each one must FAIL on the old and PASS on the new.

**Do not edit `run_loop.sh` in place while the loop is running.** bash reads a
script by byte offset; `patch` and `mv` replace the inode, so the running loop
keeps its old copy and picks the new one up at the next service restart. An
in-place edit (`sed` without a temp, an editor that truncates) can make a running
bash resume at the wrong offset.

**Line endings:** every file here is LF. CRLF in `run_loop.sh` makes
`SLEEP_SECONDS` carry a trailing `\r` and silently corrupts the loop — that bug
was hit and fixed during this revision. Check with `file run_loop.sh`.

## What takes effect when
| change | effect |
|---|---|
| `acoustic_units.py`, `colony.py`, `fire.py`, `lanes.py` | **next cycle** (≤15 min) — the loop re-execs `python3 fire.py cycle` every 900 s |
| `run_loop.sh` | **next restart of voice-ant-farm.service** — nobody in this workflow restarts it |
| `status.sh` | next time a human runs it |

## Proof results (run on eran2, `nice -n 19`, real code, not the live process)
All nine FAIL against the pre-revision backup and PASS against the fixed tree:
VAF-02, VAF-03, VAF-04, VAF-05, VAF-06, VAF-07, VAF-08, VAF-09, VAF-10.
Outputs: `eran2:~/voice-ant-farm/rev-proofs-20260906/VAF-*.{old,new}.txt` and
`D:\CLAUDE\_deliverables\code-revision\vaf-proofs\`.
The project's own suite (`tests/`, 22 tests + 3 subtests) passes unchanged.

## The one thing this patch deliberately does NOT do
It does not re-derive the contaminated `current.json` checkpoints. On eran3 **all
four ants** are currently 55-61% synthetic in their waveform exemplars
(ant-a 35/64, ant-b/c/d 39/64). The patch stops the contamination from
compounding; undoing it means throwing away a month of promotions, which is
Iddo's call — see `..\..\NEEDS-IDDO-voice_ant_farm.md` §2.
