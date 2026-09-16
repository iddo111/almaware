"""MELUMAD dedupe pass 2 -- cluster by INCIDENT, not by rule wording.

Four independent extractors read overlapping sources, so the same incident arrives
worded three different ways. Pure string similarity on the rule missed all of them.
This clusters on content-word overlap across title+rule+failure, requires the same
domain, and prints every proposed merge so it can be eyed before it is accepted.

  python dedupe.py           # dry run, prints proposed merges
  python dedupe.py --apply   # rewrites lessons.jsonl
"""
import json, os, re, sys, collections

HERE = os.path.dirname(os.path.abspath(__file__))
LESSONS = os.path.join(HERE, "lessons.jsonl")

STOP = set("""a an the and or of to in on for with without is are was were be been being it its this that
these those any all no not never always must should can cannot do does did done use used using when while
before after from by as at into onto than then there their them they you your our we us if but so such only
one two more most less least other another each every both same different new old real true false thing
things something anything nothing what which who whom whose how why where over under about against between
run runs ran running make makes made making get gets got getting take takes took taking give gives gave
has have had having will would could may might shall not out up down off own very just also even still
""".split())

NUM = re.compile(r"\d+(?:\.\d+)?")


def words(s):
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9֐-׿ ]+", " ", s)
    return {w for w in s.split() if len(w) > 2 and w not in STOP}


def nums(s):
    """Distinctive numbers are the best fingerprint for 'same incident'."""
    out = set()
    for m in NUM.findall(s or ""):
        if m in ("0", "1", "2", "3", "4", "5", "10", "100"):
            continue
        out.add(m)
    return out


def jaccard(a, b):
    return len(a & b) / len(a | b) if (a | b) else 0.0


def main():
    apply = "--apply" in sys.argv
    rows = [json.loads(l) for l in open(LESSONS, encoding="utf-8") if l.strip()]
    for r in rows:
        r["_w"] = words(r["title"] + " " + r["rule"])
        r["_wf"] = words(r["failure"] + " " + r.get("measurement", ""))
        r["_n"] = nums(r["failure"] + " " + r.get("measurement", ""))

    parent = list(range(len(rows)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        a, b = find(i), find(j)
        if a != b:
            parent[max(a, b)] = min(a, b)

    proposals = []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            A, B = rows[i], rows[j]
            if A["domain"] != B["domain"]:
                continue
            jt = jaccard(A["_w"], B["_w"])          # rule/title agreement
            jf = jaccard(A["_wf"], B["_wf"])        # incident agreement
            shared_n = A["_n"] & B["_n"]
            same = (jt >= 0.50) or (jf >= 0.42) or (jt >= 0.32 and jf >= 0.30) \
                or (len(shared_n) >= 2 and (jt >= 0.22 or jf >= 0.22))
            if same:
                proposals.append((round(jt, 2), round(jf, 2), sorted(shared_n)[:4], A, B))
                union(i, j)

    print(f"{len(rows)} lessons -> {len(proposals)} merge proposals\n")
    for jt, jf, sn, A, B in sorted(proposals, key=lambda p: -(p[0] + p[1])):
        print(f"[title/rule {jt}  incident {jf}  shared#{sn}]  {A['domain']}")
        print(f"   KEEP {A['id']:10s} {A['title'][:88]}")
        print(f"   DUP  {B['id']:10s} {B['title'][:88]}")

    clusters = collections.defaultdict(list)
    for i in range(len(rows)):
        clusters[find(i)].append(i)
    distinct = len(clusters)
    print(f"\n{len(rows)} raw -> {distinct} distinct incidents "
          f"({len(rows)-distinct} collapsed)")

    if not apply:
        print("\n(dry run - pass --apply to rewrite lessons.jsonl)")
        return

    out = []
    for root, members in sorted(clusters.items()):
        members.sort(key=lambda i: (not rows[i].get("measurement", "").strip(),
                                    -len(rows[i].get("measurement", "")),
                                    rows[i]["id"]))
        keep = rows[members[0]]
        keep["corroborated_by"] = [rows[i]["source"] for i in members[1:]]
        keep["corroborating_ids"] = [rows[i]["id"] for i in members[1:]]
        keep["independent_sources"] = 1 + len(members) - 1
        for k in ("_w", "_wf", "_n"):
            keep.pop(k, None)
        out.append(keep)

    out.sort(key=lambda r: (r["domain"], r["id"]))
    for n, r in enumerate(out, 1):
        r["lesson_id"] = f"L{n:03d}"
    with open(LESSONS, "w", encoding="utf-8", newline="\n") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    multi = sum(1 for r in out if r["independent_sources"] > 1)
    print(f"\nwrote {len(out)} distinct lessons; {multi} confirmed by >1 independent extractor")


if __name__ == "__main__":
    main()
