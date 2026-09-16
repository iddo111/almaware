"""MIKO v1 -- search CLI. All four methods live here; BM25 is the default because it is
the one that WON the 30-query exam (0.30 recall@1 vs 0.13 zero-shot e5, 0.10 e5+adapter,
0.00 from-scratch). CPU inference on the PC is fine here -- these nets are already
trained; this is not training. לזכרה של עלמה ז"ל.

    python search.py "<query>"                     # BM25 (best on the real exam)
    python search.py "<query>" --method e5          # frozen multilingual-e5-small
    python search.py "<query>" --method adapter     # e5 + our trained adapter
    python search.py "<query>" --method scratch     # our from-scratch net (weak, honest)
    python search.py "<query>" --method all         # print all four, side by side
"""
from __future__ import annotations

import argparse
import json
import pathlib

import torch

HERE = pathlib.Path(__file__).resolve().parent


def load_corpus():
    return [json.loads(l) for l in (HERE / "corpus.jsonl").open(encoding="utf-8")]


def search_bm25(query: str, docs: list[dict], top_k: int = 5):
    from bm25 import BM25
    bm25 = BM25([d["id"] for d in docs], [d["text"] for d in docs])
    hits = bm25.search(query, top_k=top_k)
    by_id = {d["id"]: d for d in docs}
    return [(doc_id, score, by_id[doc_id]["query"], by_id[doc_id]["source"]) for doc_id, score in hits]


def search_scratch(query: str, docs: list[dict], top_k: int = 5, device: str = "cpu"):
    from model import MikoBiEncoder
    ckpt = torch.load(HERE / "miko-v1.pt", map_location=device, weights_only=False)
    model = MikoBiEncoder(d=ckpt["d"], depth=ckpt["depth"]).to(device)
    model.load_state_dict(ckpt["model_state"])
    model.eval()
    with torch.no_grad():
        doc_emb = model.encode([d["text"] for d in docs], device=device)
        q_emb = model.encode([query], device=device)
        sims = (q_emb @ doc_emb.T).squeeze(0)
    order = sims.argsort(descending=True)[:top_k].tolist()
    return [(docs[i]["id"], float(sims[i]), docs[i]["query"], docs[i]["source"]) for i in order]


def _e5_encode(texts, prefix, tok, model, device):
    import torch.nn.functional as F
    enc = tok([prefix + t for t in texts], padding=True, truncation=True, max_length=512,
              return_tensors="pt").to(device)
    with torch.no_grad():
        o = model(**enc)
        mask = enc["attention_mask"].unsqueeze(-1).float()
        pooled = (o.last_hidden_state * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
        return F.normalize(pooled, dim=-1)


def search_e5(query: str, docs: list[dict], top_k: int = 5, device: str = "cpu", use_adapter: bool = False):
    try:
        from transformers import AutoModel, AutoTokenizer
    except ImportError as e:
        raise SystemExit(
            "transformers is not importable on this PC install (huggingface-hub version "
            "mismatch, pre-existing -- not something this task patched). Run --method e5 "
            "or --method adapter via: ssh eran3 \"cd ~/miko/v1 && python3 search.py '<query>' "
            f"--method {'adapter' if use_adapter else 'e5'}\" instead.\n(underlying error: {e})"
        )
    tok = AutoTokenizer.from_pretrained(str(HERE / "e5-small"))
    backbone = AutoModel.from_pretrained(str(HERE / "e5-small")).to(device).eval()
    doc_pack_path = HERE / "e5_doc_emb.pt"
    if doc_pack_path.exists():
        pack = torch.load(doc_pack_path, map_location=device, weights_only=False)
        doc_ids, doc_emb = pack["ids"], pack["emb"].to(device)
    else:
        doc_ids = [d["id"] for d in docs]
        doc_emb = _e5_encode([d["text"] for d in docs], "passage: ", tok, backbone, device)
    q_emb = _e5_encode([query], "query: ", tok, backbone, device)

    if use_adapter:
        from adapter import Adapter
        ackpt = torch.load(HERE / "adapter-v1.pt", map_location=device, weights_only=False)
        adapter = Adapter(d_in=ackpt["d_in"], d_out=ackpt["d_out"], depth=ackpt["depth"]).to(device)
        adapter.load_state_dict(ackpt["model_state"])
        adapter.eval()
        with torch.no_grad():
            doc_emb = adapter(doc_emb)
            q_emb = adapter(q_emb)

    with torch.no_grad():
        sims = (q_emb @ doc_emb.T).squeeze(0)
    order = sims.argsort(descending=True)[:top_k].tolist()
    by_id = {d["id"]: d for d in docs}
    return [(doc_ids[i], float(sims[i]), by_id[doc_ids[i]]["query"], by_id[doc_ids[i]]["source"])
            for i in order]


def print_results(title: str, results):
    print(f"\n-- {title} --")
    for rank, (doc_id, score, desc, source) in enumerate(results, 1):
        print(f"{rank}. [{score:.4f}] {doc_id}  ({source})")
        print(f"   {desc[:150]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="+")
    ap.add_argument("--method", choices=["bm25", "scratch", "e5", "adapter", "all"], default="bm25")
    ap.add_argument("--top-k", type=int, default=5)
    args = ap.parse_args()
    query = " ".join(args.query)
    docs = load_corpus()

    if args.method in ("bm25", "all"):
        print_results("BM25 (best on the 30-query exam)", search_bm25(query, docs, args.top_k))
    if args.method in ("scratch", "all"):
        print_results("from-scratch net (honest, currently weak)", search_scratch(query, docs, args.top_k))
    if args.method in ("e5", "all"):
        print_results("frozen multilingual-e5-small (zero-shot)", search_e5(query, docs, args.top_k))
    if args.method in ("adapter", "all"):
        print_results("e5 + trained adapter", search_e5(query, docs, args.top_k, use_adapter=True))


if __name__ == "__main__":
    main()
