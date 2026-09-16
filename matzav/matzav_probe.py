# -*- coding: utf-8 -*-
r"""
matzav_probe.py — OBSERVE. Real state, never declared state.

> BROKEN WINDOWS LAW: test the REAL output, not a proxy.

Two tiers:
  cheap  — read almaware-hud/status.json (the collector already SSHes the fleet
           every ~5 s). Never SSHes itself. Used for the "is the box alive"
           background hint only, and NEVER believed on its own: at build time
           that file reported ALL FOUR boxes unreachable while SSH answered in
           4.2 s. A single failure is UNKNOWN, not DOWN.
  deep   — exactly ONE ssh per box, one composite command, every probe batched.

THE SINGLE MOST DANGEROUS DETAIL ON THIS FLEET: every ERAN/ALMA service on all
four Sparks is a systemd USER unit. Plain `systemctl status eranb-life` returns
"Unit could not be found" while `systemctl --user` returns active. So every call
here is `systemctl --user` with XDG_RUNTIME_DIR set defensively, and
"unit not found" is NEVER read as "not running".

AND: on GB10 there is no VRAM gauge. nvidia-smi returns FB Memory Total/Used/
Free = N/A on all four Sparks. The budget is /proc/meminfo MemAvailable — never
MemFree (eran3 measured MemFree 3.4 GB vs MemAvailable 111.3 GB; 103.6 GB of the
difference was page cache), and never torch.cuda.mem_get_info (it reports
MemFree, so it paints every mode red on a box that is 92% free).
"""
import json
import io
import os
import re
import socket
import struct
import subprocess
import time
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
REGISTRY = os.path.join(HERE, "registry")
HUD_STATUS = r"D:\CLAUDE\almaware-hud\status.json"

SSH_TIMEOUT = 16
HUMAN_HOLD_MAX_AGE_S = 4 * 3600


class RegistryRefusal(Exception):
    """Fail closed. MATZAV refuses to start rather than load a bad registry."""


# --------------------------------------------------------------------------
# registry load  —  GATE 1 of the sacred guard
# --------------------------------------------------------------------------
def load_registry():
    from matzav_sacred import is_sacred, sacred_reason

    with io.open(os.path.join(REGISTRY, "units.json"), encoding="utf-8") as f:
        reg = json.load(f)

    units = {}
    for u in reg["units"]:
        # --- schema rule: a unit whose only probe is systemd is REJECTED -----
        p = u.get("probe") or {}
        if not p or p.get("type") in (None, "systemd"):
            raise RegistryRefusal(
                "unit %s has no real probe (systemd is a declaration, not a "
                "measurement). Requirement 4 is structural, not aspirational."
                % u["id"])
        # --- GATE 1: sacred units lose their stop verb, in the object --------
        if is_sacred(u["box"], u["unit"]):
            u["sacred"] = True
            u["stop"] = None          # there is no stop verb left to call
            u["start"] = None
            u["sacred_why"] = sacred_reason(u["box"], u["unit"])
        elif u.get("sacred"):
            raise RegistryRefusal(
                "unit %s claims sacred=true but is not in matzav_sacred.SACRED. "
                "The table in code is the only source of immunity." % u["id"])
        units[u["id"]] = u

    modes = []
    for fn in sorted(os.listdir(os.path.join(REGISTRY, "modes"))):
        if not fn.endswith(".json"):
            continue
        with io.open(os.path.join(REGISTRY, "modes", fn), encoding="utf-8") as f:
            m = json.load(f)
        errs = []
        for uid in m.get("want", []) + m.get("concede", []):
            if uid not in units:
                errs.append("unknown unit id: %s" % uid)
        # --- GATE 1b: conceding a sacred unit fails the WHOLE load ----------
        for uid in m.get("concede", []):
            if uid in units and units[uid].get("sacred"):
                raise RegistryRefusal(
                    "mode %s concedes SACRED unit %s (%s). MATZAV refuses to "
                    "start." % (m["id"], uid, units[uid].get("sacred_why")))
        if errs:
            m["runnable"] = False
            m["validation_errors"] = errs
        modes.append(m)
    modes.sort(key=lambda m: m.get("order", 999))
    return reg, units, modes


