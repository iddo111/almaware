# SSH Full-Duplex Setup — A70 Android + HP Pavilion Linux
# הגדרת SSH דו-כיווני — A70 אנדרואיד + לפטופ HP Pavilion לינוקס

> **Goal:** SSH into both devices from the PC (Windows) and from each other, over Tailscale (works everywhere) and LAN (fallback).
> **A70 Tailscale IP:** `<tailnet-ip>` | **PC Tailscale IP:** `<tailnet-ip>`
> **A70 LAN IP (typical):** `<lan-ip>` | **HP Pavilion LAN IP:** discover with `ip addr`

---

## חלק א: SSH ל-A70 (Android / Termux)
## Part A: SSH into the A70 (Android via Termux)

Termux provides a native OpenSSH server. No root required.

### שלב 1 / Step 1 — Install OpenSSH in Termux

Run inside Termux on the A70:
```bash
pkg update -y
pkg install -y openssh
```

### שלב 2 / Step 2 — Set a password for your Termux user

```bash
passwd
# Enter a strong password when prompted (used for password auth as fallback)
```

### שלב 3 / Step 3 — Start sshd on port 8022

```bash
sshd
# Termux SSH always runs on port 8022 (ports <1024 require root)
```

Verify it's listening:
```bash
ss -tlnp | grep 8022
# Expected: LISTEN 0 ... *:8022
```

### שלב 4 / Step 4 — Add your PC's SSH public key (for passwordless login)

On PC (PowerShell/Git Bash), generate a key if you don't have one:
```bash
# On PC — run once if ~/.ssh/id_ed25519 doesn't exist
ssh-keygen -t ed25519 -C "iddo-pc-to-a70" -f ~/.ssh/id_ed25519 -N ""
```

Copy the public key to Termux:
```bash
# Option A — via ADB push (PC to A70, if ADB connected)
# On PC PowerShell:
$pubkey = Get-Content "$HOME\.ssh\id_ed25519.pub"
adb -s <lan-ip>:40723 shell "mkdir -p ~/.ssh && chmod 700 ~/.ssh"
adb -s <lan-ip>:40723 shell "echo '$pubkey' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"

# Option B — manual copy-paste inside Termux:
mkdir -p ~/.ssh && chmod 700 ~/.ssh
# Paste your id_ed25519.pub content:
echo "ssh-ed25519 AAAA... iddo-pc-to-a70" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

### שלב 5 / Step 5 — Connect from PC

```bash
# Over Tailscale (works from anywhere):
ssh -p 8022 -i ~/.ssh/id_ed25519 u0_a688@<tailnet-ip>

# Over LAN:
ssh -p 8022 -i ~/.ssh/id_ed25519 u0_a688@<lan-ip>

# Or just (if ~/.ssh/config is set up — see below):
ssh a70
```

### שלב 6 / Step 6 — Add SSH config entry on PC (~/.ssh/config)

```
# Add to C:\Users\<user>\.ssh\config (create if missing):
Host a70
    HostName <tailnet-ip>
    Port 8022
    User u0_a688
    IdentityFile ~/.ssh/id_ed25519
    ServerAliveInterval 30
    ServerAliveCountMax 6
```

After this: `ssh a70` connects directly.

### שלב 7 / Step 7 — Auto-start sshd on boot (Termux:Boot)

Requires Termux:Boot installed (see whatsapp_fix_guide.md Part C, Step 2):
```bash
mkdir -p ~/.termux/boot
cat > ~/.termux/boot/10-sshd.sh << 'EOF'
#!/data/data/com.termux/files/usr/bin/bash
# Start SSH server on boot
sshd
EOF
chmod +x ~/.termux/boot/10-sshd.sh
```

---

## חלק ב: SSH ל-HP Pavilion Linux
## Part B: SSH into the HP Pavilion Linux Laptop

### שלב 1 / Step 1 — Install and enable OpenSSH server

Most Ubuntu/Debian-based distros:
```bash
# On the HP Pavilion (run in terminal):
sudo apt update
sudo apt install -y openssh-server

# Enable and start:
sudo systemctl enable ssh
sudo systemctl start ssh

# Verify running:
sudo systemctl status ssh
# Expected: active (running)
```

For Fedora/RHEL-based:
```bash
sudo dnf install -y openssh-server
sudo systemctl enable --now sshd
```

For Arch-based:
```bash
sudo pacman -S openssh
sudo systemctl enable --now sshd
```

### שלב 2 / Step 2 — Find the HP Pavilion's IP addresses

```bash
# On HP Pavilion:
ip addr show | grep "inet "
hostname -I
# Note LAN IP (e.g. 192.168.1.XXX) and Tailscale IP (100.x.x.x if Tailscale is installed)
```

### שלב 3 / Step 3 — Install Tailscale on HP Pavilion (for persistent access)

```bash
# On HP Pavilion:
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
# Follow the auth URL printed — sign in to Iddo's tailnet account
sudo systemctl enable --now tailscaled
```

After this, the HP Pavilion gets a stable `100.x.x.x` Tailscale IP that works from anywhere.

### שלב 4 / Step 4 — Add PC's public key to HP Pavilion

```bash
# On HP Pavilion — replace with your actual public key content:
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo "ssh-ed25519 AAAA... iddo-pc-to-hp" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

