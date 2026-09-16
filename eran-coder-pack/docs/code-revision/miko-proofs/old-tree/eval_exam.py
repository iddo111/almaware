"""MIKO v1 -- the 30-query hand-labelled exam. Hebrew + English, written by hand from
the corpus (not copied from any stored description), so this is the one number Iddo
will actually care about. Reports MIKO's trained net AND BM25 side by side.

Run:
    python eval_exam.py --ckpt miko-v1.pt
"""
from __future__ import annotations

import argparse
import json
import pathlib

import torch

from bm25 import BM25
from model import MikoBiEncoder

HERE = pathlib.Path(__file__).resolve().parent


def load_all():
    docs = [json.loads(l) for l in (HERE / "corpus.jsonl").open(encoding="utf-8")]
    by_id = {d["id"]: d for d in docs}
    exam = json.loads((HERE / "exam.json").read_text(encoding="utf-8"))
    return docs, by_id, exam


@torch.no_grad()
def miko_rank(model, docs, query, device):
    doc_ids = [d["id"] for d in docs]
    doc_emb = model.encode([d["text"] for d in docs], device=device)
    q_emb = model.encode([query], device=device)
    sims = (q_emb @ doc_emb.T).squeeze(0)
    order = sims.argsort(descending=True).tolist()
    return [doc_ids[i] for i in order], sims.tolist()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", type=str, default=str(HERE / "miko-v1.pt"))
    ap.add_argument("--device", type=str, default="cpu")
    args = ap.parse_args()

    docs, by_id, exam = load_all()
    doc_ids_all = [d["id"] for d in docs]

    ckpt = torch.load(args.ckpt, map_location=args.device, weights_only=False)
    model = MikoBiEncoder(d=ckpt["d"], depth=ckpt["depth"]).to(args.device)
    model.load_state_dict(ckpt["model_state"])
    model.eval()

    bm25 = BM25(doc_ids_all, [d["text"] for d in docs])

    # precompute doc embeddings once
    with torch.no_grad():
        doc_emb = model.encode([d["text"] for d in docs], device=args.device)

    rows = []
    miko_r1 = miko_r5 = bm25_r1 = bm25_r5 = 0
    for ex in exam:
        q, gold = ex["query"], ex["target_id"]
        with torch.no_grad():
            q_emb = model.encode([q], device=args.device)
            sims = (q_emb @ doc_emb.T).squeeze(0)
            order = sims.argsort(descending=True).tolist()
        miko_ranked = [doc_ids_all[i] for i in order]
        miko_rank_pos = miko_ranked.index(gold) + 1
        bm25_ranked = bm25.search_all_ranked(q)
        bm25_rank_pos = bm25_ranked.index(gold) + 1

        if miko_rank_pos == 1:
            miko_r1 += 1
        if miko_rank_pos <= 5:
            miko_r5 += 1
        if bm25_rank_pos == 1:
            bm25_r1 += 1
        if bm25_rank_pos <= 5:
            bm25_r5 += 1

        rows.append({
            "query": q, "lang": ex["lang"], "target": gold,
            "miko_rank": miko_rank_pos, "miko_top5": miko_ranked[:5],
            "bm25_rank": bm25_rank_pos, "bm25_top5": bm25_ranked[:5],
        })

    n = len(exam)
    summary = {
        "n": n,
        "miko_recall@1": miko_r1 / n, "miko_recall@5": miko_r5 / n,
        "bm25_recall@1": bm25_r1 / n, "bm25_recall@5": bm25_r5 / n,
    }
    out = {"summary": summary, "rows": rows}
    (HERE / "exam_results.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nwrote per-query detail -> {HERE / 'exam_results.json'}")


if __name__ == "__main__":
    main()
