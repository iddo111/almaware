"""
Power-dense CPU benchmark: OpenBLAS DGEMM (AVX2) on i7-7700K.

This is the hard one -- BLAS matmul is the closest thing to a Prime95-class
power load we can run from stdlib+numpy, and it produces a real GFLOPS score.

Phase A: 1 BLAS thread  (single-core GFLOPS)
Phase B: all threads, sustained soak (multi-core GFLOPS + thermal curve)

Safety: monitor thread polls LibreHardwareMonitor :8085 every 2 s and hard-stops
the run at ABORT_C.
"""
import csv
import json
import os
import sys
import threading
import time
import urllib.request

OUT_CSV = sys.argv[1] if len(sys.argv) > 1 else "bench_avx.csv"
SOAK_SECONDS = int(sys.argv[2]) if len(sys.argv) > 2 else 180
LHM = "http://127.0.0.1:8085/data.json"
ABORT_C = 95.0
N = 3072  # matrix dim; 2*N^3 flops per matmul

T0 = time.time()
rows = []
stop = threading.Event()
phase = ["idle"]


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
        "pkg_w": g("i7-7700K/Powers/CPU Package"),
        "mhz": g("i7-7700K/Clocks/CPU Core #1"),
        "load": g("i7-7700K/Load/CPU Total"),
        "fan2": g("NCT6793D/Fans/Fan #2"),
        "fan3": g("NCT6793D/Fans/Fan #3"),
    }


def monitor():
    while not stop.is_set():
        try:
            s = sample()
        except Exception as e:
            s = {"err": str(e)[:60]}
        s["t"] = round(time.time() - T0, 1)
        s["phase"] = phase[0]
        rows.append(s)
        if (s.get("pkg_c") or 0) >= ABORT_C:
            print(f"!! ABORT at {s['pkg_c']} C", flush=True)
            stop.set()
            return
        time.sleep(2)


def gflops_run(np, seconds, label):
    a = np.random.rand(N, N)
    b = np.random.rand(N, N)
    flops_per = 2.0 * N ** 3
    # warm-up
    a @ b
    t0 = time.time()
    n = 0
    while time.time() - t0 < seconds and not stop.is_set():
        a @ b
        n += 1
    dt = time.time() - t0
    gf = (n * flops_per) / dt / 1e9
    print(f"{label}: {n} matmuls in {dt:.1f}s -> {gf:.1f} GFLOPS", flush=True)
    return gf


if __name__ == "__main__":
    threading.Thread(target=monitor, daemon=True).start()
    print("== idle baseline 10 s ==", flush=True)
    time.sleep(10)

    # Phase A -- single BLAS thread, in a child process so env applies
    phase[0] = "single"
    print("== phase A: 1 BLAS thread / 20 s ==", flush=True)
    import subprocess

    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1")
    code = (
        "import numpy,time;N=%d;a=numpy.random.rand(N,N);b=numpy.random.rand(N,N);"
        "a@b;t=time.time();n=0\n"
        "while time.time()-t<20: a@b; n+=1\n"
        "print((n*2*N**3)/(time.time()-t)/1e9)" % N
    )
    r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    single_gf = float(r.stdout.strip().splitlines()[-1]) if r.returncode == 0 else None
    print(f"single-thread: {single_gf} GFLOPS", flush=True)

    # Phase B -- all threads
    phase[0] = "allcore"
    import numpy as np

    print(f"== phase B: all BLAS threads / {SOAK_SECONDS} s ==", flush=True)
    multi_gf = gflops_run(np, SOAK_SECONDS, "all-core")

    phase[0] = "cooldown"
    print("== cooldown 20 s ==", flush=True)
    time.sleep(20)
    stop.set()
    time.sleep(0.3)

    keys = ["t", "phase", "pkg_c", "pkg_w", "mhz", "load", "fan2", "fan3", "err"]
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    def stat(ph, key, fn):
        v = [r[key] for r in rows if r.get("phase") == ph and r.get(key) is not None]
        return round(fn(v), 1) if v else None

    hit = [r["pkg_c"] for r in rows if (r.get("pkg_c") or 0) >= ABORT_C]
    summary = {
        "matrix_N": N,
        "aborted": bool(hit),
        "single_thread_gflops": round(single_gf, 1) if single_gf else None,
        "all_core_gflops": round(multi_gf, 1),
        "idle_pkg_c": stat("idle", "pkg_c", lambda v: sum(v) / len(v)),
        "allcore_max_c": stat("allcore", "pkg_c", max),
        "allcore_avg_c": stat("allcore", "pkg_c", lambda v: sum(v) / len(v)),
        "allcore_max_w": stat("allcore", "pkg_w", max),
        "allcore_avg_w": stat("allcore", "pkg_w", lambda v: sum(v) / len(v)),
        "allcore_min_mhz": stat("allcore", "mhz", min),
        "allcore_max_mhz": stat("allcore", "mhz", max),
        "allcore_avg_load": stat("allcore", "load", lambda v: sum(v) / len(v)),
        "fan2_max": stat("allcore", "fan2", max),
        "fan3_max": stat("allcore", "fan3", max),
        "cooldown_end_c": rows[-1].get("pkg_c") if rows else None,
        "samples": len(rows),
    }
    with open(OUT_CSV.replace(".csv", ".json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    print(json.dumps(summary, indent=2), flush=True)
