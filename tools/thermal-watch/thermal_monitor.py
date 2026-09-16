"""
ALMA-ThermalWatch -- Iddo 2026-09-15, after an unexplained PC hard-freeze
(16:48-19:24, no BSOD/dump/WHEA logged -- see D:\\CLAUDE\\CLAUDE.md PC thermal note).
Purpose: keep a rolling temp/load log on disk so that IF it freezes again,
the last lines before the gap show what was hot/loaded right before.
Flushes to disk every tick -- a hard hang can't lose data already written.
Runs BELOW_NORMAL priority per the PC-heavy-work law; never chokes the PC.
"""
import csv
import os
import subprocess
import sys
import time

try:
    import psutil
except ImportError:
    print("psutil missing: pip install psutil", file=sys.stderr)
    sys.exit(1)

INTERVAL_SEC = 10
LOG_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(LOG_DIR, "thermal_log.csv")
MAX_LINES = 500_000  # ~58 days at 10s ticks; trimmed to half when exceeded

GPU_TEMP_WARN = 83
CPU_PCT_WARN = 95

HEADER = ["timestamp", "cpu_pct", "mem_pct", "gpu_name", "gpu_temp_c",
          "gpu_util_pct", "gpu_power_w", "gpu_mem_used_mb", "flag"]


def set_below_normal():
    try:
        p = psutil.Process(os.getpid())
        p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    except Exception:
        pass


def read_gpu():
    try:
        out = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=name,temperature.gpu,utilization.gpu,power.draw,memory.used",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return ("N/A", "", "", "", "")
        parts = [p.strip() for p in out.stdout.strip().splitlines()[0].split(",")]
        while len(parts) < 5:
            parts.append("")
        return tuple(parts[:5])
    except Exception:
        return ("N/A", "", "", "", "")


def trim_if_huge():
    try:
        if not os.path.exists(LOG_PATH):
            return
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > MAX_LINES:
            keep = [lines[0]] + lines[-(MAX_LINES // 2):]
            tmp = LOG_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.writelines(keep)
            os.replace(tmp, LOG_PATH)
    except Exception:
        pass


def main():
    set_below_normal()
    new_file = not os.path.exists(LOG_PATH)
    trim_if_huge()
    while True:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        cpu_pct = psutil.cpu_percent(interval=1)
        mem_pct = psutil.virtual_memory().percent
        gpu_name, gpu_temp, gpu_util, gpu_power, gpu_mem = read_gpu()

        flag = ""
        try:
            if gpu_temp and float(gpu_temp) >= GPU_TEMP_WARN:
                flag = "GPU_HOT"
        except ValueError:
            pass
        if cpu_pct >= CPU_PCT_WARN:
            flag = (flag + "+CPU_HIGH") if flag else "CPU_HIGH"

        row = [ts, cpu_pct, mem_pct, gpu_name, gpu_temp, gpu_util, gpu_power, gpu_mem, flag]

        with open(LOG_PATH, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow(HEADER)
                new_file = False
            w.writerow(row)
            f.flush()
            os.fsync(f.fileno())

        time.sleep(max(0, INTERVAL_SEC - 1))


if __name__ == "__main__":
    main()
