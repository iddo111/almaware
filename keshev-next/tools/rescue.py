"""KESHEV RESCUE -- what Iddo can run alone at 3 a.m. when the mic is dead.

🪟 BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY.

Design rules, all of them load-bearing:

  * IT NEVER OPENS THE MICROPHONE. Not once, not for a level test, not to
    enumerate. Devices are read out of the registry (winreg, read-only);
    decoders are asked over HTTP GET /health; processes are read with tasklist.
    The Sacred Audio Law is not something a diagnostic gets to bend.

  * STDLIB ONLY. No sounddevice, no requests, no numpy, no imports from
    app/ -- because every one of those is a way for the rescue tool to be
    broken by the thing it is supposed to rescue. At 3 a.m. this must run.

  * IT DIAGNOSES BY DEFAULT AND REPAIRS ONLY ON A KEYPRESS. Nothing here
    changes the machine unless Iddo types a number and presses Enter.

  * EVERY LINE IS HEBREW FIRST, THEN A SHORT ENGLISH TAG. If the console font
    eats Hebrew, the English still says what happened.

The four failures it is built for, all of which really happened:
  1. a PAUSED file left behind by an agent (2026-09-03 22:55 -> 06:34, one
     whole night; the window looked alive BECAUSE the pause kept the log busy)
  2. a window with no engine behind it, or a stale mic.pid
  3. the decoder unreachable -- and main.py's wait_until_ready() blocks
     FOREVER on purpose, so an unreachable decoder is a silent dead mic
  4. KESHEV_STT_URL pointing somewhere that is not running (the :8738 trap)
"""

import os
import sys
import time
import json
import socket
import subprocess
import urllib.request
import urllib.error

KESHEV_NEXT = r"D:\CLAUDE\keshev-next"
STATE = os.path.join(KESHEV_NEXT, "state")
PAUSE_FILE = os.path.join(STATE, "PAUSED")
MIC_PID_FILE = os.path.join(STATE, "mic.pid")
HEARTBEAT = os.path.join(STATE, "gui.heartbeat")
MIC_CHOICE = os.path.join(STATE, "mic-choice.json")
TRIAL_LOG = os.path.join(KESHEV_NEXT, "trial.log")
GUI_CRASH = os.path.join(STATE, "gui-crash.log")
RUN_KESHEV = os.path.join(KESHEV_NEXT, "RUN-KESHEV.cmd")
RUN_STT_PC = r"D:\CLAUDE\mic-rebuild\RUN-STT-PC.cmd"
TOKEN_FILE = r"D:\CLAUDE\mic-rebuild\state\stt-token"

# The three decoders that exist on this machine and fleet, and what they are.
DECODERS = [
    ("http://127.0.0.1:8737", "המפענח של המחשב (PC)", "PC :8737"),
    ("http://<lan-ip>:8737", "המפענח של ערן1 (הראשי כרגע)", "eran1 :8737"),
    ("http://127.0.0.1:8738", "קשב-6 (החדש, לא נבחר)", "keshev-6 :8738"),
]

# Bluetooth / headset names the Sacred Audio Law forbids as an input, ever.
FORBIDDEN = ("wh-1000", "hands-free", "handsfree", "headset", "bluetooth",
             "vive", "index", "quest", "rift", "oculus", "virtual",
             "stereo mix", "what u hear", "loopback")

problems = []   # (severity, hebrew, english, repair_key or None)


def say(he, en=""):
    line = he if not en else f"{he}   [{en}]"
    try:
        print(line)
    except UnicodeEncodeError:
        print(en or "?")


def hr():
    print("-" * 74)


def head(t):
    print()
    print("=" * 74)
    say(t)
    print("=" * 74)


def ago(seconds):
    """Human Hebrew for an age in seconds."""
    if seconds is None:
        return "לא ידוע"
    s = int(seconds)
    if s < 90:
        return f"{s} שניות"
    if s < 5400:
        return f"{s // 60} דקות"
    return f"{s // 3600} שעות ו-{(s % 3600) // 60} דקות"


# ── processes ────────────────────────────────────────────────────────────────

