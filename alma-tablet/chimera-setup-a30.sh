#!/data/data/com.termux/files/usr/bin/bash
# alma-tablet / chimera-setup-a30.sh — a real Linux userland on the Galaxy A30,
# WITHOUT touching the bootloader.
#
# This is Iddo's legally-owned A30 (a gift from Noam). Adapted from the Tab A7
# Lite chimera; the only device-specific parts were the SSH key comment and the
# fleet addresses, both corrected below. The chimera itself is device-agnostic:
# Termux + proot Debian runs on any Android 7+ ARM device.
#
# THE POINT OF THE CHIMERA
#   Keep Samsung's own Android kernel as the driver layer — touch, wifi,
#   battery, backlight, suspend and USB all keep working — and put a genuine
#   Debian userland on top through proot. You get apt, a real shell, a real
#   desktop if you want one, and every tool that does not need kernel access.
#   No bootloader unlock, no Knox e-fuse tripped, fully reversible.
#
#   What the chimera CANNOT do, stated plainly so it is not a surprise later:
#     - no kernel modules, so no monitor mode / packet injection on internal wifi
#     - no raw sockets without root, so nmap SYN scans are limited
#       (nmap TCP-connect scans work fine)
#     - no access to another app's data
#   Those need an external USB wifi adapter and root, or bare metal — a hardware
#   choice, not something this script can grant.
#
# BEFORE RUNNING THIS
#   Install Termux from F-Droid — NOT the Play Store (that build is years stale
#   and fails in confusing ways):  https://f-droid.org/packages/com.termux/
#   Then open Termux and run this script. To copy it over from the PC:
#     adb push chimera-setup-a30.sh /sdcard/
#     (in Termux)  bash /sdcard/chimera-setup-a30.sh

set -u

say() { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
ok()  { printf '   \033[1;32mOK\033[0m  %s\n' "$*"; }
warn(){ printf '   \033[1;33m!!\033[0m  %s\n' "$*"; }

say "ALMA chimera (A30) — Debian userland on Android, no bootloader changes"

if [ ! -d /data/data/com.termux ]; then
  echo "This must run inside Termux on the A30, not on the PC."
  exit 1
fi

say "1/6  Termux base"
yes | pkg upgrade -y >/dev/null 2>&1
pkg install -y proot-distro openssh tmux git curl wget nano python termux-api >/dev/null 2>&1
ok "termux packages"

say "2/6  storage access"
termux-setup-storage 2>/dev/null || warn "grant the storage permission when Android asks"
ok "storage"

say "3/6  Debian rootfs (the big download — a few hundred MB)"
if proot-distro list 2>/dev/null | grep -q "debian.*installed"; then
  ok "debian already installed"
else
  proot-distro install debian || { echo "debian install failed"; exit 1; }
  ok "debian installed"
fi

say "4/6  inside Debian: the actual toolkit"
proot-distro login debian -- bash -c '
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends \
    ca-certificates curl wget git nano vim less \
    openssh-client mosh tmux htop \
    iputils-ping dnsutils net-tools iproute2 traceroute \
    nmap tcpdump iperf3 \
    python3 python3-pip python3-venv \
    build-essential 2>&1 | tail -2
echo "   debian toolkit installed"
'
ok "toolkit"

say "5/6  SSH key + fleet shortcuts"
if [ ! -f "$HOME/.ssh/id_ed25519" ]; then
  ssh-keygen -t ed25519 -N "" -C "alma-a30" -f "$HOME/.ssh/id_ed25519" >/dev/null
  ok "new ed25519 key generated"
else
  ok "key already present"
fi
mkdir -p "$HOME/.ssh"
# Fleet addresses reach the DGX over Tailscale, which works at the Android
# layer once the Tailscale app is logged in. The QSFP fabric is PC-only.
cat > "$HOME/.ssh/config" <<'SSHCFG'
Host eran1
    HostName <lan-ip>
    User eran1
Host eran2
    HostName <lan-ip>
    User eran2
Host eran3
    HostName <tailnet-host>
    User eran3
Host eran4
    HostName <tailnet-host>
    User eran4
Host pc
    HostName <tailnet-ip>
    User iddo1
SSHCFG
chmod 600 "$HOME/.ssh/config"
ok "ssh config written"

say "6/6  launcher"
cat > "$PREFIX/bin/alma" <<'LAUNCH'
#!/data/data/com.termux/files/usr/bin/bash
exec proot-distro login debian --shared-tmp -- bash -l
LAUNCH
chmod +x "$PREFIX/bin/alma"
ok "type 'alma' to enter Debian"

say "DONE"
cat <<EOF

   Type            alma          -> a real Debian shell
   Your public key (add it to the DGX authorized_keys):

$(cat "$HOME/.ssh/id_ed25519.pub" 2>/dev/null)

   NEXT, for a graphical desktop:
     1. install Termux:X11 from F-Droid  (com.termux.x11)
     2. pkg install x11-repo && pkg install termux-x11-nightly
     3. inside Debian:  apt install xfce4 xfce4-terminal dbus-x11
     4. run  termux-x11 :0 &  then export DISPLAY=:0 and start xfce4-session

   Tailscale: install the Android app from the Play Store and log in there.
   It routes at the Android layer and Debian inherits it. Do NOT run
   tailscaled inside proot — it needs a TUN device it cannot get without root.

EOF
