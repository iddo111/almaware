#!/bin/bash
# install.sh — install + enable Chai's two dmidi- units (systemd --user).
# New dmidi- prefix only: zero name collision with any archived darwish-* unit.
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST_DIR="$HOME/.config/systemd/user"

mkdir -p "$DEST_DIR"
cp "$SRC_DIR/dmidi-life.service" "$DEST_DIR/dmidi-life.service"
cp "$SRC_DIR/dmidi-tap.service" "$DEST_DIR/dmidi-tap.service"

systemctl --user daemon-reload
systemctl --user enable --now dmidi-life.service
systemctl --user enable --now dmidi-tap.service

echo "--- dmidi-life.service ---"
systemctl --user status dmidi-life.service --no-pager -l | head -n 8 || true
echo "--- dmidi-tap.service ---"
systemctl --user status dmidi-tap.service --no-pager -l | head -n 8 || true
echo "--- archived darwish-* units (should all stay inactive) ---"
systemctl --user list-units 'darwish-*' --all --no-pager || true
