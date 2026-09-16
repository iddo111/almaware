"""Extract a real-web corpus subsample from the local fineweb-edu parquet.
Read-only on eran3; nice'd; single pass; writes jsonl.gz."""
import gzip, json, os, re, sys
import pyarrow.parquet as pq

SRC = "/home/eran3/.cache/huggingface/hub/datasets--HuggingFaceFW--fineweb-edu/snapshots/87f09149ef4734204d70ed1d046ddc9ca3f2b8f9/sample/10BT/013_00000.parquet"
OUT = "/home/eran3/miko_corpus.jsonl.gz"
TARGET = 40000
MAXCHARS = 3000

pf = pq.ParquetFile(SRC)
kept = 0
with gzip.open(OUT, "wt", encoding="utf-8") as f:
    for batch in pf.iter_batches(batch_size=2000,
                                 columns=["text", "id", "url", "language",
                                          "language_score", "token_count", "score", "dump"]):
        d = batch.to_pydict()
        for i in range(len(d["id"])):
            if kept >= TARGET:
                break
            if d["language"][i] != "en" or d["language_score"][i] < 0.85:
                continue
            tc = d["token_count"][i]
            if tc < 200 or tc > 4000:
                continue
            txt = d["text"][i]
            if not txt:
                continue
            txt = re.sub(r"\s+", " ", txt).strip()
            if len(txt) < 400:
                continue
            f.write(json.dumps({
                "doc_id": d["id"][i],
                "url": d["url"][i],
                "dump": d["dump"][i],
                "edu_score": float(d["score"][i]),
                "token_count": int(tc),
                "text": txt[:MAXCHARS],
            }, ensure_ascii=False) + "\n")
            kept += 1
        if kept >= TARGET:
            break
print("kept", kept, "->", OUT, os.path.getsize(OUT))