# --------------------------------------------------------------------------
# the composite remote probe
# --------------------------------------------------------------------------
def _build_script(box, units):
    user_units, sys_units, patterns, ssh_urls, ollama = [], [], [], [], False
    for u in units.values():
        if u["box"] != box:
            continue
        if u["kind"] == "systemd-user":
            user_units.append(u["unit"])
        elif u["kind"] == "systemd-system":
            sys_units.append(u["unit"])
        pt = u["probe"]["type"]
        if pt == "pgrep":
            patterns.append(u["probe"]["pattern"])
        elif pt == "http" and u["probe"].get("via") == "ssh":
            ssh_urls.append(u["probe"]["url"])
        elif pt == "ollama":
            ollama = True
    union = "|".join(re.escape(p) for p in patterns) or "__none__"

    L = ["export XDG_RUNTIME_DIR=/run/user/$(id -u) 2>/dev/null",
         "echo '#MEM'", "grep -E '^(MemTotal|MemAvailable|SwapFree):' /proc/meminfo",
         "echo '#GPUAPPS'",
         "nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader 2>/dev/null",
         "echo '#DF'", "df -B1 --output=avail / 2>/dev/null | tail -1",
         "echo '#LOAD'", "cat /proc/loadavg", "nproc",
         "echo '#HOST'", "hostname; uptime -s"]
    if user_units:
        L += ["echo '#UNITS'",
              "systemctl --user show %s -p Id -p LoadState -p ActiveState "
              "-p SubState -p MainPID -p UnitFileState --no-pager 2>/dev/null"
              % " ".join(user_units)]
    if sys_units:
        L += ["echo '#UNITS_SYS'",
              "systemctl show %s -p Id -p LoadState -p ActiveState -p SubState "
              "-p MainPID -p UnitFileState --no-pager 2>/dev/null"
              % " ".join(sys_units)]
    L += ["echo '#PS'",
          "ps -eo pid=,lstart=,args= | grep -E '%s' | grep -v grep" % union,
          "echo '#CG'",
          "for p in $(ps -eo pid=,args= | grep -E '%s' | grep -v grep | "
          "awk '{print $1}'); do echo \"$p $(head -c 300 /proc/$p/cgroup "
          "2>/dev/null | tr '\\n' ',')\"; done" % union,
          "echo '#PORTS'", "ss -tlnH 2>/dev/null | awk '{print $4}'"]
    if ollama:
        # `curl -s` emits NO trailing newline. Without the bare `echo` the next
        # section marker merges onto the JSON line and the whole section after
        # it is lost. That bug cost three false DOWN readings during the build;
        # measured, then fixed.
        L += ["echo '#OLLAMA'",
              "curl -s --max-time 4 http://127.0.0.1:11434/api/ps || echo '{}'",
              "echo"]
    if ssh_urls:
        L.append("echo '#HTTP'")
        for u_ in ssh_urls:
            L.append("echo \"%s $(curl -s -o /dev/null -w '%%{http_code}' "
                     "--max-time 6 '%s')\"" % (u_, u_))
    L.append("echo '#END'")
    return "\n".join(L) + "\n"


def _ssh(box_ssh, script, timeout=SSH_TIMEOUT):
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
           "-o", "ServerAliveInterval=3", "-o", "ServerAliveCountMax=2",
           box_ssh, "bash -s"]
    t0 = time.time()
    try:
        r = subprocess.run(cmd, input=script.encode("utf-8"),
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           timeout=timeout)
        return (r.stdout.decode("utf-8", "replace"),
                r.stderr.decode("utf-8", "replace"), r.returncode,
                round(time.time() - t0, 2))
    except subprocess.TimeoutExpired:
        return "", "TIMEOUT after %ss" % timeout, -1, round(time.time() - t0, 2)
    except Exception as e:                                   # noqa: BLE001
        return "", "%s: %s" % (type(e).__name__, e), -2, round(time.time() - t0, 2)


