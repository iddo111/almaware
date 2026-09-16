"""Download FLEURS he_il (CC-BY-4.0) audio tarballs + TSVs to a staging dir."""
import os, sys
from huggingface_hub import hf_hub_download

STAGE = r"D:\CLAUDE\voice-ant-farm\corpus-big\_staging\fleurs_he_il"
os.makedirs(STAGE, exist_ok=True)

FILES = [
    "data/he_il/train.tsv",
    "data/he_il/dev.tsv",
    "data/he_il/test.tsv",
    "data/he_il/audio/dev.tar.gz",
    "data/he_il/audio/test.tar.gz",
    "data/he_il/audio/train.tar.gz",
]

for f in FILES:
    print(f"[fetch] {f}", flush=True)
    p = hf_hub_download(
        repo_id="google/fleurs",
        filename=f,
        repo_type="dataset",
        local_dir=STAGE,
    )
    print(f"[ok]    {p}  {os.path.getsize(p)/1e6:.1f} MB", flush=True)

print("DONE", flush=True)
