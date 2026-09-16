> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# MIKO v1 — code revision 2026-09-06 · patch for eran3 · NOT APPLIED

**עברית:** התיקונים של MIKO בוצעו על הדיסק של הפיסי בלבד. עותק הקוד ב-`eran3:~/miko/v1`
נמדד ונמצא **זהה בייט-לבייט למצב שלפני התיקון** — כלומר eran3 מפגר עכשיו. אימון מחדש שם
בלי להחיל את הטלאי הזה ישחזר את כל הבאגים. **לא נגעתי ב-eran3.**

**English:** the MIKO fixes were applied on the PC only. `eran3:~/miko/v1` was measured and is
**byte-identical to the pre-fix state**, so eran3 is now behind: a retrain there without this
patch reproduces every defect. **Nothing on eran3 was written, restarted or signalled.**

## What is here

| file | what it is |
|---|---|
| `miko-v1-code-revision-20260906.diff` | unified diff, PC pre-fix → PC post-fix, 13 files changed + 3 new (`signals.py`, `exam_gate.py`, `migrate_ram_ids.py`) |
| `miko-proofs/proof_MIKO-*.py` | 11 proof scripts; each FAILS on the old code and PASSES on the new |

## Measured, 2026-09-06

`ssh eran3 "cd ~/miko/v1 && md5sum ..."` — read-only — matches the PC's pre-fix backups exactly:

```
1e7556bd5815fafc00d518114c131f50  model.py
53c0ca68ba0927c416e4aa57e18633bf  adapter.py
70a76aacfe7e6caa8045ad76c912e66c  train.py
22f42cc228ad1b303e377fd657b45e1c  adapter_train.py
d7726477c9b0d2ff02e9dad3e8eaf677  scar_guard.py
144cf7565bec560bfc6aea50bbf96f5a  bm25.py
0c587ea8c6d7693588c778cc6f452f94  build_corpus.py
c2b7ac8885e88c0a3aad1d818446c33f  exam.json
```

## How to apply, when someone decides to retrain

MIKO has **no service, no unit, no port, no timer** on eran3 — nothing is running, so nothing
gets restarted. `coder-train.service` is the live thing on that box and this patch does not
touch it. Still: check the box's load before starting anything.

```bash
ssh eran3 'cd ~/miko/v1 && for f in *.py *.json *.jsonl; do cp -p "$f" "$f.bak-rev-20260906"; done'
scp D:/CLAUDE/_deliverables/code-revision/eran3-patches/miko-v1-code-revision-20260906.diff eran3:~/
ssh eran3 'cd ~/miko && patch -p2 --dry-run < ~/miko-v1-code-revision-20260906.diff'   # dry run FIRST
```

Then the data artefacts, which the diff does **not** carry (they are binary or huge):

* `corpus.jsonl`, `split.json`, `e5_doc_emb.pt`, `e5_query_emb.pt`, `e5_exam_emb.pt` — these
  had their RAMCHAT ids migrated from positional to content-addressed (MIKO-06). Either copy
  the PC's versions over, or run `python3 migrate_ram_ids.py` on eran3 (idempotent).
* `e5_exam_emb.pt` is **stale on purpose** — it was embedded from the corrupted exam text
  (MIKO-05). Re-run `python3 encode_e5.py` on eran3 before any e5/adapter number is reported.
  Until then `compare_all.py` and `exam_detail.py` **refuse**, by design.

Run the proofs on eran3 after applying:

```bash
ssh eran3 'cd ~/miko/v1 && for p in proof_MIKO-*.py; do python3 "$p" >/dev/null && echo "$p PASS" || echo "$p FAIL"; done'
```

## What still is NOT fixed by this patch

The shipped checkpoints `miko-v1.pt` and `adapter-v1.pt` are **09-03 artefacts and stay
wrong**: both carry the inverted temperature, both are their run's epoch-1 model, and the
adapter's residual branch is still ~zero. Every number in `MIKO-V1-20260903.md` for the
`from_scratch` and `e5_plus_adapter` columns describes those artefacts. The fixes are nets
for the NEXT run. A retrain, on a fleet box, is what produces numbers worth reporting — and
those go to Iddo before any claim is made about them.
