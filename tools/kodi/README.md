# Kodi 21 Omega Setup for Iddo's Windows PC

**Status:** Configuration files ready. Download pending.

---

## What's Here

This folder contains **everything you need** to set up Kodi media center on your Windows PC:

| File | Purpose |
|------|---------|
| **INSTALL.md** | Complete step-by-step installation guide (READ THIS FIRST) |
| **addons-recommended.md** | List of free, useful add-ons (subtitles, web remote, etc.) |
| **start_kodi.cmd** | Launcher script (single-instance, runs from portable dir) |
| **register_kodi_autostart.ps1** | PowerShell script to set Kodi to auto-start on boot |
| **kodi-sources.xml** | Pre-configured media sources (your D:\xxxmovies, D:\xmove) |

---

## Quick Start (TL;DR)

1. **Download** Kodi 21.3 portable from https://kodi.tv/download (the `.zip` file, NOT `.exe`)
2. **Extract** to `D:\CLAUDE\tools\kodi\Kodi-portable\`
3. **Create** a zero-byte file named `portable_mode` in the same folder
4. **Double-click** `kodi.exe` to launch
5. **Read** INSTALL.md for detailed configuration (web interface, add-ons, auto-start, etc.)

---

## Key Features (Already Set Up For You)

✓ **Portable mode** — reversible, no system pollution  
✓ **Media sources configured** — D:\xxxmovies and D:\xmove are ready to scan  
✓ **Web interface** — control from browser at `http://localhost:8090`  
✓ **Auto-start script** — launch on boot (optional, via PowerShell)  
✓ **Hebrew support** — language pack + BiDi fixes documented  
✓ **Free add-ons listed** — Chorus2, subtitles, mobile remote, etc.  

---

## Media Directories Found

Your PC has video files in:
- **D:\xxxmovies** ✓ (primary)
- **D:\xmove** ✓ (secondary)
- **D:\D_drive_recovery** (optional, recovery videos)

Kodi will auto-discover all of them once you configure sources.

---

## Important Notes

**Port 8090:** Kodi's web interface is configured for port **8090** (not 8080, which your landing-page server uses).

**This is temporary:** While you wait for the Mi Box to arrive, this Windows Kodi is a test deployment. The real media center solution is the Mi Box — see `D:\CLAUDE\mibox\PLAN.md`.

**Reversible:** Simply delete `D:\CLAUDE\tools\kodi\Kodi-portable\` folder to uninstall. Zero system registry impact.

---

## Next Step

👉 **Open INSTALL.md now** — it has everything: download instructions, configuration steps, troubleshooting, add-on installation, and auto-start setup.

---

**Brand:** iddoperez.ai  
**Date:** May 2026  
**Kodi Official:** https://kodi.tv/ | https://kodi.wiki/
