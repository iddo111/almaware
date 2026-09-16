"""Verify local DeepSeek-V4-Flash-REAP-150b shards against the live HF repo listing.
Per docs/deepseek-v4.md: 'A download can finish with a truncated shard even when the
client reports success... compare every local shard size with the Hugging Face
repository before treating it as an engine failure.'
"""
import os, sys
from huggingface_hub import HfApi

REPO = "puwaer/DeepSeek-V4-Flash-0731-reap-150b"
DEST = r"C:\models\colibri\DeepSeek-V4-Flash-reap-150b"

def main():
    api = HfApi()
    info = api.repo_info(REPO, files_metadata=True)
    expected = {s.rfilename: s.size for s in info.siblings}
    total_expected = sum(expected.values())

    ok, missing, mismatched = 0, [], []
    total_local = 0
    for fn, size in expected.items():
        local = os.path.join(DEST, fn)
        if not os.path.isfile(local):
            missing.append(fn)
            continue
        actual = os.path.getsize(local)
        total_local += actual
        if actual != size:
            mismatched.append((fn, actual, size))
        else:
            ok += 1

    print(f"repo={REPO}")
    print(f"expected files={len(expected)}  expected total={total_expected/1e9:.2f} GB")
    print(f"local total={total_local/1e9:.2f} GB")
    print(f"OK={ok}  missing={len(missing)}  size-mismatch={len(mismatched)}")
    for fn in missing:
        print(f"  MISSING: {fn} (expected {expected[fn]/1e9:.2f} GB)")
    for fn, actual, size in mismatched:
        print(f"  MISMATCH: {fn} local={actual} expected={size} diff={actual-size}")

    if not missing and not mismatched:
        print("VERIFY_PASS: all shards byte-exact")
        return 0
    else:
        print("VERIFY_FAIL: incomplete or truncated shards")
        return 1

if __name__ == "__main__":
    sys.exit(main())
