# A30 — Enable USB Debugging Walkthrough

Goal: get `adb devices` on this PC to recognize the A30 so the rest of the toolkit (backup, partition dump, bootloader prep) can run.

Time: ~5 min on the phone, ~30 s of verification on the PC.

---

## On the A30 phone

### Step 1 — Enable Developer options (one-time)

1. Open **Settings**.
2. Scroll to the bottom → tap **About phone**.
3. Tap **Software information** (sub-section).
4. Find **Build number**.
5. Tap **Build number** **7 times** in a row.
   - After 3 taps a small "you're 4 steps away from being a developer" toast appears.
   - After 7 taps: "Developer mode has been enabled" or similar.
   - PIN/pattern may be required mid-sequence — enter it and continue tapping.

### Step 2 — Turn on USB Debugging

1. Back out to **Settings** main page.
2. Scroll down → tap **Developer options** (a new entry, near the bottom).
3. Toggle **Developer options** ON at the top (if not already).
4. Scroll down to **Debugging** section.
5. Toggle **USB debugging** ON.
6. A confirmation dialog asks "Allow USB debugging?" → tap **OK**.

### Step 3 — Connect to the PC and authorize

1. Plug the A30 into the Windows PC with a **data USB cable** (not a charge-only cable — many "spare" cables are charge-only and silently fail this step).
2. On the A30 a popup will appear: **"Allow USB debugging?"** with the PC's RSA fingerprint.
3. Tick **"Always allow from this computer"**.
4. Tap **Allow**.

If the popup doesn't appear, the cable is the prime suspect. Swap to a known-data cable. If still nothing: pull-down notification → "USB for charging" → switch to **File transfer (MTP)** mode → re-plug.

---

## On the PC (verify)

Open PowerShell and run:

```powershell
$adb = "C:\Users\<user>\AppData\Local\Microsoft\WinGet\Packages\Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe\platform-tools\adb.exe"
& $adb devices -l
```

Expected output before A30 is plugged in (current state — A70 connected):
```
<lan-ip>:37275                                  device product:a70qxx model:SM_A705FN device:a70q
adb-R58MC0KVS0X-QEqIr1 (2)._adb-tls-connect._tcp     device product:a70qxx model:SM_A705FN device:a70q
adb-R58MC0KVS0X-QEqIr1._adb-tls-connect._tcp         device product:a70qxx model:SM_A705FN device:a70q
```

After A30 is plugged in and authorized, you'll see one new line:
```
RXXXXXXXXXX             device product:a30* model:SM_A305* device:a30 ...
```
where `RXXXXXXXXXX` is the A30's serial number.

If the new line says `unauthorized` instead of `device`, the popup fingerprint hasn't been accepted yet — unlock the phone, look at the popup, tick "Always allow", tap Allow.

If `adb devices` shows nothing new at all:
1. `& $adb kill-server; & $adb start-server` (resets the daemon).
2. Re-plug the cable.
3. Check the phone's notification shade — sometimes the "Allow" popup hides behind the cable connection notification.

---

## Once authorized, A30 toolkit can resume

Quick smoke-test:

```powershell
& $adb -s <A30-serial> shell getprop ro.product.model
& $adb -s <A30-serial> shell getprop ro.build.version.release
& $adb -s <A30-serial> shell ip addr show wlan0
```

After that the A30 backup + partition dump pipeline (~30 min) per `D:\CLAUDE\a30-toolkit\BLOCKED_2026-04-27.md` can run.

**Knox e-fuse warning** (per memory): bootloader unlock blows the Knox fuse. ADB backup + partition dump do NOT — they're safe. Stop short of `fastboot flashing unlock` unless Iddo explicitly approves.
