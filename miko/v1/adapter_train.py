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
import sys
import time

import torch
import torch.nn.functional as F

import scar_guard
import signals
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
    # MIKO-08 (code revision 2026-09-06): these defaults used to be lr=1e-3, d_out=256,
    # depth=2, patience=20 -- i.e. the REFUTED configuration. d_out=256 != d_in=384 also made
    # Adapter silently drop `residual` and fall back to the random-init head the report itself
    # calls "worse than doing nothing" (that silent path now raises; see MIKO-08 in adapter.py).
    # The configuration that actually produced adapter-v1.pt existed only in report prose --
    # no results file, checkpoint field, log or shell history recorded it. It is recorded here
    # (d_out=384, depth=1 read back from the checkpoint; lr=1e-5 from the report; patience=8
    # implied by the run stopping at epoch 9 with best_epoch=1) AND written into the
    # checkpoint and *_final_results.json below, so the next run is never a guess again.
    ap.add_argument("--epochs", type=int, default=150)
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--lr", type=float, default=1e-5)
    ap.add_argument("--d-out", type=int, default=384)
    ap.add_argument("--depth", type=int, default=1)
    ap.add_argument("--patience", type=int, default=8)
    ap.add_argument("--device", type=str, default="auto")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out-dir", type=str, default=str(HERE))
    args = ap.parse_args()

    # MIKO-08: train.py left a train_stdout.log on eran3; the adapter run left nothing, so
    # its console output -- the only place its arguments appeared -- is gone forever.
    log_path = pathlib.Path(args.out_dir) / "adapter_train_stdout.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    _log_fh = log_path.open("w", encoding="utf-8")

    class _Tee:
        def write(self, t):
            sys.__stdout__.write(t)
            _log_fh.write(t)
            _log_fh.flush()

        def flush(self):
            sys.__stdout__.flush()
            _log_fh.flush()

    sys.stdout = _Tee()
    print(f"args = {json.dumps(vars(args), ensure_ascii=False)}")

    device = ("cuda" if torch.cuda.is_available() else "cpu") if args.device == "auto" else args.device
    torch.manual_seed(args.seed)
    random.seed(args.seed)

    docs, by_id, split, doc_pack, q_pack, doc_id2row, q_id2row = load_everything()
    doc_id_lookup = doc_id2row
    doc_ids = doc_pack["ids"]
    doc_emb_raw = doc_pack["emb"]                                # (N, 384) on CPU, frozen
    q_emb_raw = q_pack["emb"]                                    # (Nq, 384) on CPU, frozen

    # MIKO-11 (code revision 2026-09-06): these three filters could silently drop EVERY id
    # if e5_query_emb.pt were stale -- and the loop below would then run zero steps, print
    # loss 0.0 through `ep_loss / max(1, n_steps)`, and still save an untrained epoch-1
    # checkpoint as "best". A filter that can exclude everything must say what it excluded.
    train_ids = [i for i in split["train"] if i in q_id2row]
    val_ids = [i for i in split["val"] if i in q_id2row]
    test_ids = [i for i in split["test"] if i in q_id2row]
    dropped = {k: len(split[k]) - len(v) for k, v in
               (("train", train_ids), ("val", val_ids), ("test", test_ids))}
    if any(dropped.values()):
        raise SystemExit(
            f"QUERY-CACHE-INCOMPLETE: e5_query_emb.pt is missing embeddings for {dropped} "
            f"split ids (it holds {len(q_id2row)}). Re-run encode_e5.py on a fleet box "
            "rather than training on whatever survived the filter. See MIKO-11.")
    signals.assert_nonempty("train", train_ids, "split.json filtered by e5_query_emb.pt")
    signals.assert_nonempty("val", val_ids, "split.json filtered by e5_query_emb.pt")
    print(f"device={device} docs={len(docs)} train={len(train_ids)} val={len(val_ids)} test={len(test_ids)}")

    # MIKO-04 (code revision 2026-09-06): the mining index used to be built over ALL 835
    # docs, so val/test documents went through the adapter WITH GRADIENT as negatives for
    # train queries (161 of 166 held-out docs on the 09-03 corpus). Mine from train only.
    from train import build_mining_index, leaked_negatives      # same gate, one definition
    bm25 = build_mining_index(docs, split["train"])
    hard_neg = mine_hard_negatives(bm25, train_ids, by_id, k=10, seed=args.seed)
    leaked = leaked_negatives(hard_neg, split["train"])
    if leaked:
        raise SystemExit(f"HOLDOUT-LEAK: {len(leaked)} non-train docs among the mined hard "
                         f"negatives, e.g. {leaked[:3]} -- see MIKO-04.")
    print(f"hard negatives: train-only index over {len(bm25.doc_ids)} docs; holdout leak = 0")

    adapter = Adapter(d_in=doc_emb_raw.shape[1], d_out=args.d_out, depth=args.depth).to(device)
    print(f"Adapter params = {param_count(adapter):,}  (frozen e5-small backbone excluded)")

    # MIKO-01 (code revision 2026-09-06): the logits below are MULTIPLIED by this. It was
    # 0.05 (a temperature, not its inverse), so the softmax was ~uniform and the objective
    # could not shape anything -- which, together with lr=1e-5 and best_epoch=1, is why
    # adapter-v1.pt's proj_in is still ~0.
    _scale0 = float(adapter.logit_scale().detach())
    assert _scale0 > 1.0, (
        f"INVERTED-TEMPERATURE: logit_scale()={_scale0:.4f} <= 1. CLIP's convention is 1/T "
        "(20.0 for T=0.05), not T. Refusing to train. See MIKO-01.")
    print(f"logit_scale at init = {_scale0:.4f} (1/T convention)")

    # MIKO-07 (code revision 2026-09-06): the Adapter had no scar guard at all.
    guard = scar_guard.run_adapter(adapter, d_in=doc_emb_raw.shape[1])
    print(f"scar guard (adapter): PASS, score spread {guard['dynamic']['std_across_pairs']:.4f}")

    # MIKO-02: with the residual branch zeroed end-to-end the adapter starts EXACTLY at the
    # frozen backbone. Assert it, so "we only nudge zero-shot" is a fact, not a docstring.
    with torch.no_grad():
        _probe = doc_emb_raw[:8].to(device)
        _delta = float((adapter(_probe) - F.normalize(_probe, dim=-1)).abs().max())
    # 1e-6 is float32 re-normalisation noise; the 09-03 init sat at ~4e-1, i.e. 5 orders up.
    assert _delta <= 1e-6, (f"ADAPTER-NOT-IDENTITY-AT-INIT: max|adapter(x)-x| = {_delta:.3e} "
                            "at step 0; the run would be measuring a random offset. MIKO-02.")
    print(f"adapter == frozen backbone at step 0 (max deviation {_delta:.3e})")
    opt = torch.optim.AdamW(adapter.parameters(), lr=args.lr, weight_decay=1e-5)

    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = out_dir / "adapter_metrics.jsonl"
    ckpt_path = out_dir / "adapter-v1.pt"
    metrics_path.write_text("", encoding="utf-8")

    best_val, best_epoch, bad_epochs = -1.0, -1, 0
    # MIKO-03 (code revision 2026-09-06): the random-ranking baseline, so a metric sitting at
    # or below it can be NAMED instead of quietly selected on.
    rand_baseline = signals.random_baseline(len(doc_ids))
    val_hist: list[float] = []
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

        if n_steps == 0:      # MIKO-11: an epoch with no steps is a state, not a 0.0 loss
            raise SystemExit(f"EMPTY-EPOCH: epoch {epoch} took 0 optimizer steps over "
                             f"{len(train_ids)} train ids. See MIKO-11.")
        val_m = eval_retrieval(adapter, doc_emb_raw, doc_ids, q_emb_raw, q_id2row, val_ids, device)
        row = {"epoch": epoch, "train_loss": ep_loss / n_steps,
               "val_recall@1": val_m["recall@1"], "val_recall@5": val_m["recall@5"],
               "val_mrr": val_m["mrr"], "elapsed_s": round(time.time() - t0, 1)}
        with metrics_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        if epoch % 5 == 0 or epoch == 1:
            print(f"epoch {epoch:3d} loss={row['train_loss']:.4f} val_r@1={row['val_recall@1']:.4f} "
                  f"val_r@5={row['val_recall@5']:.4f} val_mrr={row['val_mrr']:.4f} t={row['elapsed_s']}s")

        # MIKO-03 (code revision 2026-09-06): selection ran on a dead signal here too --
        # val declined monotonically from epoch 1 (0.667 -> 0.348), so "best" was the FIRST
        # epoch, 11 steps in, and adapter-v1.pt is that model. A metric that only ever gets
        # worse is a named state: the run is not learning, it is decaying.
        val_hist.append(val_m["recall@1"])
        dead = signals.val_signal_state(val_hist, rand_baseline)
        if dead:
            raise SystemExit(dead)

        if val_m["recall@1"] > best_val and val_m["recall@1"] > rand_baseline:
            best_val, best_epoch, bad_epochs = val_m["recall@1"], epoch, 0
            torch.save({"model_state": adapter.state_dict(), "d_in": doc_emb_raw.shape[1],
                        "d_out": args.d_out, "depth": args.depth, "epoch": epoch,
                        "val_recall@1": best_val,
                        "args": vars(args)},          # MIKO-08: the run records itself
                       ckpt_path)
        else:
            bad_epochs += 1
            if bad_epochs >= args.patience:
                print(f"early stop at epoch {epoch} (best epoch {best_epoch}, val_r@1={best_val:.4f})")
                break

    # MIKO-03: nothing above the baseline means nothing to reload and nothing to report.
    if best_epoch < 0:
        raise SystemExit(f"NO-CHECKPOINT: val recall@1 never exceeded the random baseline "
                         f"({rand_baseline:.4f}) in {len(val_hist)} epochs. See MIKO-03.")

    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
    adapter.load_state_dict(ckpt["model_state"])
    adapter.eval()

    test_m = eval_retrieval(adapter, doc_emb_raw, doc_ids, q_emb_raw, q_id2row, test_ids, device)
    val_m_final = eval_retrieval(adapter, doc_emb_raw, doc_ids, q_emb_raw, q_id2row, val_ids, device)

    final = {"best_epoch": best_epoch, "adapter_val": val_m_final, "adapter_test": test_m,
             "params": param_count(adapter), "device": device,
             "args": vars(args),                       # MIKO-08: never a guess again
             "val_history": val_hist,                  # MIKO-03: the selection signal itself
             "random_baseline_recall@1": rand_baseline,
             "total_time_s": round(time.time() - t0, 1)}
    (out_dir / "adapter_final_results.json").write_text(json.dumps(final, ensure_ascii=False, indent=2),
                                                          encoding="utf-8")
    print("\n=== ADAPTER FINAL ===")
    print(json.dumps(final, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
