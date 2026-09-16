"""MIKO v1 -- train the adapter on cached frozen e5-small embeddings.

Same task, same split, same BM25-mined hard negatives as the from-scratch run
(train.py) -- so the three numbers (BM25 / from-scratch / e5+adapter) are directly
comparable. Training is on cached vectors, so this is fast even without a GPU, but we
still run it on eran3 (GPU present, and Iddo's PC never trains).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import time

import torch
import torch.nn.functional as F

from adapter import Adapter, param_count
from bm25 import BM25

HERE = pathlib.Path(__file__).resolve().parent


def load_everything():
    docs = [json.loads(l) for l in (HERE / "corpus.jsonl").open(encoding="utf-8")]
    by_id = {d["id"]: d for d in docs}
    split = json.loads((HERE / "split.json").read_text(encoding="utf-8"))
    doc_pack = torch.load(HERE / "e5_doc_emb.pt", weights_only=False)
    q_pack = torch.load(HERE / "e5_query_emb.pt", weights_only=False)
    doc_id2row = {i: r for r, i in enumerate(doc_pack["ids"])}
    q_id2row = {i: r for r, i in enumerate(q_pack["ids"])}
    return docs, by_id, split, doc_pack, q_pack, doc_id2row, q_id2row


def mine_hard_negatives(bm25: BM25, ids: list[str], by_id: dict, k: int = 10, seed: int = 0):
    hard = {}
    for i in ids:
        q = by_id[i]["query"]
        hits = [d for d, _ in bm25.search(q, top_k=k + 3) if d != i][:k]
        hard[i] = hits if hits else None
    return hard


@torch.no_grad()
def eval_retrieval(adapter: Adapter, doc_emb_raw: torch.Tensor, doc_ids: list[str],
                    q_emb_raw: torch.Tensor, q_id2row: dict, ids: list[str], device):
    if not ids:
        return {"recall@1": None, "recall@5": None, "mrr": None, "n": 0}
    adapter.eval()
    doc_out = adapter(doc_emb_raw.to(device))                    # (N, d)
    r1 = r5 = mrr = 0.0
    for i in range(0, len(ids), 256):
        chunk = ids[i:i + 256]
        rows = [q_id2row[c] for c in chunk]
        q_out = adapter(q_emb_raw[rows].to(device))
        sims = q_out @ doc_out.T
        ranks = sims.argsort(dim=-1, descending=True)
        for row, gold in enumerate(chunk):
            gold_row = doc_ids.index(gold) if gold not in doc_id_lookup else doc_id_lookup[gold]
            pos = (ranks[row] == gold_row).nonzero(as_tuple=True)[0].item() + 1
            if pos == 1:
                r1 += 1
            if pos <= 5:
                r5 += 1
            mrr += 1.0 / pos
    n = len(ids)
    return {"recall@1": r1 / n, "recall@5": r5 / n, "mrr": mrr / n, "n": n}


doc_id_lookup = {}


def main():
    global doc_id_lookup
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=150)
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--d-out", type=int, default=256)
    ap.add_argument("--depth", type=int, default=2)
    ap.add_argument("--patience", type=int, default=20)
    ap.add_argument("--device", type=str, default="auto")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out-dir", type=str, default=str(HERE))
    args = ap.parse_args()

    device = ("cuda" if torch.cuda.is_available() else "cpu") if args.device == "auto" else args.device
    torch.manual_seed(args.seed)
    random.seed(args.seed)

    docs, by_id, split, doc_pack, q_pack, doc_id2row, q_id2row = load_everything()
    doc_id_lookup = doc_id2row
    doc_ids = doc_pack["ids"]
    doc_emb_raw = doc_pack["emb"]                                # (N, 384) on CPU, frozen
    q_emb_raw = q_pack["emb"]                                    # (Nq, 384) on CPU, frozen

    train_ids = [i for i in split["train"] if i in q_id2row]
    val_ids = [i for i in split["val"] if i in q_id2row]
    test_ids = [i for i in split["test"] if i in q_id2row]
    print(f"device={device} docs={len(docs)} train={len(train_ids)} val={len(val_ids)} test={len(test_ids)}")

    bm25 = BM25([d["id"] for d in docs], [d["text"] for d in docs])
    hard_neg = mine_hard_negatives(bm25, train_ids, by_id, k=10, seed=args.seed)

    adapter = Adapter(d_in=doc_emb_raw.shape[1], d_out=args.d_out, depth=args.depth).to(device)
    print(f"Adapter params = {param_count(adapter):,}  (frozen e5-small backbone excluded)")
    opt = torch.optim.AdamW(adapter.parameters(), lr=args.lr, weight_decay=1e-5)

    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = out_dir / "adapter_metrics.jsonl"
    ckpt_path = out_dir / "adapter-v1.pt"
    metrics_path.write_text("", encoding="utf-8")

    best_val, best_epoch, bad_epochs = -1.0, -1, 0
    t0 = time.time()

    for epoch in range(1, args.epochs + 1):
        adapter.train()
        rng = random.Random(args.seed * 1000 + epoch)
        order = list(range(len(train_ids)))
        rng.shuffle(order)
        ep_loss, n_steps = 0.0, 0
        for bstart in range(0, len(order), args.batch_size):
            idxs = order[bstart:bstart + args.batch_size]
            batch_ids = [train_ids[i] for i in idxs]

            q_rows = [q_id2row[i] for i in batch_ids]
            pos_rows = [doc_id2row[i] for i in batch_ids]
            hn_rows = []
            for i in batch_ids:
                hn = hard_neg.get(i)
                if hn:
                    hn_rows.append(doc_id2row[rng.choice(hn)])
                else:
                    hn_rows.append(doc_id2row[batch_ids[rng.randrange(len(batch_ids))]])

            q_in = q_emb_raw[q_rows].to(device)
            pos_in = doc_emb_raw[pos_rows].to(device)
            hn_in = doc_emb_raw[hn_rows].to(device)

            q_out = adapter(q_in)
            pos_out = adapter(pos_in)
            hn_out = adapter(hn_in)
            scale = adapter.logit_scale()

            pool = torch.cat([pos_out, hn_out], dim=0)
            logits_full = (q_out @ pool.T) * scale
            target = torch.arange(len(batch_ids), device=device)
            loss_q2d = F.cross_entropy(logits_full, target)

            logits_pos = (q_out @ pos_out.T) * scale
            loss_d2q = F.cross_entropy(logits_pos.T, target)

            loss = loss_q2d + loss_d2q
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(adapter.parameters(), 5.0)
            opt.step()
            ep_loss += float(loss.item())
            n_steps += 1

        val_m = eval_retrieval(adapter, doc_emb_raw, doc_ids, q_emb_raw, q_id2row, val_ids, device)
        row = {"epoch": epoch, "train_loss": ep_loss / max(1, n_steps),
               "val_recall@1": val_m["recall@1"], "val_recall@5": val_m["recall@5"],
               "val_mrr": val_m["mrr"], "elapsed_s": round(time.time() - t0, 1)}
        with metrics_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        if epoch % 5 == 0 or epoch == 1:
            print(f"epoch {epoch:3d} loss={row['train_loss']:.4f} val_r@1={row['val_recall@1']:.4f} "
                  f"val_r@5={row['val_recall@5']:.4f} val_mrr={row['val_mrr']:.4f} t={row['elapsed_s']}s")

        if val_m["recall@1"] > best_val:
            best_val, best_epoch, bad_epochs = val_m["recall@1"], epoch, 0
            torch.save({"model_state": adapter.state_dict(), "d_in": doc_emb_raw.shape[1],
                        "d_out": args.d_out, "depth": args.depth, "epoch": epoch,
                        "val_recall@1": best_val}, ckpt_path)
        else:
            bad_epochs += 1
            if bad_epochs >= args.patience:
                print(f"early stop at epoch {epoch} (best epoch {best_epoch}, val_r@1={best_val:.4f})")
                break

    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
    adapter.load_state_dict(ckpt["model_state"])
    adapter.eval()

    test_m = eval_retrieval(adapter, doc_emb_raw, doc_ids, q_emb_raw, q_id2row, test_ids, device)
    val_m_final = eval_retrieval(adapter, doc_emb_raw, doc_ids, q_emb_raw, q_id2row, val_ids, device)

    final = {"best_epoch": best_epoch, "adapter_val": val_m_final, "adapter_test": test_m,
             "params": param_count(adapter), "device": device, "total_time_s": round(time.time() - t0, 1)}
    (out_dir / "adapter_final_results.json").write_text(json.dumps(final, ensure_ascii=False, indent=2),
                                                          encoding="utf-8")
    print("\n=== ADAPTER FINAL ===")
    print(json.dumps(final, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
