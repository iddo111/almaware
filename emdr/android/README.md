# ALMA-EMDR for Android — האפליקציה

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

> ✅ **נבנה כאן. / BUILT HERE.** APK אמיתי, 28 בדיקות עוברות. 2026-09-01.
> 🔴 **לא הורץ על טלפון. / NEVER RUN ON A PHONE.** אין באזרים, אין אוזניות, אין מדידה.
> The APK exists and the tests pass. **Nothing here has been executed on a device, and no
> latency number below has been measured on Iddo's handset.** Every one is a design target.

---

## Build — the exact command

```bash
cd D:\CLAUDE\emdr\android
gradlew.bat :app:assembleDebug :app:testDebugUnitTest
```

That single line builds the APK **and** runs the unit tests. On a POSIX shell it is
`./gradlew :app:assembleDebug :app:testDebugUnitTest`.

The APK lands at `app\build\outputs\apk\debug\app-debug.apk`.
Install with `adb install -r app\build\outputs\apk\debug\app-debug.apk`.

For a release APK (unsigned — signing is Iddo's key, not mine):
`gradlew.bat :app:assembleRelease` → `app\build\outputs\apk\release\app-release-unsigned.apk`

### Prerequisites, all present on this machine

| | needed | here |
|---|---|---|
| JDK | 17+ | **21.0.11** (Temurin) ✅ |
| Android SDK | platform 35, build-tools 35 | **C:\Android\Sdk** ✅ |
| Gradle | 8.9+ | **8.10.2** via the wrapper ✅ |
| AGP / Kotlin | — | **8.7.3 / 2.1.0**, pinned ✅ |

`local.properties` points at the SDK. It is **not** checked in (`.gitignore`); on
another machine either recreate it (`sdk.dir=C:/Android/Sdk`, forward slashes) or set
`ANDROID_HOME` to the SDK root. First build needs the network to fetch AGP, Kotlin and
JUnit from `google()` and `mavenCentral()`; after that it is offline-capable.

### ✅ VERIFIED HERE, 2026-09-01

```
:app:assembleDebug        SUCCESS   app-debug.apk             927 318 B
:app:assembleRelease      SUCCESS   app-release-unsigned.apk  668 201 B  (lintVital passed)
:app:testDebugUnitTest    SUCCESS   28 tests, 0 failures

aapt2 dump badging app-debug.apk:
  package ai.iddoperez.emdr   minSdkVersion 26   targetSdkVersion 35
  BLUETOOTH_SCAN (neverForLocation) · BLUETOOTH_CONNECT
  BLUETOOTH / BLUETOOTH_ADMIN / ACCESS_FINE_LOCATION, all maxSdkVersion=30
  NO INTERNET permission
  bluetooth, bluetooth_le, location — all uses-feature-NOT-required
```

---

## Why native Kotlin and not a WebView

**An Android WebView has no Web Bluetooth.** That is Google's deliberate position — the
Chrome team's own "Web on Android" guidance names Web Bluetooth as the example of an API
WebView omits because the OS has a native equivalent. So a Cordova/Capacitor wrapper
around `ALMA-EMDR.html` **cannot reach the buzzers at all** without a native BLE plugin
underneath it, at which point the wrapper has bought nothing.

A Trusted Web Activity *would* get Web Bluetooth (it runs in real Chrome), but it is a
browser tab: no audio focus, and **no `AudioTrack.getTimestamp()`** — which is the one
API that makes Bluetooth-headphone timing possible at all. That killed it.

So: native. What is reused from the browser app is the **protocol and the timing model**,
not a line of its code. The slider ranges match it exactly (0.15–1.5 Hz, buzz 40–255,
pulse 40–400 ms, pitch 120–520 Hz) so a client moving between the two feels no change.

**Zero third-party dependencies.** No AndroidX, no Material, no Compose, no BLE wrapper.
Every API used — BLE GATT, `AudioTrack`, `Choreographer`, `SeekBar` — is framework. The
only dependency in the whole project is JUnit, and it is test-only. A therapy device
should have the shortest supply chain it can.

---

## The three things this app does

### 1 · The dot — mono, or twice for cardboard

`EmdrView.kt`, ~170 lines. Black `View`, `Choreographer`-driven, position evaluated at
the **next** vsync (`frameTimeNanos + refreshPeriod`) because that is when the frame is
actually scanned out.

Stereo is a fixed IPD offset and a `clipRect` per eye. **No Cardboard SDK, no Unity, no
lens profile, no distortion mesh** — for one bright dot on a black field a fixed offset
is genuinely enough, and black hides the edge artefacts.

### 2 · The sound — to Bluetooth headphones, on time

`ToneEngine.kt`. One `AudioTrack`, 48 kHz stereo, written by a dedicated thread in 10 ms
chunks with the bilateral clicks rendered at exact sample offsets.

The whole file exists because of one measured fact: **Bluetooth headphones are ~300–370 ms
late, and up to 484 ms on some handsets** (SoundGuys, WALT rig, 2 800 samples). At 1 Hz
the half-cycle is 500 ms. Uncompensated, the buzz beats the beep by most of a beat and
the bilateral illusion — the thing the therapy is made of — is gone.

You cannot speed audio up, so everything else waits for it:

```
perceived(frame) = presentation(frame) + calibrationOffset
```

`presentation()` comes from `AudioTrack.getTimestamp()`, which the Android CDD requires
to be accurate to **±2 ms**. `calibrationOffset` is the part no public Android API will
tell you — codec, air, buds — so a human measures it once per pair of headphones in
`CalibrationActivity`, with a **nulling** slider ("move it until the buzz and the beep
become one thing"), 10 ms steps, 0–500 ms. Nulling, not tapping: no reaction-time bias.

Above **250 ms** the app says so and recommends wired headphones. It does not silently
deliver a badly-timed session to someone in trauma processing.

If `getTimestamp()` refuses (it can), the engine falls back to `playbackHeadPosition`,
**says so on the calibration screen**, and the whole sink latency simply lands on the
slider instead. That still works — it is just less precise, and the user can see which
one they have.

### 3 · The buzzers — BLE, the 9-byte frame

`BleBuzzerLink.kt` + `BuzzerFrame.kt`. Scan by service UUID, connect with the scanned
`BluetoothDevice` (never an address string — that is documented to break with two
devices, and two balls is exactly that case), **Write Without Response**, **no MTU
negotiation ever** (9 bytes fit the default 23-byte ATT MTU, which removes the most
common cross-platform BLE failure), **no pairing or bonding**,
`CONNECTION_PRIORITY_BALANCED` (not `HIGH` — `HIGH` fights A2DP for airtime and buys
nothing at four events per second).

Frames go out **three times, 8 ms apart**; the ball remembers the last 8 `(op,seq)` pairs
for 2 s and ignores repeats, so the first copy to arrive wins — which is also the
lowest-latency copy.

---

## The one idea the whole thing rests on

The app does **not** fire a buzz when the dot reaches the edge. Three times a second it
whispers:

> *"next tap: LEFT, in 180 ms, 160 ms long"*

The ball holds exactly **one** pending tap. A whisper that agrees with the pending one to
within **30 ms** is a restatement, not a new beat. That single rule turns 0–50 ms of
Bluetooth jitter into an even rhythm — **and**, because a ball that stops being whispered
to stops by itself in 1500 ms, it is also the entire safety story. The ball has no ON
state; it only ever has a countdown.

`SessionEngine.kt` is that whisper, plus the audio look-ahead. Because the rhythm is
periodic and known from `t0` and the rate, the whole beat sequence is computable a second
ahead — look-ahead is free.

### And why it can never miss a beat (PROTOCOL D.4)

`Timeline.kt` derives edges from the **phase**, in closed form. It never looks at a
position or a pixel.

That is not style. The PC widget's edge test is a 6-pixel band combined with a random
±2 % amplitude jitter, and **when the jitter is negative the orb never reaches the band
and the event never fires — for the whole session, silently.** 32.8 % of seeds at
1920 px, 37.3 % at 2560, 41.6 % at 3840. The default seed (42) happens to be positive,
which is why nobody caught it. A buzzer hung off that test would never buzz for a third
of users.

`TimelineTest.kt` **reproduces that defect** and then proves this app cannot have it:

```
the_pixel_band_test_is_broken_for_negative_amplitude_jitter   ✅  fires 0 times
phase_crossing_is_immune_to_amplitude_jitter                  ✅  60 beats, every jitter
phase_crossing_survives_a_dropped_frame_at_the_apex           ✅
crossing_counter_and_closed_form_edges_agree                  ✅  two derivations, 4 rates
```

---

## Permissions — and what is deliberately absent

```xml
<uses-permission android:name="android.permission.BLUETOOTH_SCAN"
    android:usesPermissionFlags="neverForLocation" tools:targetApi="s" />
<uses-permission android:name="android.permission.BLUETOOTH_CONNECT" tools:targetApi="s" />
<uses-permission android:name="android.permission.BLUETOOTH"          android:maxSdkVersion="30" />
<uses-permission android:name="android.permission.BLUETOOTH_ADMIN"    android:maxSdkVersion="30" />
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" android:maxSdkVersion="30" />
```

- **`neverForLocation` is a promise the code actually keeps** — nothing derives location
  from a scan result. That is what lets a modern phone ask for **no location permission
  at all**.
- The three legacy permissions are capped at API 30, so they are never requested on a
  current phone. On Android 11 and below the old stack still demands `FINE_LOCATION` for
  a BLE scan *and* location services switched on — the app says so in plain words rather
  than failing silently, because that is a real support call for a therapist.
- **There is no `INTERNET` permission.** The app cannot reach the network. Nothing about
  a person in trauma processing leaves the phone. `allowBackup="false"` too, so the
  calibration store never goes to a cloud backup.
- 🪟 **Fixed while building:** Play *implies* a **required** `android.hardware.bluetooth`
  from the legacy permissions, and a required `android.hardware.location` from
  `FINE_LOCATION` — which would have hidden the app from any device without that
  hardware, even though it works perfectly as dot-plus-sound. All three features are now
  declared `required="false"`. **Found by running `aapt2 dump badging` on the built APK,
  not by reading the manifest.**
- **No foreground service, no background mode, on purpose.** The set stops when the
  session screen stops being visible. If the therapist takes a call, the balls stop —
  and if anything prevents the STOP frame arriving, the balls' own dead-man stops them
  1500 ms later regardless.

---

## ⚠️ An honest warning about the cardboard glasses

I built it because Iddo asked for it. Three things first, and they are in the app's own
UI as well as here:

1. **The optics fight the therapy.** EMDR needs a wide horizontal sweep. In a cheap
   cardboard viewer each eye is locked to a fixed lens axis, and the extremes of the
   sweep — exactly the part that matters — land at the lens edge, the blurriest and most
   distorted region. The arithmetic is visible in `EmdrView.onDraw`: the usable amplitude
   in stereo is materially smaller than on a flat screen.
2. **It hides the client's face.** An EMDR clinician watches the face to know when to
   stop a set. For עמותת המלאכים של ערן — real people in real distress — occluding the
   face is a **safety regression**, not a feature.
3. **Nothing in EMDR needs stereo depth.** There is no evidence a 3D dot beats a flat one.

For actual therapy: phone in landscape on a stand, or a TV, dark room, the sound and the
two balls. The stereo switch is there for whatever reason Iddo has that I do not — the
buzzers and the headphones work identically either way.

---

## Files

```
app/src/main/java/ai/iddoperez/emdr/
  BuzzerFrame.kt        the 9-byte wire protocol (C.1, C.2, C.4)
  Timeline.kt           THE ONE CLOCK. Phase-crossing, closed-form edges (D.4)
  ToneEngine.kt         AudioTrack, the audio timebase, A2DP compensation (D.3)
  BleBuzzerLink.kt      scan, connect, triple-send, notifications, keep-alive
  SessionEngine.kt      the look-ahead scheduler and the 3 Hz whisper (C.3, D.3)
  Calibration.kt        which headphone, and how late it is
  EmdrView.kt           the dot, mono or stereo
  EmdrApp.kt            one link, one audio engine, one scheduler, process-wide
  MainActivity.kt       the therapist's screen
  SessionActivity.kt    the set
  CalibrationActivity.kt  the twenty seconds that make Bluetooth usable
app/src/test/java/ai/iddoperez/emdr/
  BuzzerFrameTest.kt    the 8 PROTOCOL C.7 vectors + clamps + decoder hostility  (16)
  TimelineTest.kt       the amp-jitter regression + crossing/closed-form agreement (12)
```

---

## ❌ What is NOT proven

| claim | status |
|---|---|
| It compiles; debug and release APKs exist | ✅ **verified here** |
| 28 unit tests pass | ✅ **verified here** |
| The frame is byte-identical to the firmware's | ✅ **both ends assert the same 8 vectors**, JVM and RISC-V |
| Manifest, permissions, minSdk in the built APK | ✅ **verified with `aapt2 dump badging`** |
| The app runs on a phone | 🔴 **never launched. No device was used.** |
| It connects to a ball | 🔴 **no ball exists** |
| A2DP compensation actually lands within ±20 ms | 🔴 **design target.** The 308/369/484 ms figures are measured — **on other people's handsets.** Calibrate on Iddo's. |
| `getTimestamp()` works on Iddo's phone | ⚠️ CDD-required, but real devices vary. The app shows which timebase it got. |
| Stereo IPD geometry looks right through a real lens | 🔴 untested |
| Nothing was published, deployed or bought | ✅ |

---

**הפרוטוקול המחייב / The binding protocol:** `D:\CLAUDE\emdr\PROTOCOL-buzzers-20260901.md`
**הקושחה / The firmware:** `D:\CLAUDE\emdr\firmware\`
