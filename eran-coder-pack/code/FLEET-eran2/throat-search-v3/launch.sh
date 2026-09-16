#!/bin/bash
# launch.sh -- start this box's v3 Stage-A worker set, detached, in one tmux
# session named "throat3".   ./launch.sh eran2|eran3|eran4
#
# DO NOT RUN until Iddo says go. sanity0_v3.py must have written ALL_OK=true
# first (run_worker refuses otherwise) and ORGANS.lock must verify.
#
# Worker plan (plan Phase 3, baseline 33 slots), re-checked 2026-08-26:
#   eran2: 20 cores, eran-senses :8830 alive        -> 12 workers, nice 5
#   eran3: 20 cores, idle, DISK 84% (run-state only) -> 13 workers, nice 5
#   eran4: 20 cores, Darwish lives here              -> 8 workers,  nice 10
# Every box keeps >=35% of its cores free. Stage A arms: ah-1kf/ih-1kf (16d),
# ba-cv (31d), ma-nasal (32d, FIRST NASAL ARM EVER), free variants (45d),
# uniform-random control twins in the same boxes.
box=$1
cd "$(dirname "$0")" || exit 1
case "$box" in
  eran2) specs="ah-1kf:0 ah-1kf:1 ih-1kf:0 ih-1kf:1 ba-cv:0 ba-cv:1 ba-cv:2 ma-nasal:0 ma-nasal:1 ma-nasal:2 control-ba-cv:0 control-ma-nasal:0"; nice_n=5;;
  eran3) specs="ah-1kf:2 ah-1kf:3 ih-1kf:2 ih-1kf:3 ba-cv:3 ba-cv:4 ma-nasal:3 ma-nasal:4 ah-free:0 ah-free:1 control-ah-1kf:0 control-ih-1kf:0 control-ba-free:0"; nice_n=5;;
  eran4) specs="ba-cv:5 ma-nasal:5 ba-free:0 ba-free:1 ma-free:0 ma-free:1 control-ba-cv:1 control-ma-nasal:1"; nice_n=10;;
# eran1 is THE ORGANISM. Opt-in surge (<=8 workers, nice >=10) exists in the
# plan but ONLY on Iddo's word -- his explicit say-so in this session's chat,
# nothing less. Uncomment and fill ONLY then:
# eran1) specs="..."; nice_n=10;;
  *) echo "usage: $0 eran2|eran3|eran4"; exit 2;;
esac
rm -f STOP
tmux has-session -t throat3 2>/dev/null || tmux new-session -d -s throat3 -n main
for spec in $specs; do
  arm=${spec%%:*}; seed=${spec##*:}
  w="$arm-$seed"
  if tmux list-windows -t throat3 -F '#W' | grep -qx "$w"; then
    echo "already running: $w"
    continue
  fi
  tmux new-window -d -t throat3 -n "$w" "bash sup.sh $arm $seed $nice_n 47"
done
echo "--- tmux windows (session throat3) ---"
tmux list-windows -t throat3
