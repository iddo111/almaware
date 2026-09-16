# Galaxy Tab A7 — Linux Plan

Written 2026-08-06. No hedging. Odds are stated where they matter.

---

## What the tablet actually is

**Unknown. We never saw it.** ADB is empty, and more than that: Windows has **never** seen a
Galaxy Tab on this machine. I dumped the full USB history (`HKLM\SYSTEM\CurrentControlSet\Enum\USB`)
— no SM-T500, no SM-T505, no SM-T220, no SM-T225, ever. The only Samsungs this box has ever
touched are `R58MC0KVS0X` (your A70), `RFCW31V1QAV`, and an S23. So this is a first connection,
not a regression.

**Go read this off the tablet right now — Settings > About tablet > Model number** (also printed
small on the back). It takes 10 seconds and it decides everything:

| You read | It is | SoC | Flash tool | Verdict |
|---|---|---|---|---|
| `SM-T500` / `T505` / `T507` | Tab A7 10.4 (2020), `gta4lwifi` / `gta4l` | Snapdragon 662 (SM6115) | Odin / Heimdall / samloader | LineageOS 23.2 **officially supported**. Good device. |
| `SM-T220` / `T225` / `T227U` | Tab A7 **Lite** (2021), `gta7lite*` | MediaTek MT8768T | mtkclient / BROM | Different world. No Lineage. pmOS port archived 2026-06-22. Worse in every direction. |

Also note the firmware version (Settings > About > Software information > Android version).
For the T500/T505 the ceiling is **Android 12 / One UI Core 4.1**, and LineageOS *requires*
you to be on stock Android 12 before installing. If it's on 11, update first.

One good piece of news: this tablet tops out below One UI 8. Samsung removed bootloader
unlocking **from the bootloader itself** in One UI 8 (2025), globally, no workaround. The Tab A7
will never get One UI 8, so it's grandfathered. If you're ever going to unlock a Samsung, this
device and this year is the window.

---

## Can it run bare-metal Linux?

# NO.

Not "difficult". Not "needs work". The drivers do not exist. Here is exactly what's missing.

There is **no postmarketOS device port for the Tab A7. None. Never was.** I enumerated all 1,456
package directories in pmaports — main (3), community (105), testing (323), downstream (48),
archived (977). Grep for `gta` returns four hits and not one is `gta4l`. Category: NONEXISTENT.

The entire global effort is **one person** — `V6lhost` at github.com/LinuxForGta4l, org created
2025-12-14, repos with 0–2 stars. His mainline kernel branch is Linux 7.0-rc1 plus **exactly four
device commits**, all February 2026. I read the device tree
(`sm6115-samsung-gta4l.dts`). This is what it actually enables:

| Hardware | Status |
|---|---|
| Display | `simple-framebuffer` only — the bootloader splash. No DSI, no panel driver, no backlight. |
| Touchscreen | `himax_ts` → `status = "disabled"`, under a node commented *"Hack for passing bootloader checks"*. **Dead.** |
| WiFi | no node at all. **Dead.** |
| Bluetooth / Audio / GPU | no nodes. **Dead.** |
| Internal eMMC (`sdhc_1`) | `disabled` — and the newest commit is literally *"Disable EMMC back"*. **You cannot install to internal storage.** |
| microSD (`sdhc_2`) | works. Your only storage. |
| USB, UART4 | work. Your only interface. |
| Battery / charging | no fuel gauge, no charger node. No charge management. |

Upstream Linux knows **two** SM6115 boards total — `sm6115-fxtec-pro1x` and
`sm6115p-lenovo-j606f`. That's the whole population. pmOS's own `linux-postmarketos-qcom-sm6115`
was archived unmaintained on 2026-06-22.

So mainline bare metal = a frozen splash screen, no touch, no wifi, no sound, no internal
storage, booting off an SD card with a serial cable as your console. **And you said headless.**
Headless kills the case for bare metal completely, because the only two things headless
actually needs — **WiFi and storage** — are exactly the two things mainline doesn't have.
A node with no network and no disk is not a node.

Odds, straight:

| Goal | Odds |
|---|---|
| pmOS mainline boots to a shell over serial | ~50% |
| pmOS mainline as a usable tablet | ~0% |
| pmOS mainline as a headless node | **~0%** — no wifi, no storage |
| pmOS *downstream* branch (4.19 vendor kernel, touch works) boots | ~35%, unproven, one maintainer, zero docs |
| LineageOS 23.2 installed and daily-usable | **90%**, given OEM unlock |
| Termux + proot + Tailscale headless node | **~99%**, one evening, zero risk |

