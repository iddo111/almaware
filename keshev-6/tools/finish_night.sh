#!/usr/bin/env bash
# Everything left, in order, so the night finishes in one pass.
cd /d/CLAUDE/keshev-6 || exit 1
export PYTHONIOENCODING=utf-8

echo "=== waiting for the soak to close ==="
n=0
while [ ! -f state/soak.json ] && [ $n -lt 40 ]; do sleep 60; n=$((n+1)); done
date "+soak closed at %H:%M:%S"
python -c "
import json; d=json.load(open('state/soak.json')); s=d['samples']
print('SOAK requests',d['requests'],'codes',d['codes'],'errors',d['errors'])
print('SOAK p50',d['p50_ms'],'p95',d['p95_ms'])
print('SOAK rss',s[0]['rss_mib'],'->',s[-1]['rss_mib'],'gpu_free_min',min(x['gpu_free_mib'] for x in s),'minutes',len(s))
print('SOAK p50/min',[x['p50_ms'] for x in s])
"

echo "=== join recovery test ==="
python tools/join_test.py 80 2>&1 | tail -22

echo "=== loud-empties sweep (peak_rms >= 4000) ==="
python tools/empties_sweep.py 4000 2>&1 | tail -50

echo "=== DONE ==="
date "+%H:%M:%S"
