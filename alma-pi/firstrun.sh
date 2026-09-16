#!/bin/bash
# ALMA Pi first-boot provisioning — לזכרה של עלמה ז"ל
# Written 2026-08-08 by claude-cli. Runs once via cmdline.txt systemd.run hook,
# then hands off to alma-provision.service (which retries until network+model OK).
set +e

# ---- optional Wi-Fi (leave empty if using ethernet or configuring on-device) ----
WIFI_SSID=""
WIFI_PASS=""
WIFI_COUNTRY="IL"

BOOTDIR=/boot/firmware
[ -d "$BOOTDIR" ] || BOOTDIR=/boot

hostnamectl set-hostname alma-pi 2>/dev/null || echo alma-pi > /etc/hostname
systemctl enable ssh 2>/dev/null

if [ -n "$WIFI_SSID" ]; then
  raspi-config nonint do_wifi_country "$WIFI_COUNTRY" 2>/dev/null
  raspi-config nonint do_wifi_ssid_passphrase "$WIFI_SSID" "$WIFI_PASS" 2>/dev/null
fi

# The heavy lifting happens in a persistent oneshot that retries until done.
cat > /etc/systemd/system/alma-provision.service << 'UNIT'
[Unit]
Description=ALMA Pi provisioning (llama.cpp + model by RAM + kiosk)
After=network-online.target
Wants=network-online.target
ConditionPathExists=!/var/lib/alma-provisioned

[Service]
Type=oneshot
TimeoutStartSec=infinity
ExecStart=/usr/local/sbin/alma-provision.sh
StandardOutput=journal+console
StandardError=journal+console

[Install]
WantedBy=multi-user.target
UNIT

cat > /usr/local/sbin/alma-provision.sh << 'PROV'
#!/bin/bash
# Retried on every boot until /var/lib/alma-provisioned exists.
set -e
LOG=/var/log/alma-provision.log
exec > >(tee -a "$LOG") 2>&1
echo "=== ALMA provision start $(date -Is) ==="

# 1. deps
apt-get update
apt-get install -y build-essential cmake git curl libcurl4-openssl-dev chromium-browser || \
  apt-get install -y build-essential cmake git curl libcurl4-openssl-dev chromium

# 2. llama.cpp (source build, ~10-15 min on a Pi 5; CPU-only is correct here)
if [ ! -x /opt/llama.cpp/build/bin/llama-server ]; then
  rm -rf /opt/llama.cpp
  git clone --depth 1 https://github.com/ggml-org/llama.cpp /opt/llama.cpp
  cmake -S /opt/llama.cpp -B /opt/llama.cpp/build -DCMAKE_BUILD_TYPE=Release -DLLAMA_CURL=ON
  cmake --build /opt/llama.cpp/build --target llama-server -j"$(nproc)"
fi

# 3. largest model this board's RAM honestly supports (Q4_K_M, ~1GB left for OS+desktop)
MEM_KB=$(awk '/MemTotal/{print $2}' /proc/meminfo)
mkdir -p /opt/alma/models
if   [ "$MEM_KB" -ge 15000000 ]; then M=Qwen3-14B;  U=https://huggingface.co/Qwen/Qwen3-14B-GGUF/resolve/main/Qwen3-14B-Q4_K_M.gguf
elif [ "$MEM_KB" -ge 7000000 ];  then M=Qwen3-8B;   U=https://huggingface.co/Qwen/Qwen3-8B-GGUF/resolve/main/Qwen3-8B-Q4_K_M.gguf
elif [ "$MEM_KB" -ge 3500000 ];  then M=Qwen3-4B;   U=https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/main/Qwen3-4B-Q4_K_M.gguf
else                                  M=Qwen3-1.7B; U=https://huggingface.co/unsloth/Qwen3-1.7B-GGUF/resolve/main/Qwen3-1.7B-Q4_K_M.gguf
fi
F=/opt/alma/models/$M-Q4_K_M.gguf
[ -s "$F" ] || curl -L --fail --retry 5 -o "$F.part" "$U"
[ -s "$F" ] || mv "$F.part" "$F"
echo "model: $M ($(du -h "$F" | cut -f1)) for $((MEM_KB/1024/1024))GB RAM"

# 4. llama-server service (built-in webui IS the GUI; MCP-capable)
cat > /etc/systemd/system/alma-llm.service << EOF
[Unit]
Description=ALMA LLM ($M via llama-server)
After=network.target

[Service]
ExecStart=/opt/llama.cpp/build/bin/llama-server -m $F --alias $M --host 0.0.0.0 --port 8080 -c 8192 -t $(nproc) --jinja
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now alma-llm.service

# 5. kiosk on the Pi's OWN screen (keyboard+HDMI, standalone by design)
KUSER=$(getent passwd 1000 | cut -d: -f1)
mkdir -p /etc/xdg/autostart
cat > /etc/xdg/autostart/alma-kiosk.desktop << 'EOF'
[Desktop Entry]
Type=Application
Name=ALMA Kiosk
Exec=sh -c 'for i in $(seq 1 60); do curl -s -o /dev/null http://localhost:8080 && break; sleep 5; done; chromium-browser --kiosk --noerrdialogs --disable-session-crashed-bubble http://localhost:8080 || chromium --kiosk http://localhost:8080'
X-GNOME-Autostart-enabled=true
EOF

touch /var/lib/alma-provisioned
echo "=== ALMA provision DONE $(date -Is) — model $M on http://alma-pi.local:8080 ==="
PROV
chmod +x /usr/local/sbin/alma-provision.sh
systemctl enable alma-provision.service

# restore cmdline so this hook never runs again
sed -i 's| systemd.run=[^ ]*||; s| systemd.run_success_action=[^ ]*||; s| systemd.unit=kernel-command-line.target||' "$BOOTDIR/cmdline.txt"
rm -f "$BOOTDIR/firstrun.sh"
exit 0
