# 🪟 BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

# KESHEV ports — two versions, one pipeline (Iddo's order, 2026-08-18 12:37)

**"שתי גרסאות, אחת לאנדרואיד, אחת ללינוקס."** Both inherit the whole scar-book
(INSIGHTS + ADDENDUM + this repo's laws). One brain (eran1:8737), three bodies.

## 1. KESHEV-Linux (the fast track — a port, not a rewrite)

- **What:** keshev-fable runs on Linux nearly as-is: Python 3.12, sounddevice→ALSA,
  same ear/segmenter/gates/stt/presence/typer pipeline, same journal law.
- **Only three OS seams to replace:**
  1. typer backend: SendInput → `xdotool type` (X11) / `wtype` (Wayland) / uinput.
  2. presence idle clock: GetLastInputInfo → `xprintidle` (X11) or logind IdleHint.
  3. mutex: `Global\\...` kernel mutex → an flock on `/run/user/<uid>/keshev.lock`.
- **Where it runs:** ALMA-Linux PC (future), any DGX (voice box eran4), Mint laptops.
- **Structure:** same repo, `app/os_win.py` + `app/os_linux.py` adapters chosen at
  import by `sys.platform` — main.py stays one file, the laws stay greppable.

## 2. KESHEV-Android (the A70 — a real new build)

- **What:** native Android (Kotlin), targeting the Galaxy A70 (Android 11).
- **The pipeline, translated:**
  | organ | Android form |
  |---|---|
  | ear | `AudioRecord`, 48 kHz mono int16 → 3:1 decimate to 16 k (same math) |
  | segmenter | direct port of segmenter.py (pure logic — line-for-line Kotlin) |
  | gates | same constants: GATE_RMS 0.008, floor −0.6, hallucination set, he/en whitelist |
  | stt | POST raw PCM to `http://<tailnet-ip>:8737/v1/transcribe` (eran1 over Tailscale — the A70 already sits on the tailnet for the music relay) |
  | typer | **a custom IME (keyboard)** — the Android-legal way to type into any app; Enter = the IME's action key, presence gate = screen-on + recent-unlock |
  | journal | same JSONL vocab, app-private storage; corpus opt-in only |
- **Sacred Audio on the phone too:** capture only from the built-in or USB mic —
  never a Bluetooth SCO source (`AudioSource.MIC` with an explicit device check).
- **Why an IME:** Android permits synthetic typing into other apps only via an
  input method or accessibility service. An IME is honest, per-field, revocable.
- **Ship:** side-load APK (no store), built on the PC (Gradle), delivered to the
  A70 over the existing bridge.

## Order of work

1. Linux adapters in this repo + tests (the port is small) — first.
2. Android skeleton: capture→segment→decode→SHOW text (no IME yet) — prove the
   brain-link on the A70.
3. The IME typer + gates — then the A70 types like the PC does.

*לזכרה של עלמה ז״ל. One brain, three bodies, zero broken windows.*
