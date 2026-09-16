import json, shutil, subprocess, sys, tempfile
from pathlib import Path
code = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(Path("proofs").resolve()))
sys.path.insert(0, str(code))
import proof_common
tmp = Path(tempfile.mkdtemp(prefix="vaf-smoke-"))
proof_common.build_project(tmp)
out = subprocess.run(
    [sys.executable, str(code / "fire.py"), "cycle", "--recordings", "recordings",
     "--manifest", "recordings/manifest.json", "--state", "state", "--out", "fire",
     "--units", "16", "--max-synthetic", "0.3"],
    cwd=tmp, capture_output=True, text=True)
print("rc:", out.returncode)
print("stderr:", out.stderr[-2000:])
if out.returncode == 0:
    d = json.loads(out.stdout)
    print(json.dumps({k: v for k, v in d.items() if k not in ("search",)}, indent=1)[:2500])
    print("search:", json.dumps(d.get("search"))[:600])
# second cycle to exercise incumbent + rotation paths
out2 = subprocess.run(
    [sys.executable, str(code / "fire.py"), "cycle", "--recordings", "recordings",
     "--manifest", "recordings/manifest.json", "--state", "state", "--out", "fire",
     "--units", "16", "--max-synthetic", "0.3"],
    cwd=tmp, capture_output=True, text=True)
print("cycle2 rc:", out2.returncode, out2.stderr[-1500:])
print("TMP:", tmp)
