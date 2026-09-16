#!/usr/bin/env python3
"""
ALMAWARE HUD - always-on-top consolidation widget.
Shows Eran / DGX fleet / training / playroom / Yigael live status.
Native (Tkinter, stdlib only). No taskbar entry. Drag anywhere to move.
"""
import tkinter as tk
import os, re, socket, threading, time, urllib.request, subprocess, json

ERAN_LOG    = r"D:\CLAUDE\eran-live\eran.log"
ERAN_WATCH  = r"D:\CLAUDE\eran-live\watch.log"
ERAN_CHAT   = "http://127.0.0.1:8792/"
DASHBOARD   = "file:///D:/CLAUDE/eran-dashboard/index.html"
GROK1       = "http://127.0.0.1:8899/"
STATUS_JSON = r"D:\CLAUDE\almaware-cockpit\status.json"
STATUS_MAX_AGE_S = 15  # collector writes every ~2s; anything older is stale
PLAYROOM_DIRS = [r"D:\CLAUDE\eran-playroom", r"D:\CLAUDE\baby-cave", r"D:\CLAUDE\eran-live\playroom"]
YIGAEL_DIRS   = [r"D:\CLAUDE\yigael", r"D:\CLAUDE\eran-live\yigael"]

# 2026-09-11 (WAVE A2): these four were hard-coded and three of the four were
# wrong — eran2 had moved to .156, eran4 to .231, and <fabric-ip> exists on NO
# interface on any box. The widget was therefore reporting most of the fleet
# dead. Addresses now come from D:\CLAUDE\fleet_inventory.json, and we use the
# TAILNET address because it survives router swaps; LAN leases do not.
import sys as _sys
_sys.path.insert(0, r"D:\CLAUDE")
try:
    import fleet_inventory as _fi
    DGX = [(n, _fi.ip(n, "best")) for n in ("eran1", "eran2", "eran3", "eran4")]
except Exception:                                             # noqa: BLE001
    DGX = [                       # tailnet addresses, stable; last measured 09-11
        ("eran1", "<tailnet-ip>"),
        ("eran2", "<tailnet-ip>"),
        ("eran3", "<tailnet-ip>"),
        ("eran4", "<tailnet-ip>"),
    ]

# ---------- data gatherers (all non-blocking) ----------
def tcp_check(host, port=22, timeout=1.0):
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.close()
        return True
    except Exception:
        return False

def eran_log_tail():
    try:
        with open(ERAN_LOG, "rb") as f:
            try: f.seek(-4096, os.SEEK_END)
            except OSError: f.seek(0)
            data = f.read().decode("utf-8", "ignore")
        line = data.strip().splitlines()[-1]
        m = re.search(
            r"step\s+([\d,]+)\s+\|\s+loss\s+([\d.]+)\s+\|\s+ema\s+([\d.]+).+?([\d.]+)\s+steps/s.+?(\d+)k?\s+tok/s.+?eran_vram\s+(\d+)\s*MB",
            line)
        if m:
            return {
                "step": int(m.group(1).replace(",", "")),
                "loss": float(m.group(2)),
                "ema":  float(m.group(3)),
                "sps":  float(m.group(4)),
                "tps":  int(m.group(5)),
                "vram": int(m.group(6)),
            }
    except Exception:
        pass
    return None

def read_status_json():
    """Return parsed status.json dict if fresh, else None. Prefer this over log-tail."""
    try:
        st = os.stat(STATUS_JSON)
        if time.time() - st.st_mtime > STATUS_MAX_AGE_S:
            return None
        with open(STATUS_JSON, "rb") as f:
            return json.loads(f.read().decode("utf-8", "ignore"))
    except Exception:
        return None

def eran_from_status(s):
    """Extract training metrics from status.json. Returns same shape as eran_log_tail()."""
    try:
        line = (s.get("eran") or {}).get("log_tail", {}).get("last_line", "")
        if not line:
            return None
        m = re.search(
            r"step\s+([\d,]+)\s+\|\s+loss\s+([\d.]+)\s+\|\s+ema\s+([\d.]+).+?([\d.]+)\s+steps/s.+?(\d+)k?\s+tok/s.+?eran_vram\s+(\d+)\s*MB",
            line)
        if m:
            return {
                "step": int(m.group(1).replace(",", "")),
                "loss": float(m.group(2)),
                "ema":  float(m.group(3)),
                "sps":  float(m.group(4)),
                "tps":  int(m.group(5)),
                "vram": int(m.group(6)),
            }
    except Exception:
        pass
    return None

