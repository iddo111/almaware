# ORDER OF THE COMMISSION — what to USE for עמותת המלאכים של ערן
## מסקנה מבצעית — הרפרנט

**בשורה אחת:** אין לבנות מחדש כלום חוץ מקושחת הקופסה ומצב-הקרטון. הכל כבר קיים בארבעה קבצים.
**One line:** nothing here needs rebuilding except the box firmware and the cardboard split-view. Four files already carry the rest.

---

## (a) PC — a REAL GUI window, shareable

**Base — use this:** `D:\CLAUDE\emdr\source-emdr-central\emdr_widget.py` (47,372 B, PyQt6, v0.4)

This is the only native window application in the entire record, and it is the one artifact Iddo ever explicitly approved: *"the emdr wdgt is spot on"* (`D:\CLAUDE\archive\_memory-hub\e-claude-memory\memory\newclaude\feedback_emdr_widget_pattern.md`). It ships with its own packaging chain already written — `_make_icon.py`, `_make_shortcut.ps1`, `_smoketest.ps1`, `EMDR_Widget.spec`, `emdr.ico` — which is exactly the "shareable" half of the requirement, already solved. A built binary exists at `D:\CLAUDE\emdr\v04-original\EMDR_Widget.exe` (70,435,783 B) and is running right now (PIDs 3824, 13092), though its bytes were written today 18:25 and its provenance is unverified.

**What is missing — the minimal delta:**

1. **It is a strip overlay, not a projector stage.** `EmdrSequence` (line 787) opens with `Qt.WindowType.Tool | FramelessWindowHint | WindowStaysOnTopHint | WindowTransparentForInput` and `setGeometry(0, STRIP_Y, screen.width(), STRIP_H)` — a translucent click-through band floating over one person's desktop. For a projector and a room you need a second mode: a real full-screen `QWidget` on a **chosen** screen (`QApplication.screens()` picker, so the projector is the target and his laptop stays usable), black background, large orb. The sweep math in `_tick()` (`phase = 2π·t·1000/period_ms`; `orb_x = mid + amp·sin(phase)`) is correct and must be reused verbatim — only the geometry changes.
2. **Zero USB output.** `grep -c serial emdr_widget.py` = **0**. It cannot drive the box. Add a writer emitting the protocol already defined in (b).
3. **English UI.** `setWindowTitle("EMDR Settings")`, all-English labels. Needs Hebrew RTL strings + עמותה branding.
4. Rebuild the exe with the existing `.spec`.

**Effort: 1–2 days.** Everything hard (audio panning with crash-safe restore, beep generation, settings persistence, tray, SOS button, icon/shortcut/exe pipeline) is already written.

**The alternative, and why I am not recommending it as the base:** `D:\CLAUDE\emdr\app\alma_emdr_launcher.py` already produces a chrome-less window (`--app=http://127.0.0.1:<port>`) and its docstring states the real reason for the local server — WebSerial requires a secure context, `file://` is not one, `http://127.0.0.1` is. That is genuinely good engineering and it is a "window, not a tab." **But it was written today, 2026-08-31 17:58, by the very session Iddo was angry at** ("אתה אשם בפתיחה של פרויקטים חדשים", 14:59). He has never seen it. Use it as the *body* of the group tool only if he says so; the approved widget is the safer base.

---

## (b) USB box driving 40 buzzer balls

**Nothing exists that does this. Say it plainly.**

- `D:\CLAUDE\emdr\source-emdr-central\EMDR1_Arduino\EMDR1.ino` (1,439 B) is the **stock Arduino Blink example**, header comment intact, modified only to alternate pins 2/7 and 4/5 at 1 Hz. Two channels in antiphase — a wiring proof, not a controller. No serial, no rate control, no sync to anything.
- `D:\CLAUDE\archive\_shopping_lists\emdr-physical-device.md` (~$90) specs **2** ERM motors + 2 DRV2605L + 1 ESP32 — one person, two balls. It is not a 20-person BOM and does not claim to be.

**Best base — and nobody has ever connected it to the EMDR work:**
`D:\CLAUDE\archive\diy\cerebro-helmet\04-FIRMWARE-CEREBRO.ino` (20,796 B, ESP32). It already has the two things you need and would otherwise write from scratch: a **working USB-serial command parser** (`MODE off|schumann|emdr|combo`, `RATE <float>` clamped 0.5–2.0 Hz, `STATUS`) and a **100 Hz bilateral envelope accumulator** (`g_envPhase += g_emdrRateHz * dt`) driving separate `PIN_LED_LEFT 25` / `PIN_LED_RIGHT 26`. It also carries a 30-minute session cap and a thermal cutoff — both worth keeping for a room full of people. The rest (AD9833 DDS, OLED, rotary encoder, thermistors) is helmet apparatus; delete it.

