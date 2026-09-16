#!/data/data/com.termux/files/usr/bin/bash
# phone-setup.sh — run ON THE PHONE (Termux, SM-S948B) by claude-cli-PHONE-CLI, 2026-09-03.
# Idempotent. Installs the shell tools Claude Code expects, writes config, a doctor script, QoL.
# Never touches PHONE-LLM's llama.cpp build or model files. Never logs in to Claude.
set -u
export DEBIAN_FRONTEND=noninteractive
P="$PREFIX"
H="$HOME"
say() { printf '\n### %s\n' "$*"; }

say "0. identity"
echo "user=$(whoami) home=$H prefix=$P arch=$(uname -m) android=$(getprop ro.build.version.release 2>/dev/null)"
echo "termux-info: $(termux-info 2>/dev/null | grep -A1 'TERMUX_VERSION' | tail -1)"

say "1. pkg install (waits on the apt lock if another agent holds it — never kills)"
PKGS="python jq tmux nano tree file wget which curl termux-api"
ok=0
for i in $(seq 1 45); do
  out=$(pkg install -y $PKGS 2>&1); rc=$?
  if [ $rc -eq 0 ]; then ok=1; echo "$out" | tail -4; break; fi
  if echo "$out" | grep -qiE 'could not get lock|unable to acquire|unable to lock|lock-frontend'; then
    echo "apt/dpkg lock held (attempt $i/45) — waiting 20s"; sleep 20
  else
    echo "pkg install failed (rc=$rc), not a lock:"; echo "$out" | tail -25; break
  fi
done
[ $ok -eq 1 ] && echo "PKG_INSTALL_OK" || echo "PKG_INSTALL_FAILED"

say "2. versions"
for c in python python3 pip git rg jq curl wget tmux nano tree which file ssh node npm; do
  if command -v "$c" >/dev/null 2>&1; then
    v=$("$c" --version 2>&1 | head -1)
    printf '%-8s %s\n' "$c" "$v"
  else
    printf '%-8s MISSING\n' "$c"
  fi
done

say "3. shebang test (#!/usr/bin/env python3), with and without termux-exec LD_PRELOAD"
mkdir -p "$H/bin" "$H/claude-work" "$H/.claude" "$H/.ssh" "$H/.termux" "$H/.shortcuts"
cat > "$H/bin/shebang-test" <<'EOF'
#!/usr/bin/env python3
print("shebang-env-python3 OK")
EOF
chmod +x "$H/bin/shebang-test"
echo -n "with preload:    "; "$H/bin/shebang-test" 2>&1 | head -1
echo -n "without preload: "; env -u LD_PRELOAD "$H/bin/shebang-test" 2>&1 | head -1
echo "LD_PRELOAD=$LD_PRELOAD"
echo "termux-exec pkg: $(dpkg -s termux-exec 2>/dev/null | grep Version)"

say "4. phone ssh key (new; nothing copied from the PC)"
if [ ! -f "$H/.ssh/id_ed25519" ]; then
  ssh-keygen -t ed25519 -f "$H/.ssh/id_ed25519" -N "" -C phone-s948b -q && echo "generated"
else
  echo "already exists"
fi
chmod 700 "$H/.ssh"; chmod 600 "$H/.ssh/id_ed25519"
cat > "$H/.ssh/config" <<'EOF'
# DGX fleet from the phone (LAN first; -ts = Tailscale). eran3 only via eran2.
Host eran1
  HostName <lan-ip>
  User eran1
Host eran2
  HostName <lan-ip>
  User eran2
Host eran4
  HostName <lan-ip>
  User eran4
Host eran3
  HostName <fabric-ip>
  User eran3
  ProxyJump eran2
Host eran1-ts
  HostName <tailnet-ip>
  User eran1
Host eran2-ts
  HostName <tailnet-ip>
  User eran2
Host eran4-ts
  HostName <tailnet-ip>
  User eran4
Host *
  IdentityFile ~/.ssh/id_ed25519
  IdentitiesOnly yes
  ServerAliveInterval 30
  ConnectTimeout 8
  StrictHostKeyChecking accept-new
