"""server.py — the window into the spiking network. stdlib only.

Iddo asked to TRAIN and to SEE ("אני רוצה לאמן ולראות"). So this serves one
page that starts a run and then draws what the neurons are actually doing:
loss, accuracy, and the spike raster — which neuron fired at which timestep —
plus the membrane potentials climbing to threshold and resetting.

Training is a SUBPROCESS, not a thread. If torch segfaults or CUDA falls over,
the page stays up and says so, instead of dying with it. The subprocess writes
newline-delimited JSON; this server tails that file and serves the parsed state
as JSON. One run at a time — a second Start while running is refused with a
message, never silently queued and never allowed to corrupt the state.

Nothing here may endanger the mic. The service is nice'd and memory-capped by
systemd; this process itself holds a few MB and does no compute.

    python server.py --port 8821
"""
import json
import os
import shlex
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(HERE, "venv", "bin", "python")
RUNS = os.path.join(HERE, "runs")
RESULTS = os.path.join(HERE, "results")
PAGE = os.path.join(HERE, "page.html")

MAX_STEP_POINTS = 400          # what the loss curve is downsampled to
MAX_LOG_LINES = 200

# Every knob the page may set: name -> (type, min, max). Anything not in here
# is dropped, and anything out of range is clamped. The config becomes an argv
# list (never a shell string), so this is about sane runs, not just safety.
KNOBS = {
    "dataset": (str, None, None),
    "encoding": (str, None, None),
    "surrogate": (str, None, None),
    "hidden": (int, 8, 4096),
    "epochs": (int, 1, 500),
    "batch": (int, 1, 512),
    "steps": (int, 4, 200),
    "beta": (float, 0.05, 0.999),
    "threshold": (float, 0.05, 20.0),
    "lr": (float, 1e-6, 1.0),
    "input_gain": (float, 0.01, 200.0),
    "seed": (int, 0, 10 ** 6),
}
CHOICES = {
    "dataset": {"mnist", "syllables"},
    "encoding": {"rate", "latency", "static", "cochlea-time"},
    "surrogate": {"atan", "sigmoid", "fast_sigmoid", "triangular",
                  "straight_through"},
}


def clean(raw):
    """Untrusted JSON from the page -> a config we are willing to run."""
    cfg = {}
    for k, (typ, lo, hi) in KNOBS.items():
        if k not in raw:
            continue
        try:
            v = typ(raw[k])
        except (TypeError, ValueError):
            continue
        if typ is str:
            if k in CHOICES and v not in CHOICES[k]:
                continue
        else:
            v = max(lo, min(hi, v))
        cfg[k] = v
    cfg.setdefault("dataset", "syllables")
    if cfg["dataset"] == "mnist" and cfg.get("encoding") == "cochlea-time":
        cfg["encoding"] = "rate"
    if cfg["dataset"] == "syllables" and cfg.get("encoding") in ("rate", "latency"):
        # The cochlear percept is mean-removed and therefore signed; rate and
        # latency coding both need values in [0,1]. Refuse rather than silently
        # feed it garbage.
        cfg["encoding"] = "cochlea-time"
    cfg["recurrent"] = bool(raw.get("recurrent"))
    return cfg


