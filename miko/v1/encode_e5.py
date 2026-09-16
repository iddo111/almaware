"""MIKO v1 -- precompute FROZEN intfloat/multilingual-e5-small embeddings for the whole
corpus + every query (train/val/test/exam), once. The backbone never trains; only a
small adapter on top of these cached vectors does (adapter_train.py). This is
distillation, not pretraining -- the direction Chinchilla's numbers force us to
(D:\\CLAUDE\\_status-reports-archive\\CHINCHILLA-20260903.md: our corpora are 3-5 orders
of magnitude too small to train a useful net from scratch; the fix is a frozen
external backbone + a small trained head).

e5 convention: "query: " / "passage: " prefixes, mean-pool over the attention mask,
L2-normalise. https://huggingface.co/intfloat/multilingual-e5-small
"""
from __future__ import annotations

import json
import pathlib

import torch
import torch.nn.functional as F
from transformers import AutoModel, AutoTokenizer

HERE = pathlib.Path(__file__).resolve().parent
E5_PATH = str(HERE / "e5-small")


def mean_pool(last_hidden, attn_mask):
    mask = attn_mask.unsqueeze(-1).float()
    summed = (last_hidden * mask).sum(1)
    counts = mask.sum(1).clamp(min=1e-9)
    return summed / counts


@torch.no_grad()
def encode_e5(texts: list[str], prefix: str, tok, model, device, bs: int = 32, max_len: int = 512):
    out = []
    for i in range(0, len(texts), bs):
        chunk = [prefix + t for t in texts[i:i + bs]]
        enc = tok(chunk, padding=True, truncation=True, max_length=max_len, return_tensors="pt").to(device)
        o = model(**enc)
        pooled = mean_pool(o.last_hidden_state, enc["attention_mask"])
        pooled = F.normalize(pooled, dim=-1)
        out.append(pooled.cpu())
    return torch.cat(out, 0)


def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained(E5_PATH)
    model = AutoModel.from_pretrained(E5_PATH).to(device).eval()
    print(f"e5-small loaded, device={device}, params={sum(p.numel() for p in model.parameters()):,}")

    docs = [json.loads(l) for l in (HERE / "corpus.jsonl").open(encoding="utf-8")]
    doc_ids = [d["id"] for d in docs]
    doc_texts = [d["text"] for d in docs]
    doc_emb = encode_e5(doc_texts, "passage: ", tok, model, device)
    torch.save({"ids": doc_ids, "emb": doc_emb}, HERE / "e5_doc_emb.pt")
    print(f"doc embeddings: {doc_emb.shape} -> e5_doc_emb.pt")

    # every unique query text across train/val/test docs (== every doc with a query)
    by_id = {d["id"]: d for d in docs}
    q_ids = [d["id"] for d in docs if d.get("query")]
    q_texts = [by_id[i]["query"] for i in q_ids]
    q_emb = encode_e5(q_texts, "query: ", tok, model, device)
    torch.save({"ids": q_ids, "emb": q_emb}, HERE / "e5_query_emb.pt")
    print(f"query embeddings: {q_emb.shape} -> e5_query_emb.pt")

    exam = json.loads((HERE / "exam.json").read_text(encoding="utf-8"))
    exam_texts = [e["query"] for e in exam]
    exam_emb = encode_e5(exam_texts, "query: ", tok, model, device)
    torch.save({"queries": exam_texts, "targets": [e["target_id"] for e in exam], "emb": exam_emb},
               HERE / "e5_exam_emb.pt")
    print(f"exam embeddings: {exam_emb.shape} -> e5_exam_emb.pt")


if __name__ == "__main__":
    main()
