#!/data/data/com.termux/files/usr/bin/bash
# alma-tablet / chimera-setup.sh — a real Linux userland on the Tab A7 Lite,
# WITHOUT touching the bootloader.
#
# THE POINT OF THE CHIMERA
#   Bare-metal postmarketOS on this device boots but the TOUCHSCREEN DOES NOT WORK,
#   only i3 runs, and the mainline MT6765 kernel refuses to boot at all because the
#   Android bootloader rejects a dummy dtbo. So bare metal costs you the screen and
#   trips the Knox e-fuse permanently, and you find out what else is broken only
#   AFTER the irreversible step.
#
#   The chimera keeps Android as the driver layer — touch, wifi, battery, backlight,
#   suspend and USB all keep working because Samsung's own kernel is still running —
#   and puts a genuine Debian userland on top. You get apt, a real shell, a real
#   desktop if you want one, and every tool that does not need kernel access.
#
#   What the chimera CANNOT do, stated plainly so it is not a surprise later:
#     - no kernel modules, so no monitor mode / packet injection on the internal wifi
#     - no raw sockets without root, so nmap SYN scans and arp tools are limited
#       (nmap TCP-connect scans work fine)
#     - no access to another app's data
#   If you need injection you need an EXTERNAL USB wifi adapter and root, or bare
#   metal. That is a hardware problem, not an OS-choice problem.
#
# BEFORE RUNNING THIS
#   Install Termux from F-Droid — NOT from the Play Store. The Play Store build is
#   abandoned and years out of date; it will fail in confusing ways.
#     https://f-droid.org/packages/com.termux/
#   Then open Termux and run this script.
#
#   adb push chimera-setup.sh /sdcard/ && (in Termux)  bash /sdcard/chimera-setup.sh

set -u

say() { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
ok()  { printf '   \033[1;32mOK\033[0m  %s\n' "$*"; }
warn(){ printf '   \033[1;33m!!\033[0m  %s\n' "$*"; }

say "ALMA chimera — Debian userland on Android, no bootloader changes"

if [ ! -d /data/data/com.termux ]; then
  echo "This must run inside Termux on the tablet, not on the PC."
  exit 1
fi

say "1/6  Termux base"
yes | pkg upgrade -y >/dev/null 2>&1
pkg install -y proot-distro openssh tmux git curl wget nano python termux-api >/dev/null 2>&1
ok "termux packages"

say "2/6  storage access"
# Lets the Linux side reach /sdcard, so files move between Android and Debian.
termux-setup-storage 2>/dev/null || warn "grant the storage permission when Android asks"
ok "storage"

say "3/6  Debian rootfs (this is the big download — a few hundred MB)"
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
# Deliberately NOT a huge metapackage. Every one of these is a diagnostic tool for
# your own kit: reach the DGX fleet, look at your own network, hold a session open.
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
  ssh-keygen -t ed25519 -N "" -C "tab-a7-lite" -f "$HOME/.ssh/id_ed25519" >/dev/null
  ok "new ed25519 key generated"
else
  ok "key already present"
fi
mkdir -p "$HOME/.ssh"
cat > "$HOME/.ssh/config" <<'SSHCFG'
# ALMA fleet. eran3 is reachable over Tailscale; the QSFP fabric is PC-only.
Host eran1
    HostName <lan-ip>
    User eran1
Host eran2
    HostName <lan-ip>
    User eran2
Host eran3
    HostName <tailnet-ip>
    User eran3
Host pc
    HostName <tailnet-ip>
    User iddo1
SSHCFG
chmod 600 "$HOME/.ssh/config"
ok "ssh config written"

say "6/6  launcher"
cat > "$PREFIX/bin/alma" <<'LAUNCH'
#!/data/data/com.termux/files/usr/bin/bash
# one word to get a Linux shell
exec proot-distro login debian --shared-tmp -- bash -l
LAUNCH
chmod +x "$PREFIX/bin/alma"
ok "type 'alma' to enter Debian"

say "DONE"
cat <<EOF

   Type            alma          -> a real Debian shell
   Your public key (add it to the DGX authorized_keys):

$(cat "$HOME/.ssh/id_ed25519.pub" 2>/dev/null)

   NEXT, if you want a graphical desktop:
     1. install Termux:X11 from F-Droid  (com.termux.x11)
     2. pkg install x11-repo && pkg install termux-x11-nightly
     3. inside Debian:  apt install xfce4 xfce4-terminal dbus-x11
     4. run  termux-x11 :0 &  then export DISPLAY=:0 and start xfce4-session

   NOT DONE by this script, on purpose:
     - Tailscale: install the Android app from the Play Store and log in there.
       It works at the Android layer and the Debian side inherits the routing.
       Do NOT try to run tailscaled inside proot — it needs a TUN device it
       cannot have without root.

EOF
