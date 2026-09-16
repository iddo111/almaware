import subprocess, sys, tempfile, os
from pathlib import Path
code = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(Path("proofs").resolve())); sys.path.insert(0, str(code))
import proof_common
tmp = Path(tempfile.mkdtemp(prefix="vaf-queen-")); proof_common.build_project(tmp)
for i in range(4):
    r = subprocess.run([sys.executable, str(code/"fire.py"), "cycle", "--recordings","recordings",
      "--manifest","recordings/manifest.json","--state","state","--out","fire","--units","16",
      "--round-id", f"20260906T00{i:02d}00Z"], cwd=tmp, capture_output=True, text=True)
    if r.returncode: print("FAIL", r.stderr[-500:]); break
q = list((tmp/"state"/"queen").glob("candidate-*.json"))
a = list((tmp/"state"/"ant-a").glob("candidate-*.json"))
print(f"{code.name}: 4 cycles -> queen candidates={len(q)} ant-a candidates={len(a)}")
