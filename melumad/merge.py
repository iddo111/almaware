"""MELUMAD merge: combine every part_*.jsonl into lessons.jsonl, dedupe, and report.

Run:  set PYTHONIOENCODING=utf-8 && python D:\\CLAUDE\\melumad\\merge.py
Read-only on every source; writes only lessons.jsonl and prints a census.
"""
import glob, json, os, re, collections, difflib

HERE = os.path.dirname(os.path.abspath(__file__))
REQUIRED = {"id", "title", "domain", "situation", "action", "failure",
            "measurement", "rule", "source", "date", "generality"}


def norm(s):
    """Normalise a rule for near-duplicate comparison."""
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9\u0590-\u05ff ]+", " ", s)
    return " ".join(s.split())


def load_parts():
    rows, problems = [], []
    for path in sorted(glob.glob(os.path.join(HERE, "part_*.jsonl"))):
        for n, line in enumerate(open(path, encoding="utf-8"), 1):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception as e:
                problems.append(f"{os.path.basename(path)}:{n} unparseable: {e}")
                continue
            missing = REQUIRED - set(r)
            if missing:
                for k in missing:
                    r[k] = ""
                problems.append(f"{os.path.basename(path)}:{n} filled missing {sorted(missing)}")
            r["_part"] = os.path.basename(path)
            rows.append(r)
    return rows, problems


def dedupe(rows, threshold=0.86):
    """Collapse near-identical lessons, keeping the one with the most evidence."""
    kept, merged = [], 0
    for r in rows:
        key = norm(r["rule"])
        hit = None
        for k in kept:
            if difflib.SequenceMatcher(None, key, norm(k["rule"])).ratio() >= threshold:
                hit = k
                break
            # same title is also a duplicate signal
            if norm(r["title"]) and norm(r["title"]) == norm(k["title"]):
                hit = k
                break
        if hit is None:
            r["also_seen_in"] = []
            kept.append(r)
        else:
            merged += 1
            hit.setdefault("also_seen_in", []).append(r["source"])
            # prefer the version that actually carries a measurement
            if not hit.get("measurement") and r.get("measurement"):
                hit["measurement"] = r["measurement"]
                hit["source"] = r["source"]
    return kept, merged


def main():
    rows, problems = load_parts()
    print(f"loaded {len(rows)} raw lessons from {len(set(r['_part'] for r in rows))} parts")
    for p in problems[:20]:
        print("  !", p)
    if len(problems) > 20:
        print(f"  ... and {len(problems)-20} more schema notes")

    kept, merged = dedupe(rows)
    print(f"deduped: {merged} collapsed -> {len(kept)} distinct lessons\n")

    # renumber stably
    for i, r in enumerate(sorted(kept, key=lambda x: (x["domain"], x["id"])), 1):
        r["lesson_id"] = f"L{i:03d}"

    out = os.path.join(HERE, "lessons.jsonl")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        for r in sorted(kept, key=lambda x: x["lesson_id"]):
            r.pop("_part", None)
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {out}  ({len(kept)} lessons)\n")

    print("by source part:")
    for k, v in collections.Counter(r.get("id", "?").split("-")[0] for r in kept).most_common():
        print(f"  {k:10s} {v:4d}")
    print("\nby domain:")
    for k, v in collections.Counter(r["domain"] for r in kept).most_common():
        print(f"  {k:18s} {v:4d}")
    print("\nby generality:")
    for k, v in collections.Counter(r["generality"] for r in kept).most_common():
        print(f"  {k:18s} {v:4d}")
    withm = sum(1 for r in kept if (r.get("measurement") or "").strip())
    print(f"\ncarrying a real measurement: {withm}/{len(kept)} ({100*withm/max(len(kept),1):.0f}%)")

    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        text = open(out, encoding="utf-8").read()
        print(f"lessons.jsonl: {len(text)} chars, {len(enc.encode(text))} tokens")
    except ImportError:
        pass


if __name__ == "__main__":
    main()