The interesting bare-metal option, if you want it later, is **not** mainline — it's the
`downstream` branch of `LinuxForGta4l/postmarketos-packages-gta4l`, which uses the LineageOS
4.19 vendor kernel and ships actual touchscreen firmware. Even the guy who wrote the mainline
DTS defaults people to downstream. Park that. It needs `uniLoader`/`lk2nd` because Samsung
bootloaders don't speak fastboot, and it's an un-upstreamed shim layer on top of everything else.

---

## Fix ADB first

Nothing below is executable until the tablet shows up. And this is **not** an adb problem, not a
driver problem, not an authorization problem. Diagnosis:

- `adb devices` → empty, daemon restarts clean. adb is fine (1.0.41 / 37.0.1-15733141).
- Samsung drivers: **v2.21.4.0, WHQL, installed 04/08/2026** — four INF packages live in the
  driver store (`ssudbus`, `ssudadb`, `ssudmdm`, `ssudrnds`). **Do not reinstall drivers. Waste of time.**
- `Get-PnpDevice -PresentOnly` → **zero** `VID_04E8` devices. 18 USB devices present, none Samsung.
- No yellow bang. No "Unknown USB Device". No "Device Descriptor Request Failed".

That combination means one thing: **Windows never received a USB attach event.** Debugging OFF
would still enumerate as MTP. A missing driver would show a yellow bang. An unaccepted prompt
would show `unauthorized`. Nothing at all = cable, port, or power.

Do these in order:

1. **Swap the cable.** ~90% this is it. Charging proves the power pins work, *not* the data pins —
   most bundled/cheap USB-C cables have no data pairs. Use a cable you have personally moved files
   with. Your own `D:\CLAUDE\archive\odin\BOM.md` already flags this exact risk.
2. **Rear motherboard USB-A port, direct.** This box has four Genesys `VID_05E3` hubs live. Get off
   the hub and off the front panel.
3. **Tablet powered on and unlocked at the home screen.** adb is blocked before first unlock after
   a cold boot.
4. **Pull down the notification shade → "Charging this device via USB" → File Transfer.**
   *If that notification never appears, the data lines are dead. Go back to step 1.*
5. **Re-enable debugging:** Settings > About tablet > Software information > tap **Build number** 7×.
   Then Developer options > **USB debugging** ON. Also tap **Revoke USB debugging authorizations**
   to force a fresh prompt.
6. **Accept the on-tablet dialog** — "Allow USB debugging?" → tick *Always allow from this computer* → Allow.

Then, in PowerShell:

```powershell
$adb = "C:\Users\<user>\AppData\Local\Microsoft\WinGet\Packages\Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe\platform-tools\adb.exe"
& $adb kill-server
& $adb devices -l
```

Check the bus directly if it's still empty — this is the real test, not `adb devices`:

```powershell
Get-PnpDevice -PresentOnly | Where-Object InstanceId -like "*VID_04E8*" | Format-Table Status,Class,FriendlyName
```

You should see `PID_6860` (MTP+ADB) or `PID_6864` (RNDIS+ADB) — that's what your Samsungs
historically enumerate as. Download/Odin mode is `PID_685D`.

**Two ways to skip the cable entirely:**

- **Read the model number off the screen** (§1). Costs nothing, decides everything.
- **Wireless debugging** (Android 11+). You've done network adb before — the A70 ran
  `adb-R58MC0KVS0X._adb-tls-connect._tcp`. Developer options > Wireless debugging > Pair device
  with pairing code:

```powershell
& $adb pair 192.168.1.xx:PORT_FROM_PAIRING_SCREEN
& $adb connect 192.168.1.xx:PORT_FROM_MAIN_SCREEN
```

That gets you every `getprop` with no cable at all.

Once it's visible, these three values decide the rest:

```powershell
& $adb shell getprop ro.product.model
& $adb shell getprop ro.boot.flash.locked        # 1 = locked, 0 = unlocked
& $adb shell getprop ro.boot.verifiedbootstate   # green = locked, orange = unlocked
& $adb shell getprop ro.build.version.release
```

And then check by eye: Developer options > is **OEM unlocking** present and not greyed out?
**That toggle, not the flashing, is where this lives or dies.** It's what killed the A30 —
`OEM LOCK = ON(L)`, `WARRANTY VOID = 0x0`, Chimera failed, phone ended up stuck in an EUB shell,
and your `pmos-a30-AP.tar.md5` (a genuine self-built 31 MB pmOS boot.img) was never flashable.
US-market Samsungs never ship that toggle and there is no workaround. Non-US: ~85% it's there.
If it's missing but you're on a non-US SKU, it may be RMM/KG "prenormal" — sign into WiFi with a
Samsung/Google account and wait up to 7 days before calling it dead.

---

## The path I recommend

**Termux + proot Debian + sshd + Tailscale.** Zero risk, no unlock, no drivers, works this week,
and it gives you exactly the headless aarch64 node you asked for — with a 7040 mAh built-in UPS.
~99%.

