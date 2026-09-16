"""MIKO v1 -- the final side-by-side: BM25 / from-scratch net / frozen e5 zero-shot /
e5 + trained adapter -- on val, test, AND the 30-query hand-written exam.
"""
from __future__ import annotations

import json
import pathlib

import torch

from adapter import Adapter
from bm25 import BM25, eval_bm25
from model import MikoBiEncoder

HERE = pathlib.Path(__file__).resolve().parent


def load_corpus():
    docs = [json.loads(l) for l in (HERE / "corpus.jsonl").open(encoding="utf-8")]
    by_id = {d["id"]: d for d in docs}
    split = json.loads((HERE / "split.json").read_text(encoding="utf-8"))
    exam = json.loads((HERE / "exam.json").read_text(encoding="utf-8"))
    return docs, by_id, split, exam


def pairs_for(by_id, ids):
    return [(by_id[i]["query"], i) for i in ids if by_id[i].get("query")]


@torch.no_grad()
def eval_scratch(model, docs, pairs, device):
    doc_ids = [d["id"] for d in docs]
    doc_emb = model.encode([d["text"] for d in docs], device=device)
    id2row = {i: r for r, i in enumerate(doc_ids)}
    r1 = r5 = mrr = 0.0
    for q, gold in pairs:
        q_emb = model.encode([q], device=device)
        sims = (q_emb @ doc_emb.T).squeeze(0)
        ranked = sims.argsort(descending=True).tolist()
        pos = ranked.index(id2row[gold]) + 1
        if pos == 1:
            r1 += 1
        if pos <= 5:
            r5 += 1
        mrr += 1.0 / pos
    n = len(pairs)
    return {"recall@1": r1 / n, "recall@5": r5 / n, "mrr": mrr / n, "n": n}


def eval_e5_frozen(doc_pack, q_pack, ids):
    doc_ids, doc_emb = doc_pack["ids"], doc_pack["emb"]
    id2row = {i: r for r, i in enumerate(doc_ids)}
    q_id2row = {i: r for r, i in enumerate(q_pack["ids"])}
    ids = [i for i in ids if i in q_id2row]
    r1 = r5 = mrr = 0.0
    for i in ids:
        sims = doc_emb @ q_pack["emb"][q_id2row[i]]
        ranked = sims.argsort(descending=True).tolist()
        pos = ranked.index(id2row[i]) + 1
        if pos == 1:
            r1 += 1
        if pos <= 5:
            r5 += 1
        mrr += 1.0 / pos
    n = len(ids)
    return {"recall@1": r1 / n, "recall@5": r5 / n, "mrr": mrr / n, "n": n}


def eval_e5_adapter(adapter, doc_pack, q_pack, ids, device):
    doc_ids = doc_pack["ids"]
    id2row = {i: r for r, i in enumerate(doc_ids)}
    q_id2row = {i: r for r, i in enumerate(q_pack["ids"])}
    ids = [i for i in ids if i in q_id2row]
    with torch.no_grad():
        doc_out = adapter(doc_pack["emb"].to(device))
    r1 = r5 = mrr = 0.0
    for i in ids:
        with torch.no_grad():
            q_out = adapter(q_pack["emb"][q_id2row[i]].unsqueeze(0).to(device))
        sims = (doc_out @ q_out.squeeze(0))
        ranked = sims.argsort(descending=True).tolist()
        pos = ranked.index(id2row[i]) + 1
        if pos == 1:
            r1 += 1
        if pos <= 5:
            r5 += 1
        mrr += 1.0 / pos
    n = len(ids)
    return {"recall@1": r1 / n, "recall@5": r5 / n, "mrr": mrr / n, "n": n}


def eval_bm25_exam(bm25, exam):
    r1 = r5 = 0
    for e in exam:
        ranked = bm25.search_all_ranked(e["query"])
        pos = ranked.index(e["target_id"]) + 1
        if pos == 1:
            r1 += 1
        if pos <= 5:
            r5 += 1
    n = len(exam)
    return {"recall@1": r1 / n, "recall@5": r5 / n, "n": n}


@torch.no_grad()
def eval_scratch_exam(model, docs, exam, device):
    doc_ids = [d["id"] for d in docs]
    doc_emb = model.encode([d["text"] for d in docs], device=device)
    id2row = {i: r for r, i in enumerate(doc_ids)}
    r1 = r5 = 0
    for e in exam:
        q_emb = model.encode([e["query"]], device=device)
        sims = (q_emb @ doc_emb.T).squeeze(0)
        ranked = sims.argsort(descending=True).tolist()
        pos = ranked.index(id2row[e["target_id"]]) + 1
        if pos == 1:
            r1 += 1
        if pos <= 5:
            r5 += 1
    n = len(exam)
    return {"recall@1": r1 / n, "recall@5": r5 / n, "n": n}


