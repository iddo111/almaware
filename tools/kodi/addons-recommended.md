# Kodi 21.3 Omega — Recommended Free Add-ons

**For Iddo** | iddoperez.ai | May 2026

This is a curated list of free, official community add-ons that enhance Kodi for personal media libraries and couch-friendly control.

---

## Installation Instructions

1. Launch Kodi
2. Navigate to **Add-ons** (home menu icon that looks like a Rubik's cube)
3. Click **Add-on Browser** (or search icon)
4. Select the category (e.g., **Video Add-ons**, **Subtitles**, **Services**)
5. Find the add-on name, click it, and select **Install**
6. Wait for the confirmation message
7. Return to the home menu and enjoy

All add-ons listed below are **100% free** and from the **official Kodi repository** (no third-party sketchy sources).

---

## Essential (Highly Recommended)

### Chorus2 — Web Interface
- **Category:** Services / Web Interface
- **What it does:** Remote control Kodi from any web browser on your LAN
- **Why:** Perfect for couch control without a physical remote
- **Access:** `http://localhost:8090` after installation and configuration
- **Note:** Make sure Kodi web server port is set to **8090** (not 8080, which is used by landing-page server)
  - Go to **Settings** → **Services** → **Web Server**
  - Enable **Allow remote control via HTTP**
  - Set port to **8090**

---

## Subtitles (Optional but Recommended for Hebrew & International Content)

### OpenSubtitles
- **Category:** Subtitles
- **What it does:** Auto-download subtitles for your videos (1M+ subtitle database)
- **Supports:** 100+ languages including Hebrew
- **Free account:** Register at opensubtitles.com (optional, but recommended for better downloads)
- **Usage:** Start a video, press 'S' or go to **Subtitles** → **Download**

### SubsCenter
- **Category:** Subtitles
- **What it does:** Hebrew subtitles specifically from SubsCenter.co
- **Supports:** Primarily Hebrew content
- **Best for:** Israeli films and TV shows

### Subscene Subtitles
- **Category:** Subtitles
- **What it does:** Alternative subtitle source (Subscene.com)
- **Supports:** 50+ languages, high community ratings

**Tip:** Install multiple subtitle add-ons. Kodi will try them in order if the first doesn't have a match.

---

## Nice-to-Have (Optional)

### Trakt — Media Sync
- **Category:** Services / Trakt
- **What it does:** Sync your watched history to Trakt.tv (free account required)
- **Why:** 
  - Track what you've watched across all devices
  - Get recommendations based on your taste
  - Share ratings with friends
- **Setup:** 
  - Create free account at trakt.tv
  - Authorize Kodi in Trakt settings
  - Enable scrobbling in Kodi
- **Cost:** Free (optional premium account for features)

### Kodi Remote Control App
- **What it does:** Control Kodi from your mobile phone (Android/iOS)
- **Where to find it:** Search "Kodi Remote" in Google Play Store or Apple App Store
- **Why:** Wireless remote when you don't have a Bluetooth remote or web browser handy
- **Cost:** Free (official app)
- **Setup:**
  1. Install app on phone
  2. In Kodi, ensure **Settings** → **Services** → **Control via HTTP** or **Control via UPnP** is enabled
  3. Open app, add your PC IP address
  4. Done!

### Artwork Downloader
- **Category:** Information
- **What it does:** Auto-download posters, banners, and fanart for your movies/TV shows
- **Why:** Makes your library look beautiful with cover art
- **Usage:** Select a movie → **Information** → **Download Art**

### Watchlist
- **Category:** Information
- **What it does:** Create custom playlists and "watch next" lists
- **Why:** Organize movies you plan to watch
- **Usage:** Add-ons → Watchlist → Add to Watchlist (from library)

---

## Advanced (For Power Users)

### YouTube
- **Category:** Video Add-ons
- **What it does:** Browse and watch YouTube videos directly in Kodi
- **Note:** Requires YouTube API setup (more technical)

### Plex
- **Category:** Video Add-ons
- **What it does:** If you run a Plex server elsewhere, stream to Kodi from that
- **Note:** Only needed if you use Plex; not necessary for local libraries

### BrowseTheWeb
- **Category:** Utilities
- **What it does:** Browse the web inside Kodi (for information lookups)
- **Note:** Not ideal for couch browsing; use Chorus2 web interface instead

---

## Installation Summary Quick Checklist

- [ ] **Chorus2** — web remote (port 8090)
- [ ] **OpenSubtitles** — subtitle downloads
- [ ] **SubsCenter** — Hebrew subtitles (optional)
- [ ] **Kodi Remote app** — mobile control (install from phone app store)
- [ ] **Trakt** — watched history sync (optional, needs free account)

---

## Tips & Tricks

### Get Better Subtitle Matches
1. Ensure video file **naming is standard:** `Movie Name (Year).mkv` or `Movie Name (Year).mp4`
   - Bad: `1080p movie version2.mkv`
   - Good: `The Matrix (1999).mkv`
2. Install multiple subtitle add-ons for fallback searches
3. Manually select from results if auto-match fails

### Use Bluetooth Remote
- If you have a Bluetooth remote (gamepad, keyboard, or universal remote):
  1. Go to **Settings** → **System** → **Input/Output**
  2. Enable **Bluetooth**
  3. Pair your remote
  4. Assign controls in **Settings** → **Input/Device Mappings**

### Optimize for Hebrew
1. Install **OpenSubtitles** and **SubsCenter**
2. In **Settings** → **Services** → **Subtitles**, ensure Hebrew subtitles are prioritized
3. Set language to **Hebrew** in add-on settings

### Disable an Add-on
- Go to **Add-ons** → find the add-on → click menu → **Disable**
- Does NOT uninstall; you can re-enable anytime

### Uninstall an Add-on
- Go to **Add-ons** → find the add-on → click menu → **Uninstall**
- Safe to reinstall later from the Add-on Browser

---

## Troubleshooting Add-ons

### Add-on won't install
- Check your internet connection
- Ensure you're clicking the correct repository (official Kodi repo, not third-party)
- Try again after a few minutes (temporary repo issues are common)

### Subtitles still won't download
- Verify video filename is standard (see "Tips & Tricks" above)
- Try a different subtitle add-on
- Manually search and download from opensubtitles.com and place `.srt` file next to video

### Web interface (Chorus2) not loading
- Verify port is set to **8090** (not 8080)
- Ensure **Allow remote control via HTTP** is enabled
- Restart Kodi
- Try `http://<YOUR-PC-IP>:8090` from another device on your network

### Remote app can't find Kodi
- Verify both phone and PC are on the same WiFi network
- Check that Kodi is running and accessible
- Manually enter your PC's IP address in the app
- Go to **Settings** → **Services** → **UPnP & DLNA** → enable **UPnP Server**

---

## Official Kodi Repository

All add-ons in this list are from the **official Kodi repository** (`https://repo.kodi.tv/`). This means:
- ✓ Regularly updated and maintained
- ✓ Scanned for security issues
- ✓ Safe to use
- ✗ Do NOT install add-ons from third-party repositories (like Exodus, Covenant, etc.) — these violate copyright and may contain malware

---

## Add-on Support & Documentation

- **Official Kodi Wiki:** https://kodi.wiki/
- **Add-on Discussions:** https://forum.kodi.tv/
- **GitHub Issues:** https://github.com/xbmc/repo-plugins/ (if you find a bug)

---

## Brand & Support

For assistance with Kodi setup and troubleshooting, refer to:
- **INSTALL.md** — step-by-step Windows setup
- **https://kodi.wiki** — official documentation
- **https://forum.kodi.tv** — community support

**This guide by iddoperez.ai | May 2026**
