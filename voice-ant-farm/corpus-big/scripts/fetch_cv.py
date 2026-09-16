"""Download Common Voice 17 Hebrew (CC0-1.0) from the fsicoli mirror."""
import os
from huggingface_hub import hf_hub_download

STAGE = r"D:\CLAUDE\voice-ant-farm\corpus-big\_staging\cv17_he"
os.makedirs(STAGE, exist_ok=True)
REPO = "fsicoli/common_voice_17_0"

FILES = [
    "transcript/he/train.tsv",
    "transcript/he/dev.tsv",
    "transcript/he/test.tsv",
    "transcript/he/other.tsv",
    "transcript/he/validated.tsv",
    "transcript/he/clip_durations.tsv",
    "audio/he/train/he_train_0.tar",
    "audio/he/dev/he_dev_0.tar",
    "audio/he/test/he_test_0.tar",
    "audio/he/other/he_other_0.tar",
]

for f in FILES:
    print(f"[fetch] {f}", flush=True)
    p = hf_hub_download(repo_id=REPO, filename=f, repo_type="dataset", local_dir=STAGE)
    print(f"[ok]    {os.path.getsize(p)/1e6:.1f} MB", flush=True)

print("DONE", flush=True)
