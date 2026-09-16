# SSH Comms Triage — 2026-04-30

Status snapshot for Iddo's SSH connectivity from this Windows PC (D:\CLAUDE) to all known nodes.

PC fingerprint: pubkey `iddo@openclaw-pi3` (ed25519, in `C:\Users\<user>\.ssh\id_ed25519.pub`)

---

## 1. SSH config (C:\Users\<user>\.ssh\config)

```
Host openclaw
  HostName openclaw.local
  User iddo
  IdentityFile ~/.ssh/id_ed25519
  IdentitiesOnly yes
```

Only one named host. Everything else is reached by IP.

## 2. known_hosts entries

| Address | Algorithm | Notes |
|---------|-----------|-------|
| <lan-ip> | ssh-rsa | LAN host (MAC c8:70:23:2f:13:1f), responds on port 22, rejects pubkey auth |
| <lan-ip> | ssh-ed25519 | router (MAC c8:70:23:1b:01:af) |
| [127.0.0.1]:2222 | ed25519 + rsa + ecdsa | localhost forward (probably ADB→Termux), currently no listener |

`known_hosts.old` (from Apr 27) holds a previous superset.

## 3. Tailscale tailnet (live)

```
<tailnet-ip>    gofuckyourself   windows  THIS PC
<tailnet-ip>   a70              android  online (Tailscale up — but no SSH server listening)
<tailnet-ip>     desktop-qkrk2bs  windows  offline 10d
<tailnet-ip>  linuxlite        linux    online (sshd up — no key match)
```

## 4. Connectivity matrix (probe results, 2026-04-30)

