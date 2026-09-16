#!/usr/bin/env bash
# Arm the ALMA BEAT ORGAN on this box. Run FROM ~/alma-beat-organ/alma-beat/deploy.
#
#   bash install.sh          # install units, enable, start all five arms
#   bash install.sh --arm    # install and enable ONLY, do not start (wait for room)
#
# TO STOP EVERYTHING:
#   systemctl --user stop 'alma-beat@*' && systemctl --user disable 'alma-beat@*'
set -euo pipefail

ARMS="alma-pert alma-pert-heads alma-3f frozen shuffled vanilla"
HERE="$(cd "$(dirname "$0")" && pwd)"

mkdir -p ~/alma-beat-organ/logs ~/alma-beat-organ/runs ~/.config/systemd/user
cp "$HERE/alma-beat@.service" ~/.config/systemd/user/
systemctl --user daemon-reload

for a in $ARMS; do
  if [ "${1:-}" = "--arm" ]; then
    systemctl --user enable "alma-beat@$a.service"
  else
    systemctl --user enable --now "alma-beat@$a.service"
  fi
done

systemctl --user list-units --all 'alma-beat@*' --no-legend || true
echo
echo "free memory now: $(awk '/MemAvailable/{printf "%.1f GB", $2/1048576}' /proc/meminfo)"
echo "each arm pauses itself below --min-free-gb 15 and writes runs/*/paused.log"
