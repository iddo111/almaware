"""pack_for_fleet.py -- gather every wav the corpus references into one tar,
with the manifests rewritten to relative paths, ready to ship to eran4.

The audio lives scattered across four projects and two spool directories on a
Windows disk; the trainer will see one directory on a Linux box. Rewriting the
paths here, once, is the difference between a corpus and a pile of references.
"""
import json
import tarfile
from pathlib import Path

OUT = Path(r"D:\CLAUDE\ozen\data")
TAR = Path(r"D:\CLAUDE\ozen\ozen-corpus.tar")


def main():
    manifests = {}
    wanted = {}
    for name in ("train", "dev", "unlabelled"):
        p = OUT / f"{name}.jsonl"
        if not p.exists():
            continue
        rows = [json.loads(l) for l in p.open(encoding="utf-8") if l.strip()]
        for r in rows:
            src = Path(r["wav"])
            arc = f"audio/{src.name}"
            wanted[arc] = src
            r["wav"] = arc
        manifests[name] = rows
        print(f"{name:11} {len(rows):6d} rows")

    print(f"unique audio files: {len(wanted)}")
    missing = [a for a, s in wanted.items() if not s.exists()]
    if missing:
        print(f"WARNING {len(missing)} referenced files are gone; first: {missing[:3]}")

    with tarfile.open(TAR, "w") as tf:
        for name, rows in manifests.items():
            tmp = OUT / f"{name}.rel.jsonl"
            with tmp.open("w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            tf.add(tmp, arcname=f"{name}.jsonl")
            tmp.unlink()
        alpha = OUT / "alphabet.json"
        if alpha.exists():
            tf.add(alpha, arcname="alphabet.json")
        n = 0
        for arc, src in wanted.items():
            if src.exists():
                tf.add(src, arcname=arc)
                n += 1
                if n % 2000 == 0:
                    print(f"   packed {n}/{len(wanted)}", flush=True)
    size = TAR.stat().st_size / (1024 ** 3)
    print(f"wrote {TAR}  ({size:.2f} GB, {n} clips)")


if __name__ == "__main__":
    main()