Or use ssh-copy-id from PC (if on same LAN):
```bash
# On PC (Git Bash or WSL):
ssh-copy-id -i ~/.ssh/id_ed25519.pub iddo@192.168.1.XXX
```

### שלב 5 / Step 5 — Harden sshd config (recommended)

```bash
# On HP Pavilion:
sudo nano /etc/ssh/sshd_config
```

Set or verify these lines:
```
Port 22
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
AuthorizedKeysFile .ssh/authorized_keys
X11Forwarding yes
AllowTcpForwarding yes
```

Apply changes:
```bash
sudo systemctl reload ssh
```

### שלב 6 / Step 6 — Connect from PC

```bash
# Over Tailscale (replace 100.x.x.x with HP Pavilion Tailscale IP):
ssh iddo@<hp-tailscale-ip>

# Over LAN:
ssh iddo@192.168.1.XXX
```

Add to `~/.ssh/config` on PC:
```
Host hp-pavilion
    HostName <hp-tailscale-ip>
    Port 22
    User iddo
    IdentityFile ~/.ssh/id_ed25519
    ServerAliveInterval 30
    ServerAliveCountMax 6
    ForwardX11 yes
```

After: `ssh hp-pavilion` connects directly.

---

## חלק ג: SSH בין A70 ל-HP Pavilion (דו-כיווני)
## Part C: SSH Between A70 and HP Pavilion (Bidirectional)

### From A70 Termux → HP Pavilion

```bash
# On A70 in Termux:
pkg install -y openssh

# Generate A70's key (if not already done):
ssh-keygen -t ed25519 -C "a70-to-hp" -f ~/.ssh/id_ed25519 -N ""

# Add A70's public key to HP Pavilion's authorized_keys
# Copy ~/.ssh/id_ed25519.pub content to HP Pavilion:
cat ~/.ssh/id_ed25519.pub
# Then on HP Pavilion: echo "..." >> ~/.ssh/authorized_keys

# Connect:
ssh -i ~/.ssh/id_ed25519 iddo@<hp-tailscale-ip>
```

### From HP Pavilion → A70 Termux

```bash
# On HP Pavilion:
# Generate HP's key (if not already done):
ssh-keygen -t ed25519 -C "hp-to-a70" -f ~/.ssh/id_ed25519_hp -N ""

# Add HP's public key to A70's Termux authorized_keys
# Then connect:
ssh -p 8022 u0_a688@<tailnet-ip>
```

---

## חלק ד: טבלת חיבורים מהירה
## Part D: Quick Connection Reference

| From | To | Command |
|---|---|---|
| PC (Windows) | A70 | `ssh a70` (after config) |
| PC (Windows) | HP Pavilion | `ssh hp-pavilion` (after config) |
| A70 (Termux) | PC | `ssh -p PORT iddo1@<tailnet-ip>` |
| A70 (Termux) | HP Pavilion | `ssh iddo@<hp-tailscale-ip>` |
| HP Pavilion | A70 | `ssh -p 8022 u0_a688@<tailnet-ip>` |
| HP Pavilion | PC | `ssh iddo1@<tailnet-ip>` |

**Default ports:**
- A70 (Termux sshd): **8022**
- HP Pavilion Linux sshd: **22**
- PC (if OpenSSH server enabled in Windows): **22**

---

## בעיות נפוצות / Troubleshooting

```bash
# Test SSH port is reachable (from PC):
Test-NetConnection <tailnet-ip> -Port 8022     # A70
Test-NetConnection <hp-tailscale-ip> -Port 22    # HP Pavilion

# On A70: confirm sshd running
pgrep -a sshd

# On HP Pavilion: confirm sshd running
sudo ss -tlnp | grep :22
sudo journalctl -u ssh -n 20

# Permission errors (common):
# On A70 Termux: chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys
# On HP Pavilion: same + check /home/iddo permissions (must not be world-writable)
chmod 755 ~
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys
```

---

*Created 2026-05-02. Tailscale IPs from [`D:\CLAUDE\dispatch-fix\ARCHITECTURE.md`](file:///D:/CLAUDE/dispatch-fix/ARCHITECTURE.md): A70=`<tailnet-ip>`, PC=`<tailnet-ip>`.*
