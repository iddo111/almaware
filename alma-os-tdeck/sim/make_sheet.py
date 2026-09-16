#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render the one-page ALMA-OS simulator sheet to JPEG + PDF on the Desktop.
HTML is authored in the scratchpad and never delivered; only jpg+pdf land on
the Desktop, per the deliverable rule. לזכרה של עלמה ז"ל · ALMAWARE"""
import base64, os, subprocess, sys, glob

SIM = os.path.dirname(os.path.abspath(__file__))
SCRATCH = r"C:\Users\<user>\AppData\Local\Temp\claude\D--CLAUDE\0bb19b15-e55e-4ca6-b4d0-9b011e3200b3\scratchpad"
DESK = os.path.join(os.path.expanduser("~"), "Desktop")
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


def b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def main():
    chat = b64(os.path.join(SIM, "shot_chat.png"))
    about = b64(os.path.join(SIM, "shot_about.png"))
    try:
        serial = open(os.path.join(SIM, "qemu_serial.log"), encoding="utf-8",
                      errors="replace").read().strip()
    except Exception:
        serial = "(no qemu log)"

    html = """<!doctype html><html lang="he"><head><meta charset="utf-8"><style>
@page {{ size: A4; margin: 12mm; }}
body {{ font-family: "Segoe UI", Arial, sans-serif; background:#fff; color:#111;
        margin:0; padding:26px 30px; }}
h1 {{ font-size:27px; margin:0 0 2px 0; color:#0a58c8; }}
.sub {{ font-size:14px; color:#555; margin-bottom:4px; }}
.mem {{ font-size:12px; color:#888; margin-bottom:18px; }}
.shots {{ display:flex; gap:18px; margin-bottom:16px; }}
.shot {{ flex:1; }}
.shot img {{ width:100%; border:2px solid #c8d4e6; border-radius:6px;
             image-rendering:pixelated; display:block; }}
.cap {{ font-size:12px; color:#666; margin-top:5px; text-align:center; }}
.box {{ border:1px solid #d8e0ec; border-left:5px solid #0a58c8; border-radius:6px;
        padding:11px 15px; margin-bottom:11px; background:#f7faff; }}
.box h2 {{ font-size:14px; margin:0 0 6px 0; color:#0a58c8;
           text-transform:uppercase; letter-spacing:.4px; }}
.he {{ direction:rtl; text-align:right; font-size:13.5px; line-height:1.6; }}
.en {{ font-size:13px; line-height:1.55; color:#333; }}
pre {{ background:#0f1420; color:#c9e2ff; border-radius:6px; padding:9px 12px;
       font-size:10.5px; line-height:1.4; margin:6px 0 0 0; overflow:hidden;
       font-family:Consolas,monospace; }}
.link {{ font-size:19px; color:#0a58c8; font-weight:600; font-family:Consolas,monospace; }}
.bad {{ border-left-color:#d97706; background:#fffbf3; }}
.bad h2 {{ color:#b45309; }}
ul {{ margin:5px 0 0 0; padding-inline-start:20px; }}
li {{ margin-bottom:3px; }}
</style></head><body>

<h1>ALMA-OS &middot; T-Deck &mdash; רץ במכונה וירטואלית</h1>
<div class="sub">ALMA-OS running in a virtual machine &mdash; 2026-09-06</div>
<div class="mem">לזכרה של עלמה ז"ל &middot; ALMAWARE</div>

<div class="shots">
  <div class="shot"><img src="data:image/png;base64,{chat}">
    <div class="cap">כרטיס הצ'אט / the chat card &mdash; 320&times;240</div></div>
  <div class="shot"><img src="data:image/png;base64,{about}">
    <div class="cap">כרטיס המערכת / the מערכת card</div></div>
</div>

<div class="box">
  <h2>אין צורך בביוס / The BIOS was never the problem</h2>
  <div class="he">ALMA-OS היא קושחת ESP32-S3 &mdash; מעבד Xtensa, לא x86.
     אמולציה של מעבד <b>אחר</b> היא תרגום תוכנה טהור, ו-VT-x לא נותן לה כלום.</div>
  <div class="en">ALMA-OS is ESP32-S3 (Xtensa) firmware. Emulating a <b>different</b>
     CPU is pure software translation &mdash; hardware virtualization buys nothing.</div>
</div>

<div class="box">
  <h2>מסלול ב' &mdash; המסך למעלה / Route B &mdash; the screens above</h2>
  <div class="he">הקושחה האמיתית שלך (main.cpp, display_st7789.cpp, radio_sx1262.cpp)
     הודרה <b>ללא שינוי</b> מול מסך ST7789 וירטואלי. כל פיקסל למעלה צויר על ידי
     הדרייבר שלך. חי, עם מקלדת וכדור-מסלול:</div>
  <div class="en">Your real firmware, compiled <b>unmodified</b> against a virtual
     ST7789 that decodes his own CASET/RASET/RAMWR byte stream. Live, with the
     keyboard and trackball wired up:</div>
  <div class="link" style="margin-top:7px">http://127.0.0.1:8864/</div>
</div>

<div class="box">
  <h2>מסלול א' &mdash; QEMU רשמי / Route A &mdash; official Espressif QEMU</h2>
  <div class="he">קובץ ה-flash האמיתי (16MB) עולה על ESP32-S3 וירטואלי ומדפיס את
     שורות ה-log שלך. <b>אין תמונה שם</b> &mdash; QEMU לא מדמה ST7789 ולא SX1262.</div>
  <div class="en">The real 16 MB flash image boots on a virtual ESP32-S3 and prints
     his own log lines. <b>No picture there</b> &mdash; QEMU models no ST7789, no SX1262.</div>
  <pre>{serial}</pre>
</div>

<div class="box bad">
  <h2>שני באגים אמיתיים שהסימולטור מצא / two real bugs it found</h2>
  <div class="he"><ul>
    <li>הפונט (124 תווים) חסר · ו-↵ ו-◀ ▶ &mdash; הם מצוירים כריבוע ריק במסכים שלך.</li>
    <li>שורה ארוכה מ-40 תווים נחתכת בשקט: drawGlyph מוותר כש-x&lt;0, בלי גלישת שורה.</li>
  </ul></div>
  <div class="en"><ul>
    <li>The 124-glyph font lacks &middot; &#8629; &#9664; &#9654; &mdash; they draw as a hollow box in his own UI strings.</li>
    <li>Lines over 40 chars are silently truncated: drawGlyph bails when x&lt;0; there is no wrap.</li>
  </ul></div>
</div>

</body></html>""".format(chat=chat, about=about, serial=serial)

    os.makedirs(SCRATCH, exist_ok=True)
    hp = os.path.join(SCRATCH, "alma_os_sim_sheet.html")
    with open(hp, "w", encoding="utf-8") as f:
        f.write(html)

    url = "file:///" + hp.replace("\\", "/")
    png = os.path.join(SCRATCH, "alma_os_sim_sheet.png")
    pdf = os.path.join(DESK, "ALMA-OS-Simulator.pdf")
    common = [EDGE, "--headless=new", "--disable-gpu", "--no-first-run",
              "--no-default-browser-check", "--hide-scrollbars"]
    subprocess.run(common + ["--screenshot=" + png, "--window-size=1240,1740", url],
                   check=False, capture_output=True, timeout=120)
    subprocess.run(common + ["--print-to-pdf=" + pdf, "--no-pdf-header-footer", url],
                   check=False, capture_output=True, timeout=120)

    from PIL import Image
    jpg = os.path.join(DESK, "ALMA-OS-Simulator.jpg")
    im = Image.open(png).convert("RGB")
    im.save(jpg, "JPEG", quality=92)
    print("JPEG:", jpg, im.size)
    print("PDF :", pdf, os.path.exists(pdf) and os.path.getsize(pdf))


if __name__ == "__main__":
    main()
