import os
import sys
import re
import subprocess
import threading
import time
from collections import deque
from datetime import datetime
import json
import tkinter as tk
from tkinter import ttk

# Genome constants for pause state
KESHEV_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_DIR = os.path.join(KESHEV_ROOT, "state")
PAUSE_FILE = os.path.join(STATE_DIR, "PAUSED")
MIC_PID_FILE = os.path.join(STATE_DIR, "mic.pid")
MIC_CHOICE_FILE = os.path.join(STATE_DIR, "mic-choice.json")
TRIAL_LOG = os.path.join(KESHEV_ROOT, "trial.log")

# --- mic lifecycle (Iddo's law 2026-08-24: "close the GUI => the mic dies with it") ---
# This dashboard used to be SEPARATE from the mic (app/main.py), so closing it left the
# mic running headless with no off switch -- exactly the Sacred-Audio "no off switch" pain.
# Now the window OWNS the mic: opening the window starts it, closing the window kills it.
_mic_proc = None

# --- the heartbeat the engine listens for (2026-09-01) ----------------------
# stop_mic() below is cooperation, and cooperation is not a guarantee: kill this
# window from Task Manager and the old engine kept recording forever with no off
# switch. app/main.py now watches this file and our pid, and stops ITSELF when
# either goes stale. We only have to keep saying "the window is still here".
HEARTBEAT_FILE = os.path.join(STATE_DIR, "gui.heartbeat")
HEARTBEAT_MS = 8000

# 2026-09-03: the heartbeat is written by this Tk loop. Under a saturated CPU the
# loop did not run for 32 s and the engine's dead-man switch fired on a LIVE
# window. Lift the window above the crowd (never REALTIME; never above the engine).
if os.name == "nt":
    try:
        import ctypes
        ABOVE_NORMAL_PRIORITY_CLASS = 0x00008000
        _k32 = ctypes.windll.kernel32
        # restype/argtypes matter: without them the pseudo-handle (-1) is truncated
        # on 64-bit and the call fails silently (measured 2026-09-03 23:0x: prio=Normal).
        _k32.GetCurrentProcess.restype = ctypes.c_void_p
        _k32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        _k32.SetPriorityClass(_k32.GetCurrentProcess(), ABOVE_NORMAL_PRIORITY_CLASS)
    except Exception:
        pass


def touch_heartbeat():
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(HEARTBEAT_FILE, "w") as f:
            f.write(str(os.getpid()))
        return True
    except OSError as exc:
        # a missed beat is safe: the engine only stops after 30 s -- but say so,
        # because on 2026-09-03 08:29 the beats stopped after the second one and
        # the engine shut itself down 30 s later with nobody the wiser.
        print(f"[gui] heartbeat write failed: {exc}", file=sys.stderr, flush=True)
        return False


def beat_forever(root):
    # Schedule the NEXT beat before writing this one, so nothing that happens in
    # the write can ever end the chain (2026-09-03 08:29: chain died at beat 2).
    try:
        root.after(HEARTBEAT_MS, lambda: beat_forever(root))
    except Exception as exc:
        print(f"[gui] heartbeat reschedule failed: {exc!r}", file=sys.stderr, flush=True)
        return        # window is going away; stop_mic() handles the rest
    ok = touch_heartbeat()
    print(f"[gui] beat {datetime.now().strftime('%H:%M:%S')} ok={ok}", file=sys.stderr, flush=True)


def clear_heartbeat():
    try:
        os.remove(HEARTBEAT_FILE)
    except OSError:
        pass


# --- the mic chooser (2026-08-29) ------------------------------------------
# Iddo, the morning after the deaf night: "אין בכלל אפשרות לבחור - תוסיף".
# The engine owns the fence; this window only offers what the engine says is
# allowed (`main.py --list-devices`) so the two can never disagree about which
# mics the Sacred Audio Law permits.

