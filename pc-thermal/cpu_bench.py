"""
CPU benchmark + thermal soak for IDDO1 (i7-7700K, GPU disconnected).

Phase A: single-thread score (15 s)
Phase B: all-core sustained soak (180 s) -> throughput score + thermal curve

Safety: a monitor thread polls LibreHardwareMonitor :8085 every 2 s.
If CPU Package temp >= ABORT_C the workers are killed immediately.
"""
import csv
import hashlib
import json
import math
import multiprocessing as mp
import sys
import time
import urllib.request

LHM = "http://127.0.0.1:8085/data.json"
ABORT_C = 95.0
SOAK_SECONDS = 180
SINGLE_SECONDS = 15
OUT_CSV = sys.argv[1] if len(sys.argv) > 1 else "bench_thermal.csv"
OUT_JSON = OUT_CSV.replace(".csv", ".json")

CHUNK = 2000  # inner ops per accounted unit


def _burn(chunk):
    """One accounted unit of mixed integer(hash) + float work."""
    h = hashlib.sha256(b"alma").digest()
    acc = 0.0
    for i in range(chunk):
        h = hashlib.sha256(h).digest()
        acc += math.sqrt(i + 1) * math.sin(i * 0.5)
    return acc


def worker(seconds, q, stop):
    units = 0
    t_end = time.time() + seconds
    while time.time() < t_end and not stop.is_set():
        _burn(CHUNK)
        units += 1
    q.put(units)


# ---------- LHM sensor walk ----------
def _flat(node, path, out):
    p = f"{path}/{node.get('Text','')}" if path else node.get("Text", "")
    v = node.get("Value") or ""
    if v:
        out[p] = v
    for c in node.get("Children", []):
        _flat(c, p, out)


def _num(s):
    try:
        return float(str(s).split()[0].replace(",", "."))
    except Exception:
        return None


def sample():
    with urllib.request.urlopen(LHM, timeout=4) as r:
        d = json.load(r)
    f = {}
    _flat(d, "", f)
    g = lambda frag: next((_num(v) for k, v in f.items() if k.endswith(frag)), None)
    return {
        "pkg_c": g("i7-7700K/Temperatures/CPU Package"),
        "core_max_c": g("i7-7700K/Temperatures/Core Max"),
        "pkg_w": g("i7-7700K/Powers/CPU Package"),
        "mhz": g("i7-7700K/Clocks/CPU Core #1"),
        "load": g("i7-7700K/Load/CPU Total"),
        "fan1": g("NCT6793D/Fans/Fan #1"),
        "fan2": g("NCT6793D/Fans/Fan #2"),
        "fan3": g("NCT6793D/Fans/Fan #3"),
        "mb_c": g("NCT6793D/Temperatures/CPU Core"),
    }


def monitor(stop, phase, rows):
    while not stop.is_set():
        try:
            s = sample()
        except Exception as e:
            s = {"err": str(e)[:60]}
        s["t"] = round(time.time() - T0, 1)
        s["phase"] = phase.value.decode()
        rows.append(s)
        pkg = s.get("pkg_c")
        if pkg is not None and pkg >= ABORT_C:
            print(f"!! ABORT {pkg} C >= {ABORT_C}", flush=True)
            stop.set()
            return
        time.sleep(2)


if __name__ == "__main__":
    mp.freeze_support()
    T0 = time.time()
    mgr = mp.Manager()
    rows = mgr.list()
    stop = mgr.Event()
    phase = mp.Array("c", b"idle      ")

    def set_phase(name):
        phase.value = name.ljust(10).encode()

    import threading

    set_phase("idle")
    mon = threading.Thread(target=monitor, args=(stop, phase, rows), daemon=True)
    mon.start()

    print("== idle baseline 10 s ==", flush=True)
    time.sleep(10)

    # ---- Phase A: single thread ----
    set_phase("single")
    print(f"== phase A: 1 thread / {SINGLE_SECONDS} s ==", flush=True)
    q = mgr.Queue()
    p = mp.Process(target=worker, args=(SINGLE_SECONDS, q, stop))
    ta = time.time()
    p.start()
    p.join()
    ta = time.time() - ta
    single_units = q.get() if not q.empty() else 0
    single_score = single_units * CHUNK / ta

    # ---- Phase B: all cores ----
    set_phase("allcore")
    n = mp.cpu_count()
    print(f"== phase B: {n} threads / {SOAK_SECONDS} s ==", flush=True)
    q2 = mgr.Queue()
    procs = [mp.Process(target=worker, args=(SOAK_SECONDS, q2, stop)) for _ in range(n)]
    tb = time.time()
    for x in procs:
        x.start()
    for x in procs:
        x.join()
    tb = time.time() - tb
    total_units = 0
    while not q2.empty():
        total_units += q2.get()
    multi_score = total_units * CHUNK / tb

    set_phase("cooldown")
    print("== cooldown 20 s ==", flush=True)
    time.sleep(20)
    stop.set()
    time.sleep(0.3)

    data = [dict(r) for r in rows]
    keys = ["t", "phase", "pkg_c", "core_max_c", "pkg_w", "mhz", "load",
            "fan1", "fan2", "fan3", "mb_c", "err"]
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(data)

    def stat(ph, key, fn):
        vals = [r[key] for r in data if r.get("phase", "").strip() == ph and r.get(key) is not None]
        return round(fn(vals), 1) if vals else None

    summary = {
        "aborted": stop.is_set() and any(
            (r.get("pkg_c") or 0) >= ABORT_C for r in data),
        "threads": n,
        "single_thread_ops_per_s": round(single_score),
        "all_core_ops_per_s": round(multi_score),
        "scaling_x": round(multi_score / single_score, 2) if single_score else None,
        "idle_pkg_c": stat("idle", "pkg_c", lambda v: sum(v) / len(v)),
        "single_max_c": stat("single", "pkg_c", max),
        "allcore_max_c": stat("allcore", "pkg_c", max),
        "allcore_avg_c": stat("allcore", "pkg_c", lambda v: sum(v) / len(v)),
        "allcore_max_w": stat("allcore", "pkg_w", max),
        "allcore_min_mhz": stat("allcore", "mhz", min),
        "allcore_max_mhz": stat("allcore", "mhz", max),
        "allcore_avg_load": stat("allcore", "load", lambda v: sum(v) / len(v)),
        "fan1_max": stat("allcore", "fan1", max),
        "fan2_max": stat("allcore", "fan2", max),
        "fan3_max": stat("allcore", "fan3", max),
        "cooldown_end_c": data[-1].get("pkg_c") if data else None,
        "samples": len(data),
    }
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    print(json.dumps(summary, indent=2), flush=True)
