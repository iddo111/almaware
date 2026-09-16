# Kodi 21.3 Omega Installation Guide for Windows

**For Iddo** | iddoperez.ai | May 2026

This guide installs Kodi 21+ (Omega) in **portable mode** on your Windows PC, configures it with your existing media library, and sets it to auto-start. **Free, no purchase needed.**

---

## What You're Getting

- **Kodi 21.3 Omega** — open-source media center (official release)
- **Portable installation** — reversible, no system registry pollution
- **Auto-start on boot** — runs silently in the background
- **Web remote** — control from any browser on your LAN (port 8090)
- **Library scanning** — automatically indexes your video collection

**Honest limits:**
- This is a **parallel test deployment** while you wait for the Mi Box.
- Kodi on Windows PC ≠ Kodi on TV in UX. For couch-friendly control, use a Bluetooth remote or the web interface.
- The real media-center plan is the Mi Box flash at `D:\CLAUDE\mibox\PLAN.md`. This Windows PC Kodi is a temporary staging ground.

---

## Step 1: Download Kodi Portable

1. Open your browser and navigate to **https://kodi.tv/download**
2. Under **Windows**, look for **Portable (64-bit)** — click to download `kodi-21.3-Omega.zip` (or latest 21.x version)
3. **Important:** Download the **`.zip` portable version**, NOT the `.exe` installer
4. Save it to `D:\CLAUDE\tools\kodi\`

**Current official mirrors:**
- https://kodi.tv/download/ (primary)
- https://mirrors.kodi.tv/releases/windows/win64/ (mirror)
- https://sourceforge.net/projects/kodi/files/releases/windows/win64/ (backup)

---

## Step 2: Extract and Configure Portable Mode

1. In `D:\CLAUDE\tools\kodi\`, extract `kodi-21.3-Omega.zip`
   - You should now have a folder like `D:\CLAUDE\tools\kodi\Kodi-portable\` with `kodi.exe` inside
   
2. Create the portable-mode flag:
   ```
   D:\CLAUDE\tools\kodi\Kodi-portable\portable_mode
   ```
   - This is a **zero-byte text file** (create an empty file named `portable_mode` with no extension)
   - On first launch, Kodi will create `portable_data\` subfolder in the same directory
   
3. Verify the structure:
   ```
   D:\CLAUDE\tools\kodi\Kodi-portable\
   ├── kodi.exe
   ├── portable_mode          (zero-byte file)
   ├── kodi
   ├── system
   ├── tools
   └── [other Kodi files]
   ```

---

## Step 3: First Launch and Initial Setup

1. Double-click `D:\CLAUDE\tools\kodi\Kodi-portable\kodi.exe`
2. Wait for Kodi to fully load (10–20 seconds on first run)
3. You should see the Kodi home screen
4. Kodi has now created `D:\CLAUDE\tools\kodi\Kodi-portable\portable_data\` containing:
   ```
   portable_data\
   └── Kodi\
       └── userdata\
           ├── sources.xml
           ├── advancedsettings.xml
           └── [other config files]
   ```

---

## Step 4: Configure Media Sources

### Option A: Manual (UI)
1. In Kodi, navigate to **Settings** → **Media** → **Library**
2. Click **Add Videos** and browse to `D:\xxxmovies`
3. Repeat for `D:\xmove` and any other video directories
4. Select **Movies** or **TV Shows** as the content type
5. Click **OK** and let Kodi scan

### Option B: Pre-baked Configuration (Faster)
1. Replace the `sources.xml` with the one provided in this folder: `kodi-sources.xml`
   - Copy `D:\CLAUDE\tools\kodi\kodi-sources.xml` → `D:\CLAUDE\tools\kodi\Kodi-portable\portable_data\Kodi\userdata\sources.xml`
   - **Overwrite** any existing file
2. Restart Kodi
3. Go to **Videos** → **Movies** and click **Scan for New Content**
4. Kodi will auto-discover and index all your video files

**Video directories being scanned:**
- `D:\xxxmovies\` — primary movie collection
- `D:\xmove\` — additional videos
- `D:\D_drive_recovery\` — recovery videos (if needed)

---

## Step 5: Configure for Hebrew + RTL Text

Hebrew filenames and UI require careful setup:

1. **Install Hebrew Language Pack:**
   - Go to **Settings** → **Interface** → **Skin** → **Fonts**
   - Select a font that supports Hebrew (e.g., "Arial Hebrew" or "DejaVu Sans")
   - Go to **Settings** → **Interface** → **Regional** → **Language**
   - Set to **Hebrew** (עברית)

2. **Fix BiDi Rendering (if text appears reversed):**
   - Navigate to `D:\CLAUDE\tools\kodi\Kodi-portable\portable_data\Kodi\userdata\`
   - Open or create `advancedsettings.xml`
   - Add this block:
     ```xml
     <advancedsettings>
       <gui>
         <rendertype>auto</rendertype>
       </gui>
     </advancedsettings>
     ```
   - Save and restart Kodi
   - Note: Kodi has known issues with right-to-left text in some skins. The `auto` render type usually resolves this.

---

## Step 6: Install Recommended Add-ons

All free, from the official Kodi repository:

1. Go to **Add-ons** → **Add-on Browser** (home icon)
2. Select **Video Add-ons**, **Subtitle Add-ons**, or **Web Interface**:

### Essential
- **Chorus2** (Web Interface) — control Kodi from any browser at `http://localhost:8090`
  - Configure port: **Settings** → **Services** → **Web Server** → **Port** → change to `8090` (port 8080 is used by landing-page server)
  - Access: `http://localhost:8090` or `http://<YOUR-PC-IP>:8090`

