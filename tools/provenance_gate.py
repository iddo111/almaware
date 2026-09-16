"""Provenance gate -- pre-flight check before any training run touches a corpus.

Born from the Fable half-year sweep (2026-09-15): 3 corpus collapses in 7 weeks
(most recently Darwish, 81/314 files not actually Darwish, trained on blind for
days) because nothing checked a corpus's paper trail before a training script
started reading it. nezer-chef/chef.py already keeps this discipline for its
own food-serving pantry (ATTRIBUTION.txt + PROVENANCE.jsonl + sha256 per file,
eran3:~/nezer-chef/chef.py); this is the same discipline as a small, generic,
stdlib-only gate any training script on any box can call first.

PROVENANCE.jsonl: one JSON object per line, at least {"file": <name>, "sha256": <hex>}.
ATTRIBUTION.txt: freeform, just has to exist and be non-empty.

Usage:
    python provenance_gate.py <corpus_dir> [--glob PATTERN] [--allow-unlisted]

Exit 0 only if:
  - ATTRIBUTION.txt exists and is non-empty
  - PROVENANCE.jsonl exists, parses, and every line has file+sha256
  - every data file in corpus_dir matching --glob (default: everything except
    ATTRIBUTION.txt/PROVENANCE.jsonl/PROVENANCE.jsonl.bak*) is listed
  - every listed sha256 matches the file's CURRENT sha256 on disk
  - (unless --allow-unlisted) no data file present is unlisted in PROVENANCE.jsonl

Meant to gate a training entrypoint:
    python provenance_gate.py /path/to/corpus || exit 1
"""
import argparse
import fnmatch
import hashlib
import json
import os
import sys

SKIP = {"ATTRIBUTION.txt", "PROVENANCE.jsonl"}


def sha256_of(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def fail(msg):
    print(f"PROVENANCE GATE: FAIL -- {msg}")
    return 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus_dir")
    ap.add_argument("--glob", default="*")
    ap.add_argument("--allow-unlisted", action="store_true",
                     help="don't fail on data files present but not in PROVENANCE.jsonl")
    args = ap.parse_args()

    d = args.corpus_dir
    if not os.path.isdir(d):
        return fail(f"not a directory: {d}")

    attrib = os.path.join(d, "ATTRIBUTION.txt")
    if not os.path.isfile(attrib) or os.path.getsize(attrib) == 0:
        return fail(f"missing or empty ATTRIBUTION.txt in {d}")

    prov = os.path.join(d, "PROVENANCE.jsonl")
    if not os.path.isfile(prov):
        return fail(f"missing PROVENANCE.jsonl in {d}")

    listed = {}
    try:
        with open(prov, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                name, sha = rec.get("file"), rec.get("sha256")
                if not name or not sha:
                    return fail(f"PROVENANCE.jsonl line {i} missing file/sha256: {line[:120]}")
                listed[name] = sha
    except json.JSONDecodeError as e:
        return fail(f"PROVENANCE.jsonl is not valid JSONL: {e}")

    if not listed:
        return fail("PROVENANCE.jsonl has zero entries")

    on_disk = sorted(
        n for n in os.listdir(d)
        if n not in SKIP and not n.startswith("PROVENANCE.jsonl.")
        and os.path.isfile(os.path.join(d, n))
        and fnmatch.fnmatch(n, args.glob)
    )

    unlisted = [n for n in on_disk if n not in listed]
    if unlisted and not args.allow_unlisted:
        return fail(f"{len(unlisted)} file(s) on disk with no PROVENANCE.jsonl entry "
                     f"(undocumented contamination risk): {unlisted[:5]}"
                     + (" ..." if len(unlisted) > 5 else ""))

    missing = [n for n in listed if n not in on_disk]
    if missing:
        return fail(f"{len(missing)} file(s) listed in PROVENANCE.jsonl but not on disk: "
                     f"{missing[:5]}" + (" ..." if len(missing) > 5 else ""))

    mismatched = []
    for n in on_disk:
        if n not in listed:
            continue
        actual = sha256_of(os.path.join(d, n))
        if actual != listed[n]:
            mismatched.append(n)
    if mismatched:
        return fail(f"{len(mismatched)} file(s) whose CURRENT sha256 does not match "
                    f"PROVENANCE.jsonl (silent drift/corruption/swap): {mismatched[:5]}"
                    + (" ..." if len(mismatched) > 5 else ""))

    print(f"PROVENANCE GATE: PASS -- {len(on_disk)} files verified against "
          f"PROVENANCE.jsonl ({len(listed)} entries), ATTRIBUTION.txt present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
