# AudioWatchdog

**Problem:** The Quad Cortex guitar pedal (NeuralDSP, USB VID 152A/PID 880A) keeps stealing the Windows "Default Communications" audio role from the Focusrite Scarlett Solo USB (VID 1235/PID 8205). When this happens, Discord, WhatsApp, and Teams go silent because they use the Communications device, not the Default Playback device.

**Root cause:** Windows treats every new USB audio device as a candidate for the Default Communications role. When the Quad Cortex is plugged in (or reconnects after a USB power cycle), Windows promotes it to Default Communications. No Focusrite or NeuralDSP software was found actively claiming the role — the switching is done silently by Windows' own plug-and-play audio policy.

---

## What the watchdog does

`audio_watchdog.ps1` runs as a background PowerShell process (hidden window) that:

1. **Checks every 30 seconds** whether the following devices hold the correct roles:
   - **Render Console** → Speakers (Scarlett Solo USB)
   - **Render Multimedia** → Speakers (Scarlett Solo USB)
   - **Render Communications** → Speakers (Scarlett Solo USB)
   - **Capture Communications** → Microphone (Scarlett Solo USB)

2. **Auto-corrects** any wrong assignment using the undocumented but stable Windows `IPolicyConfig` COM interface — the same mechanism used by tools like SoundVolumeView and NirCmd.

3. **Logs every correction** (and startup events) to `audio_watchdog.log` in this folder:
   ```
   [2026-05-02 20:13:32] [FIX] FIXED Render/Communications: was '{0.0.0.00000000}.{QUAD-GUID}' -> set to 'Speakers (Scarlett Solo USB)'
   ```

4. **Skips correction if the Scarlett is not plugged in** — prevents it from trying to set a disconnected device as default.

---

## How it's installed

Two complementary mechanisms ensure the watchdog starts at login:

| Mechanism | Location | Details |
|-----------|----------|---------|
| Scheduled Task | Task Scheduler → `AudioWatchdog` | `SC MINUTE /MO 1` — fires every minute, `IgnoreNew` if already running |
| Registry Run key | `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\AudioWatchdog` | Starts the script at user logon |

The watchdog itself runs an infinite `while ($true) { Start-Sleep 30; Check }` loop, so one process covers continuous 30-second monitoring.

---

## Device GUIDs (this machine)

| Device | Role | GUID |
|--------|------|------|
| Speakers (Scarlett Solo USB) | Default Playback + Communications | `{0.0.0.00000000}.{2a19ecc6-16d2-4348-871d-5ad0bac2fe1a}` |
| Microphone (Scarlett Solo USB) | Default Communications Capture | `{0.0.1.00000000}.{9e858882-3bd6-4be0-bb70-f066846c47e5}` |

---

## Stop / restart / uninstall

**Stop the watchdog:**
```powershell
Stop-ScheduledTask -TaskName AudioWatchdog
Get-Process powershell | Where-Object { $_.CPU -gt 0 } | Stop-Process  # or use Task Manager
```

**Restart it:**
```powershell
Start-ScheduledTask -TaskName AudioWatchdog
```

**Temporarily disable (survives reboot):**
```powershell
Disable-ScheduledTask -TaskName AudioWatchdog
Remove-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name 'AudioWatchdog'
```

**Uninstall completely:**
```powershell
Stop-ScheduledTask -TaskName AudioWatchdog -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName AudioWatchdog -Confirm:$false
Remove-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name 'AudioWatchdog' -ErrorAction SilentlyContinue
```

**Re-install from scratch:**
```powershell
# Run as the target user (not required to be admin)
schtasks /Create /TN AudioWatchdog /TR 'powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "D:\CLAUDE\tools\audio-watchdog\audio_watchdog.ps1"' /SC MINUTE /MO 1 /F
Set-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name 'AudioWatchdog' -Value 'powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "D:\CLAUDE\tools\audio-watchdog\audio_watchdog.ps1"'
Start-ScheduledTask -TaskName AudioWatchdog
```

---

## Files

| File | Purpose |
|------|---------|
| `audio_watchdog.ps1` | Main watchdog script (runs forever) |
| `install_watchdog.ps1` | Admin installer (if you ever have elevation) |
| `_install_task.ps1` | Non-admin installer helper used during setup |
| `audio_watchdog.log` | Auto-created; logs all corrections and startup events |
| `README.md` | This file |

---

*Diagnosed and installed 2026-05-02. Prior diagnosis: `D:/CLAUDE/FOCUSRITE_AUDIO_FIX_2026-04-29.md`*
