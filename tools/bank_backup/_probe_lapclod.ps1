# Probe lapclod for the existing backup mechanism.
# ASCII only.
$key = 'C:\Users\<user>\.ssh\laptop93'
$host_ = 'linuxlite@<lan-ip>'

$cmd = @'
echo "=== home ==="
ls ~/finalize-lapclod.sh ~/backup.sh ~/sync.sh 2>/dev/null
echo "=== crontab user ==="
crontab -l 2>/dev/null
echo "=== systemd timers ==="
systemctl --user list-timers 2>/dev/null | head -10
echo "=== root systemd ==="
ls /etc/systemd/system/*backup* /etc/systemd/system/*sync* /etc/systemd/system/*lapclod* 2>/dev/null
echo "=== mounts ==="
mount | grep -E "smb|cifs|sshfs" | head -10
echo "=== recent rsync ==="
ls -la ~/sync.log ~/backup.log /var/log/sync.log 2>/dev/null | head -5
echo "=== disk usage of home ==="
du -sh ~/* 2>/dev/null | sort -h | tail -15
'@

ssh -i $key -o ConnectTimeout=5 -o StrictHostKeyChecking=no $host_ $cmd
