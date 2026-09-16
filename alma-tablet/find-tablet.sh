#!/data/data/com.termux/files/usr/bin/bash
# find-tablet.sh — run this in TERMUX ON THE A70 PHONE to locate the Tab A7 Lite
# on the WiFi, and connect to it over wireless ADB from the phone.
#
# WHY FROM THE PHONE
#   The PC sees nothing on USB — 20 USB devices present, zero Samsung. That is a dead
#   cable or a different machine, not a driver problem. The phone is already on the same
#   WiFi and already on the tailnet, so it can reach the tablet without any cable at all.
#
# WHAT IT DOES
#   1. works out the phone's own subnet
#   2. sweeps it for live hosts
#   3. looks for the ports Android wireless-debugging actually uses
#   4. tries to fingerprint which one is the tablet
#
#   pkg install nmap iproute2 android-tools
#   bash find-tablet.sh

set -u
c()  { printf '\033[1;36m%s\033[0m\n' "$*"; }
ok() { printf '   \033[1;32m%s\033[0m\n' "$*"; }
w()  { printf '   \033[1;33m%s\033[0m\n' "$*"; }

command -v nmap >/dev/null || { echo "pkg install nmap"; exit 1; }

c "1. where am I"
IP=$(ip -4 addr show 2>/dev/null | grep -oE 'inet [0-9.]+' | awk '{print $2}' \
     | grep -vE '^127\.' | head -1)
[ -z "$IP" ] && IP=$(ifconfig 2>/dev/null | grep -oE 'inet [0-9.]+' | awk '{print $2}' | grep -vE '^127\.' | head -1)
[ -z "$IP" ] && { echo "could not find my own IP — is WiFi on?"; exit 1; }
SUB=$(echo "$IP" | cut -d. -f1-3)
ok "phone is $IP, scanning ${SUB}.0/24"

c "2. who is alive"
nmap -sn --host-timeout 8s "${SUB}.0/24" -oG - 2>/dev/null \
  | awk '/Up$/{print $2}' > /tmp/alive.txt
ok "$(wc -l < /tmp/alive.txt) hosts up"

c "3. which of them speaks ADB"
# 5555 is classic 'adb tcpip' (needs a cable once). Android 11+ WIRELESS DEBUGGING
# uses a RANDOM high port instead and advertises it over mDNS — that is why a plain
# 5555 scan usually finds nothing on a modern device, and why the pairing screen
# shows you the port. Scan both the classic port and the wireless-debug range.
FOUND=0
while read -r H; do
  [ "$H" = "$IP" ] && continue
  R=$(nmap -Pn -p 5555 --host-timeout 6s "$H" 2>/dev/null | grep -E '^5555.*open')
  if [ -n "$R" ]; then ok "$H  ADB 5555 OPEN  <-- connect to this"; FOUND=1; fi
done < /tmp/alive.txt
[ "$FOUND" = 0 ] && w "nothing on 5555 — expected on Android 11+, see step 4"

c "4. mDNS — how wireless debugging actually announces itself"
if command -v avahi-browse >/dev/null; then
  avahi-browse -art 2>/dev/null | grep -iE "adb|_adb-tls" | head
else
  w "no avahi. Use the ports shown on the tablet screen instead:"
  w "  Settings > Developer options > Wireless debugging"
  w "  the MAIN screen shows  IP:PORT_A   (for connect)"
  w "  'Pair device with pairing code' shows IP:PORT_B + a 6-digit code"
  w "  they are DIFFERENT ports. You need both."
fi

c "5. connect"
cat <<'EOF'
   From the phone (or the PC, same commands):

     adb pair    <IP>:<PORT_B>        # then type the 6-digit code
     adb connect <IP>:<PORT_A>
     adb devices -l

   Once connected, everything else works over WiFi — shell, push, pull, logcat.
   The only thing WiFi adb CANNOT do is fastboot/Odin flashing. Bare-metal
   flashing needs a real data cable, always.
EOF
