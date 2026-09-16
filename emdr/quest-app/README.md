# ALMA EMDR — Quest app

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

Iddo, 2026-09-09 02:04: **"אני רוצה אפליקציה ממש לא אתר"** — an actual installable app, not a website.
This delivers that: a real `.apk`, a home-screen icon on the Quest, no browser address bar visible
once it launches. It is **built here** (both debug and release APKs assemble and pass
`lintVital`). It has **not been installed on the actual headset** — the Quest 3S is off the
tailnet right now (see "What is blocked" below) — so runtime-on-device is honestly UNTESTED, not
faked as working.

## The decision: which reuse path, and why

Two research reports were commissioned before any code was written (per the 2026-08-31
commission of inquiry that found this exact tool rebuilt 7 times from nothing — REUSE is
mandatory, not optional). Both are quoted in full in the task history; the short version:

**Path A (adapt the Godot/OpenXR `emdr-vive` project) was rejected.** `emdr-vive` and its 4.3
ancestor are real, complete, runnable Godot 4 projects — but for HTC Vive over SteamVR, not
standalone Android. Neither has an `export_presets.cfg`, and this PC has **no Android NDK**
anywhere under `C:\Android` (only unrelated `libbinder_ndk_cpp` AOSP files match "ndk") and an
**empty `export_templates\` cache**. Exporting either project to a Quest `.apk` today is not a
"click export" — it needs an NDK install, matching export templates, a Godot editor binary, and
a hand-built Android export preset, on top of an OpenXR/rendering rework since neither project
targets a standalone headset. That is a rebuild, not a reuse, exactly as the commission's own
`COMMISSION-verdict.md` already concluded for the phone/cardboard case.

**Path B (wrap the existing, already-tested WebXR page) was taken.** `D:\CLAUDE\quest-drop\
files\emdr\index.html` already has the exact mandatory safety gate, the tested cosine bilateral
sweep, and a "VR" button using the identical `three.js r128` + `navigator.xr` pattern SDERA
already proved reaches this exact headset's browser (confirmed: Iddo wore the Quest 3 and viewed
SDERA in VR on 2026-09-03). The discovery report did **not** find an existing native shell that
already loads WebXR content as an installed app — SDERA itself is a bare URL opened in the stock
Oculus Browser via adb intent, not a wrapped APK. So the shell built here reuses that exact,
proven delivery mechanism (URL → `com.oculus.browser` → WebXR), just triggered by tapping an
installed icon instead of a PC-side `adb` command, with the page served from `127.0.0.1` inside
the APK instead of from a PC on the LAN — no dependency on the PC being reachable at all.

A genuinely custom native-rendered OpenXR app (Meta Spatial SDK / raw OpenXR in C++) was
considered and rejected for this iteration: it would mean writing an entire new rendering/haptics/
passthrough stack from scratch inside one session, which is the opposite of "reuse what already
exists" and carries a real risk of shipping something worse-tested than the page that already
works. If Iddo wants that path later, `emdr-vive`'s Godot scripts (`emdr_orb.gd`, `emdr_main.gd`)
are the right reference implementation once the NDK + export templates are actually installed.

## What was reused verbatim vs. newly written

**Reused verbatim** (byte-for-byte, only new code inserted around it):
- The seizure/crisis gate HTML+JS from `quest-drop\files\emdr\index.html` — same warning text,
  same single "הבנתי, אני בוחר להמשיך על אחריותי" button, same "no memory of a previous click"
  behaviour, same ער"ן 1201 line.
- The bilateral sweep math (`x = cos(halfCycles·π)·width·-1`, sets/rest/pass-counting), the
  three.js scene (ball/halo/rail/HUD), and the existing controller mappings (trigger=pause/resume,
  thumbstick=speed, grip=end-set).
- The Gradle/AGP/Kotlin toolchain configuration (`settings.gradle.kts`, root `build.gradle.kts`,
  `gradle.properties`, the Gradle 8.10.2 wrapper jar) verbatim from the sibling, already-verified
  `D:\CLAUDE\emdr\android` (phone/BLE) project — same pinned versions that built and unit-tested
  successfully there on 2026-09-01.
- Haptic tuning reference: `archive\emdr-vive\scripts\emdr_main.gd`'s parameters (duration ≈0.18s,
  amplitude 1.0 — "buzz as pronounced as possible" — re-trigger ≈100ms) were carried over as the
  WebXR Gamepad Haptic Actuator pulse parameters (150ms / intensity 1.0 / 120ms interval).

**Newly written, additive only** (in `webapp/index.html`, clearly marked with a comment block):
1. Controller haptics synced to the sweep — every animation frame during the active sweep,
   whichever side the ball currently occupies pulses that hand's Touch controller via
   `XRInputSource.gamepad.hapticActuators[0].pulse(...)`, rate-limited to ~120ms.
2. A Passthrough-AR toggle checkbox on the start screen. Ticking it requests an `immersive-ar`
   session instead of `immersive-vr` and hides the opaque room (floor/ring/fog) so the real room
   shows through the Quest's passthrough cameras; the ball/halo/rail/HUD stay visible either way.
   Falls back to plain VR automatically if `immersive-ar` is unsupported or the request fails.
3. A visible session-length cap (20 minutes of active/running time) with an on-screen countdown
   badge — mirrors the Cerebro helmet firmware's session-cap + cooldown pattern named in the
   brief. At zero it pauses, shows a full-screen "session over, take a breath" card, and requires
   one explicit tap to start a fresh timed session. It cannot silently run unbounded.
4. A second, controller-only hard-stop: pressing both grips together ends the session instantly
   (same effect as the existing on-screen ■ עצור button), in addition to the pre-existing
   trigger-pause and single-grip-end-set controls.
5. **The entire native Android shell** (`android/` — Kotlin, ~250 lines total across
   `MainActivity.kt` and `EmdrServerService.kt`): a launcher icon, a tiny loopback-only HTTP
   server (plain `java.net.ServerSocket`, no third-party library, no NDK) that serves the one
   bundled HTML file so it runs as a secure context (`http://127.0.0.1:8879/`) without needing a
   TLS certificate, and an explicit `ACTION_VIEW` intent targeting `com.oculus.browser` — the
   installed-app equivalent of what `quest-drop\OPEN-ON-QUEST.cmd` already does over `adb`.

