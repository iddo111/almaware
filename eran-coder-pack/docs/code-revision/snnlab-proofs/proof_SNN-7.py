"""proof_SNN-7 — starting a CUDA run on eran4 must need a credential.

eran4 carries alma-mic :7789 (Iddo's phone dictation), alma-stt, dmidi/Chai
:8806 and the coder door. POST /api/start on 0.0.0.0:8821 spawned a training
subprocess for anyone on the LAN or Tailscale, with no key of any kind, and
the systemd unit caps RAM/CPU/IO but not the GPU.

No training is started by this proof: Lab.launch is stubbed out.

  FAILS on server.py.bak-rev-20260906   PASSES on the fixed server.py
"""
import argparse
import json
import os
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from _proofcommon import HERE, load, verdict


def post(url, token=None):
    req = urllib.request.Request(url, data=b"{}", method="POST",
                                 headers={"Content-Type": "application/json"})
    if token is not None:
        req.add_header("X-SNN-Token", token)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def get(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(HERE, "server.py"))
    a = ap.parse_args()
    mod = load(a.src, "server_under_test")

    started = {"n": 0}

    def stub_launch(cfg):
        started["n"] += 1
        return True, "stub-no-real-run"
    mod.LAB.launch = stub_launch
    mod.LAB.stop = lambda: (True, "stub")

    srv = ThreadingHTTPServer(("127.0.0.1", 0), mod.Handler)
    srv.daemon_threads = True
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    try:
        code_health = get(base + "/api/health")
        code_open, body_open = post(base + "/api/start")
        token = getattr(mod.LAB, "token", None)
        code_auth, _ = post(base + "/api/start", token=token or "")
        code_bad, _ = post(base + "/api/start", token="not-the-key")
        code_stop, _ = post(base + "/api/stop")
        print(f"GET  /api/health                 -> {code_health}")
        print(f"POST /api/start  (no key)        -> {code_open} "
              f"{str(body_open.get('msg'))[:60]!r}")
        print(f"POST /api/start  (wrong key)     -> {code_bad}")
        print(f"POST /api/start  (correct key)   -> {code_auth}")
        print(f"POST /api/stop   (no key)        -> {code_stop}")
        print(f"training launches by an unauthenticated caller: {started['n']}")

        ok = (code_health == 200 and code_open == 401 and code_bad == 401
              and code_stop == 401 and code_auth == 200
              and token and len(str(token)) >= 16)
        # And the GPU ceiling the systemd caps never covered.
        try:
            T = load(os.path.join(HERE, "train.py"), "train_for_gpu_cap")
            seen = []
            T.torch.cuda.set_per_process_memory_fraction = \
                lambda f, d=0: seen.append((f, d))
            applied = T.cap_gpu_memory(T.torch.device("cuda"), 0.5,
                                       log=lambda *a: None)
            none_on_cpu = T.cap_gpu_memory(T.torch.device("cpu"), 0.5,
                                           log=lambda *a: None)
            print(f"cap_gpu_memory(cuda, 0.5) -> {applied}, torch told {seen}; "
                  f"on cpu -> {none_on_cpu}")
            ok = ok and applied == 0.5 and seen == [(0.5, 0)] and none_on_cpu is None
        except AttributeError as e:
            print(f"no GPU ceiling in train.py: {e}")
            ok = False
        return verdict(ok, "looking stays open; starting and stopping need the "
                           "key, and a run cannot take the whole card")
    finally:
        srv.shutdown()
        srv.server_close()


if __name__ == "__main__":
    sys.exit(main())
