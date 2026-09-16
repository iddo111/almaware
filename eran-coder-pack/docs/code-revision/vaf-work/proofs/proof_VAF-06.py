"""VAF-06 proof: the per-ant training mix must hardlink, not copy.

build_training_mix copied EVERY real training wav for EVERY ant on EVERY
round. Measured on eran4's 405-file corpus: 405 MB per round, ~2.6 GB/hour of
write churn, 19.4 GB standing at VAF_FIRE_KEEP=48. eran3 is at 84% disk.

FAILS on the pre-revision code, PASSES on the fixed code.
"""
import os, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import proof_common

code = proof_common.use_code(sys.argv)
import colony, fire  # noqa: E402

UNITS = 16
tmp = Path(tempfile.mkdtemp(prefix="vaf-proof-06-"))
recordings = proof_common.build_project(tmp, train=6)
state, fire_root = tmp / "state", tmp / "fire"
colony.train_colony(recordings, recordings / "manifest.json", state, units=UNITS)
fire.run_fire_round(state, recordings, fire_root, round_id="20260906T000030Z")

mix = fire_root / "20260906T000030Z" / "mix" / "ant-a"
shared, copied, bytes_copied = 0, 0, 0
for source in sorted((recordings / "train").glob("*.wav")):
    linked = mix / f"real-{source.name}"
    if os.stat(linked).st_ino == os.stat(source).st_ino and os.stat(linked).st_ino != 0:
        shared += 1
    else:
        copied += 1
        bytes_copied += os.stat(linked).st_size

round_bytes = sum(p.stat().st_size for p in (fire_root / "20260906T000030Z").rglob("*.wav"))
checks = [(
    "every real recording in the mix shares its inode with the corpus file",
    copied == 0, f"{shared} hardlinked, {copied} copied ({bytes_copied} duplicated bytes)",
), (
    "the round directory no longer duplicates the corpus per ant",
    bytes_copied == 0,
    f"round holds {round_bytes} bytes of wav; duplicated real audio = {bytes_copied}",
)]

print(f"workspace: {tmp}")
raise SystemExit(proof_common.report("VAF-06", checks))
