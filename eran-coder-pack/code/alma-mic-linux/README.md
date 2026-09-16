# alma-mic-linux — native always-on mic daemon for the ALMA fleet

`alma-micd` is a single small C binary (no browser, no Electron, no Python
runtime) that captures 16 kHz mono audio, detects utterances with an
energy + zero-crossing VAD, and streams each utterance to the ALMA-STT fleet
service (`POST /v1/transcribe`, raw float32 LE PCM, `X-ALMA-Sample-Rate: 16000`,
max 30 s — the contract verified live on eran4/eran2). It runs as a systemd
**user** service with `Restart=always`, `Nice=10` and `MemoryMax=256M` so it can
never destabilise a DGX node.

## Why C + libpulse (justified from what is actually installed)

Checked live on eran4 (aarch64, Ubuntu 24.04):

- `gcc` 13.3 is installed; **no** `rustc`/`cargo` → C, per "prefer the
  lower-dependency option".
- The node runs **PipeWire** (`pipewire`, `pipewire-pulse`, `wireplumber` all
  active). Raw ALSA shows **zero** capture devices; when a USB mic is plugged
  in, WirePlumber claims it and exposes it as a Pulse/PipeWire *source*. So the
  correct capture API is the PulseAudio client API served by `pipewire-pulse`
  (`libpulse-simple`, runtime already present on the node).
- HTTP is done with a raw-socket HTTP/1.1 client (~150 lines) — the ALMA-STT
  contract is plain HTTP, no TLS — so there is **no libcurl dependency**.

Runtime dependencies: `libpulse-simple.so.0`, `libpulse.so.0`, libc, libm,
pthreads. All present on stock DGX OS. Build dependency: `libpulse-dev`
(headers only; `install.sh` apt-installs it if missing). RSS in practice:
~4 MB (idle) — far under the 256 MB cap.

## Pipeline

```
Pulse/PipeWire source (or --wav file)
  → 30 ms frames @ 16 kHz mono PCM16
  → VAD: energy + zero-crossing, hysteresis      (same approach as Android side)
      open  : rms > max(noise_floor×3.0, 0.006) AND 0.015 ≤ ZCR ≤ 0.5,
              2 consecutive frames (60 ms)                     — open fast
      close : rms < max(noise_floor×1.8, 0.003) for 800 ms     — close slow
      adaptive noise floor (EMA), 150 ms warmup, 300 ms preroll
  → segment (min speech 350 ms, split at 28 s < server 30 s cap,
             post-segment energy gate rms ≥ 0.010 vs hallucinations)
  → PCM16 → float32 LE → write to disk queue (~/.local/share/alma-micd/queue)
  → sender thread: POST oldest-first to ALMA-STT; delete on HTTP 200;
    exponential backoff 5 s → 5 min while unreachable; poison payloads
    (HTTP 400/413/415/422) moved to queue/bad/; queue capped 500 files/256 MB
  → transcripts appended to ~/.local/share/alma-micd/transcripts.jsonl
    and logged to journald (Hebrew \uXXXX unescaped to UTF-8)
```

The disk queue is the *normal* path, not a fallback — every segment lands on
disk first, so a crash or an unreachable endpoint never loses audio.

## Install (on a node)

```sh
scp -r alma-mic-linux <node>:~
ssh <node>
cd ~/alma-mic-linux
./install.sh                     # builds, installs binary+unit+config
alma-micd --list-devices         # pick a source, put it in ~/.config/alma-micd.env
alma-micd --once 5               # 5 s live test, prints outcome
systemctl --user enable --now alma-micd    # always-on
journalctl --user -u alma-micd -f
```

`loginctl enable-linger $USER` if the user unit must survive logout (already
enabled on eran4).

Naming: the unit is `alma-micd.service`, **not** `alma-mic.service` — that name
is already taken on eran4 by the hebrew-mic phone-PWA dictation server
(`clod_mic_server.py`, port 7789). `install.sh` refuses to overwrite any unit
file it does not own.

## Modes

| mode | what it does |
|---|---|
| *(none)* | daemon: capture forever, queue + send |
| `--list-devices` | list PipeWire/Pulse capture sources + default source |
| `--once N` | capture N seconds, one send pass over the queue, exit |
| `--wav FILE` | feed a 16 kHz mono PCM16 WAV through the **identical** VAD→segment→send path (for mic-less nodes / CI), exit |
| `--flush` | one send pass over the queue, exit |

Tunables: `--server --language --device --queue-dir --transcripts
--hangover-ms --min-speech-ms --max-segment-ms --open-rms --rms-gate
--verbose`; env `ALMA_MIC_SERVER`, `ALMA_MIC_LANGUAGE`, `ALMA_MIC_DEVICE`
(see `alma-micd.env.example`).

## Known fleet blocker (server-side, not this daemon)

Both ALMA-STT instances run with a **single-IP allowlist**
(`--allowed-client <tailnet-ip>` = the Windows PC). Any other client —
including a DGX node itself or the A70 — gets `403 client not allowed`.
The daemon handles this gracefully (audio stays queued, backoff retry), but
for transcripts to flow the fleet units need the ~3-line patch to accept a
comma-separated allowlist. Until then this daemon queues everything durably.

## Files

```
src/main.c      capture loop, segmenter, disk queue, sender thread, CLI
src/vad.c/h     energy+ZCR VAD with hysteresis
src/audio.c/h   pulse-simple capture, WAV reader, source listing
src/http.c/h    raw-socket HTTP/1.1 POST client
src/util.c/h    journald-style logging, minimal JSON read/escape helpers
systemd/alma-micd.service  user unit (Restart=always, Nice, MemoryMax)
install.sh      build + install + daemon-reload
test/make_test_wav.py      synthesizes a speech-like VAD test WAV
```