EOF
chmod 600 "$H/.ssh/config"
echo "PUBKEY_BEGIN"; cat "$H/.ssh/id_ed25519.pub"; echo "PUBKEY_END"

say "5. ~/.claude/settings.json (no permission bypass)"
if [ -f "$H/.claude/settings.json" ]; then cp "$H/.claude/settings.json" "$H/.claude/settings.json.bak-$(date +%Y%m%d%H%M%S)"; echo "backed up existing"; fi
cat > "$H/.claude/settings.json" <<'EOF'
{
  "permissions": {
    "defaultMode": "default",
    "allow": [
      "Read",
      "Grep",
      "Glob",
      "Bash(git status:*)",
      "Bash(git diff:*)",
      "Bash(git log:*)",
      "Bash(ls:*)",
      "Bash(cat:*)",
      "Bash(ssh eran1 *)",
      "Bash(ssh eran2 *)",
      "Bash(ssh eran4 *)"
    ],
    "deny": [
      "Bash(rm -rf /*)",
      "Bash(pkg upgrade:*)",
      "Bash(apt upgrade:*)",
      "Bash(claude-update:*)"
    ]
  },
  "env": {
    "DISABLE_AUTOUPDATER": "1",
    "USE_BUILTIN_RIPGREP": "0",
    "LANG": "en_US.UTF-8"
  }
}
EOF
python -c "import json;json.load(open('$H/.claude/settings.json'));print('settings.json valid JSON')"

say "6. ~/claude-work/CLAUDE.md"
cat > "$H/claude-work/CLAUDE.md" <<'EOF'
# CLAUDE.md — Claude Code on Iddo's phone (Termux)

## Where you are
- Termux (GitHub build 0.119.x) on Iddo's Samsung S948B, Android 16, arm64. No root.
- `claude` is a bash wrapper that runs the official linux-arm64 binary through Termux's
  glibc loader (`unset LD_PRELOAD`, then `$PREFIX/glibc/lib/ld-linux-aarch64.so.1`).
  `DISABLE_AUTOUPDATER=1` — updates only via `claude-update`, never on their own.
- Tools: python3/pip, git, rg, jq, curl, wget, tmux, nano, tree, file, ssh. All bionic (Termux) builds.
- NO GPU, ~12 GB RAM shared with the OS. This phone runs INFERENCE only — never train anything here.
  A separate on-device llama.cpp + GGUF model may live in the home dir (built by another agent):
  do not delete or rebuild it.
- Battery: long jobs need `termux-wake-lock` (the widget script does it). Prefer tmux for anything >1 min.

## Reaching the DGX fleet (key auth, ~/.ssh/config already set)
- `ssh eran1` (<lan-ip>) — ERAN himself lives here (eranb-life, :8820). NEVER restart eranb-life.
- `ssh eran2` (<lan-ip>)  — the senses (:8830), SHAMASH librarian (:8850), fabric hub.
- `ssh eran4` (<lan-ip>)   — Darwish/MIDI (:8806) + audio.
- `ssh eran3` — no LAN of its own; ProxyJump through eran2 to <fabric-ip>.
- Off-LAN: eran1-ts / eran2-ts / eran4-ts (Tailscale <tailnet-ip> / <tailnet-ip> / <tailnet-ip>).
- Heavy compute belongs on the fleet, not on this phone.