def python_command_lines():
    """Every live python command line. WMIC is gone on Win11, so use PowerShell
    CIM -- but never fail hard: an empty list is an honest answer."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name like '%python%'\" | "
             "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }"],
            capture_output=True, text=True, timeout=40,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        rows = []
        for line in out.stdout.splitlines():
            if "\t" in line:
                pid, cl = line.split("\t", 1)
                try:
                    rows.append((int(pid.strip()), cl.strip()))
                except ValueError:
                    pass
        return rows
    except Exception:
        return []


def pid_alive(pid):
    if not pid:
        return False
    try:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                             capture_output=True, text=True, timeout=20,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return str(pid) in out.stdout
    except Exception:
        return False


# ── decoders ─────────────────────────────────────────────────────────────────

def token():
    try:
        with open(TOKEN_FILE, encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def health(base, timeout=4.0):
    """(state, detail). Never raises. UNREACHABLE is an honest third answer."""
    req = urllib.request.Request(base + "/health",
                                 headers={"Authorization": "Bearer " + token()})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:
            return "UNREACHABLE", f"HTTP {e.code}"
    except Exception as e:
        return "UNREACHABLE", type(e).__name__
    try:
        d = json.loads(body)
        return str(d.get("state", "?")), ", ".join(str(m) for m in d.get("models", []))[:60]
    except ValueError:
        return "UNREACHABLE", "bad json"


def effective_stt_url():
    """WHICH decoder the mic will actually use, and why. This is the trap that
    cost 2026-09-04: RUN-KESHEV.cmd sets the URL inline (setlocal), so it wins
    for a launch through the icon -- but a user-level setx wins for every OTHER
    way of starting it, and nothing on screen tells them apart."""
    user_level = ""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            user_level = str(winreg.QueryValueEx(k, "KESHEV_STT_URL")[0])
    except Exception:
        user_level = ""
    in_cmd = ""
    try:
        with open(RUN_KESHEV, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                s = line.strip()
                if s.lower().startswith("set keshev_stt_url="):
                    in_cmd = s.split("=", 1)[1].strip()
    except OSError:
        pass
    return in_cmd, user_level


# ── devices, WITHOUT opening one ─────────────────────────────────────────────

def capture_devices():
    """Capture endpoints that are PRESENT, by full name ("Microphone (Logitech
    BRIO)"). Get-PnpDevice enumerates the PnP tree -- it never opens an audio
    endpoint, never starts a stream, and cannot flip a Bluetooth headset into
    HFP. That distinction is the Sacred Audio Law and it is why this is not
    done with sounddevice.

    NOTE for whoever maintains this: the MMDevices registry alone is NOT enough.
    Its friendly-name properties are empty on this machine, so it yields only
    "Microphone" for every USB mic -- which produced a FALSE "your mic is gone"
    alarm the first time this tool ran. A false alarm at 3 a.m. is worse than
    no tool. Returns [(full_name, present_bool)]."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "Get-PnpDevice -Class AudioEndpoint -ErrorAction SilentlyContinue | "
             "ForEach-Object { \"$($_.Status)`t$($_.FriendlyName)\" }"],
            capture_output=True, text=True, timeout=60,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        rows = []
        for line in out.stdout.splitlines():
            if "\t" not in line:
                continue
            status, name = line.split("\t", 1)
            name = name.strip()
            if not name:
                continue
            # Endpoints we cannot dictate into are noise here: keep inputs only.
            low = name.lower()
            if not any(w in low for w in ("microphone", "mic", "line in",
                                          "headset", "input", "cortex")):
                continue
            rows.append((name, status.strip().upper() == "OK"))
        return rows
    except Exception:
        return []


# ── the log, summarised ──────────────────────────────────────────────────────

def tail_lines(path, kb=192):
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            fh.seek(max(0, size - kb * 1024))
            data = fh.read()
        return data.decode("utf-8", "replace").splitlines()
    except OSError:
        return []


