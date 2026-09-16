# Galaxy A70 Bridge — Local Music Relay

הפרויקט הקיים הורחב, לא הוחלף. הוא שומר את מסוף ה‑Grok/קול/טיוטות ומוסיף מסלול חד־כיווני למוזיקה:

The existing project is extended in place, not replaced. Its Grok/voice/draft console remains, with a new one-way music path:

```text
Windows default output
  → WASAPI loopback (SoundCard, 48 kHz stereo)
  → aiortc WebRTC encoder (Opus)
  → direct local ICE host candidate (no STUN/TURN/cloud)
  → Galaxy A70 Chrome/PWA <audio>
  → Android media route → paired Bluetooth headphones
```

Nemotron is not placed in the media path. An LLM is useful for control or metadata, but it cannot make PCM/Opus transport more faithful; it would add latency and another failure point. The relay is deterministic local audio code.

## Safety boundary · גבולות בטיחות

- The phone sends only an SDP offer and session-close request. There is no shell, PowerShell, SSH, file, or arbitrary proxy endpoint.
- A fresh 48-bit pairing token is printed by every launch. It is sent in an HTTP header, never in the URL, service-worker cache, `localStorage`, or `sessionStorage`.
- Node validates the pairing token with constant-time comparison before forwarding signaling.
- The Python control sidecar is hard-limited to `127.0.0.1` and requires a separate 192-bit internal token.
- WebRTC is configured with `iceServers: []`: no public STUN server, TURN relay, or cloud media path.
- One phone session is allowed; a new authenticated session closes the old one.
- The launcher binds Node only to loopback plus one explicit physical LAN IPv4 address. It refuses `0.0.0.0`.
- No firewall rule, scheduled task, or persistent service is created by setup or launch.

WASAPI loopback captures the selected Windows output mix, not a single app. Protected/DRM audio may be unavailable to loopback. Use this only for audio you are entitled to play and relay.

## Setup on Windows · התקנה במחשב

From this directory in PowerShell:

```powershell
.\setup-music-relay.ps1 -ProbeWasapi
```

This creates `.venv`, installs the exact versions in `requirements-music.txt`, lists output devices, and optionally opens a real 20 ms WASAPI capture probe. It does **not** start a service.

To select a non-default Windows output, inspect the device list:

```powershell
.\.venv\Scripts\python.exe .\music_relay.py --list-devices
```

## Launch · הפעלה

```powershell
.\start-music-relay.ps1
```

The launcher detects one active physical LAN/Wi‑Fi IPv4, starts two hidden non-persistent processes, then prints:

- the A70 URL, such as `http://<lan-ip>:4173/#music-relay`;
- the one-launch pairing token;
- the exact capture device and process IDs.

Optional explicit choices:

```powershell
.\start-music-relay.ps1 -ListenAddress <lan-ip> -AudioDevice 'Speakers'
```

It does not start or alter the existing Grok SSH tunnel. Local AI controls remain present, but Grok generation still needs its separate existing runtime.

Stop only the processes recorded by this launch:

```powershell
.\stop-music-relay.ps1
```

The stop script validates each PID's command line against this project before stopping it. Logs stay under `.runtime`.

## A70 use · שימוש ב‑A70

1. Put the PC and Galaxy A70 on the same trusted Wi‑Fi/LAN.
2. Pair/connect the Bluetooth headphones in Android first.
3. Open the exact URL printed by the launcher.
4. Enter the printed pairing token and tap **Check**.
5. Tap **Connect**. This tap is the user gesture Android/Chrome may require for audio playback.
6. If sound comes from the phone speaker, use Android's media-output selector to choose the Bluetooth headphones.
7. Watch the on-page codec, bitrate, loss, jitter, route, and scrolling connection log.

Direct LAN HTTP can play a received WebRTC track, but service-worker/PWA installation features normally require a trusted HTTPS origin. The existing Tailscale HTTPS route can still serve the same UI; the acceptance test must inspect the selected ICE route before calling the media path local. A trusted local certificate is another option, but is not generated or installed automatically.

## Firewall, only if Windows blocks the phone

First preview the exact scope; this changes nothing:

```powershell
.\configure-private-firewall.ps1 -ListenAddress <lan-ip>
```

If reviewed and needed, rerun elevated with `-Apply`. It creates only:

- TCP `4173` for the exact Node executable, one local IP, `Private` profile, `LocalSubnet` remotes;
- dynamic UDP for the exact base Python runtime used by the project venv, one local IP, `Private` profile, `LocalSubnet` remotes (WebRTC ICE uses a dynamic UDP port). This is slightly broader than a frozen relay executable, so the helper remains dry-run by default.

Rollback is printed by the helper. No firewall change has been applied merely by building or testing this project.

## Acceptance tests · בדיקות קבלה

### PC-only automated proof

```powershell
.\test-music-relay.ps1 -ProbeWasapi
```

This runs:

1. static safety/regression tests for the existing PWA and new boundaries;
2. an actual Node-authenticated WebRTC offer/answer using a deterministic local tone;
3. receipt and decoding of a real Opus audio frame through the peer connection;
4. wrong-token rejection and authenticated session close;
5. with `-ProbeWasapi`, a second full peer connection carrying a real default-output WASAPI frame through Opus (silence is valid when the PC is not playing audio).

The tone smoke test uses random loopback TCP ports, starts no browser, touches no firewall, and terminates its child processes.

### Physical A70 + Bluetooth proof (must be performed on the devices)

Do not mark this verified until all items are observed in one fresh run:

- [ ] A70 is on the same trusted local network and the token is accepted.
- [ ] UI shows `Connected (Opus)`, growing bitrate/packet counters, and a host/local route.
- [ ] A known Windows marker track is audible on the A70 with intelligible left/right channels.
- [ ] Android shows the intended Bluetooth headphones as active media output and sound is heard in them.
- [ ] Muting/stopping the Windows source changes/stops the A70 audio.
- [ ] Turning A70 Wi‑Fi off breaks the stream (evidence that no fallback cloud path exists).
- [ ] Packet loss/jitter and subjective latency are recorded.

Current device status must remain **BLOCKED / UNVERIFIED** until that checklist is witnessed. A local PC tone test or `/health` response does not prove A70 or Bluetooth playback.

## Existing console behavior retained

- Grok health/generation remains same-origin under `/api/grok/*`.
- English Agent and Exact Raw remain visibly separate.
- Hebrew (`he-IL`) and English (`en-US`) voice-input choices remain.
- Remote actions remain drafts or explicit links requiring user approval.
- The service worker caches only the static shell and never API responses.

## Open-source components · מקורות חינמיים

No paid API or cloud audio service is required. Exact direct dependencies and source/license links are recorded in [THIRD_PARTY-NOTICES.md](THIRD_PARTY-NOTICES.md).

## Operational rollback

This new music feature has no scheduled task. Stop it with `stop-music-relay.ps1`. If optional firewall rules were explicitly applied, remove only these names:

```powershell
Remove-NetFirewallRule -DisplayName 'ALMA A70 Music Relay TCP Private LAN','ALMA A70 Music Relay WebRTC UDP Private LAN'
```

The older optional Tailscale/Grok tasks and their rollback remain separate from this launcher.