def eval_e5_zeroshot_exam():
    exam_pack = torch.load(HERE / "e5_exam_emb.pt", weights_only=False)
    doc_pack = torch.load(HERE / "e5_doc_emb.pt", weights_only=False)
    doc_ids = doc_pack["ids"]
    r1 = r5 = 0
    for q_emb, target in zip(exam_pack["emb"], exam_pack["targets"]):
        sims = doc_pack["emb"] @ q_emb
        ranked = sims.argsort(descending=True).tolist()
        pos = ranked.index(doc_ids.index(target)) + 1
        if pos == 1:
            r1 += 1
        if pos <= 5:
            r5 += 1
    n = len(exam_pack["targets"])
    return {"recall@1": r1 / n, "recall@5": r5 / n, "n": n}


def eval_e5_adapter_exam(adapter, device):
    exam_pack = torch.load(HERE / "e5_exam_emb.pt", weights_only=False)
    doc_pack = torch.load(HERE / "e5_doc_emb.pt", weights_only=False)
    doc_ids = doc_pack["ids"]
    with torch.no_grad():
        doc_out = adapter(doc_pack["emb"].to(device))
        q_out = adapter(exam_pack["emb"].to(device))
    r1 = r5 = 0
    for row, target in enumerate(exam_pack["targets"]):
        sims = doc_out @ q_out[row]
        ranked = sims.argsort(descending=True).tolist()
        pos = ranked.index(doc_ids.index(target)) + 1
        if pos == 1:
            r1 += 1
        if pos <= 5:
            r5 += 1
    n = len(exam_pack["targets"])
    return {"recall@1": r1 / n, "recall@5": r5 / n, "n": n}


def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    docs, by_id, split, exam = load_corpus()
    val_pairs = pairs_for(by_id, split["val"])
    test_pairs = pairs_for(by_id, split["test"])

    bm25 = BM25([d["id"] for d in docs], [d["text"] for d in docs])
    bm25_val = eval_bm25(bm25, val_pairs)
    bm25_test = eval_bm25(bm25, test_pairs)
    bm25_exam = eval_bm25_exam(bm25, exam)

    ckpt = torch.load(HERE / "miko-v1.pt", map_location=device, weights_only=False)
    scratch = MikoBiEncoder(d=ckpt["d"], depth=ckpt["depth"]).to(device)
    scratch.load_state_dict(ckpt["model_state"])
    scratch.eval()
    scratch_val = eval_scratch(scratch, docs, val_pairs, device)
    scratch_test = eval_scratch(scratch, docs, test_pairs, device)
    scratch_exam = eval_scratch_exam(scratch, docs, exam, device)

    doc_pack = torch.load(HERE / "e5_doc_emb.pt", weights_only=False)
    q_pack = torch.load(HERE / "e5_query_emb.pt", weights_only=False)
    e5_val = eval_e5_frozen(doc_pack, q_pack, split["val"])
    e5_test = eval_e5_frozen(doc_pack, q_pack, split["test"])
    e5_exam = eval_e5_zeroshot_exam()

    ackpt = torch.load(HERE / "adapter-v1.pt", map_location=device, weights_only=False)
    adapter = Adapter(d_in=ackpt["d_in"], d_out=ackpt["d_out"], depth=ackpt["depth"]).to(device)
    adapter.load_state_dict(ackpt["model_state"])
    adapter.eval()
    ad_val = eval_e5_adapter(adapter, doc_pack, q_pack, split["val"], device)
    ad_test = eval_e5_adapter(adapter, doc_pack, q_pack, split["test"], device)
    ad_exam = eval_e5_adapter_exam(adapter, device)

    out = {
        "bm25": {"val": bm25_val, "test": bm25_test, "exam": bm25_exam},
        "from_scratch_net": {"val": scratch_val, "test": scratch_test, "exam": scratch_exam,
                              "params": sum(p.numel() for p in scratch.parameters())},
        "e5_zeroshot": {"val": e5_val, "test": e5_test, "exam": e5_exam, "params": 117653760,
                         "frozen": True},
        "e5_plus_adapter": {"val": ad_val, "test": ad_test, "exam": ad_exam,
                             "adapter_params": sum(p.numel() for p in adapter.parameters()),
                             "frozen_backbone_params": 117653760},
    }
    (HERE / "compare_all_results.json").write_text(json.dumps(out, ensure_ascii=False, indent=2),
                                                     encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
