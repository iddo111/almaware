"""MIKO v1 -- training: real backprop, real contrastive loss, real held-out eval.

Task = search: query (a note's description / a RAMCHAT message's first sentence /
a status report's heading) -> the one right document, among the WHOLE corpus.
Whole-DOCUMENT holdout (split.json, seed 1337) -- never a row-level split.

Loss = InfoNCE (symmetric query<->doc on the in-batch positives, plus an asymmetric
query->doc term over the batch's positives + BM25-mined hard negatives).

Run:
    python train.py --epochs 60 --batch-size 64 --device auto
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import time

import torch
import torch.nn.functional as F

import scar_guard
import signals
from bm25 import BM25, eval_bm25, tokenize
from hashvocab import truncation_report
from model import MikoBiEncoder, param_count

HERE = pathlib.Path(__file__).resolve().parent


def load_corpus():
    docs = [json.loads(l) for l in (HERE / "corpus.jsonl").open(encoding="utf-8")]
    by_id = {d["id"]: d for d in docs}
    split = json.loads((HERE / "split.json").read_text(encoding="utf-8"))
    return docs, by_id, split


def build_pairs(by_id: dict, ids: list[str]) -> list[tuple[str, str]]:
    return [(by_id[i]["query"], i) for i in ids if by_id[i].get("query")]


def build_mining_index(docs: list[dict], train_ids) -> BM25:
    """MIKO-04 (code revision 2026-09-06): the index hard negatives are mined FROM.

    It used to be the whole-corpus index -- despite the call site's comment claiming
    "mined ONCE from train queries only (no test/val leak)" -- so held-out documents were
    pushed through the encoder WITH GRADIENT as negatives for train queries: measured on
    the 09-03 corpus, 609 of 669 train examples carried at least one val/test document
    among their ten hard negatives, and 161 of 166 held-out docs (95 of 100 test docs)
    were seen this way. "Documents the model never saw" was not true as written.
    The full-corpus index stays -- for EVALUATION, which is what it is for.
    """
    keep = set(train_ids)
    train_docs = [d for d in docs if d["id"] in keep]
    return BM25([d["id"] for d in train_docs], [d["text"] for d in train_docs])


def leaked_negatives(hard_neg: dict, train_ids) -> list[str]:
    """Non-train documents that appear as mined hard negatives. Must be empty (MIKO-04)."""
    keep = set(train_ids)
    return sorted({g for hits in hard_neg.values() if hits for g in hits if g not in keep})


def mine_hard_negatives(bm25: BM25, pairs: list[tuple[str, str]], k: int = 10, seed: int = 0):
    rng = random.Random(seed)
    hard = {}
    for q, gold in pairs:
        hits = [d for d, _ in bm25.search(q, top_k=k + 3) if d != gold][:k]
        hard[gold] = hits if hits else None
    return hard


@torch.no_grad()
def encode_corpus(model: MikoBiEncoder, docs: list[dict], device, bs: int = 128):
    ids, embs = [], []
    model.eval()
    for i in range(0, len(docs), bs):
        chunk = docs[i:i + bs]
        ids.extend([d["id"] for d in chunk])
        e = model.encode([d["text"] for d in chunk], device=device)
        embs.append(e.cpu())
    return ids, torch.cat(embs, 0)


@torch.no_grad()
def eval_retrieval(model: MikoBiEncoder, docs: list[dict], pairs: list[tuple[str, str]], device):
    if not pairs:
        return {"recall@1": None, "recall@5": None, "mrr": None, "n": 0}
    doc_ids, doc_emb = encode_corpus(model, docs, device)
    id2row = {i: r for r, i in enumerate(doc_ids)}
    doc_emb = doc_emb.to(device)
    r1 = r5 = mrr = 0.0
    model.eval()
    for i in range(0, len(pairs), 128):
        chunk = pairs[i:i + 128]
        q_emb = model.encode([q for q, _ in chunk], device=device)
        sims = q_emb @ doc_emb.T                      # (b, N)
        ranks = sims.argsort(dim=-1, descending=True)
        for row, (_, gold) in enumerate(chunk):
            gold_row = id2row[gold]
            pos = (ranks[row] == gold_row).nonzero(as_tuple=True)[0].item() + 1
            if pos == 1:
                r1 += 1
            if pos <= 5:
                r5 += 1
            mrr += 1.0 / pos
    n = len(pairs)
    return {"recall@1": r1 / n, "recall@5": r5 / n, "mrr": mrr / n, "n": n}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--batch-size", type=int, default=48)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--d", type=int, default=192)
    ap.add_argument("--depth", type=int, default=3)
    ap.add_argument("--patience", type=int, default=10)
    ap.add_argument("--device", type=str, default="auto")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out-dir", type=str, default=str(HERE))
    args = ap.parse_args()

    device = ("cuda" if torch.cuda.is_available() else "cpu") if args.device == "auto" else args.device
    torch.manual_seed(args.seed)
    random.seed(args.seed)

    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = out_dir / "metrics.jsonl"
    ckpt_path = out_dir / "miko-v1.pt"

    docs, by_id, split = load_corpus()
    train_pairs = build_pairs(by_id, split["train"])
    val_pairs = build_pairs(by_id, split["val"])
    test_pairs = build_pairs(by_id, split["test"])
    print(f"device={device}  docs={len(docs)}  train={len(train_pairs)} "
          f"val={len(val_pairs)} test={len(test_pairs)}")

    # MIKO-11 (code revision 2026-09-06): the ERAN starvation shape. An empty train set used
    # to run zero steps per epoch, print loss 0.0 via `ep_loss / max(1, n_steps)`, let eval
    # run, and still save the UNTRAINED epoch-1 model as "best" (0.0 > -1.0) -- no exception,
    # no log line. Refuse before the loop instead of succeeding without reading any input.
    signals.assert_nonempty("train", train_pairs,
                            f"build_pairs over {len(split['train'])} train ids in split.json")
    signals.assert_nonempty("val", val_pairs,
                            f"build_pairs over {len(split['val'])} val ids in split.json")

    # BM25 index over the WHOLE corpus -- for EVALUATION only (the control column).
    bm25 = BM25([d["id"] for d in docs], [d["text"] for d in docs])

    # MIKO-04 (code revision 2026-09-06): hard negatives used to be mined from that
    # whole-corpus index despite the comment claiming otherwise, so held-out documents were
    # pushed through the encoder WITH GRADIENT as negatives for train queries: 161 of 166
    # val+test docs (95 of 100 test docs) on the 09-03 corpus. "Documents the model never
    # saw" was false as written. Mine from a TRAIN-ONLY index; assert the leak is zero.
    bm25_mine = build_mining_index(docs, split["train"])
    hard_neg = mine_hard_negatives(bm25_mine, train_pairs, k=10, seed=args.seed)
    leaked = leaked_negatives(hard_neg, split["train"])
    if leaked:
        raise SystemExit(f"HOLDOUT-LEAK: {len(leaked)} non-train docs among the mined hard "
                         f"negatives, e.g. {leaked[:3]} -- see MIKO-04.")
    n_with_hard = sum(1 for v in hard_neg.values() if v)
    print(f"hard negatives mined for {n_with_hard}/{len(train_pairs)} train examples "
          f"(train-only index, {len(bm25_mine.doc_ids)} docs; holdout leak = 0)")

    model = MikoBiEncoder(d=args.d, depth=args.depth).to(device)
    print(f"MikoBiEncoder params = {param_count(model):,}")

    # MIKO-01 (code revision 2026-09-06): the logits below are MULTIPLIED by this number.
    # A value < 1 is an inverted temperature: the softmax goes ~uniform, InfoNCE collapses to
    # a linear mean-negative loss, and the whole attainable loss window is 8.30-8.44 -- the
    # exact window the 09-03 run traversed while val recall@1 never left 0.0000.
    _scale0 = float(model.logit_scale().detach())
    assert _scale0 > 1.0, (
        f"INVERTED-TEMPERATURE: logit_scale()={_scale0:.4f} <= 1. CLIP's convention is "
        "logit_scale = 1/T (14.29 for T=0.07), not T. Refusing to train. See MIKO-01.")
    print(f"logit_scale at init = {_scale0:.4f} (1/T convention)")

    # MIKO-07 (code revision 2026-09-06): the advertised scar guard was imported by NOTHING,
    # and run standalone it built a fresh random d=64 net and guarded that -- never a model
    # anyone shipped. A gate that never refused is not demonstrated (Iddo's law). It runs on
    # the real model here, and it raises.
    guard = scar_guard.run(model)
    if not guard["PASS"]:
        raise SystemExit(f"SCAR GUARD FAILED on the model about to be trained: {guard}")
    print("scar guard: PASS (static LayerNorm(1) check + dynamic score-varies) on THIS model")

    # MIKO-12 (code revision 2026-09-06): name the tokenizer's silent truncation out loud.
    print(truncation_report([d["text"] for d in docs], model.ns, model.max_grams))

    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-5)

    best_val = -1.0
    best_epoch = -1
    bad_epochs = 0
    # MIKO-03 (code revision 2026-09-06): what a random ranker scores on this task, so a
    # "metric" sitting at or below it can be NAMED instead of quietly selected on.
    rand_baseline = signals.random_baseline(len(docs))
    val_hist: list[float] = []
    t0 = time.time()
    metrics_path.write_text("", encoding="utf-8")

    for epoch in range(1, args.epochs + 1):
        model.train()
        rng = random.Random(args.seed * 1000 + epoch)
        order = list(range(len(train_pairs)))
        rng.shuffle(order)
        ep_loss, n_steps = 0.0, 0
        for bstart in range(0, len(order), args.batch_size):
            idxs = order[bstart:bstart + args.batch_size]
            batch = [train_pairs[i] for i in idxs]
            qs = [q for q, _ in batch]
            gold_ids = [g for _, g in batch]
            pos_texts = [by_id[g]["text"] for g in gold_ids]
            hn_texts = []
            for g in gold_ids:
                hn = hard_neg.get(g)
                if hn:
                    hn_texts.append(by_id[rng.choice(hn)]["text"])
                else:
                    other = gold_ids[rng.randrange(len(gold_ids))]
                    hn_texts.append(by_id[other]["text"])

            q_emb = model.encode(qs, device=device)
            pos_emb = model.encode(pos_texts, device=device)
            hn_emb = model.encode(hn_texts, device=device)
            scale = model.logit_scale()

            pool = torch.cat([pos_emb, hn_emb], dim=0)          # (2B, d)
            logits_full = (q_emb @ pool.T) * scale               # (B, 2B)
            target = torch.arange(len(batch), device=device)
            loss_q2d = F.cross_entropy(logits_full, target)

            logits_pos = (q_emb @ pos_emb.T) * scale             # (B, B)
            loss_d2q = F.cross_entropy(logits_pos.T, target)

            loss = loss_q2d + loss_d2q
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            opt.step()

            ep_loss += float(loss.item())
            n_steps += 1

        # MIKO-11: `ep_loss / max(1, n_steps)` printed a clean 0.0 for an epoch that never
        # stepped. An epoch with no steps is a state, not a number.
        if n_steps == 0:
            raise SystemExit(f"EMPTY-EPOCH: epoch {epoch} took 0 optimizer steps over "
                             f"{len(train_pairs)} train pairs. See MIKO-11.")
        val_metrics = eval_retrieval(model, docs, val_pairs, device)
        row = {
            "epoch": epoch,
            "train_loss": ep_loss / n_steps,
            "val_recall@1": val_metrics["recall@1"],
            "val_recall@5": val_metrics["recall@5"],
            "val_mrr": val_metrics["mrr"],
            "elapsed_s": round(time.time() - t0, 1),
        }
        with metrics_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        print(f"epoch {epoch:3d}  loss={row['train_loss']:.4f}  "
              f"val_r@1={row['val_recall@1']:.4f}  val_r@5={row['val_recall@5']:.4f}  "
              f"val_mrr={row['val_mrr']:.4f}  t={row['elapsed_s']}s")

        # MIKO-03 (code revision 2026-09-06): checkpoint selection and early stopping ran on
        # a signal that was numerically DEAD and nobody noticed -- val recall@1 was identically
        # 0.0 for all 15 epochs of the 09-03 run, so `val > best_val` fired only at epoch 1
        # (0.0 > -1.0), the shipped miko-v1.pt IS that epoch-1 model, and the loop then idled
        # ten more epochs to patience. "best" == first: selection never selected anything.
        # A flat metric at the random baseline is a NAMED state, and it stops the run.
        val_hist.append(val_metrics["recall@1"])
        dead = signals.val_signal_state(val_hist, rand_baseline)
        if dead:
            raise SystemExit(dead)

        # ...and never call "best" something a coin flip matches.
        if val_metrics["recall@1"] > best_val and val_metrics["recall@1"] > rand_baseline:
            best_val = val_metrics["recall@1"]
            best_epoch = epoch
            bad_epochs = 0
            torch.save({"model_state": model.state_dict(),
                        "d": args.d, "depth": args.depth,
                        "epoch": epoch, "val_recall@1": best_val}, ckpt_path)
        else:
            bad_epochs += 1
            if bad_epochs >= args.patience:
                print(f"early stop at epoch {epoch} (best epoch {best_epoch}, "
                      f"val_recall@1={best_val:.4f})")
                break

    # MIKO-03: if nothing ever beat the random baseline there is no "best" to reload and no
    # number worth reporting. Say so instead of loading whatever happens to sit on disk.
    if best_epoch < 0:
        raise SystemExit(
            f"NO-CHECKPOINT: val recall@1 never exceeded the random baseline "
            f"({rand_baseline:.4f}) in {len(val_hist)} epochs -- nothing was saved, and "
            "nothing should be. See MIKO-03.")

    # reload best checkpoint and report final test numbers
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
    model.load_state_dict(ckpt["model_state"])
    model.eval()
    test_metrics = eval_retrieval(model, docs, test_pairs, device)
    val_metrics_final = eval_retrieval(model, docs, val_pairs, device)

    bm25_val = eval_bm25(bm25, val_pairs)
    bm25_test = eval_bm25(bm25, test_pairs)

    final = {
        "best_epoch": best_epoch,
        "miko_val": val_metrics_final,
        "miko_test": test_metrics,
        "bm25_val": bm25_val,
        "bm25_test": bm25_test,
        "params": param_count(model),
        "device": device,
        "total_time_s": round(time.time() - t0, 1),
    }
    (out_dir / "final_results.json").write_text(
        json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== FINAL ===")
    print(json.dumps(final, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
