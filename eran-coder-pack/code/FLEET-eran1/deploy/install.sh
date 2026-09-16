#!/bin/bash
# install.sh — plant the organism on eran1 under systemd --user.
# Run ON the box, from ~/eran-brain: bash deploy/install.sh
set -eu
BASE="${HOME}/eran-brain"
UNITS="${HOME}/.config/systemd/user"

mkdir -p "${BASE}/state" "${BASE}/food/train" "${BASE}/food/words" \
         "${BASE}/feedback/inbox" "${BASE}/songs/outbox" "${BASE}/results" \
         "${BASE}/proof/heldout-vault" "${UNITS}"

chmod +x "${BASE}/deploy/nanny.sh"
cp "${BASE}/deploy/eranb-life.service" \
   "${BASE}/deploy/eranb-serve.service" \
   "${BASE}/deploy/eranb-nanny.service" \
   "${BASE}/deploy/eranb-nanny.timer" \
   "${BASE}/deploy/eranb-tournament.service" \
   "${BASE}/deploy/eranb-tournament.timer" \
   "${UNITS}/"

systemctl --user daemon-reload
systemctl --user enable --now eranb-serve.service
systemctl --user enable --now eranb-life.service
systemctl --user enable --now eranb-nanny.timer

# ERAN-14 (2026-09-06): the ear tournament is RETIRED while genome.EAR_FROZEN
# is True -- a tournament that cannot crown a new ear changes nothing, and its
# timer is correctly disabled on the box (last result 2026-08-24). This
# installer used to re-arm it on every run, and results/tournament-*.json going
# quiet is exactly the shape of "a job nobody noticed had died".
if python3 -c "import sys; sys.path.insert(0, '${BASE}/body'); import genome; sys.exit(0 if genome.EAR_FROZEN else 1)"; then
    echo "[install] tournament: NOT enabled - genome.EAR_FROZEN is True (the crowned ear is frozen; a tournament would be inert)"
    systemctl --user disable eranb-tournament.timer 2>/dev/null || true
else
    systemctl --user enable --now eranb-tournament.timer
fi

# without linger, the organism dies when the ssh session ends
if loginctl show-user "$(whoami)" 2>/dev/null | grep -q "Linger=yes"; then
    echo "[install] linger: yes — the organism survives logout"
else
    echo "[install] WARNING: linger is OFF. Run: loginctl enable-linger $(whoami)"
fi

echo "[install] done. Window: http://127.0.0.1:8820/  (tunnel from the PC:"
echo "          ssh -L 8820:127.0.0.1:8820 eran1)"
echo "[install] first meal: python3 eran_life.py --feed-all  (or let --live eat)"