### Subtitles (Optional but Recommended)
- **OpenSubtitles** — search 1M+ subtitle files
- **SubsCenter** — Hebrew subtitles from SubsCenter.co
- **Subscene Subtitles** — alternative subtitle source

### Nice-to-Have
- **Trakt** — sync watched history to Trakt.tv (free account)
- **Kodi Remote** — mobile remote control app (search "Kodi Remote" in your phone's app store)

---

## Step 7: Configure Web Interface Port

**Important:** Port 8080 is already used by your landing-page server. Configure Kodi's web interface on **port 8090**:

1. In Kodi, go to **Settings** → **Services** → **Web Server**
2. Enable **Allow remote control via HTTP**
3. Change **Port** from `8080` to **`8090`**
4. Save settings and restart Kodi
5. Open browser: `http://localhost:8090` (or `http://<PC-IP>:8090` from another device on your LAN)

---

## Step 8: Auto-Start on Boot

Choose one method:

### Method A: Windows Scheduled Task (Recommended)
Run `register_kodi_autostart.ps1` (included in this folder):

```powershell
# In PowerShell (as Administrator):
cd D:\CLAUDE\tools\kodi
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force
.\register_kodi_autostart.ps1
```

This will:
- Create a Windows Scheduled Task named `KodiAutoStart`
- Launch Kodi at boot time
- Run minimized (no splash screen)
- Auto-restart if Kodi crashes

### Method B: Startup Folder Shortcut
1. Press `Win+R`, type `shell:startup`, click OK
2. Right-click → **New** → **Shortcut**
3. Target: `D:\CLAUDE\tools\kodi\start_kodi.cmd`
4. Name: `Kodi Media Center`
5. Right-click shortcut → **Properties** → **Advanced** → check **Run minimized**
6. Click OK and save

---

## Step 9: Smoke Test

1. **Launch Kodi** (double-click `kodi.exe` or wait for auto-start)
2. **Verify movie library:**
   - Navigate to **Videos** → **Movies**
   - You should see thumbnails and titles from `D:\xxxmovies` and `D:\xmove`
3. **Test web interface:**
   - Open browser: `http://localhost:8090`
   - You should see the Chorus2 web remote
   - Try playing a video, adjust volume, check it works
4. **Verify Hebrew rendering:**
   - In **Videos** → **Movies**, check if Hebrew filenames display correctly (not reversed)
   - If text is mangled, apply the `advancedsettings.xml` fix from Step 5

---

## Troubleshooting

### Kodi won't start
- Check `D:\CLAUDE\tools\kodi\Kodi-portable\kodi.exe` exists
- Make sure `portable_mode` file (zero-byte, no extension) is in the same directory
- Try running as Administrator: right-click `kodi.exe` → **Run as Administrator**

### Videos not showing in library
- Manually add sources: **Settings** → **Media** → **Library** → **Add Videos**
- Verify paths exist: `D:\xxxmovies\` and `D:\xmove\`
- Manually scan: **Videos** → **Movies** → **Scan for New Content**

### Hebrew text is reversed
- Ensure `advancedsettings.xml` has `<rendertype>auto</rendertype>`
- Try different Kodi skins: **Settings** → **Interface** → **Skin**
- (Kodi has known BiDi limitations; this is a workaround, not a full fix)

### Port 8090 not accessible
- Check firewall: Windows Defender Firewall → Allow an app → Kodi.exe
- Verify Kodi's web server is enabled: **Settings** → **Services** → **Web Server** → **Allow remote control via HTTP**
- Confirm port is set to `8090`, not `8080`

### Kodi crashes on startup
- Check Event Viewer for errors: `Win+R` → `eventvwr.msc`
- Try disabling add-ons: rename `D:\CLAUDE\tools\kodi\Kodi-portable\portable_data\Kodi\userdata\addons\` to `addons-disabled\`, restart Kodi, then re-enable one by one

---

## Files in This Folder

- **INSTALL.md** — this guide
- **start_kodi.cmd** — launcher script (single instance, runs `kodi.exe`)
- **register_kodi_autostart.ps1** — Windows Scheduled Task registration script
- **kodi-sources.xml** — pre-configured sources.xml (copy to `Kodi-portable/portable_data/Kodi/userdata/`)
- **addons-recommended.md** — list of free community add-ons

---

## Important Notes

### Reversibility
- Kodi portable is **fully reversible**. To uninstall:
  - Delete `D:\CLAUDE\tools\kodi\Kodi-portable\` folder
  - If auto-start was configured, delete the Scheduled Task: `schtasks /delete /tn "KodiAutoStart" /f`

### Data Storage
- All Kodi settings, library metadata, watched-list, and add-ons are stored in `portable_data/` subfolder
- Zero system registry impact
- Safe to move or copy the entire folder to another PC

### Performance
- **First library scan can take 5–10 minutes** (depending on file count)
- After initial scan, Kodi tracks changes automatically

### Updates
- Kodi checks for updates on launch. You can manually update by downloading the latest `.zip` from https://kodi.tv/download and extracting over the existing `Kodi-portable\` folder
- **Do NOT delete `portable_data\` when updating** — it contains your settings and library metadata

---

## Next Steps: Mi Box Deployment

Once the Mi Box arrives, you can:
1. Refer to `D:\CLAUDE\mibox\PLAN.md` for the official media-center setup
2. Keep this Windows PC Kodi for testing add-ons, library imports, or as a fallback
3. Share the configured sources.xml between both deployments for consistency

---

## Support & Brand

For Kodi documentation, visit [https://kodi.wiki](https://kodi.wiki)  
This deployment by **iddoperez.ai** | May 2026

---

**Ready to start?** Download the portable `.zip` from https://kodi.tv/download, extract to `D:\CLAUDE\tools\kodi\Kodi-portable\`, create the `portable_mode` file, and launch `kodi.exe`.