## Mandatory safety gate — how each requirement is met

| Requirement | Where |
|---|---|
| Photosensitive-seizure warning, every launch, non-skippable | `#gate` overlay, reused verbatim; no localStorage/cookie check — reappears every load, by design (comment in the original file says so) |
| "NOT a medical device" text | In the same gate, both Hebrew and English |
| ER"AN 1201 crisis line | `.crisis` line in the gate: "ער"ן 1201 (24 שעות, חינם) · חירום: 101" |
| Explicit acknowledgment tap to proceed | Single `#agree` button; nothing else dismisses the gate |
| Visible session cap / max duration | New 20-minute wall-clock cap, addition #3 above, with a persistent `#cap` badge once a session starts |
| A way to stop immediately, at any time | Three independent ways: the always-visible `#stop` button, the existing controller trigger (pause/resume), and the new both-grips hard-stop (addition #4) — plus, at the OS level, the foreground-service notification's "עצור / Stop" action and the shell's own "■ עצור שרת" button |

## Build it yourself — exact commands

```powershell
cd D:\CLAUDE\emdr\quest-app\android
.\gradlew.bat :app:assembleDebug      # -> app\build\outputs\apk\debug\app-debug.apk
.\gradlew.bat :app:assembleRelease    # -> app\build\outputs\apk\release\app-release-unsigned.apk
```

### ✅ VERIFIED HERE, 2026-09-09

```
:app:assembleDebug     SUCCESS   app-debug.apk               2,375,034 B
:app:assembleRelease   SUCCESS   app-release-unsigned.apk    2,049,429 B  (lintVital passed)

aapt2 dump badging app-debug.apk:
  package ai.iddoperez.emdrquest   minSdkVersion 29   targetSdkVersion 35
  permissions: FOREGROUND_SERVICE, FOREGROUND_SERVICE_SPECIAL_USE, POST_NOTIFICATIONS
  NO INTERNET permission requested by this app's own process
  launchable-activity: ai.iddoperez.emdrquest.MainActivity
  assets/emdr/index.html present in the package (22,896 B)
```

Same proven toolchain as `D:\CLAUDE\emdr\android`: JDK 21 (Temurin), Android SDK `C:\Android\Sdk`
(platform 35, build-tools 36.0.0), Gradle 8.10.2 via the wrapper, AGP 8.7.3 / Kotlin 2.1.0.

### Install, once the headset is reachable

```
adb install -r D:\CLAUDE\emdr\quest-app\android\app\build\outputs\apk\debug\app-debug.apk
```

(Release APK is unsigned — Iddo's signing key, not mine — so `adb install` needs the debug one,
or the release one signed first.)

## What is verified-working vs. untested vs. blocked

- **VERIFIED:** the APK builds successfully (debug + release), `lintVital` passes, the manifest
  and bundled assets are exactly what was intended (checked directly with `aapt2 dump badging`
  and `unzip -l`, not assumed).
- **VERIFIED (inherited):** the gate HTML/JS and sweep math are unchanged from the
  `quest-drop\files\emdr\index.html` copy that was flat-mode tested 2026-09-03 (no console
  errors, ball moves, sliders work).
- **UNTESTED — could not be verified this session:** anything that only shows up at runtime on
  the actual headset — whether `com.oculus.browser` actually accepts the `127.0.0.1:8879` URL and
  opens WebXR immersive-vr from it, whether the passthrough (`immersive-ar`) toggle is actually
  supported by this Quest's browser build, whether the haptic pulses are felt as intended, and
  whether the foreground service survives long enough in practice. None of the WebXR additions
  (haptics, passthrough) had ever been run on a real headset even before this session — the
  underlying VR button itself was flagged as "not yet tested on a real headset" in the discovery
  report.
- **BLOCKED, and why:** installing/running this on the actual Quest 3S could not be attempted.
  `adb connect <tailnet-ip>:5555` fails and `tailscale status` shows the headset
  `offline, last seen 1d ago` — it needs Iddo to put the headset on (which wakes its Tailscale
  client) before `adb devices` will show it again, and USB debugging may need re-accepting on
  the headset the first time this exact app is installed.

## Files

- `webapp/index.html` — the source-of-truth WebXR page (edit here, then re-copy into the Android
  assets folder below before rebuilding).
- `android/` — the Gradle project. `android/app/src/main/assets/emdr/index.html` is a copy of
  `webapp/index.html` baked into the APK.
- `android/app/build/outputs/apk/debug/app-debug.apk` — the built, installable APK.
- `android/app/build/outputs/apk/release/app-release-unsigned.apk` — release build, unsigned.
