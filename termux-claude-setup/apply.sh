#!/usr/bin/env bash
# apply.sh — PC side (Git Bash). Finishes the Claude-Code-in-Termux setup on Iddo's S948B in ONE go.
# PRECONDITION: the phone's sshd is up. In Termux on the phone Iddo types:   sshd
#   (after this script runs once, ~/.bashrc starts sshd automatically whenever Termux opens)
# Steps: 1) run phone-setup.sh on the phone  2) push the phone's NEW pubkey to eran1/eran2/eran4
#        3) verify ssh eranN from the phone + run claude-doctor.   Never logs in to Claude.
set -u
KEY="$HOME/.ssh/termux_s948b"; PH="<lan-ip>"
SSH="ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new -p 8022 -i $KEY termux@$PH"
D="$(cd "$(dirname "$0")" && pwd)"
LOG="$D/apply-$(date +%Y%m%d-%H%M%S).log"
$SSH true 2>/dev/null || { echo "phone sshd :8022 not reachable — in Termux type: sshd"; exit 2; }
echo "== 1. phone-setup.sh on the phone" | tee "$LOG"
sed 's/\r$//' "$D/phone-setup.sh" | $SSH 'cat > ~/phone-setup.sh && chmod +x ~/phone-setup.sh && bash ~/phone-setup.sh' 2>&1 | tee -a "$LOG"
PUB=$(sed -n '/PUBKEY_BEGIN/,/PUBKEY_END/p' "$LOG" | grep '^ssh-ed25519' | head -1)
[ -z "$PUB" ] && { echo "no pubkey captured — stop"; exit 1; }
echo "== 2. push pubkey to the fleet" | tee -a "$LOG"
for h in eran1 eran2 "eran4@<lan-ip>"; do
  ssh -o BatchMode=yes -o ConnectTimeout=6 "$h" "mkdir -p ~/.ssh && chmod 700 ~/.ssh && touch ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && (grep -qF '$PUB' ~/.ssh/authorized_keys || echo '$PUB' >> ~/.ssh/authorized_keys) && echo \"$h: \$(grep -c phone-s948b ~/.ssh/authorized_keys) phone key(s) in authorized_keys\"" 2>&1 | tee -a "$LOG"
done
echo "== 3. verify from the phone + claude-doctor" | tee -a "$LOG"
$SSH 'for h in eran1 eran2 eran4; do echo "phone->$h: $(ssh -o BatchMode=yes -o ConnectTimeout=5 $h hostname 2>&1 | head -1)"; done; echo; ~/bin/claude-doctor' 2>&1 | tee -a "$LOG"
echo "log: $LOG"
