"""
Alma Federation — Worker (a member node: a free VM, Colab, Oracle always-free, ...).  [HARDENED]
Registers with the coordinator, pulls jobs, runs them, posts results back.
Pure stdlib — deploy on any free-tier box you legitimately own. לע"נ עלמה ז"ל.

⚠️  SECURITY: a worker executes commands the coordinator sends it. ONLY point a
worker at YOUR OWN coordinator with YOUR OWN secret token, over Tailscale/VPN.
Never join a coordinator/token you don't control.

Run:  ALMA_COORD=http://<dgx>:8900 ALMA_TOKEN=<secret> python worker.py
Env:  ALMA_COORD  ALMA_TOKEN  ALMA_WORKER(hostname)  ALMA_POLL(3)  ALMA_JOB_TIMEOUT(600)
"""
import json, os, socket, subprocess, time, urllib.request, urllib.error, platform, sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

COORD = os.environ.get("ALMA_COORD", "http://127.0.0.1:8900").rstrip("/")
TOKEN = os.environ.get("ALMA_TOKEN", "alma")
WORKER = os.environ.get("ALMA_WORKER", socket.gethostname())
POLL = float(os.environ.get("ALMA_POLL", "3"))
JOB_TIMEOUT = int(os.environ.get("ALMA_JOB_TIMEOUT", "600"))


def call(path, obj=None):
    data = json.dumps(obj).encode() if obj is not None else None
    req = urllib.request.Request(COORD + path, data=data, method=("POST" if data is not None else "GET"))
    req.add_header("X-Alma-Token", TOKEN)
    if data is not None: req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read() or b"{}")


def run_job(cmd):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=JOB_TIMEOUT)
        out = (p.stdout + (("\n[stderr]\n" + p.stderr) if p.stderr else "")).strip()
        return out, p.returncode
    except subprocess.TimeoutExpired:
        return f"[worker] job exceeded {JOB_TIMEOUT}s timeout", 124
    except Exception as e:
        return f"[worker error] {e}", 1


def main():
    if TOKEN == "alma":
        print("⚠️  [worker] DEFAULT TOKEN 'alma' — set ALMA_TOKEN=<secret> for real use.")
    if "127.0.0.1" in COORD or "localhost" in COORD:
        print("ℹ️  [worker] coordinator is localhost (test mode).")
    print(f"🔒 [worker] I will run commands sent by {COORD}. Only join a coordinator YOU control.")
    meta = {"host": WORKER, "os": platform.platform(), "py": platform.python_version(),
            "cpus": os.cpu_count()}
    while True:
        try:
            call("/register", {"worker": WORKER, "meta": meta})
            print(f"[alma-federation] worker '{WORKER}' joined {COORD}")
            break
        except Exception as e:
            print(f"  [register failed] {e}; retrying in {POLL}s"); time.sleep(POLL)
    while True:
        try:
            job = call(f"/pull?worker={WORKER}")
            if job.get("job_id"):
                jid, cmd = job["job_id"], job["cmd"]
                print(f"  -> {jid}: {cmd[:60]}")
                out, rc = run_job(cmd)
                call("/result", {"job_id": jid, "output": out, "rc": rc})
                print(f"  <- {jid} done (rc={rc})")
            else:
                time.sleep(POLL)
        except Exception as e:
            print(f"  [poll error] {e}; retry in {POLL}s"); time.sleep(POLL)


if __name__ == "__main__":
    main()