_SECTION_NAMES = {"MEM", "GPUAPPS", "DF", "LOAD", "HOST", "UNITS", "UNITS_SYS",
                  "PS", "CG", "PORTS", "OLLAMA", "HTTP", "END"}


def _sections(out):
    sec, cur = {}, None
    for line in out.splitlines():
        s = line.strip()
        if s.startswith("#") and s[1:] in _SECTION_NAMES:
            cur = s[1:]
            sec[cur] = []
            continue
        if cur:
            sec[cur].append(line.rstrip())
    return sec


# --------------------------------------------------------------------------
# PC-local probes
# --------------------------------------------------------------------------
def http_probe(url, ok_status, timeout, retries=1):
    """MEASURED during the build: the stdlib single-threaded http.server pages on
    this fleet (eran-listen :8807, alma-recall :8794) answer in 5 ms when idle
    and 2.5-4.9 s when they are mid-request for someone else. A tight timeout
    turns a healthy sacred service into a false DOWN. So: generous timeout, and
    one retry before we are allowed to say the word."""
    last = None
    for attempt in range(retries + 1):
        t0 = time.time()
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                code = r.status
        except urllib.error.HTTPError as e:
            code = e.code
        except Exception as e:                               # noqa: BLE001
            last = {"up": False, "code": None,
                    "ms": round((time.time() - t0) * 1000),
                    "error": "%s%s" % (type(e).__name__,
                                       " (after retry)" if attempt else "")}
            continue
        return {"up": code in ok_status, "code": code,
                "ms": round((time.time() - t0) * 1000), "error": None}
    return last


def tcp_json_probe(host, port, op, expect_key, timeout):
    """sense_organ :8830 is NOT HTTP — 4-byte big-endian length prefix + JSON.
    A curl against it hangs the full timeout and returns 000. Measured."""
    t0 = time.time()
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.settimeout(timeout)
        payload = json.dumps({"op": op}).encode("utf-8")
        s.sendall(struct.pack(">I", len(payload)) + payload)
        head = s.recv(4)
        if len(head) < 4:
            s.close()
            return {"up": False, "code": None,
                    "ms": round((time.time() - t0) * 1000),
                    "error": "short frame"}
        n = struct.unpack(">I", head)[0]
        buf = b""
        while len(buf) < n and len(buf) < 65536:
            c = s.recv(min(4096, n - len(buf)))
            if not c:
                break
            buf += c
        s.close()
        obj = json.loads(buf.decode("utf-8", "replace"))
        return {"up": bool(obj.get(expect_key)), "code": "json",
                "ms": round((time.time() - t0) * 1000), "error": None,
                "detail": obj}
    except Exception as e:                                   # noqa: BLE001
        return {"up": False, "code": None,
                "ms": round((time.time() - t0) * 1000),
                "error": "%s" % (type(e).__name__,)}


def read_hud():
    try:
        with io.open(HUD_STATUS, encoding="utf-8") as f:
            d = json.load(f)
        return d
    except Exception:                                        # noqa: BLE001
        return None


# --------------------------------------------------------------------------
# OBSERVE
# --------------------------------------------------------------------------
_MONTH = dict(Jan=1, Feb=2, Mar=3, Apr=4, May=5, Jun=6, Jul=7, Aug=8, Sep=9,
              Oct=10, Nov=11, Dec=12)


def _lstart_epoch(txt):
    # "Mon Aug 17 02:35:32 2026"
    m = re.match(r"\w{3}\s+(\w{3})\s+(\d+)\s+(\d+):(\d+):(\d+)\s+(\d{4})", txt)
    if not m:
        return None
    import calendar
    mo, d, H, M, S, Y = m.groups()
    try:
        return time.mktime((int(Y), _MONTH[mo], int(d), int(H), int(M),
                            int(S), 0, 0, -1))
    except Exception:                                        # noqa: BLE001
        return None


