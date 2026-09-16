#!/data/data/com.termux/files/usr/bin/sh
# A70 Termux — one-shot SSH server bring-up
# Run inside Termux on the A70 phone:
#   sh /sdcard/famesh-ssh-setup.sh
#
# Prerequisite: the pubkey file already on /sdcard
#   /sdcard/iddo-pubkey.pub  (pushed via ADB this session)

set -e

mkdir -p $HOME/.ssh
chmod 700 $HOME/.ssh

# Append (don't overwrite — preserves any future keys)
if ! grep -qF "$(cat /sdcard/iddo-pubkey.pub)" $HOME/.ssh/authorized_keys 2>/dev/null; then
    cat /sdcard/iddo-pubkey.pub >> $HOME/.ssh/authorized_keys
fi
chmod 600 $HOME/.ssh/authorized_keys

# Start sshd (port 8022 by default per Termux openssh package)
sshd

# Make it persist after reboot via Termux:Boot
mkdir -p $HOME/.termux/boot
cat > $HOME/.termux/boot/01-sshd <<'EOF'
#!/data/data/com.termux/files/usr/bin/sh
termux-wake-lock
sshd
EOF
chmod +x $HOME/.termux/boot/01-sshd

# Status report to /sdcard so PC-side can read it back via adb pull
{
    echo "=== famesh-ssh-setup result $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
    echo
    echo "authorized_keys:"
    ls -la $HOME/.ssh/authorized_keys
    wc -c $HOME/.ssh/authorized_keys
    echo
    echo "sshd processes:"
    ps -ef 2>/dev/null | grep -v grep | grep sshd || echo "(no sshd process found — check pkg install -y openssh)"
    echo
    echo "Listening sockets (may need root for full ss output):"
    ss -tnl 2>/dev/null | head -10 || netstat -tln 2>/dev/null | head -10 || echo "(no socket inspector available)"
    echo
    echo "Termux user:"
    whoami
    id
    echo
    echo "Network:"
    ip addr show wlan0 2>/dev/null | grep -E "inet|wlan0" | head -5
    tailscale status 2>/dev/null | head -5 || echo "(tailscale CLI not in Termux — that's fine, the system Tailscale app is enough)"
} > /sdcard/famesh-ssh-result.txt

echo "Done. From PC: adb -s <lan-ip>:37275 pull /sdcard/famesh-ssh-result.txt -"
echo "Then test:    ssh -p 8022 $(whoami)@\$(ip addr show wlan0 | awk '/inet /{print \$2}' | cut -d/ -f1) 'echo ok'"