class Lab:
    """The one run, and everything known about it."""

    def __init__(self):
        self.lock = threading.Lock()
        self.proc = None
        self.reader = None
        self.reset()
        os.makedirs(RUNS, exist_ok=True)
        os.makedirs(RESULTS, exist_ok=True)

    def reset(self):
        self.run_id = None
        self.cfg = None
        self.start = None          # the "start" event: device, chance, baselines
        self.steps = []
        self.epochs = []
        self.viz = None
        self.log = []
        self.done = None
        self.error = None
        self.started_at = None

    # ------------------------------------------------------------- lifecycle
    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def launch(self, cfg):
        with self.lock:
            if self.running():
                return False, f"a run is already going ({self.run_id}) — stop it first"
            if not os.path.exists(PY):
                return False, f"interpreter missing: {PY}"
            self.reset()
            run_id = f"{cfg['dataset']}-{time.strftime('%Y%m%d-%H%M%S')}"
            ev = os.path.join(RUNS, run_id + ".jsonl")
            res = os.path.join(RESULTS, run_id + ".json")
            argv = [PY, os.path.join(HERE, "train.py"),
                    "--run-id", run_id, "--events", ev, "--results", res]
            for k, v in cfg.items():
                if k == "recurrent":
                    if v:
                        argv.append("--recurrent")
                elif k == "input_gain":
                    argv += ["--input-gain", str(v)]
                else:
                    argv += [f"--{k}", str(v)]
            self.run_id, self.cfg, self.started_at = run_id, cfg, time.time()
            self.log.append("$ " + " ".join(shlex.quote(a) for a in argv))
            self.proc = subprocess.Popen(
                argv, cwd=HERE, stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT, start_new_session=True)
            self.reader = threading.Thread(target=self._tail, args=(ev,),
                                           daemon=True)
            self.reader.start()
            return True, run_id

    def stop(self):
        with self.lock:
            if not self.running():
                return False, "nothing is running"
            # SIGTERM is a REQUEST: train.py catches it, finishes the step and
            # writes the partial result. Only escalate if it ignores us.
            self.proc.send_signal(signal.SIGTERM)
            return True, f"asked {self.run_id} to stop"

    def _tail(self, path):
        """Follow the subprocess's event file until it exits and stops growing."""
        deadline = None
        pos = 0
        while True:
            try:
                if os.path.exists(path):
                    with open(path, "r", encoding="utf-8") as f:
                        f.seek(pos)
                        for line in f:
                            if not line.endswith("\n"):
                                break          # half-written; get it next pass
                            pos += len(line.encode("utf-8"))
                            self._absorb(line)
            except OSError:
                pass
            alive = self.proc is not None and self.proc.poll() is None
            if not alive:
                # Give the file a moment to settle after the process exits.
                deadline = deadline or time.time() + 2.0
                if time.time() > deadline:
                    if self.done is None and self.error is None:
                        rc = self.proc.poll() if self.proc else None
                        self.error = (f"training exited with code {rc} "
                                      f"before finishing")
                    return
            time.sleep(0.25)

    def _absorb(self, line):
        try:
            e = json.loads(line)
        except ValueError:
            return
        kind = e.get("ev")
        if kind == "start":
            self.start = e
        elif kind == "step":
            self.steps.append(e)
        elif kind == "epoch":
            self.epochs.append(e)
        elif kind == "viz":
            self.viz = e
        elif kind == "done":
            self.done = e
        elif kind == "error":
            self.error = e.get("msg")
        elif kind == "log":
            self.log.append(e.get("msg", ""))
            del self.log[:-MAX_LOG_LINES]

    # ----------------------------------------------------------------- views
    def state(self):
        steps = self.steps
        if len(steps) > MAX_STEP_POINTS:
            k = len(steps) / MAX_STEP_POINTS
            steps = [steps[min(len(steps) - 1, int(i * k))]
                     for i in range(MAX_STEP_POINTS)]
        return {
            "running": self.running(),
            "run_id": self.run_id,
            "cfg": self.cfg,
            "start": self.start,
            "steps": [{"s": s["step"], "l": s["loss"],
                       "a": s.get("train_batch_acc"),
                       "r": s.get("hidden_rate")} for s in steps],
            "epochs": self.epochs,
            "viz": self.viz,
            "log": self.log[-40:],
            "done": self.done,
            "error": self.error,
            "elapsed": round(time.time() - self.started_at, 1)
            if self.started_at else None,
            "now": time.time(),
        }

    def history(self, limit=40):
        out = []
        try:
            files = sorted(os.listdir(RESULTS), reverse=True)
        except OSError:
            return out
        for fn in files:
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(RESULTS, fn), "r", encoding="utf-8") as f:
                    r = json.load(f)
            except (OSError, ValueError):
                continue
            # results/ also holds reports that are not runs (SWEEP.json,
            # HELDOUT-TEMPORAL.json). Without this they render as a row of
            # empty cells, which reads like a run that failed.
            if not isinstance(r, dict) or "cfg" not in r or "run_id" not in r:
                continue
            c = r.get("cfg", {})
            out.append({
                "run_id": r.get("run_id", fn[:-5]),
                "dataset": c.get("dataset"), "encoding": c.get("encoding"),
                "hidden": c.get("hidden"), "beta": c.get("beta"),
                "threshold": c.get("threshold"), "lr": c.get("lr"),
                "steps": c.get("steps"), "surrogate": c.get("surrogate"),
                "recurrent": bool(c.get("recurrent")),
                "epochs_done": r.get("epochs_done"),
                "final": r.get("final_test_acc"), "best": r.get("best_test_acc"),
                "chance": r.get("chance"), "wall": r.get("wall_seconds"),
                "device": r.get("device"), "stopped": r.get("stopped"),
                "hidden_rate": r.get("hidden_rate"),
                "vs_organism": r.get("vs_prototype_organism"),
                "when": r.get("finished_utc"),
            })
            if len(out) >= limit:
                break
        return out


LAB = Lab()


class Handler(BaseHTTPRequestHandler):
    server_version = "snn-lab"

    def log_message(self, fmt, *args):
        pass                      # the journal does not need every poll

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        blob = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(blob)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(blob)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            try:
                with open(PAGE, "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")
            except OSError as e:
                return self._send(500, f"page.html unreadable: {e}",
                                  "text/plain; charset=utf-8")
        if path == "/api/state":
            return self._json(LAB.state())
        if path == "/api/runs":
            return self._json({"runs": LAB.history()})
        if path == "/api/health":
            return self._json({"ok": True, "running": LAB.running(),
                               "run_id": LAB.run_id})
        return self._send(404, "not found", "text/plain; charset=utf-8")

    def do_POST(self):
        path = self.path.split("?")[0]
        try:
            n = int(self.headers.get("Content-Length") or 0)
            raw = json.loads(self.rfile.read(n) or b"{}") if n else {}
        except (ValueError, TypeError):
            return self._json({"ok": False, "msg": "bad JSON"}, 400)
        if path == "/api/start":
            if not isinstance(raw, dict):
                return self._json({"ok": False, "msg": "bad config"}, 400)
            # Audit line: every run start says who asked. This box is shared
            # with other agents and other sessions; when a run appears that
            # nobody admits to, this is the only way to find out whose it was.
            print(f"START from {self.client_address[0]} "
                  f"ua={self.headers.get('User-Agent', '?')!r} "
                  f"ref={self.headers.get('Referer', '-')!r} cfg={raw}",
                  flush=True)
            ok, msg = LAB.launch(clean(raw))
            return self._json({"ok": ok, "msg": msg}, 200 if ok else 409)
        if path == "/api/stop":
            ok, msg = LAB.stop()
            return self._json({"ok": ok, "msg": msg})
        return self._send(404, "not found", "text/plain; charset=utf-8")


def main():
    port = 8821
    host = "0.0.0.0"
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "--port" and i + 1 < len(args):
            port = int(args[i + 1])
        if a == "--host" and i + 1 < len(args):
            host = args[i + 1]
    srv = ThreadingHTTPServer((host, port), Handler)
    srv.daemon_threads = True
    print(f"snn-lab on http://{host}:{port}/  (page {PAGE})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if LAB.running():
            LAB.proc.send_signal(signal.SIGTERM)


if __name__ == "__main__":
    main()
