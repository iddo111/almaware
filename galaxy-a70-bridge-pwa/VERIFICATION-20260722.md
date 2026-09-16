# Music Relay verification — 2026-07-22 (Asia/Jerusalem)

## VERIFIED locally

- `setup-music-relay.ps1` created an isolated `.venv`, installed the five pinned direct dependencies, and imported them successfully.
- Windows audio enumeration found seven output endpoints and matching WASAPI loopbacks. The current default was `Headphones (WH-1000XM4)`, stereo.
- `npm test`: 19/19 passed.
- `test/webrtc_smoke.py --source tone`: wrong pairing token rejected; authenticated Node proxy health passed; WebRTC offer/answer passed; `Opus/48000/2`; one 960-sample frame decoded with PCM peak 2890; `cloud=false`.
- `test/webrtc_smoke.py --source loopback`: the same authenticated WebRTC/Opus path carried one real 960-sample WASAPI loopback frame. The PC was silent during capture, so peak 0 is expected and is not evidence of audible content.
- Chrome responsive check at 412 × 915: music controls and accessibility tree present; no console errors; page height 2711 px; page `overflow-y:auto`; diagnostics log `max-height:150px` and `overflow-y:auto`; music card remained within the viewport.
- Production launcher briefly bound Node only to `127.0.0.1` and `<lan-ip>`, and bound sidecar control only to `127.0.0.1`. The scoped stop script stopped the exact recorded Node/Python processes.
- After verification, ports 4173, 4180, and 49173 were free and no A70 relay Node/Python process remained.
- No firewall rule, scheduled task, persistent service, STUN server, TURN server, or cloud audio endpoint was added.

## BLOCKED / not yet physically verified

- No Galaxy A70 browser was connected during this build run.
- No Android-selected Bluetooth-headphone output was observed.
- No known Windows marker track was heard on the A70/headphones.
- Phone-side packet counters, selected ICE candidate pair, packet loss, jitter, and subjective end-to-end latency were not recorded.

Therefore the PC capture/signaling/WebRTC/Opus implementation is locally verified, while **Windows → A70 → Bluetooth headphones end-to-end remains UNVERIFIED** until the physical checklist in `README.md` is completed.

---

## ✅ PHYSICAL E2E VERIFIED — 2026-08-10 ~06:0x (Asia/Jerusalem)

Iddo confirmed BY EAR: PC audio (WASAPI loopback of default output "Headphones (2- JBL TUNE510BT)") → WebRTC/Opus → Galaxy A70 (<lan-ip>) → second BT headphones = **audible, working now**.
Evidence trail: launcher 04:29 (bridge PID 200, relay PID 8876, token F76A4E1F40F6), ICE CandidatePair <lan-ip>:56830→<lan-ip>:60783 SUCCEEDED 04:33:28, "ICE completed", continuous WASAPI capture, Iddo voice-confirmation ~06:0x. The July "BLOCKED / not yet physically verified" section is now CLOSED (remaining unrecorded: packet loss/jitter numbers, marker-track L/R check).
