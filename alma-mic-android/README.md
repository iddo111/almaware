# ALMA Mic — native Android always-on Hebrew microphone (A70)

Native Kotlin app (NOT a PWA/WebView). Foreground service (`foregroundServiceType="microphone"`)
captures 16 kHz mono PCM16, runs an on-device energy+ZCR VAD with hysteresis and 360 ms pre-roll,
persists every utterance to disk, and drains the queue to the **alma-stt** fleet service over
Tailscale. Hebrew-first RTL UI (`values-iw/`), English fallback.

Lineage: VAD/service constants ported from `D:\grok\projects\almaware-hebrew-mic-a70` (proven
design, dead server) + `D:\CLAUDE\alma-mic` desktop pipeline; protocol per live probe of eran4
on 2026-08-06.

## Wire protocol (verified live)

```
POST http://<tailnet-ip>:8844/v1/transcribe?language=he&task=transcribe
Content-Type: application/octet-stream
X-ALMA-Sample-Rate: 16000
Body: raw little-endian float32 PCM, mono, 16 kHz, max 1,920,000 bytes (30 s)
→ 200 {"text": "...", "language": "he", ...}
```

The app records PCM16 (half the disk size), converts to float32 at upload time, and force-splits
segments at 28 s to stay under the server's 30 s cap.

## THE ONE FLEET-SIDE BLOCKER

Both alma-stt instances allow a **single client IP: <tailnet-ip> (the Windows PC)**.
The A70 (`<tailnet-ip>`) gets `403 client not allowed` until one of:

1. Patch `server.py` to accept a comma-separated allowlist and add `<tailnet-ip>`
   (eran4 config: `/home/eran4/.config/alma-stt.env`, `ALMA_STT_ALLOWED_CLIENT=...`;
   eran2: hardcoded in the systemd unit `ExecStart`). ~3-line change — recommended.
2. Relay phone audio through the PC.

The app handles 403 gracefully: it shows "blocked" status, keeps every utterance queued on disk,
and retries with backoff — so it can be installed before the fleet patch lands.

## Build

Prereqs on this machine (all verified present): JDK 21 (`JAVA_HOME` set), Android SDK at
`C:\Android\Sdk` (pinned via `local.properties`), Gradle wrapper included.

```powershell
cd D:\CLAUDE\alma-mic-android
.\gradlew.bat assembleDebug
# APK: app\build\outputs\apk\debug\app-debug.apk
```

Release (unsigned): `.\gradlew.bat assembleRelease`

## Install on the A70 (SM-A705, Android 11)

ADB is not yet reachable — one-time phone-side step, then everything is scriptable:

- **Wireless (no cable):** Settings → Developer options → Wireless debugging → ON →
  "Pair device with pairing code", then on the PC:
  `adb pair <tailnet-ip>:<pair-port> <code>` and `adb connect <tailnet-ip>:<debug-port>`
- **USB once:** enable USB debugging, plug in, `adb tcpip 5555`, unplug, then
  `adb connect <tailnet-ip>:5555`

Then: `adb install -r app\build\outputs\apk\debug\app-debug.apk`

## On-device setup

1. Open the app, grant microphone permission.
2. Tap "בטל אופטימיזציית סוללה" (disable battery optimization) — Samsung kills background
   services aggressively; this is required for true always-on.
3. Optionally edit the server URL (defaults to eran4 `http://<tailnet-ip>:8844`, language `he`).
4. Tap "התחל האזנה". A persistent notification appears; the mic survives backgrounding and
   screen-lock. The service must be started from the app UI — Android 11 blocks mic access for
   foreground services started from the background (which is also why there is no boot receiver).

## Architecture

| File | Role |
|---|---|
| `MicService.kt` | Foreground service; AudioRecord VOICE_RECOGNITION 16 kHz mono PCM16, 30 ms frames; pre-roll; 28 s force-flush; partial wakelock held only while VAD is open |
| `Vad.kt` | Energy+zero-crossing VAD; adaptive noise floor; opens after 60 ms above `max(floor*3, 0.010)`, closes after 800 ms below `max(floor*1.8, 0.006)`; ZCR keeps fricative word-endings alive |
| `SegmentStore.kt` | Durable disk queue (`files/queue/*.pcm16`, atomic writes, 500-file cap, poison-pill parking in `files/rejected/`) |
| `Uploader.kt` | Oldest-first drain; float32 conversion; exponential backoff 2→60 s; no network = no radio spin; own wakelock only while a POST is in flight; `/health` probe |
| `MainActivity.kt` | Hebrew RTL UI: state, connection, queue depth, last transcript; permissions flow (RECORD_AUDIO + POST_NOTIFICATIONS on 13+); settings; battery exemption |

Pins: Gradle 8.10.2 · AGP 8.7.3 · Kotlin 2.1.0 · compileSdk 35 · targetSdk 34 · minSdk 26.

ALMAWARE · לזכרה של עלמה ז״ל
