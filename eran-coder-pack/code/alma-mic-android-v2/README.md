# ALMA מיקרופון — alma-mic-android-v2

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

Clean rewrite (2026-09-03, Iddo's order) of the always-on Hebrew microphone for the
**Samsung SM-S948B, Android 16 (API 36)**. Kotlin, 100% ours: AndroidX core + appcompat only,
no third-party libraries, no WebView. Package `com.almaware.almamic2` (the old
`D:\CLAUDE\alma-mic-android` / `com.almaware.almamic` is untouched and does not conflict).

## What it does

Foreground service (`foregroundServiceType="microphone"`, started only from the visible
activity — Android 14+/16 rule) captures 16 kHz mono PCM16 with `VOICE_RECOGNITION`, runs our
energy+ZCR VAD (proven constants: open 60 ms above max(floor×3, 0.010), close 800 ms below
max(floor×1.8, 0.006), ZCR ≥ 0.15 rescue, 360 ms pre-roll, 350 ms minimum, 28 s force-split),
persists every utterance to `files/queue/` BEFORE any network attempt, and drains oldest-first
to **KESHEV STT on eran1** with backoff (radio-quiet when offline). Every transcript lands in
the app list (newest on top, tap to copy, Share button) and in `files/transcripts/YYYY-MM-DD.txt`.

## STT endpoint (wired, verified live)

```
POST http://<lan-ip>:8737/v1/transcribe            (eran1 keshev-stt, LAN)
Authorization: Bearer <64-hex token>                    (token = mic-rebuild/state/stt-token,
Content-Type: audio/pcm;rate=16000;encoding=s16le;channels=1        byte-identical to eran1's)
X-Request-Id: <session8hex>-<seq:06d>                   (per-install session + seq = dedup key)
X-Audio-Duration-Ms / X-Lang-Hint: he
Body: raw s16le PCM 16 kHz mono, ≤ 960,000 bytes (30 s)
→ 200 {"text","lang","no_speech_prob","decode_ms","model",...}
```

Why eran1 and not alma-stt (:8844 over Tailscale): the phone has Tailscale installed but no
100.x address up; eran1 is on the same Wi-Fi (9 ms ping) and answered the real Hebrew clips
from the PC in ~170 ms. The token is baked in from `keshev.properties` (gitignored) into
`BuildConfig` and is editable in the app's settings, as is the server URL.

## Self-test

`res/raw/selftest_abba.wav` = eran1 `~/eran-brain/food/train/abba_t06_0.wav` (a real human
clip, 1.33 s). The self-test button frames it exactly like the mic and pushes it through the
SAME Segmenter → SegmentStore → Uploader → Transcripts path; the verdict is shown in the app
and logged as `SELFTEST_RESULT pass=... text=...`.

## Build / install

```powershell
cd D:\CLAUDE\alma-mic-android-v2
.\gradlew.bat assembleDebug           # APK: app\build\outputs\apk\debug\app-debug.apk (copy in dist\)
adb -s <lan-ip>:38885 install -r app\build\outputs\apk\debug\app-debug.apk
adb -s <lan-ip>:38885 shell pm grant com.almaware.almamic2 android.permission.RECORD_AUDIO
adb -s <lan-ip>:38885 shell pm grant com.almaware.almamic2 android.permission.POST_NOTIFICATIONS
# launch, start listening and run the self-test without touching the screen:
adb -s <lan-ip>:38885 shell am start -n com.almaware.almamic2/.MainActivity --ez start true --ez selftest true
```

Pins: Gradle 8.10.2 · AGP 8.7.3 · Kotlin 2.1.0 · compileSdk/targetSdk 36 · minSdk 30 · JDK 21.
`local.properties` must contain `sdk.dir=C\:\\Android\\Sdk` (ANDROID_HOME on this PC is one
level too high). Edge-to-edge is mandatory on targetSdk 36 — insets are handled in MainActivity.

## Acceptance record — 2026-09-03 09:18 (real outputs)

| check | result | evidence |
|---|---|---|
| APK builds + installs | VERIFIED | `BUILD SUCCESSFUL`, `adb install -r` → Success |
| Foreground mic service | VERIFIED | `dumpsys activity services`: `isForeground=true types=0x00000080` |
| Mic really open | VERIFIED | `dumpsys audio`: `VOICE_RECOGNITION 1ch 16000Hz ... silenced:false pack:com.almaware.almamic2` |
| Self-test → real transcript | VERIFIED | logcat `SELFTEST_RESULT pass=true text="אבא." roundtrip_ms=309`; PC probe of the same WAV → `אבא.` |
| Transcript reaches storage | VERIFIED | phone `files/transcripts/2026-09-03.txt`: `09:17:52 he selftest אבא.` |
| UI Hebrew, RTL, bright | VERIFIED | screenshot: `מקשיב…`, self-test line, `אבא.` row, white theme |
| Live room speech → transcript | VERIFIED | mic → VAD → queue → eran1: `09:18:35 he תודה.` and `09:19:29 he תודה רבה.` in the phone's daily file; queue drained to 0, nothing rejected |
| Speaker was Iddo | UNKNOWN | someone spoke near the phone; identity not verifiable from here |
| Battery/doze exemption | PLANNED | button exists; one tap by Iddo (not set via adb on purpose) |

## Files

`App` (channel + Pipeline) · `Pipeline` (singletons) · `MicService` (FGS + AudioRecord) ·
`Segmenter` (VAD + pre-roll + split policy) · `Vad` · `SegmentStore` (durable queue) ·
`Uploader` (KESHEV protocol) · `Transcripts` (daily file + list) · `SelfTest` · `Prefs` ·
`StateBus` · `MainActivity` (UI). Strings: `values/` Hebrew (primary), `values-en/` English.

ALMAWARE · לזכרה של עלמה ז״ל