## The PC (Iddo's Windows box, D:\CLAUDE)
- LAN <lan-ip>. RAMCHAT (the team's shared memory / work queue) lives there at D:\CLAUDE\RAMCHAT
  and is reachable only while the PC is on. The PC's sshd service is installed but STOPPED —
  there is no ssh into the PC unless Iddo starts it. Other agents (Claude Desktop, other Claude
  Code sessions, Codex, Grok, Gemini) coordinate through RAMCHAT; if you cannot reach it, say so
  in your report instead of pretending you posted.

## Laws that bind here
- SACRED AUDIO: never touch Iddo's audio — no playing, recording, muting, or Bluetooth mic use.
  The Bluetooth headset is never a microphone.
- No training on the phone (or the PC). Inference only. Training runs on the DGX fleet.
- Broken Windows: if something is broken, fix it now and test the REAL output, not a proxy.
- Never log in, accept terms, or type credentials on Iddo's behalf. Never reboot the phone.
- Say plainly and early when something is beyond reach.

## How to talk to Iddo
- Answer Iddo in HEBREW. Short. Simple. Evidence first, no overselling.
- Call him Iddo. Do not mother him.
EOF
wc -l "$H/claude-work/CLAUDE.md"

say "7. Termux QoL: termux.properties extra-keys, .bashrc, widget wake-lock"
TP="$H/.termux/termux.properties"
[ -f "$TP" ] && cp "$TP" "$TP.bak-$(date +%Y%m%d%H%M%S)"
{ [ -f "$TP" ] && grep -vE '^\s*extra-keys' "$TP"; echo "extra-keys = [['ESC','/','-','|','HOME','UP','END'],['TAB','CTRL','ALT','PGUP','LEFT','DOWN','RIGHT']]"; } > "$TP.new" && mv "$TP.new" "$TP"
grep extra-keys "$TP"
termux-reload-settings 2>&1 && echo "termux-reload-settings sent"

BRC="$H/.bashrc"
touch "$BRC"
if ! grep -q 'claude-cli-PHONE-CLI' "$BRC"; then
cat >> "$BRC" <<'EOF'

# --- claude-cli-PHONE-CLI 2026-09-03: Claude Code on the phone ---
export LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8
export DISABLE_AUTOUPDATER=1 USE_BUILTIN_RIPGREP=0
export PATH="$HOME/bin:$PATH"
alias c='claude'
alias doctor='claude-doctor'
# keep the door open for the PC while Termux is up (key auth only, no passwords)
pgrep -x sshd >/dev/null 2>&1 || sshd 2>/dev/null
# start in the work dir on a fresh interactive shell
case "$-" in *i*) [ "$PWD" = "$HOME" ] && cd "$HOME/claude-work" 2>/dev/null ;; esac
# --- end claude-cli-PHONE-CLI ---
EOF
echo ".bashrc block appended"
else echo ".bashrc block already present"; fi
# Termux login shell reads ~/.bash_profile (or ~/.profile); make sure .bashrc gets sourced
if [ ! -f "$H/.bash_profile" ] && [ ! -f "$H/.profile" ]; then
  printf '[ -f ~/.bashrc ] && . ~/.bashrc\n' > "$H/.bash_profile"; echo ".bash_profile created (sources .bashrc)"
else
  for f in "$H/.bash_profile" "$H/.profile"; do [ -f "$f" ] && grep -q bashrc "$f" && echo "$f already sources .bashrc"; done
fi
grep -c 'PasswordAuthentication' "$P/etc/ssh/sshd_config" >/dev/null && grep -E '^(PasswordAuthentication|PubkeyAuthentication)' "$P/etc/ssh/sshd_config"

WS="$H/.shortcuts/claude.sh"
if [ -f "$WS" ]; then
  echo "--- existing widget:"; cat "$WS"
  cp "$WS" "$WS.bak-$(date +%Y%m%d%H%M%S)"
fi
cat > "$WS" <<'EOF'
#!/data/data/com.termux/files/usr/bin/bash
# Termux:Widget entry — starts Claude Code with a wake-lock so the session survives the screen going off.
termux-wake-lock
export DISABLE_AUTOUPDATER=1 USE_BUILTIN_RIPGREP=0 LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8
export PATH="$HOME/bin:$PATH"
pgrep -x sshd >/dev/null 2>&1 || sshd 2>/dev/null
mkdir -p "$HOME/claude-work" && cd "$HOME/claude-work"
if command -v tmux >/dev/null 2>&1; then
  exec tmux new-session -A -s claude claude
else
  exec claude
fi
EOF
chmod +x "$WS"; echo "widget written: $WS"

