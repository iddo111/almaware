#!/bin/bash
# launch.sh -- start this box's worker set, detached, in one tmux session.
#   ./launch.sh eran2|eran3|eran4
# Worker counts CHOSEN FROM MEASUREMENTS 2026-08-25 (free -g / nproc / uptime):
#   eran2: 115G avail, 20 cores, load 0.12, live eran-senses  -> 12 workers, nice 5
#   eran3: 115G avail, 20 cores, load 0.29, idle              -> 13 workers, nice 5
#   eran4: 99G avail,  20 cores, load 0.03, Darwish lives here-> 8 workers,  nice 10
# Every box keeps >=35% of its cores and >95% of its RAM free.
box=$1
cd "$(dirname "$0")" || exit 1
case "$box" in
  eran2) specs="ba:0 ba:1 ba:2 ba:3 abba:0 abba:1 abba:2 abba:3 abba-free:0 abba-free:1 control-ba:0 control-abba:0"; nice_n=5;;
  eran3) specs="ba:4 ba:5 ba:6 ba:7 abba:4 abba:5 abba:6 abba:7 abba-free:2 abba-free:3 abba-free:4 control-ba:1 control-abba:1"; nice_n=5;;
  eran4) specs="ba:8 ba:9 abba:8 abba:9 abba:10 abba-free:5 abba-free:6 control-abba:2"; nice_n=10;;
  *) echo "usage: $0 eran2|eran3|eran4"; exit 2;;
esac
rm -f STOP
tmux has-session -t throat 2>/dev/null || tmux new-session -d -s throat -n main
for spec in $specs; do
  arm=${spec%%:*}; seed=${spec##*:}
  w="$arm-$seed"
  if tmux list-windows -t throat -F '#W' | grep -qx "$w"; then
    echo "already running: $w"
    continue
  fi
  tmux new-window -d -t throat -n "$w" "bash sup.sh $arm $seed $nice_n 47"
done
echo "--- tmux windows ---"
tmux list-windows -t throat