def observe(units, boxes, only_boxes=None):
    """One SSH per box. Returns {'boxes': {...}, 'units': {...}, 'ts': ...}."""
    import threading
    now = time.time()
    hud = read_hud()
    out = {"ts": now, "boxes": {}, "units": {}, "hud_ok": hud is not None}
    lock = threading.Lock()

    def do_box(box, meta):
        b = {"box": box, "title": meta["title"], "reachable": None,
             "reserve_gb": meta.get("reserve_gb", 8), "note": meta.get("note"),
             "err": None, "probe_ms": None, "sections": {}}
        if box == "pc":
            b.update(_observe_pc())
        else:
            script = _build_script(box, units)
            o, e, rc, secs = _ssh(meta["ssh"], script)
            b["probe_ms"] = int(secs * 1000)
            if rc != 0 or "#END" not in o:
                # A TIMEOUT IS UNKNOWN, NOT DOWN.
                b["reachable"] = None if rc in (-1, -2) else False
                b["err"] = (e or "rc=%s" % rc).strip()[:200]
            else:
                b["reachable"] = True
                b["sections"] = _sections(o)
                b.update(_parse_box(b["sections"]))
        if hud:                      # cheap tier, purely advisory
            fb = (hud.get("fleet") or {}).get(box)
            if fb:
                b["hud_reachable"] = fb.get("reachable")
                b["hud_age_s"] = round(now - (fb.get("cached_at") or now))
        with lock:
            out["boxes"][box] = b

    threads = []
    for box, meta in boxes.items():
        if only_boxes and box not in only_boxes:
            continue
        t = threading.Thread(target=do_box, args=(box, meta), daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join(SSH_TIMEOUT + 6)

    def do_unit(uid, u):
        s = _unit_state(u, out["boxes"].get(u["box"]) or {}, now)
        with lock:
            out["units"][uid] = s

    threads = []
    for uid, u in units.items():
        if only_boxes and u["box"] not in only_boxes:
            continue
        t = threading.Thread(target=do_unit, args=(uid, u), daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join(20)
    return out


def _observe_pc():
    b = {"reachable": True, "sections": {}}
    try:
        r = subprocess.run(["nvidia-smi",
                            "--query-gpu=memory.total,memory.used,memory.free",
                            "--format=csv,noheader,nounits"],
                           stdout=subprocess.PIPE, timeout=10)
        t, us, fr = [x.strip() for x in
                     r.stdout.decode().splitlines()[0].split(",")]
        b["vram_total_mb"] = int(t)
        b["vram_free_mb"] = int(fr)
    except Exception:                                        # noqa: BLE001
        b["vram_free_mb"] = None
    try:
        import ctypes

        class MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        ms = MS()
        ms.dwLength = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
        b["ram_avail_gb"] = round(ms.ullAvailPhys / 1e9, 1)
        b["ram_total_gb"] = round(ms.ullTotalPhys / 1e9, 1)
        b["mem_load_pct"] = ms.dwMemoryLoad
    except Exception:                                        # noqa: BLE001
        b["ram_avail_gb"] = None
    return b


def _parse_box(sec):
    d = {}
    mem = {}
    for line in sec.get("MEM", []):
        m = re.match(r"(\w+):\s+(\d+) kB", line.strip())
        if m:
            mem[m.group(1)] = int(m.group(2))
    if mem:
        d["ram_total_gb"] = round(mem.get("MemTotal", 0) * 1024 / 1e9, 1)
        # MemAvailable — never MemFree. This IS the VRAM budget on GB10.
        d["ram_avail_gb"] = round(mem.get("MemAvailable", 0) * 1024 / 1e9, 1)

    gpu, tot = {}, 0
    for line in sec.get("GPUAPPS", []):
        m = re.match(r"\s*(\d+),\s*(\d+)\s*MiB", line)
        if m:
            gpu[int(m.group(1))] = int(m.group(2))
            tot += int(m.group(2))
    d["gpu_by_pid"] = gpu
    d["gpu_held_gb"] = round(tot * 1.048576 / 1000, 1)
    d["gpu_gauge"] = None     # GB10: nvidia-smi reports FB memory as N/A

    for line in sec.get("DF", []):
        if line.strip().isdigit():
            d["disk_avail_gb"] = round(int(line.strip()) / 1e9)
    la = sec.get("LOAD", [])
    if la:
        try:
            d["load1"] = float(la[0].split()[0])
            d["nproc"] = int(la[1].strip()) if len(la) > 1 else None
            if d.get("nproc"):
                d["load_ratio"] = round(d["load1"] / d["nproc"], 2)
        except Exception:                                    # noqa: BLE001
            pass
    h = sec.get("HOST", [])
    if h:
        d["hostname"] = h[0].strip()
        if len(h) > 1:
            d["booted"] = h[1].strip()

    units = {}
    for key in ("UNITS", "UNITS_SYS"):
        cur = {}
        for line in sec.get(key, []):
            s = line.strip()
            if not s:
                if cur.get("Id"):
                    units[cur["Id"]] = cur
                cur = {}
                continue
            if "=" in s:
                k, v = s.split("=", 1)
                cur[k] = v
        if cur.get("Id"):
            units[cur["Id"]] = cur
    d["systemd"] = units

    procs = []
    for line in sec.get("PS", []):
        m = re.match(r"\s*(\d+)\s+(\w{3}\s+\w{3}\s+\d+\s+[\d:]+\s+\d{4})\s+(.*)",
                     line)
        if m:
            procs.append({"pid": int(m.group(1)),
                          "started": _lstart_epoch(m.group(2)),
                          "args": m.group(3)})
    d["procs"] = procs
    cg = {}
    for line in sec.get("CG", []):
        p = line.strip().split(" ", 1)
        if len(p) == 2 and p[0].isdigit():
            cg[int(p[0])] = p[1]
    d["cgroups"] = cg

    d["ports"] = [x.strip() for x in sec.get("PORTS", []) if x.strip()]

    oll = {}
    raw = "\n".join(sec.get("OLLAMA", [])).strip()
    if raw:
        try:
            j = json.loads(raw)
            for m in j.get("models", []):
                oll[m.get("name", "")] = {
                    "size_vram": m.get("size_vram"),
                    "expires_at": m.get("expires_at")}
        except Exception:                                    # noqa: BLE001
            pass
    d["ollama"] = oll

    http = {}
    for line in sec.get("HTTP", []):
        p = line.strip().rsplit(" ", 1)
        if len(p) == 2:
            try:
                http[p[0]] = int(p[1])
            except ValueError:
                http[p[0]] = None
    d["http"] = http
    return d


def _unit_state(u, box, now):
    """Every unit yields a triple: (declared, real, warm). Plus human_hold."""
    st = {"id": u["id"], "box": u["box"], "unit": u["unit"],
          "title_he": u.get("title_he"), "kind": u["kind"],
          "sacred": bool(u.get("sacred")), "sacred_why": u.get("sacred_why"),
          "watch_only": bool(u.get("watch_only")),
          "broken_window": u.get("broken_window"),
          "cost": u.get("cost", {}), "provenance": u.get("provenance"),
          "declared": None, "real": "unknown", "warm": None,
          "warm_expires_in_s": None, "human_hold": False, "detail": None,
          "startable": bool(u.get("start")), "stoppable": bool(u.get("stop"))}

    if box.get("reachable") is not True:
        st["real"] = "unknown"
        st["detail"] = "box %s: %s" % (u["box"], box.get("err") or "unreachable")
        return st

    sd = (box.get("systemd") or {}).get(u["unit"])
    if sd:
        ls, act = sd.get("LoadState"), sd.get("ActiveState")
        st["declared"] = act if ls == "loaded" else "%s/%s" % (ls, act)
        st["unit_file_state"] = sd.get("UnitFileState")
        try:
            st["main_pid"] = int(sd.get("MainPID") or 0) or None
        except ValueError:
            st["main_pid"] = None
        # "unit not found" is NEVER "not running"
        if ls == "not-found":
            st["declared"] = "not-found"

    p = u["probe"]
    t = p["type"]
    if t == "pgrep":
        hits = [q for q in (box.get("procs") or [])
                if re.search(re.escape(p["pattern"]), q["args"])]
        st["real"] = "up" if hits else "down"
        if hits:
            st["pids"] = [h["pid"] for h in hits]
            st["detail"] = hits[0]["args"][:160]
            st["main_pid"] = st.get("main_pid") or hits[0]["pid"]
            for h in hits:
                cgl = (box.get("cgroups") or {}).get(h["pid"], "")
                age = (now - h["started"]) if h.get("started") else None
                if ("session-" in cgl and "app.slice" not in cgl and
                        age is not None and age < HUMAN_HOLD_MAX_AGE_S):
                    st["human_hold"] = True
                    st["human_hold_why"] = (
                        "הופעל ביד לפני %d דקות (session scope, לא app.slice)"
                        % int(age / 60))
    elif t == "http":
        if p.get("via") == "ssh":
            code = (box.get("http") or {}).get(p["url"])
            st["real"] = ("up" if code in p["ok_status"] else
                          ("down" if code in (0, None, 000) else "down"))
            st["detail"] = "HTTP %s (from the box: loopback-only)" % code
        else:
            r = http_probe(p["url"], p["ok_status"], p.get("timeout_s", 5))
            st["real"] = "up" if r["up"] else "down"
            st["detail"] = ("HTTP %s in %s ms" % (r["code"], r["ms"])
                            if r["code"] else r["error"])
    elif t == "tcp_json":
        r = tcp_json_probe(p["host"], p["port"], p["op"], p["expect_key"],
                           p.get("timeout_s", 5))
        st["real"] = "up" if r["up"] else "down"
        st["detail"] = ("%s in %s ms" % (json.dumps(r.get("detail"),
                                                    ensure_ascii=False), r["ms"])
                        if r["up"] else r["error"])
    elif t == "ollama":
        found = None
        for name, info in (box.get("ollama") or {}).items():
            if name.startswith(p["model"]):
                found = info
                break
        st["real"] = "up" if found else "down"
        st["warm"] = bool(found)
        if found:
            st["detail"] = "ollama %.1f GB resident" % (
                (found.get("size_vram") or 0) / 1e9)
            exp = found.get("expires_at")
            if exp:
                try:
                    from datetime import datetime
                    e = datetime.fromisoformat(exp.replace("Z", "+00:00"))
                    st["warm_expires_in_s"] = int(e.timestamp() - now)
                except Exception:                            # noqa: BLE001
                    pass

    # warmth
    if st["warm"] is None:
        w = u.get("warm") or {}
        if w.get("type") == "gpu_ledger":
            # Check EVERY pid we know for this unit, not just systemd's MainPID:
            # winston-forever-v2's MainPID is a wrapper shell while the GPU is
            # held by its python child. MainPID alone reported it cold.
            cand = set(st.get("pids") or [])
            if st.get("main_pid"):
                cand.add(st["main_pid"])
            mb = sum((box.get("gpu_by_pid") or {}).get(p, 0) for p in cand)
            st["gpu_mb"] = mb
            st["warm"] = mb >= w.get("warm_gpu_gb", 5) * 1000
        elif st["real"] == "up":
            st["warm"] = None  # unknown warmth; do not claim

    # requirement 4: config vs reality, both shown
    d, r = st["declared"], st["real"]
    if d in ("active",) and r == "down":
        st["disagreement"] = "systemd אומר active, המדידה אומרת כבוי"
    elif d in ("inactive", "failed", "not-found", None) and r == "up":
        st["disagreement"] = ("systemd אומר %s, אבל התהליך רץ במדידה"
                              % (d or "לא מוגדר"))
    return st
