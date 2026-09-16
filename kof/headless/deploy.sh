#!/bin/bash
# Deploy KESHEV 7 / KOF headless to eran1. Run from D:/CLAUDE/kof/headless.
# Copies the runner + eval + goal, builds the split from the corpus already on
# eran1 (~/keshev7-kof/corpus), seals, installs the USER unit (NOT started).
set -euo pipefail
H=eran1
echo "== copy runner tree =="
ssh $H 'mkdir -p ~/keshev7-kof/site ~/keshev7-eval ~/keshev7'
scp -q kof_headless.py make_split.py GOAL.md config.json keshev7-kof.service README.md $H:~/keshev7-kof/
scp -q site/sitecustomize.py $H:~/keshev7-kof/site/
scp -q eval/eval.py $H:~/keshev7-eval/
echo "== self-checks =="
ssh $H 'cd ~/keshev7-eval && PYTHONIOENCODING=utf-8 python3 eval.py selfcheck'
echo "== build train/heldout split (idempotent; refuses if already built) =="
ssh $H 'cd ~/keshev7-kof && PYTHONIOENCODING=utf-8 python3 make_split.py \
        --src ~/keshev7-kof/corpus --sandbox ~/keshev7 --eval ~/keshev7-eval \
        || echo "(split already present - skipping)"'
echo "== seal (permissions + fingerprint) =="
ssh $H 'cd ~/keshev7-kof && PYTHONIOENCODING=utf-8 python3 kof_headless.py seal && python3 kof_headless.py verify-seal'
echo "== install USER unit (NOT started) =="
ssh $H 'mkdir -p ~/.config/systemd/user && cp ~/keshev7-kof/keshev7-kof.service ~/.config/systemd/user/ && systemctl --user daemon-reload && echo installed'
echo "== brain ping =="
ssh $H 'cd ~/keshev7-kof && PYTHONIOENCODING=utf-8 python3 kof_headless.py brain-ping'
echo "DONE. To start (Iddo's go): ssh eran1 'systemctl --user start keshev7-kof'"
