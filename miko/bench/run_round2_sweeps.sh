#!/bin/bash
# theta first, then lr - both on VALIDATION only. The test sets are never scored here.
set -e
cd /home/eran2/miko-bench
export PYTHONUNBUFFERED=1
P=data/pairs2f.jsonl
S=${1:-300}

echo "=== stage 1: the DECISIVE rule's agreement threshold, on validation ==="
python3 sweep2.py --stage theta --pairs $P --steps $S --out sweep2_theta.json 2>&1 | tee sweep2_theta.log

T=$(python3 -c "
import json
d=json.load(open('sweep2_theta.json'))
best=min(d,key=lambda k:d[k]['val_mae_best'])
print(best.split('@theta=')[1].split('@')[0])")
echo "CHOSEN theta = $T   (on validation, never on test)"
echo $T > theta_best.txt

echo "=== stage 2: learning rate, same three values for every arm, on validation ==="
python3 sweep2.py --stage lr --pairs $P --steps $S --theta $T --out sweep2_lr.json 2>&1 | tee sweep2_lr.log

python3 - <<'PY' | tee lr_best2.txt
import json
d=json.load(open('sweep2_lr.json'))
out=[]
for arm in ("decisive","bloc","median","mean","vanilla"):
    c={k:v['val_mae_best'] for k,v in d.items() if k.startswith(arm+"@")}
    b=min(c,key=c.get)
    lr=b.split('@lr=')[1]
    out.append(f"{arm}={lr}")
    print(f"# {arm:<9} best lr {lr}  val MAE {c[b]:.4f}")
print(",".join(out))
PY
echo "=== SWEEPS DONE ==="; date
