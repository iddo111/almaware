#!/bin/sh
# alma-mic-linux installer - run ON the Linux node from this repo directory.
# Installs binary `alma-micd` and user unit `alma-micd.service`.
# (Deliberately NOT named alma-mic.service: that unit name is already taken on
#  eran4 by the hebrew-mic phone-PWA dictation server. Never overwrite it.)
set -e

BIN_DIR="$HOME/.local/bin"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT="$UNIT_DIR/alma-micd.service"
DATA_DIR="$HOME/.local/share/alma-micd"

echo "== alma-micd install =="

command -v gcc >/dev/null 2>&1 || { echo "ERROR: gcc not found"; exit 1; }

if [ ! -f /usr/include/pulse/simple.h ]; then
    echo "libpulse headers missing - installing libpulse-dev (needs sudo)..."
    sudo apt-get install -y --no-install-recommends libpulse-dev
fi

make

# Collision guard: refuse to clobber a unit file that is not ours.
if [ -f "$UNIT" ] && ! grep -q "ALMA always-on mic" "$UNIT"; then
    echo "ERROR: $UNIT exists and is not an alma-micd unit - refusing to overwrite."
    exit 1
fi

install -Dm755 alma-micd "$BIN_DIR/alma-micd"
install -Dm644 systemd/alma-micd.service "$UNIT"
if [ ! -f "$HOME/.config/alma-micd.env" ]; then
    install -Dm644 alma-micd.env.example "$HOME/.config/alma-micd.env"
    echo "wrote default config -> ~/.config/alma-micd.env (edit server/device there)"
fi
mkdir -p "$DATA_DIR/queue/bad"

systemctl --user daemon-reload

echo
echo "Installed:"
echo "  binary : $BIN_DIR/alma-micd"
echo "  unit   : $UNIT"
echo "  config : $HOME/.config/alma-micd.env"
echo
echo "Test   : $BIN_DIR/alma-micd --list-devices"
echo "         $BIN_DIR/alma-micd --once 5"
echo "Enable : systemctl --user enable --now alma-micd"
echo "Logs   : journalctl --user -u alma-micd -f"