def list_input_devices():
    try:
        out = subprocess.run(
            [sys.executable, "-X", "utf8", os.path.join(KESHEV_ROOT, "app", "main.py"),
             "--list-devices"],
            capture_output=True, text=True, encoding="utf-8", timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return json.loads(out.stdout.strip().splitlines()[-1])
    except Exception as exc:
        print(f"list_input_devices failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return []


def read_mic_choice():
    try:
        with open(MIC_CHOICE_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {"mode": "default"}


def write_mic_choice(choice):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = MIC_CHOICE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(choice, fh, ensure_ascii=False)
    os.replace(tmp, MIC_CHOICE_FILE)


_ENGINE_SEEN = {"pid": 0, "at": 0.0, "ok": False}


def _image_name(pid):
    """The .exe behind `pid`, or None if it cannot be read."""
    try:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
                             capture_output=True, text=True,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        line = out.stdout.strip().splitlines()[0] if out.stdout.strip() else ""
        if not line.startswith('"'):
            return None                     # "INFO: No tasks are running..."
        return line.split('","')[0].lstrip('"')
    except Exception:
        return None


def _cmdline_is_engine(pid):
    """Does `pid`'s command line name THIS engine? Cached: at most one query
    per pid per 30 s, because supervise_engine() asks every 5 s."""
    now = time.time()
    if _ENGINE_SEEN["pid"] == pid and now - _ENGINE_SEEN["at"] < 30.0:
        return _ENGINE_SEEN["ok"]
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             f"(Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}')"
             ".CommandLine"],
            capture_output=True, text=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        cmd = (out.stdout or "").lower()
        if not cmd.strip():
            return True                     # unreadable: see the note below
        ok = "keshev-next" in cmd and "main.py" in cmd
    except Exception:
        return True                         # unreadable: see the note below
    _ENGINE_SEEN.update(pid=pid, at=now, ok=ok)
    return ok


def _pid_alive(pid):
    """True only if `pid` is OUR engine -- not merely a live pid number.

    2026-09-07 16:15: state/mic.pid held 4224 from an engine that died the
    night before, and Windows had recycled 4224 to conhost.exe. This function
    asked only "is that number alive", tasklist said yes, so start_mic()
    returned early and the microphone was never opened. The window was up, the
    heartbeat was green, gui-crash.log was empty -- and KESHEV was deaf for
    18 hours. A liveness check that outlives its subject is worse than none,
    because it reports health it cannot see.

    So: exact when the engine is our own child; otherwise the pid must still
    BE a python process running the keshev-next engine (app/main.py). When the process
    cannot be inspected at all we answer True (do not start a rival mic --
    2026-09-02's two-typers night) but we never again accept a bare number.
    """
    if pid <= 0:
        return False
    if _mic_proc is not None and _mic_proc.pid == pid and _mic_proc.poll() is None:
        return True                         # our own child, no query needed
    name = _image_name(pid)
    if name is None:
        return False                        # not running at all -> start it
    if not name.lower().startswith("python"):
        return False                        # PID REUSE (the conhost case)
    return _cmdline_is_engine(pid)


def start_mic():
    """Start app/main.py as a child, unless a live mic is already recorded in mic.pid."""
    global _mic_proc
    try:
        if os.path.exists(MIC_PID_FILE):
            old = int(open(MIC_PID_FILE).read().strip() or "0")
            if old and _pid_alive(old):
                return  # a mic is already running; don't start a second
    except Exception:
        pass
    os.makedirs(STATE_DIR, exist_ok=True)
    touch_heartbeat()      # exists before the engine arms its dead-man switch
    try:
        logf = open(TRIAL_LOG, "a", encoding="utf-8", errors="ignore")
    except PermissionError:
        # trial.log is locked by an engine started OUTSIDE the window (the old
        # RUN-KESHEV.cmd's ">> trial.log" redirect). Starting a second engine
        # is forbidden, and dying here is worse: on 2026-08-25 this exact line
        # crashed the window before it opened ("i cant load keshev"). Stay a
        # viewer of the running engine instead.
        return
    logf.write(f"\n=== gui start mic {datetime.now().isoformat()} ===\n")
    logf.flush()
    # Absolute path on purpose: rival-mic guards (mic-rebuild's ALMA_PROC_RE)
    # recognize this engine by "keshev-next" in its command line. A relative
    # "app\main.py" is invisible to them (2026-08-25, the two-typers night).
    _mic_proc = subprocess.Popen(
        [sys.executable, "-X", "utf8",
         os.path.join(KESHEV_ROOT, "app", "main.py")],
        cwd=KESHEV_ROOT,
        env=dict(os.environ, PYTHONIOENCODING="utf-8",
                 KESHEV_OWNER_PID=str(os.getpid())),
        stdout=logf, stderr=subprocess.STDOUT,
        # 2026-09-03 19:50 -- measured: the engine ran at NORMAL priority and starved.
        # trial.log that evening: dropped_blocks 0 -> 256 in 8 min, then
        # "[deadman] heartbeat 32s stale" three times; the PC was at 100% CPU with
        # two render jobs from other sessions (psy_render 2.5 cores, truthviews 0.7),
        # 16 claude.exe and 43 python.exe. Not the BRIO, not DirectSound, not the
        # code: nobody ever gave the microphone a place in the queue. HIGH means the
        # audio consumer thread gets its slice before any render does.
        creationflags=(subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
                       | subprocess.HIGH_PRIORITY_CLASS)
        if os.name == "nt" else 0,
    )
    try:
        with open(MIC_PID_FILE, "w") as f:
            f.write(str(_mic_proc.pid))
    except Exception:
        pass


def stop_mic():
    """Kill the mic child tree. Called on window close -- no window, no mic."""
    global _mic_proc
    pids = []
    if _mic_proc is not None:
        pids.append(_mic_proc.pid)
    try:
        if os.path.exists(MIC_PID_FILE):
            p = int(open(MIC_PID_FILE).read().strip() or "0")
            if p:
                pids.append(p)
    except Exception:
        pass
    for pid in set(pids):
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           capture_output=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception:
            pass
    try:
        if os.path.exists(MIC_PID_FILE):
            os.remove(MIC_PID_FILE)
    except Exception:
        pass
    clear_heartbeat()
    _mic_proc = None

def main():
    # Compute default log path: parent of parent of gui.py + 'trial.log'
    script_path = os.path.abspath(__file__)
    keshev_root = os.path.dirname(os.path.dirname(script_path))
    default_log = os.path.join(keshev_root, 'trial.log')

    # Parse command line args
    log_file = default_log
    debug_mode = False
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == '--debug':
            debug_mode = True
        else:
            log_file = sys.argv[i]
        i += 1

    # Regex patterns for parsing lines
    # 2026-08-29 -- this used to demand `device='NAME' native=` with nothing between
    # them. The mic fence then started printing `[MME] (index 1 ... fenced)` in that
    # gap, the pattern stopped matching, and the window silently kept displaying the
    # LAST line it could still parse -- 'Microphone (2- HTC Vive)' from 23:42 the
    # night before. Iddo saw a headset that was switched off named as his live mic
    # for hours. `.*?` across the middle so extra detail can never lie again.
    drops_pattern = re.compile(r'^\[mic\] status_events=(\d+) dropped_blocks=(\d+)')
    mic_pattern = re.compile(r"\[mic\]\s+device='([^']+)'.*?native=(\d+)Hz\s+resample=(\d+)/(\d+)\s+->\s+(\d+)Hz\s+block=(\d+)ms")
    segment_pattern = re.compile(
        r"\[segment\]\s+bytes=\d+\s+secs=[\d.]+\s+peak_rms=(\d+)\s+gate=([\d.]+)/(PASS|BLOCK)\s+decode=(\S+)\s+route=(\S+)\s+text=(?:'([^']*)'|\"([^\"]*)\"|-)"
    )
    # 2026-09-03 02:10 -- typer.py refuses to type into a window that runs as
    # Administrator (Windows UIPI would eat the keys and report success) and
    # prints this line instead. Iddo spent a quarter of an hour on "it doesn't
    # type in the CLI" with no clue on screen; the banner below is that clue.
    typer_blocked_pattern = re.compile(r"\[typer\] BLOCKED admin-window proc=(\S+)")

    # State
    # 2026-09-03 08:25 -- this used to be `offset = 0`: every launch re-read the
    # WHOLE trial.log (6 MB, days of history), so a "[typer] BLOCKED admin-window"
    # line written at 03:37 armed the red "runs as Administrator" banner on a
    # fresh window at 08:20, and Iddo read it as "KESHEV comes up elevated".
    # History is not this session: start near the tail, and while catching up
    # learn only the mic line -- no banner, no typed/blocked counts.
    try:
        offset = max(0, os.path.getsize(log_file) - 65536)
    except OSError:
        offset = 0
    partial_line = b''
    catching_up = True
    mic_info = None
    segment_queue = deque(maxlen=12)
    typed_count = 0
    blocked_count = 0
    admin_block_until = 0.0
    admin_block_proc = ''

    def get_verdict(gate, decode, route):
        if gate == 'BLOCK':
            return 'blocked'
        elif decode == 'ok' and route != '-':
            return 'typed'
        else:
            return 'dropped'

    def parse_line(line):
        nonlocal mic_info
        line = line.strip()
        if not line:
            return

        # [typer] BLOCKED admin-window line -> banner for 20 s
        m = typer_blocked_pattern.match(line)
        if m:
            if catching_up:
                return          # a block from a previous session is not news
            nonlocal admin_block_until, admin_block_proc
            admin_block_until = time.time() + 20
            admin_block_proc = m.group(1)
            return

        # [mic] status_events=N dropped_blocks=M  (2026-09-03: the health line)
        m = drops_pattern.match(line)
        if m:
            drops = int(m.group(2))
            try:
                colour = '#666' if drops < 10 else ('#E67E22' if drops < 60 else '#C0392B')
                drops_label.config(text=f'נפילות שמע: {drops}' + ('' if drops < 10 else '  ⚠ המחשב עמוס, המיקרופון מאבד שמע'), fg=colour)
            except Exception:
                pass
            return

        # [mic] line
        m = mic_pattern.match(line)
        if m:
            device, native, res_in, res_out, target, block = m.groups()
            mic_info = {
                'device': device,
                'native': native,
                'resample': f"{res_in}/{res_out}",
                'target': target,
                'block': block
            }
            if debug_mode:
                print(f"DEBUG mic device={mic_info['device']} native={mic_info['native']}", file=sys.stderr, flush=True)
            return

        # [segment] line (skip SKIP lines)
        m = segment_pattern.match(line)
        if not m:
            return
        if catching_up:
            return              # old segments would inflate this session's counts

        peak_rms, gate, gate_status, decode, route, *text_parts = m.groups()
        text = text_parts[0] if text_parts[0] else (text_parts[1] if len(text_parts) > 1 and text_parts[1] else '-')

        # Skip lines with ' SKIP' in original line
        if 'SKIP' in line:
            return

        verdict = get_verdict(gate_status, decode, route)
        if debug_mode:
            print(f"DEBUG seg verdict={verdict} gate={gate} rms={peak_rms} text={text}", file=sys.stderr, flush=True)

        # Update counts
        if verdict == 'typed':
            nonlocal typed_count
            typed_count += 1
        elif verdict == 'blocked':
            nonlocal blocked_count
            blocked_count += 1

        # Add to queue (newest first)
        segment_queue.appendleft({
            'time': datetime.now().strftime('%H:%M:%S'),
            'text': text,
            'gate': float(gate),
            'peak_rms': int(peak_rms),
            'verdict': verdict
        })

    def refresh_pause_ui():
        paused = os.path.exists(PAUSE_FILE)
        
        # Update button appearance
        if paused:
            pause_button.config(text="האזן 🟢", bg='#FF851B', fg='#FFFFFF')
            pause_banner.pack(fill='x', padx=10, pady=(5, 0), before=status_label)
        else:
            pause_button.config(text="השהה 🔴", bg='#FFFFFF', fg='#C0392B')
            pause_banner.pack_forget()

    def toggle_pause():
        try:
            if os.path.exists(PAUSE_FILE):
                os.remove(PAUSE_FILE)
            else:
                os.makedirs(STATE_DIR, exist_ok=True)
                # 2026-09-07 -- SIGN THE PAUSE, because an unsigned one gets undone.
                # This button wrote a bare timestamp: byte-for-byte the shape of the
                # 2026-09-03 scar (an agent wrote state\\PAUSED and walked away, and
                # Iddo had no microphone until morning). Since then
                # tools\\watchdogs\\keshev_delivery_watchdog.py clears exactly that shape
                # after 15 minutes -- and at 17:08:39 today it cleared IDDO'S OWN
                # pause, 16 minutes after he pressed this button, and the mic typed
                # the whole room into his chat until he noticed. gui6.py was signed
                # on 2026-09-06; this window, the one he actually runs, was not.
                # A watcher may only act on a state it can name. So name it: with
                # who/why present, that watchdog's looks_like_receipt guard leaves a
                # human pause alone however long it lasts.
                tmp = PAUSE_FILE + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump({
                        "who": "iddo (pause button in KESHEV 5000)",
                        "why": "he pressed pause -- the mic stays off until he presses listen",
                        "at": datetime.now().isoformat(),
                        "expires": None,
                        "restore": "press listen in the window, or delete state\\PAUSED",
                        "disables": True,
                    }, f, ensure_ascii=False, indent=2)
                os.replace(tmp, PAUSE_FILE)      # never a half-written pause
        except Exception:
            pass
        refresh_pause_ui()

    def update_status():
        nonlocal offset, partial_line, catching_up

        # Check if file exists and get mtime for alive dot
        try:
            mtime = os.path.getmtime(log_file)
            age = time.time() - mtime
            alive_color = '#2ECC40' if age <= 60 else '#BBBBBB'
        except (FileNotFoundError, OSError):
            mtime = None
            age = float('inf')
            alive_color = '#BBBBBB'

        # Update alive dot
        canvas_dot.delete("all")
        canvas_dot.create_oval(2, 2, 14, 14, fill=alive_color, outline='')

        # Try to read new data
        try:
            if not os.path.exists(log_file):
                status_label.config(text="ממתין ללוג... / waiting for log")
                return

            with open(log_file, 'rb') as f:
                file_size = os.path.getsize(log_file)
                if file_size < offset:
                    offset = 0
                f.seek(offset)
                data = f.read()
                offset += len(data)

            # Combine with partial line from previous poll
            full_data = partial_line + data
            lines = full_data.split(b'\n')
            partial_line = b''

            if len(lines) > 1:
                for i in range(len(lines) - 1):
                    try:
                        line_str = lines[i].decode('utf-8', errors='replace')
                        parse_line(line_str)
                    except Exception:
                        pass
                # Keep incomplete last line
                partial_line = lines[-1]
            elif len(full_data) > 0 and not full_data.endswith(b'\n'):
                partial_line = full_data

        except Exception:
            pass
        catching_up = False     # from here on every line is live

        # Update mic status if available
        if mic_info:
            status_text = f"{mic_info['device']} | {mic_info['native']}Hz → {mic_info['target']}Hz"
            status_label.config(text=status_text)
        else:
            status_label.config(text="אין נתוני מיקרופון עדיין")

        # Update segment list
        update_segment_list()

        # Update level meter and totals
        if segment_queue:
            latest = segment_queue[0]
            rms = min(latest['peak_rms'], 16000)
            width = int((rms / 16000) * 440)
            canvas_meter.delete("all")
            canvas_meter.create_rectangle(0, 2, width, 24, fill='#2ECC40', outline='')
        else:
            canvas_meter.delete("all")

        totals_label.config(text=f"הוקלדו: {typed_count}  |  נחסמו: {blocked_count}")
        
        # Refresh pause UI on every poll
        refresh_pause_ui()

        # Admin-window banner: the focused window runs as Administrator, so
        # Windows drops our keystrokes. Shown for 20 s after the last such block.
        if time.time() < admin_block_until:
            # 2026-09-06: bilingual (Iddo's law).
            admin_banner.config(text=f"🚫 החלון הפעיל ({admin_block_proc}) רץ כמנהל (Administrator) — "
                                     f"ווינדוס חוסם הקלדה לתוכו. פתח אותו מחדש בלי 'הרץ כמנהל'.\n"
                                     f"The focused window ({admin_block_proc}) runs as Administrator — "
                                     f"Windows blocks typing into it. Reopen it WITHOUT 'Run as administrator'.")
            if not admin_banner.winfo_ismapped():
                admin_banner.pack(fill='x', padx=10, pady=(5, 0), before=status_label)
        elif admin_banner.winfo_ismapped():
            admin_banner.pack_forget()

    _seg_sig = [None]

    def update_segment_list():
        # 2026-08-28: this ran on EVERY 300 ms poll and tore down + rebuilt ~40 Tk
        # widgets each time, whether or not anything had changed. Measured live at
        # ~25% of a core on an idle window, forever. Tk widget create/destroy is not
        # cheap. Rebuild only when the list actually differs.
        sig = tuple((sg['time'], sg['text'], sg['verdict']) for sg in segment_queue)
        if sig == _seg_sig[0]:
            return
        _seg_sig[0] = sig

        # Clear current rows
        for widget in segment_container.winfo_children():
            widget.destroy()

        # Add new rows (newest first)
        for seg in segment_queue:
            row = tk.Frame(segment_container, bg=get_verdict_color(seg['verdict']))
            row.pack(fill='x', padx=5, pady=2)

            time_label = tk.Label(row, text=seg['time'], font=('Arial', 9), bg=row.cget('bg'), fg='#333')
            time_label.pack(side='left', padx=(5, 10))

            # Determine text and alignment
            text_val = seg['text'] if seg['text'] != '-' else '—'
            has_hebrew = any('\u0590' <= c <= '\u05FF' for c in text_val)
            justify = 'right' if has_hebrew else 'left'
            anchor = 'e' if has_hebrew else 'w'

            text_label = tk.Label(row, text=text_val, font=('Arial', 10), bg=row.cget('bg'), fg='#333',
                                  justify=justify, anchor=anchor)
            text_label.pack(side='left', fill='x', expand=True, padx=(5, 5))

            gate_label = tk.Label(row, text=f"{seg['gate']:.2f}", font=('Arial', 9), bg=row.cget('bg'), fg='#333')
            gate_label.pack(side='right', padx=(10, 5))

    def get_verdict_color(verdict):
        if verdict == 'typed':
            return '#D6F5D6'
        elif verdict == 'dropped':
            return '#FFE2B8'
        else:  # blocked
            return '#E8E8E8'

    # Create main window
    root = tk.Tk()
    root.title('קשב 5000 — חי')
    root.geometry('480x700')
    root.configure(bg='#FFFFFF')

    # Top section: title, status, alive dot, topmost toggle
    top_frame = tk.Frame(root, bg='#FFFFFF')
    top_frame.pack(fill='x', padx=10, pady=(15, 5))

    title_label = tk.Label(top_frame, text='קשב 5000', font=('Arial', 28, 'bold'), fg='#1E88E5', bg='#FFFFFF')
    title_label.pack()

    # --- THE MIC CHOOSER -------------------------------------------------
    mic_row = tk.Frame(root, bg='#FFFFFF')
    mic_row.pack(fill='x', padx=10, pady=(8, 0))

    tk.Label(mic_row, text='🎙 מיקרופון:', font=('Arial', 11, 'bold'),
             fg='#1E88E5', bg='#FFFFFF').pack(side='right', padx=(6, 0))

    mic_devices = []            # parallel to the combobox entries
    mic_combo = ttk.Combobox(mic_row, state='readonly', font=('Arial', 10))
    mic_combo.pack(side='right', fill='x', expand=True)

    mic_note = tk.Label(root, text='', font=('Arial', 9), fg='#666', bg='#FFFFFF')
    mic_note.pack(fill='x', padx=10, pady=(2, 0))

    # 2026-09-03 22:58 -- the health line Iddo never had: the engine's own
    # "[mic] status_events=N dropped_blocks=M" is shown HERE, in the window, so a
    # starving microphone is seen while it is still alive (tonight it died three
    # times with nobody watching the log). Grey = fine, orange = losing audio,
    # red = the dead-man switch is near.
    drops_label = tk.Label(root, text='נפילות שמע: 0', font=('Arial', 9), fg='#666', bg='#FFFFFF')
    drops_label.pack(fill='x', padx=10, pady=(0, 0))

    def refresh_mic_list(select_current=True):
        """Ask the engine which mics the fence allows, and show them.

        2026-09-03 08:45: list_input_devices() is a subprocess with a 30 s
        timeout, and it used to run right here, in the Tk thread. Every
        after() timer -- the 8 s heartbeat included -- froze for as long as
        Windows took to enumerate audio devices, and the engine's dead-man
        switch fires at 30 s. Now the wait happens in a worker thread and only
        the widget update runs on the Tk thread.
        """
        def work():
            devs = list_input_devices()
            try:
                root.after(0, lambda: apply(devs))
            except Exception:
                pass          # window is gone

        def apply(devs):
            _apply_mic_list(devs, select_current)

        threading.Thread(target=work, daemon=True, name="mic-list").start()

    def _apply_mic_list(devs, select_current):
        nonlocal mic_devices
        mic_devices = [None] + devs          # None == follow the PC
        labels = []
        pc_name = next((d['name'] for d in devs if d.get('is_pc_default')), None)
        labels.append('ברירת מחדל של המחשב'
                      + (f'  ({pc_name})' if pc_name else '  (אין ברירת מחדל תקינה)'))
        for d in devs:
            star = ' ⭐' if d.get('is_pc_default') else ''
            labels.append(f"{d['name']}  [{d['hostapi']}]{star}")
        mic_combo['values'] = labels
        if not select_current:
            return
        choice = read_mic_choice()
        idx = 0
        if choice.get('mode') != 'default':
            for i, d in enumerate(devs):
                if d['name'] == choice.get('name') and d['hostapi'] == choice.get('hostapi'):
                    idx = i + 1
                    break
        mic_combo.current(idx)

    def on_mic_selected(_event=None):
        """Save the pick and restart the engine on it. The window owns the mic."""
        i = mic_combo.current()
        if i < 0:
            return
        d = mic_devices[i] if i < len(mic_devices) else None
        if d is None:
            write_mic_choice({'mode': 'default'})
            mic_note.config(text='עוקב אחרי ברירת המחדל של Windows / following the PC',
                            fg='#666')
        else:
            write_mic_choice({'mode': 'pick', 'name': d['name'], 'hostapi': d['hostapi']})
            mic_note.config(text=f"נבחר: {d['name']} — מפעיל מחדש… / restarting on it",
                            fg='#1E88E5')
        root.update_idletasks()
        stop_mic()
        time.sleep(1.0)
        start_mic()
        root.after(2500, lambda: mic_note.config(
            text='המיקרופון הופעל מחדש / mic restarted', fg='#2E7D32'))

    mic_combo.bind('<<ComboboxSelected>>', on_mic_selected)

    refresh_button = tk.Button(mic_row, text='⟳', font=('Arial', 11),
                               bg='#FFFFFF', fg='#1E88E5', takefocus=0,
                               command=lambda: refresh_mic_list())
    refresh_button.pack(side='left', padx=(6, 0))

    refresh_mic_list()

    # Pause toggle button
    pause_button = tk.Button(root, text="השהה 🔴", font=('Arial', 18, 'bold'),
                             bg='#FFFFFF', fg='#C0392B',
                             command=toggle_pause, takefocus=0,
                             padx=20, pady=15)  # takefocus=0 (2026-08-28):
    # a focused tk.Button also fires on Space and Return. This one is full-width
    # and near the top, so a stray space silently paused the mic -- twice in 90
    # minutes, and both times Iddo reported "the mic doesn't work" not knowing
    # he had done it. Only a real mouse click can pause now.
    pause_button.pack(fill='x', padx=10, pady=(5, 10))

    # Pause banner (hidden by default)
    pause_banner = tk.Label(root, text="⏸ מושהה - המיקרופון לא מקליד", bg='#FF851B', fg='#FFFFFF',
                            font=('Arial', 14, 'bold'))
    # Admin-window banner (hidden by default; shown while typer reports UIPI blocks)
    admin_banner = tk.Label(root, text="", bg='#C0392B', fg='#FFFFFF',
                            font=('Arial', 12, 'bold'), wraplength=440, justify='center')

    status_label = tk.Label(root, text="ממתין ללוג... / waiting for log", font=('Arial', 10), fg='#333', bg='#FFFFFF')
    status_label.pack(fill='x', padx=10, pady=(5, 10))

    # Status row: alive dot and topmost toggle
    status_row = tk.Frame(root, bg='#FFFFFF')
    status_row.pack(fill='x', padx=10)

    canvas_dot = tk.Canvas(status_row, width=20, height=20, bg='#FFFFFF', highlightthickness=0)
    canvas_dot.pack(side='left')

    topmost_var = tk.BooleanVar(value=True)
    def toggle_topmost():
        root.attributes('-topmost', topmost_var.get())
    
    # Apply initial topmost state right after creating the checkbox
    topmost_button = tk.Checkbutton(status_row, text="תמיד עליון", variable=topmost_var,
                                    command=toggle_topmost, bg='#FFFFFF', fg='#333',
                                    font=('Arial', 9), selectcolor='#E0E0E0')
    topmost_button.pack(side='left', padx=(15, 0))
    
    # Apply initial topmost setting
    root.attributes('-topmost', True)

    # Middle section: segment list
    middle_frame = tk.Frame(root, bg='#FFFFFF')
    middle_frame.pack(fill='both', expand=True, padx=10, pady=(10, 5))

    # Segment container with scrollbar
    canvas_seg = tk.Canvas(middle_frame, bg='#FFFFFF', highlightthickness=0)
    scrollbar = tk.Scrollbar(middle_frame, orient="vertical", command=canvas_seg.yview)
    segment_container = tk.Frame(canvas_seg, bg='#FFFFFF')

    segment_container.bind(
        "<Configure>",
        lambda e: canvas_seg.configure(scrollregion=canvas_seg.bbox("all"))
    )

    canvas_seg.create_window((0, 0), window=segment_container, anchor="nw")
    canvas_seg.configure(yscrollcommand=scrollbar.set)

    # Bind mouse wheel scrolling
    def _on_mousewheel(event):
        canvas_seg.yview_scroll(int(-1*(event.delta/120)), "units")

    canvas_seg.bind_all("<MouseWheel>", _on_mousewheel)

    canvas_seg.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    # Bottom section: level meter and totals
    bottom_frame = tk.Frame(root, bg='#FFFFFF')
    bottom_frame.pack(fill='x', padx=10, pady=(5, 15))

    canvas_meter = tk.Canvas(bottom_frame, width=440, height=26, bg='#FFFFFF', highlightthickness=1,
                             highlightbackground='#CCCCCC')
    canvas_meter.pack()

    totals_label = tk.Label(bottom_frame, text="הוקלדו: 0  |  נחסמו: 0", font=('Arial', 9), fg='#333', bg='#FFFFFF')
    totals_label.pack(pady=(5, 0))

    # Start polling
    # Engine supervisor (2026-09-03 08:33). The engine's dead-man switch stops
    # the mic 30 s after this window's heartbeat goes stale -- and Tk's timers
    # DO stall on Windows (measured: a synchronous PrintWindow into this window
    # froze every after() callback for 3.5 min; beats resumed on the next
    # message). Nobody restarted the engine, so Iddo had a live window over a
    # dead mic. The window owns the mic; if the engine is gone while the window
    # is alive and not closing, start it again -- same start_mic(), same fences,
    # same one-mic check, at most once per 20 s.
    closing = [False]
    last_supervise = [0.0]
    last_restart = [0.0]

    def supervise_engine():
        now = time.time()
        if closing[0] or now - last_supervise[0] < 5.0:
            return
        last_supervise[0] = now
        try:
            pid = int(open(MIC_PID_FILE).read().strip() or "0") if os.path.exists(MIC_PID_FILE) else 0
        except Exception:
            pid = 0
        if pid and _pid_alive(pid):
            return
        if now - last_restart[0] < 20.0:
            return
        last_restart[0] = now
        print(f"[gui] engine dead (mic.pid={pid or '-'}) - restarting it "
              f"{datetime.now().strftime('%H:%M:%S')}", file=sys.stderr, flush=True)
        try:
            with open(log_file, "a", encoding="utf-8", errors="ignore") as lf:
                lf.write("[gui] engine dead (mic.pid=%s) - restarting %s" % (pid or "-", datetime.now().isoformat()) + chr(10))
        except OSError:
            pass
        try:
            start_mic()
        except Exception as exc:
            print(f"[gui] restart failed: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)

    def poll():
        update_status()
        supervise_engine()
        root.after(300, poll)

    # Initial alive dot state (before any file check)
    canvas_dot.create_oval(2, 2, 14, 14, fill='#BBBBBB', outline='')

    # Initialize pause UI on startup
    refresh_pause_ui()

    # The window OWNS the mic: start it now, kill it when the window closes.
    # The window must OPEN even if the mic cannot start — a dead window hides
    # every other failure (2026-08-25).
    try:
        start_mic()
    except Exception as exc:
        print(f"start_mic failed: {type(exc).__name__}: {exc}", file=sys.stderr)

    def on_close():
        closing[0] = True
        stop_mic()
        root.after(120, root.destroy)

    root.protocol("WM_DELETE_WINDOW", on_close)
    beat_forever(root)   # keep telling the engine the window is still alive

    # Start the loop
    root.after(300, poll)
    try:
        root.mainloop()
    finally:
        stop_mic()   # belt and suspenders: never leave the mic alive without a window

if __name__ == '__main__':
    try:
        main()
    except Exception:
        # A window that dies silently reads as "KESHEV won't load" (2026-08-25).
        # Leave a trace on disk and on screen, always.
        import traceback
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(os.path.join(STATE_DIR, "gui-crash.log"), "a", encoding="utf-8") as f:
            f.write(f"\n=== {datetime.now().isoformat()} ===\n{traceback.format_exc()}")
        try:
            import ctypes
            ctypes.WinDLL("user32").MessageBoxW(
                None,
                "KESHEV 5000 window crashed — details in state\\gui-crash.log",
                "KESHEV 5000", 0x00040010)  # MB_ICONERROR | MB_TOPMOST
        finally:
            raise
