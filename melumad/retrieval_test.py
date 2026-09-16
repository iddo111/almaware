"""Does retrieval over lessons.jsonl actually work? Measure it, do not assume it.

Reuses miko/v1/bm25.py (the house's existing Okapi BM25 control) rather than writing
another one. The queries below are written as a confused engineer would describe the
SYMPTOM -- deliberately NOT reusing the lesson's own wording, which would be cheating.

  set PYTHONIOENCODING=utf-8 && python retrieval_test.py
"""
import json, os, sys

sys.path.insert(0, r"D:\CLAUDE\miko\v1")
from bm25 import BM25  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
LESSONS = os.path.join(HERE, "lessons.jsonl")

# (symptom as an engineer would say it, {ids that are ALL correct answers})
# Several lessons exist in near-duplicate form from different extractors, so the gold is
# a SET: retrieving any member is a hit. Scoring a duplicate as a miss understates BM25.
QUERIES = [
    ("my contrastive training loss barely moves and the curve looks flat",       {"core-015", "vaada-022"}),
    ("the saved model file says epoch 1 but I trained for 15 epochs",             {"core-016", "vaada-023"}),
    ("my normalisation layer outputs zeros no matter what I feed it",             {"mem-018"}),
    ("the dictation types thank you when nobody is talking",                      {"bak-002", "mem-044", "vaada-056"}),
    ("python script stopped halfway through and printed nothing, hebrew text",    {"core-003"}),
    ("my retriever scores zero but the training loss went down nicely",           {"vaada-025"}),
    ("keystrokes go nowhere when I send them to an admin window",                 {"bak-031", "mem-007"}),
    ("half of what the user says is being thrown away as too quiet",              {"core-011", "bak-023"}),
    ("two microphones are typing at the same time",                               {"core-014", "mem-039", "vaada-010"}),
    ("the service looks healthy but the output is wrong",                         {"core-004", "mem-064"}),
    ("we called the audio human but it was generated",                            {"core-009", "mem-005", "vaada-053"}),
    ("the log file is empty so the request never arrived, right?",                {"core-007"}),
    ("cpu is pinned at 100 percent and the microphone keeps timing out",          {"core-008", "mem-042", "vaada-081"}),
    ("a marker file turned something off and nobody noticed for hours",           {"core-018"}),
    ("the tool deleted its own directory while running",                          {"core-020"}),
    ("systemctl says the unit does not exist but the process is clearly running", {"emet-003"}),
    ("the summary says there is no risk but the original said do not ship",       {"emet-004"}),
    ("BM25 beats my trained embedding model, is that normal",                     {"core-017", "vaada-006"}),
    ("scaling law says I need this much data, does it apply to my search index",  {"vaada-001"}),
    ("the gate lets the room noise through but blocks quiet speech",              {"core-013"}),
]

# The corpus is bilingual: measurements were often recorded in Hebrew while the lesson
# prose is English. These pairs test the SAME lesson in both languages.
BILINGUAL = [
    ("the dictation types thank you when nobody is talking",  "המיקרופון מקליד תודה כשאף אחד לא מדבר",
     {"bak-002", "mem-044", "vaada-056"}),
    ("half of what the user says is thrown away as too quiet", "חצי ממה שנאמר נזרק כי הוא שקט מדי",
     {"core-011", "bak-023"}),
]


def main():
    rows = [json.loads(l) for l in open(LESSONS, encoding="utf-8") if l.strip()]
    by_id = {r["id"]: r for r in rows}
    ids = [r["id"] for r in rows]
    # index the whole lesson, the way it would be indexed in production
    texts = [" ".join([r["title"], r["rule"], r["situation"], r["action"],
                       r["failure"], r.get("measurement", ""), r["domain"]]) for r in rows]
    bm = BM25(ids, texts)

    def best_rank(query, gold_set):
        """Rank of the FIRST acceptable answer; any member of the set counts."""
        ranked = [d for d, _ in bm.search(query, top_k=len(rows))]
        for i, d in enumerate(ranked, 1):
            if d in gold_set:
                return i, ranked
        return None, ranked

    r1 = r3 = r5 = 0
    mrr = 0.0
    scored = [(q, {g for g in gs if g in by_id}) for q, gs in QUERIES]
    dropped = [q for q, gs in scored if not gs]
    scored = [(q, gs) for q, gs in scored if gs]
    if dropped:
        print(f"!! {len(dropped)} queries had no surviving gold id and were dropped\n")
    print(f"{len(scored)} queries against {len(rows)} lessons\n")
    for q, gold in scored:
        rank, ranked = best_rank(q, gold)
        if rank == 1:
            r1 += 1
        if rank and rank <= 3:
            r3 += 1
        if rank and rank <= 5:
            r5 += 1
        if rank:
            mrr += 1 / rank
        mark = "OK " if rank == 1 else ("~  " if rank and rank <= 5 else "MISS")
        got = by_id[ranked[0]]["title"][:52] if ranked else "-"
        print(f"  [{mark}] rank={str(rank):>4}  {q[:56]:<56} -> {got}")

    n = len(scored)
    print(f"\n  recall@1 = {r1/n:.3f}   recall@3 = {r3/n:.3f}   recall@5 = {r5/n:.3f}   MRR = {mrr/n:.3f}   (n={n})")

    print("\n  --- bilingual check: same lesson, English query vs Hebrew query ---")
    for en, he, gold in BILINGUAL:
        gold = {g for g in gold if g in by_id}
        if not gold:
            continue
        re_, _ = best_rank(en, gold)
        rh, _ = best_rank(he, gold)
        print(f"    EN rank={str(re_):>5}   HE rank={str(rh):>5}   {en[:50]}")
    print("\n  Baseline for comparison, same house, same source documents:")
    print("    miko/v1 trained 50.8M-param retriever : recall@1 = 0.000")
    print("    miko/v1 BM25 control                  : recall@1 = 0.712 val / 0.540 test")


if __name__ == "__main__":
    main()