| Device | Endpoint | Reachable | Auth | Status |
|--------|----------|-----------|------|--------|
| openclaw | openclaw.local:22 | NO | n/a | DNS does not resolve (mDNS not propagating, host probably off) |
| Digital Vagabond | <tailnet-ip>:22 | YES | ed25519 | WORKING — `ssh iddo1@<tailnet-ip>` returns `ok` |
| A70 (Tailscale) | <tailnet-ip>:22 | NO | n/a | TCP timeout — no sshd listening |
| A70 (LAN/ADB) | <lan-ip> | YES via ADB | ADB | Termux installed, openssh package installed, sshd NOT running, authorized_keys was 0 bytes |
| linuxlite (Tailscale) | <tailnet-ip>:22 | YES | rejected | sshd alive, no matching pubkey for iddo1/root/mibox — likely Mibox or Digital Vagabond's WSL |
| Mibox legacy | <lan-ip>:5555 | NO | n/a | offline |
| LAN node | <lan-ip>:22 | YES | rejected | sshd alive, MAC c8:70:23:2f:13:1f (likely a TP-Link/router-segment device — not iddo's) |
| LAN node | <lan-ip>:22 | YES | rejected | sshd alive, no matching pubkey |
| Router | <lan-ip>:22 | NO | n/a | TCP closed |

## 5. Per-device next actions

### A. A70 (Iddo's daily) — primary FAMESH node 1

**Current state**: Termux + openssh installed; sshd not running; authorized_keys was empty (now staged for one-shot fix).

**Files staged on /sdcard via ADB this session:**
- `/sdcard/iddo-pubkey.pub` — Iddo's Windows ed25519 pubkey
- `/sdcard/famesh-ssh-setup.sh` — one-shot installer

**Iddo: open Termux on A70 (already auto-launched) and run ONE LINE:**
```bash
sh /sdcard/famesh-ssh-setup.sh
```

(or, equivalently, manually:
```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
cat /sdcard/iddo-pubkey.pub >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
sshd
ps -ef | grep sshd
```
)

**Make it persist after reboot** — Termux already has `~/.termux/boot/00-bridge.sh`. Add an sshd line:
```bash
echo 'sshd' >> ~/.termux/boot/00-bridge.sh
# install Termux:Boot from F-Droid first if not already (pkg list shows com.termux only — Termux:Boot is com.termux.boot)
```

**Then verify from this PC:**
```bash
ssh -o ConnectTimeout=3 -p 8022 iddo1@<lan-ip> 'echo ok'      # LAN
ssh -o ConnectTimeout=3 -p 8022 iddo1@<tailnet-ip> 'echo ok'     # Tailscale
```

**On the VPN-blocking-SSH question (the 2026-04-28 blocker)**: the report read this wrong. Tailscale is up (`tailscale status` shows A70 online). The reason port 22 / 8022 timeouts on the Tailscale IP is **sshd is simply not running on A70**. Once the one-liner above runs, Tailscale-to-A70 SSH will work even off the LAN. No split-tunnel/VPN gymnastics needed. Tailscale **IS** the clean alternative recommended in the task brief — already installed and operational.

**Always-on Tailscale toggle (separate from the post-reboot Tailscale issue noted in dispatch-fix)**: Settings → Connections → More connection settings → VPN → Tailscale gear → toggle Always-on VPN. This was Iddo's other ask.

### B. A30 (secondary)

**Blocker per memory**: USB Debugging not enabled.

**Resolved in walkthrough file**: see `D:\CLAUDE\tools\ssh-comms-triage\a30-usb-debug-walkthrough.md` — 7-tap Build Number, USB debug toggle, Allow PC fingerprint.

**adb is already installed** at:
`C:\Users\<user>\AppData\Local\Microsoft\WinGet\Packages\Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe\platform-tools\adb.exe`

After Iddo enables USB debug and plugs in:
```powershell
adb devices            # should show one new device line beyond the A70 entries
adb -s <A30-serial> shell getprop ro.product.model      # should print SM-A305* (or whatever the A30 reports)
```

### C. Mibox (Armbian build)

**Blocker per memory**: `gh` token missing `workflow` scope.

**Verified this session** (from this PC):
```
gh auth status
> Token scopes: 'gist', 'read:org', 'repo'    # 'workflow' is missing
```

**Iddo runs from this PC (interactive browser, ~30 s):**
```powershell
gh auth refresh -h github.com -s repo,workflow
```
Browserless variant if needed:
```powershell
gh auth refresh -s repo,workflow --hostname github.com
# then paste the device code at https://github.com/login/device
```

Helper script: `D:\CLAUDE\tools\ssh-comms-triage\mibox-gh-auth-refresh.sh`

After refresh succeeds, `gh auth status` should show `Token scopes: 'gist', 'read:org', 'repo', 'workflow'` and the Armbian build can proceed (`mibox-armbian-mission/STATUS.md` Iteration 2).

**Note**: The Mibox device (<lan-ip>:5555) is currently offline — that's a separate hardware issue (Mi Box S unplugged or not on Wi-Fi). The auth refresh unblocks the BUILD; running it on the device is a separate step once it's back on network.

The `linuxlite` Tailscale node at <tailnet-ip> may actually be the WSL Ubuntu where the Armbian build runs — sshd is up there but our keys aren't authorized. Worth a future deploy step if Iddo wants direct SSH into the build VM.

### D. Digital Vagabond

**Status**: WORKING from this PC.

`ssh iddo1@<tailnet-ip> 'echo ok'` returns `ok`. The 2026-04-29 report said "service does not exist" — that was during install. Install completed; sshd is now Running. Per `D:\CLAUDE\digital-vagabond\STATUS.md`, this is the same Windows PC's OpenSSH server bound to the Tailnet.

Note: "Digital Vagabond" is **this Windows PC's identity on the Tailnet** (machine name `gofuckyourself`, Tailscale IP `<tailnet-ip>`). It's not a separate Linux box. The remote-friendly SSH/VNC/dashboard combo lets Iddo's A70 phone act as a thin client into the PC.

**Verify from PC:**
```powershell
Get-Service sshd | Select-Object Status,StartType
Test-NetConnection <tailnet-ip> -Port 22
```

**Verify from A70 (after Termux sshd is up so the loop can be tested both directions):**
```bash
ssh iddo1@<tailnet-ip> 'hostname; uname -a'
```

### E. S22/S23 phones (mom + dad — FAMESH phase-1 nodes 2 + 3)

Neither is reachable today. They have not yet been provisioned. Per FAMESH project memory, week-1 open question #3 is "Tailscale on mom + dad's S22/S23 — Iddo to install + magic-link join their devices?" This SSH triage gives Iddo the per-phone steps to combine with that Tailscale step.

**Per-phone setup (each phone, ~10 min over WhatsApp video call):**

1. **Install Termux** (F-Droid build, NOT Play Store — Play Store version is unmaintained).
   - URL to share with parent: https://f-droid.org/en/packages/com.termux/
   - Or APK direct: https://f-droid.org/repo/com.termux_118.apk

2. **Install Termux:Boot** (so sshd autostarts after reboot).
   - https://f-droid.org/en/packages/com.termux.boot/
   - First launch must be opened once (taps the launcher icon) for the boot intent to register.

3. **Open Termux, run once:**
   ```bash
   pkg update -y && pkg upgrade -y
   pkg install -y openssh
   sshd                                     # starts immediately (port 8022)
   passwd                                   # set password (fallback for emergency)
   mkdir -p ~/.ssh && chmod 700 ~/.ssh
   ```

4. **Add Iddo's pubkey** to `~/.ssh/authorized_keys`. Two options:
   - **Iddo dictates** the pubkey over WA voice and parent types it (long, error-prone — avoid)
   - **Iddo sends** the pubkey via WA chat as a code block, parent long-presses → copy → in Termux: `echo "<paste>" >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys`
   - **Cleanest**: Iddo posts the pubkey to a private gist, parent runs `curl -fsSL <gist-raw-url> >> ~/.ssh/authorized_keys`

   Iddo's pubkey to deploy:
   ```
   ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJcQGzefFRBOX7AfrO/qA7tPLzrPg1rEx+Q6LeIaqId0 iddo@openclaw-pi3
   ```

5. **Auto-start sshd at boot** (Termux:Boot script):
   ```bash
   mkdir -p ~/.termux/boot
   cat > ~/.termux/boot/start-sshd <<'EOF'
   #!/data/data/com.termux/files/usr/bin/sh
   termux-wake-lock
   sshd
   EOF
   chmod +x ~/.termux/boot/start-sshd
   ```
   Termux:Boot must be opened once after install for the script to fire on next reboot.

6. **Tailscale install** (separate app, not Termux):
   - Play Store: https://play.google.com/store/apps/details?id=com.tailscale.ipn
   - Iddo magic-link-joins each phone to his tailnet from his admin console (https://login.tailscale.com/admin/machines)
   - On phone: Settings → Connections → More connection settings → VPN → Tailscale gear → "Always-on VPN" + "Block connections without VPN" OFF (don't block, only force-on)

7. **Verify from PC** (one round trip after each phone is provisioned):
   ```bash
   ssh -p 8022 -o ConnectTimeout=3 u0_a<NNN>@<phone-tailscale-ip> 'hostname; whoami; uname -a'
   ```

   To find the phone's Tailscale IP after install: `tailscale status` from this PC will list the new device.
   To find the Termux user (`u0_a<NNN>` varies per phone): on the phone in Termux: `whoami`.

**Lower-friction alternative (if mom/dad balk at Termux)**: SimpleSSHD app from F-Droid is a single-purpose APK with a UI — start/stop button, port + authorized_keys field. Less power than Termux but trivial to walk through. Default port 2222 (will conflict with the localhost:2222 entry currently in known_hosts — change to 8022).

---

## 6. Files written this session

- This status doc: `D:\CLAUDE\tools\ssh-comms-triage\ssh-status-2026-04-30.md`
- A30 walkthrough: `D:\CLAUDE\tools\ssh-comms-triage\a30-usb-debug-walkthrough.md`
- Mibox gh refresh helper: `D:\CLAUDE\tools\ssh-comms-triage\mibox-gh-auth-refresh.sh`
- A70 setup script (also pushed to A70 /sdcard): `D:\CLAUDE\tools\ssh-comms-triage\a70-termux-ssh-setup.sh`
- A70 pubkey copy on phone: `/sdcard/iddo-pubkey.pub` (on A70 device)
