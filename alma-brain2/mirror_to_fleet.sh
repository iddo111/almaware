#!/bin/sh
# ALMA SECOND BRAIN -- read-only backup mirror to every DGX (Iddo 2026-09-12).
# PC has no sshd (fleet_inventory.json), so this always PUSHES from the PC.
# The live writable door stays the PC (tailnet :8897) -- this is redundancy only.
set -e
SRC=/d/CLAUDE/alma-brain2
HOSTS="eran1 eran2 eran3 eran4"
for h in $HOSTS; do
  ssh "$h" "rm -rf ~/brain2-mirror && mkdir -p ~/brain2-mirror" 2>>"$SRC/state/mirror.log"
  scp -rq "$SRC/wiki" "$SRC/state" "$h:~/brain2-mirror/" 2>>"$SRC/state/mirror.log" \
    && echo "$(date -Iseconds) OK $h" >>"$SRC/state/mirror.log" \
    || echo "$(date -Iseconds) FAIL $h" >>"$SRC/state/mirror.log"
done