def summarise_log():
    """What the engine has actually been doing, counted -- not guessed.

    Scoped to the CURRENT session: everything after the last
    "=== gui start mic" marker. Counting the whole tail mixes last night's
    disaster into this morning's verdict, which is exactly the kind of stale
    history that armed a false Administrator banner on 2026-09-03 08:20."""
    lines = tail_lines(TRIAL_LOG)
    start = 0
    for i, ln in enumerate(lines):
        if ln.startswith("=== gui start mic"):
            start = i
    session = lines[start:]
    lines = session if len(session) > 3 else lines
    c = {"typed": 0, "paused": 0, "quiet": 0, "noise": 0, "vadskip": 0,
         "empty": 0, "fail": 0, "deaf": 0, "waiting": 0, "beats": 0, "blocked": 0}
    for ln in lines:
        if ln.startswith("[paused]"):
            c["paused"] += 1
        elif "SKIP too-quiet" in ln:
            c["quiet"] += 1
        elif "SKIP steady-noise" in ln:
            c["noise"] += 1
        elif "vad=" in ln and " SKIP" in ln:
            c["vadskip"] += 1
        elif "decode=empty" in ln:
            c["empty"] += 1
        elif "decode=fail" in ln:
            c["fail"] += 1
        elif "decode=ok" in ln:
            c["typed"] += 1
        elif "[mic] DEAF" in ln:
            c["deaf"] += 1
        elif "waiting for the decoder" in ln:
            c["waiting"] += 1
        elif "[mic] heartbeat:" in ln:
            c["beats"] += 1
        elif "BLOCKED admin-window" in ln:
            c["blocked"] += 1
    return c, lines


# ═══════════════════════════════ THE DIAGNOSIS ═══════════════════════════════