**The protocol is already written — by the page, not the firmware.** `ALMA-EMDR.html` line 338 onward: 115200 baud, newline-terminated ASCII — `?` identify, `I<power>`, `P<ms>`, `L`, `R`, `X` stop. **No firmware anywhere implements it.** That gap is the whole job.

**The architecture point that makes this cheap:** 20 people × 2 balls = 40 balls, but only **TWO logical channels** — all-left, then all-right. So the box is 2 channels fanned to 20 outputs each. The problem is current, not code: ~20 ERM discs per rail is roughly 1.6–2 A per rail — you need one N-channel MOSFET per rail with flyback diodes and a 5 V / 5 A supply, **not** the $8 supply in the BOM, and **not** DRV2605L (that is one driver per motor = 40 drivers, absurd at this scale).

**Delta:** ~150 lines of ESP32 firmware (Cerebro's parser + envelope, stripped to 2 pins, speaking the `L`/`R`/`I`/`P`/`X` protocol) + a revised BOM for 40 balls and 2 MOSFET rails.
**Effort:** firmware 1 day. Hardware: parts + assembling 40 balls and their cabling is realistically a week of hands. **The evidence contains no price for a 40-ball build** — the $90 figure is for two, and cable management for 40 tethered balls in a room is uncosted.

**Safety gate, inherited:** `D:\CLAUDE\.playwright-mcp\page-2026-06-11T15-43-08-795Z.yml` places EMDR-VR in a **HALT** row beside e-stim and strobe devices — risks named are unclosed-trauma self-therapy and seizure induction. Twenty people at once amplifies both. The BOM's own line — *"Wellbeing/educational use only — NOT a medical device"* — belongs physically on the box and on screen.

---

## (c) Phone (Android + iPhone) + cardboard + BT headphones + 2 balls

**Do NOT use the Godot VR app.** `D:\CLAUDE\archive\emdr-vive\project.godot` reads `openxr/enabled=true`, `config/description="Personal EMDR therapy tool for HTC Vive"`, viewport 1280×720, `config/features=("4.6","Forward Plus")`. Cardboard is not an OpenXR target, there is no mobile export preset anywhere in either Godot copy, and Forward Plus on a phone is wrong. Porting it is a rebuild, not a reuse.

**Base — use this:** `D:\CLAUDE\archive\projects\emdr-iddoperez\site\index.html` (52,312 B)
It already carries, verified in the file: `navigator.vibrate` (line 713), `requestFullscreen` (line 902), `createStereoPanner` (line 677), speed / dot-size / volume / timer controls, `prefers-reduced-motion` handling, plus 4·4·4·4 box breathing, 5-4-3-2-1 grounding, butterfly hug, safe place, the 8 phases, and crisis lines (ער״ן 1201, סה״ר). It runs from a URL on both platforms — no store, no install, no fee. That matches "cheapest possible."

**What is missing — the minimal delta:**

1. **Stereoscopic side-by-side view.** This is the one genuinely new piece: render the orb into two viewports with a small IPD offset so the cardboard lenses fuse it. Half a day on the existing page.
2. **Balls on the phone are not solved and the evidence contains nothing.** WebSerial **does not exist on iOS Safari at all**, and on Android needs Chrome + a USB-OTG adapter. A Bluetooth-LE ball box would solve it — **no design, no BOM, no code for one exists anywhere in the record.** That is a new hardware project, 2+ weeks, starting from zero.
3. The handset's own `navigator.vibrate` is a single motor — it physically cannot do left/right. Do not sell it as bilateral.

**Honest recommendation:** ship (c) as **cardboard + BT headphones**, where the existing `StereoPanner` does the real left/right work through the ears. That is genuinely complete after the SBS view. Balls-on-phone stays an open hardware item, declared as such.

---

## (d) Publishing on his site

**Nothing to build. The pipeline is proven three separate ways:**

1. `D:\CLAUDE\_consolidation\logs\_cf_named.err` — cloudflared named ingress `emdr.iddoperez.ai` → `127.0.0.1:8092`, independently audited **200 OK** on 2026-06-09.
2. `D:\CLAUDE\alma-emdr\wrangler.jsonc` — a Cloudflare Worker literally named `"emdr"`, `"assets": { "directory": "." }`, `workers_dev: true`. One `wrangler deploy` publishes whatever HTML sits beside it.
3. `D:\CLAUDE\iddoperez-portal\index.html` line 215 — the public card, currently pointing at `https://emdr-3p0.pages.dev`.

**What is missing is a decision, not code.** Three live surfaces point at three different builds, and **no source directory for `emdr-3p0` exists anywhere on D:** — that public card is a dead end. Pick ONE canonical URL (`emdr.iddoperez.ai` is the one with an audit trail), put one file behind it, repoint the portal card, retire the other two.

**Effort: about an hour**, once the file is chosen.

---

## DO NOT REBUILD — reuse these exact files

| file | what it already solves | for |
|---|---|---|
| `D:\CLAUDE\emdr\source-emdr-central\emdr_widget.py` | the entire native GUI: sweep engine, settings dialog, tray, SOS button, beep synthesis, playlist. **Iddo-approved.** | (a) |
| `D:\CLAUDE\emdr\source-emdr-central\soundcard_pan.py` | system-wide L↔R panning via Windows Core Audio, with a 0.15 floor that never fully mutes and atexit restore-on-crash. Honours the SACRED AUDIO LAW. Do not reimplement this. | (a) |
| `D:\CLAUDE\emdr\source-emdr-central\_make_icon.py` · `_make_shortcut.ps1` · `_smoketest.ps1` · `EMDR_Widget.spec` · `emdr.ico` | the whole icon → shortcut → exe → smoketest chain. This IS the delivery pattern he named as how he likes things done. | (a) |
| `D:\CLAUDE\archive\diy\cerebro-helmet\04-FIRMWARE-CEREBRO.ino` | ESP32 USB-serial command parser + 100 Hz bilateral envelope + session cap + thermal cutoff. Strip the helmet, keep the engine. | (b) |
| `D:\CLAUDE\archive\_shopping_lists\emdr-physical-device.md` | the 2-ball parts list and the "NOT a medical device" line. Scale it; don't restart it. | (b) |
| `D:\CLAUDE\archive\projects\emdr-iddoperez\site\index.html` | the full web suite: bilateral engine, vibrate, fullscreen, StereoPanner, breathing, grounding, butterfly hug, safe place, 8 phases, crisis lines. 52 KB of finished work. | (c), (d) |
| `D:\CLAUDE\emdr\app\ALMA-EMDR.html` | the WebSerial protocol definition (`?`/`I`/`P`/`L`/`R`/`X` @115200), SUD logging, Hebrew RTL, three themes, and the עמותת המלאכים של ערן branding — **already in the `<title>`**. Written today, never reviewed by Iddo. | (b) protocol, (a)/(c) content |
| `D:\CLAUDE\emdr\app\alma_emdr_launcher.py` | chrome-less window + the localhost-secure-context reason WebSerial works from an exe. | (a) |
| `D:\CLAUDE\alma-emdr\wrangler.jsonc` | the deploy target named `emdr`. | (d) |

**Duplicate, not a second build:** `D:\CLAUDE\archive\_pages_stage\iddoperez-emdr\index.html` is byte-identical to the 52 KB suite (same md5, same mtime). Edit one, not both.

---

## Two flags the commission must not bury

**1. Build #7 is this session's own.** `D:\CLAUDE\emdr\app\*` was created 2026-08-31 between 17:47 and 18:27 — and at **14:59** Iddo wrote *"זה מרגיז ברמות… אתה אשם בפתיחה של פרויקטים חדשים… תריץ וועדת חקירה על הכל."* The files are good and they target the עמותה by name, but presenting them as "what already exists" would be exactly the offence under investigation. They are five hours old and unseen by him. Label them as such when you hand them over.

**2. `D:\CLAUDE\emdr\phone\` contains one file: `tailscale-android-universal-1.102.3.apk`, 105 MB.** That is not a phone EMDR app. There is no Android or iOS EMDR artifact anywhere in the record — (c) genuinely starts from the web page.

**כלום לא צריך להיבנות מחדש חוץ מקושחת הקופסה ומצב הקרטון. / Nothing needs rebuilding except the box firmware and the cardboard view.**