say "8. ~/bin/claude-doctor"
cat > "$H/bin/claude-doctor" <<'EOF'
#!/data/data/com.termux/files/usr/bin/bash
# claude-doctor — one screen of truth about Claude Code on this phone.
export DISABLE_AUTOUPDATER=1
echo "== claude-doctor  $(date '+%Y-%m-%d %H:%M:%S')  $(getprop ro.product.model 2>/dev/null) android $(getprop ro.build.version.release 2>/dev/null)"
printf 'claude   : %s\n' "$(timeout 30 claude --version 2>&1 | head -1)"
auth=$(timeout 30 claude auth status 2>&1 | head -3 | tr '\n' ' ')
if echo "$auth" | grep -qiE 'unknown command|error: unknown|not a command'; then
  auth=$(timeout 45 claude -p ping 2>&1 | head -1)
fi
printf 'login    : %s\n' "${auth:-(no answer)}"
printf 'node     : %s\n' "$(node --version 2>&1 | head -1)"
printf 'python   : %s\n' "$(python --version 2>&1 | head -1)"
printf 'git      : %s\n' "$(git --version 2>&1 | head -1)"
printf 'rg       : %s\n' "$(rg --version 2>&1 | head -1)"
printf 'sshd     : %s\n' "$(pgrep -x sshd >/dev/null && echo running :8022 || echo not running)"
for h in eran1 eran2 eran4; do
  r=$(ssh -o BatchMode=yes -o ConnectTimeout=2 "$h" hostname 2>&1 | head -1)
  if ssh -o BatchMode=yes -o ConnectTimeout=2 "$h" true 2>/dev/null; then printf 'ssh %-5s: OK (%s)\n' "$h" "$r"; else printf 'ssh %-5s: FAIL (%s)\n' "$h" "$r"; fi
done
printf 'RAM      : %s\n' "$(free -m | awk '/Mem:/{printf "%d MB free of %d MB", $7, $2}')"
printf 'storage  : %s\n' "$(df -h "$HOME" | awk 'NR==2{printf "%s free of %s (%s used)", $4, $2, $5}')"
printf 'wakelock : %s\n' "$(command -v termux-wake-lock >/dev/null && echo available || echo MISSING)"
EOF
chmod +x "$H/bin/claude-doctor"
ls -la "$H/bin/claude-doctor"

say "9. Hebrew README"
cat > "$H/claude-work/README.txt" <<'EOF'
Claude Code על הטלפון — איך מתחילים
====================================

1. פותחים Termux (או לוחצים על הווידג'ט "claude").
2. כותבים:   claude        (או בקיצור:  c )
3. בפעם הראשונה בלבד — להתחבר:
      בתוך claude כותבים  /login
      נפתח דפדפן, מאשרים את החשבון, חוזרים ל-Termux. פעם אחת וזהו.
4. בדיקת מצב בכל רגע:   claude-doctor

המחשבים של הצי (מפתח כבר מותקן, בלי סיסמה):
      ssh eran1     ← ערן עצמו (<lan-ip>). לא להפעיל מחדש שום דבר שם.
      ssh eran2     ← החושים (<lan-ip>)
      ssh eran4     ← דרוויש (<lan-ip>)
      (מחוץ לבית: eran1-ts / eran2-ts / eran4-ts דרך Tailscale)

טיפים:
- מקשי ESC וחצים נמצאים בשורת המקשים הנוספת מעל המקלדת.
- כשהמסך כבה הסשן נשאר חי (הווידג'ט מפעיל wake-lock).
- tmux: אם התנתקת,  tmux attach  מחזיר את אותו מסך.
- הטלפון מריץ רק inference. אימונים — רק על הצי.
EOF
ls -la "$H/claude-work/README.txt"

say "10. claude wrapper sanity"
echo "wrapper: $(command -v claude)"; head -20 "$(command -v claude)" 2>/dev/null
echo "claude --version: $(timeout 30 claude --version 2>&1 | head -1)"

say "DONE phone-setup.sh"