def diagnose():
    head("קשב — בדיקה / KESHEV RESCUE — diagnosis")
    say(time.strftime("%Y-%m-%d %H:%M:%S"))

    # ---- 1. PAUSED ---------------------------------------------------------
    hr()
    if os.path.exists(PAUSE_FILE):
        try:
            since = open(PAUSE_FILE, encoding="utf-8").read().strip()
        except OSError:
            since = "?"
        age = time.time() - os.path.getmtime(PAUSE_FILE)
        say("🔴 המיקרופון מושהה. הוא לא יקליד כלום.", "PAUSED file present")
        say(f"   מושהה מאז {since} — כלומר כבר {ago(age)}.")
        if age > 3600:
            say("   זה הרבה יותר מדי. כמעט בטוח שמישהו שכח לבטל.",
                "stale pause — almost certainly forgotten")
        problems.append(("RED", "המיקרופון מושהה", "PAUSED file", "1"))
    else:
        say("🟢 אין השהיה.", "not paused")

    # ---- 2. window + engine ------------------------------------------------
    hr()
    procs = python_command_lines()
    gui = [(p, c) for p, c in procs if "keshev-next" in c.lower() and "gui" in c.lower()]
    eng = [(p, c) for p, c in procs if "keshev-next" in c.lower() and "main.py" in c.lower()]
    rival = [(p, c) for p, c in procs
             if ("client.app" in c and "mic-rebuild" in c.lower())
             or ("alma-mic" in c.lower() and "app.py" in c.lower())]

    if gui:
        say(f"🟢 חלון קשב פועל (pid {gui[0][0]}).", "window running")
    else:
        say("🔴 חלון קשב לא פועל.", "window NOT running")
        problems.append(("RED", "אין חלון", "no window", "2"))

    if eng:
        say(f"🟢 מנוע ההקלטה פועל (pid {eng[0][0]}).", "engine running")
    else:
        say("🔴 מנוע ההקלטה לא פועל — גם אם החלון פתוח, אף מילה לא נקלטת.",
            "engine NOT running")
        if gui:
            problems.append(("RED", "חלון בלי מנוע", "window with no engine", "2"))

    pid = 0
    try:
        if os.path.exists(MIC_PID_FILE):
            pid = int(open(MIC_PID_FILE).read().strip() or "0")
    except Exception:
        pid = 0
    if pid and not eng and pid_alive(pid):
        say(f"🟠 mic.pid מצביע על תהליך {pid} שחי אבל הוא לא המנוע. "
            "החלון יחשוב שיש מיק ולא יפעיל אחד.",
            "STALE mic.pid points at a live unrelated process — window will refuse to start the engine")
        problems.append(("RED", "mic.pid תקוע", "stale mic.pid", "5"))
    elif pid and not pid_alive(pid):
        say(f"🟠 mic.pid מצביע על תהליך מת ({pid}). לא מזיק, אבל מלוכלך.",
            "dead mic.pid — harmless")

    if os.path.exists(HEARTBEAT):
        hb = time.time() - os.path.getmtime(HEARTBEAT)
        if hb > 60:
            say(f"🟠 פעימת החלון ישנה ({ago(hb)}). המנוע כובה את עצמו אחרי 60 שניות.",
                "heartbeat stale — the deadman switch will have killed the engine")
        else:
            say(f"🟢 פעימת החלון טרייה ({ago(hb)}).", "heartbeat fresh")
    else:
        say("⚪ אין קובץ פעימה — סימן שהחלון סגור.", "no heartbeat file")

    if rival:
        say(f"🔴 מיקרופון מתחרה פועל (pid {rival[0][0]}). שניים מקלידים יחד = ג'יבריש.",
            "RIVAL mic running — two typers")
        problems.append(("RED", "שני מיקרופונים", "rival mic", None))

    # ---- 3. the decoder ----------------------------------------------------
    hr()
    in_cmd, user_level = effective_stt_url()
    say("איזה מפענח המיק באמת ישתמש בו:", "which decoder the mic will use")
    say(f"   מתוך RUN-KESHEV.cmd: {in_cmd or '(לא מוגדר)'}")
    say(f"   מתוך משתני הסביבה:  {user_level or '(לא מוגדר)'}")
    if in_cmd:
        say("   → הפעלה מהאייקון תשתמש בזה שמתוך ה-cmd.", "icon launch uses the cmd value")
    chosen = in_cmd or user_level

    states = {}
    for base, he, en in DECODERS:
        st, models = health(base)
        states[base] = st
        mark = "🟢" if st == "READY" else ("🟠" if st == "LOADING" else "🔴")
        star = "  ← זה שנבחר" if chosen.startswith(base) else ""
        say(f"   {mark} {he}: {st}{star}", f"{en} {st} {models}")

    if chosen:
        cbase = chosen.split("/v1/")[0]
        if states.get(cbase) != "READY":
            say("🔴 המפענח שנבחר לא עונה. זו התקלה השקטה הגרועה מכולן:",
                "chosen decoder not READY")
            say("   המיק פשוט לא ייפתח, ויחכה לנצח בלי להגיד כלום.",
                "main.py wait_until_ready() blocks FOREVER")
            problems.append(("RED", "המפענח לא עונה", "decoder unreachable", "3"))
        else:
            say("🟢 המפענח שנבחר עונה.", "chosen decoder READY")

    if user_level and "8738" in user_level:
        say("🟠 שים לב: משתנה הסביבה עדיין מצביע על 8738 — המפענח שירה הזיות "
            "לתוך הצ'אט ב-04/09 והוחזר אחורה. ה-cmd מגן עליך, אבל כל הפעלה אחרת לא.",
            "user env still points at :8738 (the rolled-back decoder)")
        problems.append(("ORANGE", "משתנה סביבה מצביע על 8738",
                         "env still :8738", "4"))

    # ---- 4. the device -----------------------------------------------------
    hr()
    choice = {}
    try:
        choice = json.load(open(MIC_CHOICE, encoding="utf-8"))
    except Exception:
        pass
    want = choice.get("name", "")
    if want:
        say(f"המיק שנבחר: {want}", f"chosen: {want}")
    else:
        say("המיק שנבחר: ברירת מחדל של המחשב.", "chosen: PC default")

    devs = capture_devices()
    present = [n for n, ok in devs if ok]
    if not devs:
        say("⚪ לא הצלחתי לקרוא את רשימת המכשירים.", "device list unreadable")
    else:
        say(f"מכשירי קלט שמחוברים עכשיו: {len(present)}",
            f"{len(present)} capture endpoints present")
        for n in present:
            bad = any(f in n.lower() for f in FORBIDDEN)
            say(("   ⛔ " if bad else "   ✓ ") + n)
        if want:
            if any(want.lower() == p.lower() for p in present):
                say(f"🟢 המיק שנבחר מחובר.", "chosen device present")
            else:
                say(f"🔴 המיק שנבחר ({want}) לא מחובר. "
                    "כנראה נותק, כובה, או ש-USB אחר תפס את מקומו.",
                    "chosen device is NOT present")
                problems.append(("RED", "המיק שנבחר לא מחובר",
                                 "chosen device missing", None))
        if any(any(f in n.lower() for f in FORBIDDEN) for n in present):
            say("   (⛔ = אסור לפי חוק השמע הקדוש. הגדר עוקף אותם — "
                "אבל אל תבחר אחד מהם ידנית לעולם.)",
                "forbidden endpoints exist; the engine's fence refuses them")

    # ---- 5. what the log says ---------------------------------------------
    hr()
    c, lines = summarise_log()
    log_age = None
    try:
        log_age = time.time() - os.path.getmtime(TRIAL_LOG)
    except OSError:
        pass
    say(f"היומן עודכן לפני {ago(log_age)}.", f"trial.log age {ago(log_age)}")
    say(f"בהפעלה האחרונה של המיק ({len(lines)} שורות): הוקלד {c['typed']} · "
        f"מושהה {c['paused']} · שקט-מדי {c['quiet']} · רעש-קבוע {c['noise']} · "
        f"ריק {c['empty']} · כשל {c['fail']} · חירש {c['deaf']} · המתנה {c['waiting']}",
        "log verdict counts")

    if c["paused"] > 20 and c["typed"] == 0:
        say("🔴 היומן מלא ב'מושהה' ואפס הוקלד — זה בדיוק הלילה שאבד ב-03/09.",
            "log is all [paused], nothing typed")
    if c["deaf"] > 0:
        say("🔴 המיק הכריז על עצמו חירש: הזרם פתוח ולא מגיע שמע.",
            "engine declared itself DEAF")
        problems.append(("RED", "המיק חירש", "DEAF", None))
    if c["waiting"] > 0 and c["typed"] == 0:
        say("🔴 המיק תקוע בהמתנה למפענח.", "stuck waiting for the decoder")
    if c["blocked"] > 0:
        say("🟠 היו חסימות הקלדה לחלון שרץ כמנהל (Administrator). "
            "פתח את החלון שאליו אתה מכתיב בלי 'הרץ כמנהל'.",
            "UIPI blocks — target window is elevated")
    if c["quiet"] > 5 * max(1, c["typed"]):
        say("🟠 הרבה מאוד מקטעים נזרקו כ'שקט מדי'. "
            "בדוק את מפלס הכניסה של המיק בווינדוס (הוא צריך להיות 100%).",
            "many too-quiet drops — check the Windows input level")

    if os.path.exists(GUI_CRASH):
        cage = time.time() - os.path.getmtime(GUI_CRASH)
        if cage < 86400:
            say(f"🟠 החלון קרס בפעם האחרונה לפני {ago(cage)} — "
                "הפרטים ב-state\\gui-crash.log",
                "recent gui crash")

    # ---- the verdict -------------------------------------------------------
    head("שורה תחתונה / VERDICT")
    reds = [p for p in problems if p[0] == "RED"]
    if not problems:
        say("🟢 לא מצאתי שום דבר שבור. אם המיק עדיין לא מקליד — "
            "ודא שהחלון שאתה מכתיב אליו בפוקוס ולא רץ כמנהל.",
            "nothing broken found")
    else:
        for sev, he, en, key in problems:
            say(("🔴 " if sev == "RED" else "🟠 ") + he, en)
    return problems


