# A70 Room-Ear for Eran — install in 60 seconds

Turn your Samsung Galaxy A70 into an always-on microphone that streams the room's
sound to the PC, feeding Eran's "heard world".

The PC must be on the **same Wi-Fi** as the phone. PC LAN IP: **<lan-ip>**.

---

## On the PC (one time)

The receiver should already be running. To (re)start it manually:

```
D:\CLAUDE\eran-audio\run_a70_receiver.cmd
```

It listens on **0.0.0.0:18190** and writes 16 kHz mono WAV files into
`D:\CLAUDE\eran-audio\heard_a70\`, which Eran's trainer scans automatically.

### Make it start at logon (optional, recommended)
Don't need a script — just drop a shortcut in the Startup folder:

1. Press `Win + R`, type `shell:startup`, Enter. (Opens the Startup folder.)
2. Right-click in the folder -> New -> Shortcut.
3. Target:
   `D:\CLAUDE\eran-audio\run_a70_receiver.cmd`
4. Name it `Eran A70 Receiver`, Finish.

(To run it hidden / windowless, set the shortcut's "Run" to *Minimized*, or wrap
it with a scheduled task at logon.)

---

## On the A70 phone (one time)

1. Open **Chrome**.
2. Go to:  **http://<lan-ip>:18190/**
3. Chrome menu (⋮) -> **Add to Home screen** -> Add. (Now it's an app icon.)
4. Open the **"אוזן ערן"** app from the home screen.

## Every time you want Eran to listen

1. Open the **אוזן ערן** app.
2. Tap the big **התחל האזנה** (START) button.
3. When Chrome asks, tap **Allow** for the microphone.
4. The button turns red and pulses; the number counts up = chunks sent to Eran.
5. **Keep the screen on** (the app asks Android to keep it awake while listening).
   Plug the phone into a charger for overnight listening.

## To stop

- Tap the red **עצור האזנה** (STOP) button, or just close the app.

---

## Confirm audio is actually arriving (from the PC)

```
curl http://127.0.0.1:18190/ping       ->  pong
curl http://127.0.0.1:18190/health     ->  {"saved": N, "rejected": M, "last": "a70_...wav", ...}
```

- `saved` should climb by 1 roughly every 10 seconds while the phone streams.
- New files appear in `D:\CLAUDE\eran-audio\heard_a70\` named
  `a70_YYYYMMDD_HHMMSS_microsec.wav`.
- Live log: `D:\CLAUDE\eran-audio\a70_receiver.log`

To verify a file is good audio (16 kHz mono):
```
ffprobe -v error -show_entries stream=sample_rate,channels D:\CLAUDE\eran-audio\heard_a70\<file>.wav
```

---

## Notes
- This is a **separate** server from the dispatch inbox (port 18180) and the
  Hebrew dictation mic — it does not touch either, and uses no GPU.
- iOS/Safari blocks background mic, so this is built for the Android A70 with the
  screen kept awake. For 24/7 use, leave the phone on the charger, screen on,
  app open.
- Audio is sent over the LAN in the clear to your own PC. Keep it to your home
  Wi-Fi. Anyone on the same Wi-Fi could POST to :18190 — fine for a home network.
