"""MIKO v1 -- per-query exam detail across all four methods, for the report table."""
from __future__ import annotations

import json
import pathlib

import torch

import exam_gate
import scar_guard
from adapter import Adapter
from bm25 import BM25
from model import MikoBiEncoder

HERE = pathlib.Path(__file__).resolve().parent


def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    docs = [json.loads(l) for l in (HERE / "corpus.jsonl").open(encoding="utf-8")]
    exam = json.loads((HERE / "exam.json").read_text(encoding="utf-8"))
    doc_ids = [d["id"] for d in docs]
    split = json.loads((HERE / "split.json").read_text(encoding="utf-8"))
    exam_gate.assert_exam_valid(exam, {d["id"]: d for d in docs})     # MIKO-05
    print(exam_gate.exam_composition(exam, split))

    bm25 = BM25(doc_ids, [d["text"] for d in docs])

    ckpt = torch.load(HERE / "miko-v1.pt", map_location=device, weights_only=False)
    scratch = MikoBiEncoder(d=ckpt["d"], depth=ckpt["depth"]).to(device)
    scratch.load_state_dict(ckpt["model_state"])
    scratch.eval()
    scar_guard.run(scratch)                                            # MIKO-07
    with torch.no_grad():
        scratch_doc_emb = scratch.encode([d["text"] for d in docs], device=device)

    exam_pack = torch.load(HERE / "e5_exam_emb.pt", weights_only=False)
    exam_gate.assert_exam_cache_fresh(exam_pack, exam)                 # MIKO-05
    doc_pack = torch.load(HERE / "e5_doc_emb.pt", weights_only=False)
    e5_doc_ids = doc_pack["ids"]

    ackpt = torch.load(HERE / "adapter-v1.pt", map_location=device, weights_only=False)
    adapter = Adapter(d_in=ackpt["d_in"], d_out=ackpt["d_out"], depth=ackpt["depth"]).to(device)
    adapter.load_state_dict(ackpt["model_state"])
    adapter.eval()
    scar_guard.run_adapter(adapter, d_in=ackpt["d_in"])                # MIKO-07
    with torch.no_grad():
        ad_doc_emb = adapter(doc_pack["emb"].to(device))

    rows = []
    for idx, e in enumerate(exam):
        q, gold = e["query"], e["target_id"]
        bm25_rank = bm25.rank_of(q, gold)      # MIKO-13: None when unreachable, not 554

        with torch.no_grad():
            q_emb = scratch.encode([q], device=device)
            sims = (q_emb @ scratch_doc_emb.T).squeeze(0)
        scratch_ranked = [doc_ids[i] for i in sims.argsort(descending=True).tolist()]
        scratch_rank = scratch_ranked.index(gold) + 1

        e5_q = exam_pack["emb"][idx]
        sims = doc_pack["emb"] @ e5_q
        e5_ranked = [e5_doc_ids[i] for i in sims.argsort(descending=True).tolist()]
        e5_rank = e5_ranked.index(gold) + 1

        with torch.no_grad():
            ad_q = adapter(e5_q.unsqueeze(0).to(device)).squeeze(0)
        sims = ad_doc_emb @ ad_q
        ad_ranked = [e5_doc_ids[i] for i in sims.argsort(descending=True).tolist()]
        ad_rank = ad_ranked.index(gold) + 1

        rows.append({"lang": e["lang"], "query": q, "target": gold,
                      "bm25_rank": bm25_rank, "scratch_rank": scratch_rank,
                      "e5_rank": e5_rank, "adapter_rank": ad_rank})

    (HERE / "exam_detail.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2),
                                            encoding="utf-8")
    for r in rows:
        print(f"[{r['lang']}] bm25={r['bm25_rank']:>4} scratch={r['scratch_rank']:>4} "
              f"e5={r['e5_rank']:>4} adapter={r['adapter_rank']:>4}  {r['query'][:60]}")


if __name__ == "__main__":
    main()