Get Termux from **F-Droid or GitHub releases — NOT the Play Store** (the Play version is ancient
and broken). You already have `termux-stable.apk` at
`D:\CLAUDE\archive\a30-hack\downloads\termux-stable.apk` and the addons at
`D:\CLAUDE\archive\a30-linux-2026-05-08\apks\`.

```powershell
& $adb install D:\CLAUDE\archive\a30-hack\downloads\termux-stable.apk
& $adb install D:\CLAUDE\archive\a30-linux-2026-05-08\apks\termux-boot.apk
& $adb install D:\CLAUDE\archive\a30-linux-2026-05-08\apks\termux-api.apk
```

On the tablet, in Termux:

```bash
pkg update -y && pkg upgrade -y
pkg install -y openssh proot-distro tmux termux-api nano
proot-distro install debian

# ssh key instead of a password
mkdir -p ~/.ssh && chmod 700 ~/.ssh
nano ~/.ssh/authorized_keys      # paste your pubkey
chmod 600 ~/.ssh/authorized_keys

sshd                              # Termux sshd listens on 0.0.0.0:8022
termux-wake-lock
whoami                            # note this — it's your ssh username
```

Autostart on boot (Termux:Boot must have been launched once):

```bash
mkdir -p ~/.termux/boot
cat > ~/.termux/boot/start-node <<'EOF'
#!/data/data/com.termux/files/usr/bin/sh
termux-wake-lock
sshd
EOF
chmod +x ~/.termux/boot/start-node
```

Then install the **Tailscale** Android app and sign in. The tailnet IP is a normal interface, so
from anywhere:

```bash
ssh -p 8022 <termux-user>@<tailnet-ip>
proot-distro login debian
```

**Three things will silently kill this. Fix all three.**

1. **Android 12+ phantom process killer** — Android murders an app's forked children past 32.
   This is *the* reason Termux background services die. Needs adb once (so: cable first):

```powershell
& $adb shell settings put global settings_enable_monitor_phantom_procs false
& $adb shell /system/bin/device_config set_sync_disabled_for_tests persistent
& $adb shell /system/bin/device_config put activity_manager max_phantom_processes 2147483647
```

On Android 13+ the `settings put` form persists across reboots. On Android 12 the `device_config`
lines must be reapplied every boot — script it.

2. **Samsung One UI battery killer** — Settings > Battery > Background usage limits >
   **turn OFF "Put unused apps to sleep"**. Set Termux and Tailscale to **Unrestricted**.
   Samsung is far more aggressive than stock Android and will kill sshd overnight.
3. **Screen off ≠ running.** `termux-wake-lock` is not optional.

**What proot can't do, so you're not surprised later:** no Docker/cgroups, no kernel modules,
no raw sockets without root, ~10–30% overhead on syscall-heavy work, and `/proc` is partly faked.
For an ssh box, a build node, a Python/Node runner, a monitoring endpoint — none of that matters.

### If you want more than that — and the OEM unlock toggle exists

Then the real win on this hardware is **LineageOS 23.2** (Android 16), *officially* supported for
both `gta4lwifi` (SM-T500) and `gta4l` (SM-T505/T505C/T505N/T507), maintainer **chrmhoffmann**,
device tree pushed 2026-05-12, kernel pushed 2026-05-22. Everything works: display, touch, WiFi,
BT, audio, camera, GPU, battery, LTE. Then put Termux on top of *that* and you have full hardware
**and** the Linux node, no compromise.

Sequence (from the official LineageOS gta4lwifi install guide — follow it, not me, at flash time):

1. Be on **stock Android 12**. Non-negotiable prerequisite for Lineage on this device.
2. Developer options > **enable OEM unlocking**.
3. Power off. Hold **Vol Down + Vol Up**, *then* plug in USB → download mode.
4. Press the on-screen **"Unlock Bootloader"** button. → **THIS IS THE POINT OF NO RETURN.**
   It wipes userdata and it **trips the Knox e-fuse to 0x1, permanently, in hardware.**
5. Boot up, re-enter Developer options, **verify OEM unlocking is still ON.** Do not skip this.
   If vbmeta gets flashed with it off, you're stuck.
6. `samloader flash --partition VBMETA vbmeta.img` (disables Android Verified Boot). You already
   have samloader installed — the martinetd fork.
7. Factory reset, run setup, **verify OEM unlocking is still on** again.
8. `samloader flash --partition RECOVERY recovery.img --no-reboot`, then **immediately** boot to
   recovery (Vol Up + Power). Stock will overwrite it if you boot normally.
9. Sideload the Lineage zip from recovery.

**Take the partition backup you never took on the A30.**
`D:\CLAUDE\archive\a30-toolkit\backups\partitions\` is empty — that's the one thing that went
wrong last time that was entirely in your control. Before step 4:

```powershell
& $adb shell getprop | Out-File -Encoding utf8 D:\CLAUDE\tab-a7-linux\getprop-before.txt
```

And download the exact stock firmware for **your** model + region with samloader **before** you
unlock, not after. Odin 3.14.4 is already at `D:\CLAUDE\archive\odin\Odin3_v3.14.4.exe` and it
works. (The `Odin3_v3.14.4.zip` copies under `a305f-recovery\tools\` are broken 431-byte stubs —
ignore those.)

---

## What could go wrong and how to undo it

**Reversible — all of it, except one thing.**

| Action | Reversible? | How |
|---|---|---|
| Termux + proot + Tailscale | Trivially | Uninstall the app |
| adb `device_config` phantom tweaks | Yes | Reboot, or set them back |
| Bootloader unlock | Yes (relock via Odin stock flash) | But see Knox below |
| **Knox e-fuse trip (0x1)** | **NO. NEVER. Hardware.** | Nothing. Not Odin, not Samsung service. |
| Flashing Lineage / pmOS | Yes | Odin + stock `.tar.md5` set |
| Soft-brick / bootloop | Yes | Download mode + Odin |

**Knox, precisely:** unlocking trips a physical fuse. `WARRANTY VOID = 0x1` forever, even after a
full stock reflash. What actually dies: Samsung Pay, Secure Folder, Samsung Health data,
Samsung Pass, Netflix/DRM HD playback, and enterprise/MDM features. On a 2020 tablet you're using
as a hack target, that costs you nothing real, and the warranty expired years ago.

**Knox does NOT block reflashing.** Your instinct — "we just put the image back" — is correct for
this device. Odin restore works fine post-Knox-trip.

**The stock restore, concretely:**

1. Get the exact firmware for **your** model + region with samloader *before* you touch anything.
   For the A30 you already did this — 4.09 GB, decrypted, `BL/AP/CP/CSC/HOME_CSC .tar.md5` split
   out. Same drill. Keep it on D:.
2. Odin 3.14.4 → `D:\CLAUDE\archive\odin\Odin3_v3.14.4.exe`.
3. Tablet into **download mode**: power off, Vol Down + Vol Up, then plug in USB.
4. Odin must show a **COM port** in the top-left box. If it doesn't → that's your cable again, or
   the driver, and you must **stop** — never flash without a confirmed COM port.
5. Load BL / AP / CP / CSC into their matching slots. **Use `CSC`, not `HOME_CSC`, if you want a
   full wipe back to factory** (`HOME_CSC` preserves data and can leave a mismatched state).
6. Options tab: **Auto Reboot ON, F. Reset Time ON. Leave Re-Partition OFF** unless you have the
   matching PIT and know why.
7. Start. Do not touch the cable. AP is multi-GB; it takes a while and the progress bar lies.

**The realistic failure modes, ranked:**

1. **The cable never works** → you never get adb. ~10%. Fixed by buying a real data cable.
2. **No OEM unlocking toggle** (US SKU) → bare metal and Lineage are both permanently out.
   ~15% overall, ~100% if it's a US model. The answer is then Termux, forever, and that's fine —
   it does the job you described.
3. **It's a Tab A7 Lite (SM-T220/T225)** → MediaTek, no LineageOS at all, pmOS port archived
   unmaintained 2026-06-22 with a non-working touchscreen. mtkclient/BROM is actually *more*
   forgiving than Knox, but there's nothing good to flash. Termux is the answer there too.
4. **Stuck in download mode / bootloop after a bad flash** → Odin + stock. This is recoverable.
   Being stuck in a *Chimera EUB shell* like the A30 is what happens when you let a paid
   repair-shop tool drive the unlock. **Don't use Chimera on this one.** The Tab A7 unlocks
   natively from download mode with an on-screen button. You don't need a dongle.

**One honest observation.** Looking at the archive: you can build postmarketOS. You did it for the
A30 (real kernel, real 31 MB `boot.img`, correct Odin AP tar) and you did it end-to-end for the
Nexus 4 (pmbootstrap 3.9.0, mainline `linux-stable`, Phosh, 1.5 GB TWRP zip, 2.9 GB rootfs,
bootloader unlocked, TWRP installed). The mako images have been sitting flashable and unflashed
since 2026-05-20 — the runbook literally says *"NOT executed — your call."*

Skill was never the blocker. On the A30 the blocker was Knox. On the Nexus 4 there was no blocker
at all. If you want a bare-metal pmOS win this month, **the Nexus 4 is one command away and it's
already unlocked with TWRP on it.** The Tab A7 will not give you bare metal, because the drivers
don't exist. It will give you a very good headless node tonight, and — if that toggle is there —
Android 16 on a 2020 tablet by the weekend.
