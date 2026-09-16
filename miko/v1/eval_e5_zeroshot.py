"""MIKO v1 -- FROZEN e5-small, zero-shot (no adapter at all). The ceiling/reference
column: what a large lab's multilingual embedder gets on our exact task with zero
training on our data.
"""
from __future__ import annotations

import json
import pathlib

import torch

HERE = pathlib.Path(__file__).resolve().parent


def eval_split(doc_pack, q_pack, ids: list[str]) -> dict:
    doc_ids = doc_pack["ids"]
    doc_emb = doc_pack["emb"]
    id2row = {i: r for r, i in enumerate(doc_ids)}
    q_id2row = {i: r for r, i in enumerate(q_pack["ids"])}
    ids = [i for i in ids if i in q_id2row]
    if not ids:
        return {"recall@1": None, "recall@5": None, "mrr": None, "n": 0}
    r1 = r5 = mrr = 0.0
    for i in ids:
        q = q_pack["emb"][q_id2row[i]]
        sims = doc_emb @ q
        ranks = sims.argsort(descending=True)
        gold_row = id2row[i]
        pos = (ranks == gold_row).nonzero(as_tuple=True)[0].item() + 1
        if pos == 1:
            r1 += 1
        if pos <= 5:
            r5 += 1
        mrr += 1.0 / pos
    n = len(ids)
    return {"recall@1": r1 / n, "recall@5": r5 / n, "mrr": mrr / n, "n": n}


def eval_exam() -> dict:
    pack = torch.load(HERE / "e5_exam_emb.pt", weights_only=False)
    doc_pack = torch.load(HERE / "e5_doc_emb.pt", weights_only=False)
    doc_ids = doc_pack["ids"]
    doc_emb = doc_pack["emb"]
    r1 = r5 = 0
    for q_emb, target in zip(pack["emb"], pack["targets"]):
        sims = doc_emb @ q_emb
        ranks = sims.argsort(descending=True)
        gold_row = doc_ids.index(target)
        pos = (ranks == gold_row).nonzero(as_tuple=True)[0].item() + 1
        if pos == 1:
            r1 += 1
        if pos <= 5:
            r5 += 1
    n = len(pack["targets"])
    return {"recall@1": r1 / n, "recall@5": r5 / n, "n": n}


def main():
    split = json.loads((HERE / "split.json").read_text(encoding="utf-8"))
    doc_pack = torch.load(HERE / "e5_doc_emb.pt", weights_only=False)
    q_pack = torch.load(HERE / "e5_query_emb.pt", weights_only=False)

    val_m = eval_split(doc_pack, q_pack, split["val"])
    test_m = eval_split(doc_pack, q_pack, split["test"])
    exam_m = eval_exam()

    out = {"e5_zeroshot_val": val_m, "e5_zeroshot_test": test_m, "e5_zeroshot_exam": exam_m}
    (HERE / "e5_zeroshot_results.json").write_text(json.dumps(out, ensure_ascii=False, indent=2),
                                                     encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