# ═══════════════════════════════ THE REPAIRS ═════════════════════════════════

def repair_menu():
    print()
    hr()
    say("תיקונים — אף אחד מהם לא קורה בלי שתבחר מספר ותלחץ Enter:",
        "repairs — nothing happens without your keypress")
    say("  1  לבטל את ההשהיה (למחוק את קובץ PAUSED)", "1 remove PAUSED")
    say("  2  להפעיל את חלון קשב (בדיוק כמו האייקון)", "2 start the KESHEV window")
    say("  3  להפעיל את המפענח של המחשב (:8737)", "3 start the PC decoder")
    say("  4  לנקות את משתנה הסביבה KESHEV_STT_URL", "4 clear KESHEV_STT_URL")
    say("  5  לנקות mic.pid תקוע", "5 clear a stale mic.pid")
    say("  9  לבדוק שוב", "9 re-run the diagnosis")
    say("  0  לצאת בלי לגעת בכלום", "0 quit, change nothing")
    hr()
    try:
        return input("> ").strip()
    except (EOFError, KeyboardInterrupt):
        return "0"


def do_repair(key):
    if key == "1":
        if not os.path.exists(PAUSE_FILE):
            say("אין מה לבטל — הוא לא מושהה.", "not paused")
            return
        try:
            stamp = time.strftime("%Y%m%d-%H%M%S")
            os.replace(PAUSE_FILE, PAUSE_FILE + ".removed-" + stamp)
            say("✅ ההשהיה בוטלה. הקובץ נשמר בצד, לא נמחק.",
                "PAUSED moved aside, not deleted")
            say("   אם החלון פתוח — הוא יבחין בזה תוך שנייה.", "the window picks it up in ~0.3s")
        except OSError as e:
            say(f"❌ לא הצלחתי: {e}", "failed")

    elif key == "2":
        say("מפעיל את חלון קשב, בדיוק דרך RUN-KESHEV.cmd...",
            "launching via RUN-KESHEV.cmd")
        try:
            subprocess.Popen(["cmd", "/c", "start", "", RUN_KESHEV],
                             cwd=KESHEV_NEXT, shell=False)
            say("✅ נשלח. החלון אמור להיפתח תוך כמה שניות.", "launched")
        except Exception as e:
            say(f"❌ לא הצלחתי: {e}", "failed")

    elif key == "3":
        st, _ = health("http://127.0.0.1:8737")
        if st == "READY":
            say("המפענח של המחשב כבר עונה. לא נגעתי.", "already READY")
            return
        say("מפעיל את המפענח של המחשב. הטעינה לוקחת בין 20 שניות לכמה דקות.",
            "starting the PC decoder; model load takes 20s-7min")
        try:
            subprocess.Popen(["cmd", "/c", "start", "", RUN_STT_PC],
                             cwd=os.path.dirname(RUN_STT_PC), shell=False)
            say("✅ נשלח. חכה שהבדיקה תראה READY לפני שתפעיל את המיק.",
                "launched; wait for READY")
        except Exception as e:
            say(f"❌ לא הצלחתי: {e}", "failed")

    elif key == "4":
        _, user_level = effective_stt_url()
        if not user_level:
            say("המשתנה כבר ריק.", "already empty")
            return
        say(f"המשתנה כרגע: {user_level}", "current value")
        say("למחוק אותו? (כן / y)", "delete it? y")
        try:
            if input("> ").strip().lower() not in ("y", "yes", "כן"):
                say("לא נגעתי.", "left alone")
                return
        except (EOFError, KeyboardInterrupt):
            return
        try:
            subprocess.run(["setx", "KESHEV_STT_URL", ""], capture_output=True,
                           timeout=20,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            say("✅ נוקה. יחול על חלונות חדשים בלבד.",
                "cleared; affects new processes only")
        except Exception as e:
            say(f"❌ לא הצלחתי: {e}", "failed")

    elif key == "5":
        if not os.path.exists(MIC_PID_FILE):
            say("אין קובץ mic.pid.", "no mic.pid")
            return
        try:
            os.replace(MIC_PID_FILE, MIC_PID_FILE + ".stale-" + time.strftime("%Y%m%d-%H%M%S"))
            say("✅ נוקה. עכשיו החלון יסכים להפעיל מנוע חדש.",
                "cleared; the window will start a fresh engine")
        except OSError as e:
            say(f"❌ לא הצלחתי: {e}", "failed")


def main():
    if "--check" in sys.argv:
        # Non-interactive: for a scheduled watchdog or another agent.
        probs = diagnose()
        return 1 if any(p[0] == "RED" for p in probs) else 0
    while True:
        problems.clear()
        diagnose()
        key = repair_menu()
        if key == "0":
            say("יוצא. לא נגעתי בכלום נוסף.", "bye")
            return 0
        if key == "9":
            continue
        do_repair(key)
        print()
        say("לוחץ Enter כדי לבדוק שוב...", "Enter to re-check")
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            return 0


if __name__ == "__main__":
    sys.exit(main())