def fleet_from_status(s):
    """Return {name: bool_reachable} from status.json fleet.nodes, or None."""
    try:
        nodes = (s.get("fleet") or {}).get("nodes") or {}
        out = {}
        for name, node in nodes.items():
            if name.startswith("_"):
                continue
            out[name] = bool(node.get("reachable"))
        return out or None
    except Exception:
        return None

def eran_latest_babble():
    try:
        with open(ERAN_WATCH, "rb") as f:
            try: f.seek(-4000, os.SEEK_END)
            except OSError: f.seek(0)
            data = f.read().decode("utf-8", "ignore")
        blocks = data.split("===== ERAN watch @")
        if len(blocks) < 2: return None
        last = blocks[-1].strip().splitlines()
        babble = " ".join(last[1:]).strip()
        babble = babble.replace("�", "").replace("  ", " ")
        return babble[:110] if babble else None
    except Exception:
        return None

def http_alive(url, timeout=2):
    try:
        urllib.request.urlopen(url, timeout=timeout)
        return True
    except Exception:
        return False

def dir_state(paths):
    """Return latest-mtime file summary from any of the given dirs, or None."""
    for p in paths:
        if os.path.isdir(p):
            files = []
            try:
                for root, _, fs in os.walk(p):
                    for name in fs:
                        fp = os.path.join(root, name)
                        try:
                            files.append((os.path.getmtime(fp), name))
                        except OSError:
                            pass
            except Exception:
                continue
            if files:
                files.sort(reverse=True)
                mt, name = files[0]
                age = int(time.time() - mt)
                if age < 90: tag = "🟢 active"
                elif age < 3600: tag = f"🟡 {age//60}m ago"
                else: tag = f"⚪ {age//3600}h ago"
                return f"{tag}\n{name[:32]}"
            return "(dir empty)"
    return None

# ---------- widget ----------
class HUD:
    def __init__(self, root):
        self.root = root
        root.title("ALMAWARE HUD")
        root.attributes('-topmost', True)
        root.overrideredirect(True)
        # top-right corner
        sw = root.winfo_screenwidth()
        root.geometry(f"320x620+{sw-340}+40")
        root.configure(bg="#0d0a1a")

        # drag support (no title bar)
        self._dx = self._dy = 0
        root.bind("<Button-1>", self._drag_start)
        root.bind("<B1-Motion>", self._drag)

        # header
        hdr = tk.Frame(root, bg="#161230", height=34); hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text="  ⬢ ALMAWARE HUD", bg="#161230", fg="#f4d06a",
                 font=("Segoe UI", 11, "bold")).pack(side="left")
        tk.Button(hdr, text="—", bg="#161230", fg="#8a8172", borderwidth=0,
                  activebackground="#161230", font=("Segoe UI", 11),
                  command=lambda: root.iconify()).pack(side="right")
        tk.Button(hdr, text="✕", bg="#161230", fg="#c9bfa8", borderwidth=0,
                  activebackground="#161230", font=("Segoe UI", 11),
                  command=root.destroy).pack(side="right", padx=(0,4))

        self.eran_lbl  = self._section("🧠 ERAN — live LM (voice-only)")
        self.babble_lbl= self._section("💬 LATEST BABBLE")
        self.dgx_lbl   = self._section("🖧 DGX FLEET")
        self.train_lbl = self._section("⏱ TRAINING")
        self.play_lbl  = self._section("🎮 PLAYROOM · חדר הילדים")
        self.yig_lbl   = self._section("👶 YIGAEL · יגאל")

        # actions
        act = tk.Frame(root, bg="#0d0a1a"); act.pack(fill="x", side="bottom", pady=(6,10))
        for txt, url in [("💬 open Eran chat", ERAN_CHAT),
                         ("📊 open dashboard", DASHBOARD),
                         ("🤖 Grok-1 (native)", GROK1)]:
            b = tk.Button(act, text=txt, bg="#221a3a", fg="#f4d06a", borderwidth=0,
                          activebackground="#2b2350", activeforeground="#ffd680",
                          font=("Segoe UI", 9, "bold"), pady=4,
                          command=lambda u=url: self._open(u))
            b.pack(fill="x", padx=10, pady=1)

        self.dgx_cache = {n: None for n, _ in DGX}
        self.babble_cache = ""
        self._chat_up = False
        self.tick()
        threading.Thread(target=self.ping_dgx_loop, daemon=True).start()
        threading.Thread(target=self.chat_probe_loop, daemon=True).start()

    def _section(self, title):
        wrap = tk.Frame(self.root, bg="#0d0a1a"); wrap.pack(fill="x", padx=10, pady=(7,0))
        tk.Label(wrap, text=title, bg="#0d0a1a", fg="#8a8172",
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        lbl = tk.Label(wrap, text="…", bg="#141028", fg="#e8edf4",
                       font=("Consolas", 9), justify="left", anchor="nw",
                       padx=9, pady=5, wraplength=290)
        lbl.pack(fill="x", pady=(2, 0))
        return lbl

    def _drag_start(self, e):
        self._dx = e.x_root - self.root.winfo_x()
        self._dy = e.y_root - self.root.winfo_y()
    def _drag(self, e):
        self.root.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")
    def _open(self, url):
        try:
            if url.startswith("file:"):
                os.startfile(url[8:].replace("/", os.sep))
            else:
                subprocess.Popen(["cmd", "/c", "start", "", url], shell=False, creationflags=_NOWIN)
        except Exception:
            pass

    # --- background loops ---
    def ping_dgx_loop(self):
        while True:
            for name, host in DGX:
                self.dgx_cache[name] = tcp_check(host, 22, 1.0)
            time.sleep(30)

    def chat_probe_loop(self):
        while True:
            self._chat_up = http_alive(ERAN_CHAT, 2)
            b = eran_latest_babble()
            if b: self.babble_cache = b
            time.sleep(15)

    # --- UI tick ---
    def tick(self):
        # Prefer collector's status.json when fresh; fall back to raw log-tail.
        status = read_status_json()
        e = eran_from_status(status) if status else None
        if not e:
            e = eran_log_tail()
        # Merge fleet reachability from status.json into dgx_cache when fresh.
        if status:
            fleet = fleet_from_status(status)
            if fleet:
                for name in self.dgx_cache:
                    if name in fleet:
                        self.dgx_cache[name] = fleet[name]
        if e:
            chat = "🟢 chat online" if self._chat_up else "🔴 chat down"
            self.eran_lbl.config(text=
                f"step  {e['step']:>10,}\n"
                f"loss  {e['loss']:.4f}   ema  {e['ema']:.4f}\n"
                f"{chat}")
            self.train_lbl.config(text=
                f"speed   {e['sps']:>5.1f} steps/s\n"
                f"tokens  {e['tps']:>4}k tok/s\n"
                f"VRAM    {e['vram']} MB (mic-throttled)")
        else:
            self.eran_lbl.config(text="(log unreadable — is training on?)")
            self.train_lbl.config(text="—")

        # babble
        self.babble_lbl.config(text=(self.babble_cache or "(waiting for next sample…)"))

        # DGX
        rows = []
        for name, host in DGX:
            state = self.dgx_cache.get(name)
            dot = "🟢 up" if state is True else ("🔴 down" if state is False else "… probing")
            rows.append(f"{name:<6} {dot:<12} {host}")
        self.dgx_lbl.config(text="\n".join(rows))

        # Playroom / Yigael from filesystem
        p = dir_state(PLAYROOM_DIRS)
        self.play_lbl.config(text=p or "(no source wired — tell Claude the path)")
        y = dir_state(YIGAEL_DIRS)
        self.yig_lbl.config(text=y or "(no source wired — tell Claude the path)")

        self.root.after(2000, self.tick)

if __name__ == "__main__":
    root = tk.Tk()
    HUD(root)
    root.mainloop()
