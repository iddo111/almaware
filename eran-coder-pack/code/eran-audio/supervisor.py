"""
supervisor.py — keep ERAN v2 (AUDIO) alive forever, and periodically make him babble.

  * Single-instance (lockfile) so autostart never double-runs him.
  * Launches train.py (python -s) and restarts it if it ever dies.
  * Every LISTEN_INTERVAL_SEC, runs listen.py once to refresh babble_latest.wav
    (so you can always open the newest babble and hear how he's growing).

Run:  pythonw -s supervisor.py   (autostart) ,  or  python -s supervisor.py (visible)
"""

import os
import sys
import time
import subprocess
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
LOCK = os.path.join(HERE, ".supervisor.lock")
SUP_LOG = os.path.join(HERE, "supervisor.log")
CACHE_NPY = os.path.join(HERE, "tokens_cache.npy")
LISTEN_INTERVAL_SEC = 300          # refresh a babble .wav every 5 min
PRETOK_INTERVAL_SEC = 900          # fold newly-recorded sound into the cache every 15 min
RESTART_DELAY_SEC = 5

PY = sys.executable                 # the Python312 (cu121) interp that launched us


def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    try:
        with open(SUP_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)


def _alive(pid):
    try:
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
        if not h:
            return False
        ctypes.windll.kernel32.CloseHandle(h)
        return True
    except Exception:
        return False


def acquire_lock():
    if os.path.exists(LOCK):
        try:
            old = int(open(LOCK).read().strip() or "0")
            if old and _alive(old):
                log(f"another supervisor (pid {old}) is alive — exiting.")
                return False
        except Exception:
            pass
    try:
        with open(LOCK, "w") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass
    return True


def start_trainer():
    return subprocess.Popen(
        [PY, "-s", os.path.join(HERE, "train.py")],
        cwd=HERE,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def run_listen():
    try:
        subprocess.run([PY, "-s", os.path.join(HERE, "listen.py")],
                       cwd=HERE, timeout=180,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        log(f"listen run failed: {e}")


def start_pretokenize():
    """Launch encoding of NEW recordings into tokens_cache.npy as a SEPARATE,
    NON-BLOCKING process (no CUDA context, so EnCodec never crashes against the
    trainer's GPU torch). Returns the Popen; the trainer keeps running and reloads
    the cache when this finishes (data.py flushes incrementally)."""
    try:
        env = dict(os.environ, HF_HUB_DISABLE_SYMLINKS_WARNING="1")
        return subprocess.Popen([PY, "-s", os.path.join(HERE, "data.py")],
                                cwd=HERE, env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        log(f"pretokenize launch failed: {e}")
        return None


def main():
    if not acquire_lock():
        return
    log(f"supervisor up (pid {os.getpid()}); python={PY}")

    # Kick off encoding of the FULL heard world in the BACKGROUND (non-blocking).
    # data.py flushes the cache every 200 files, so the trainer can start NOW on
    # whatever exists and reload the bigger cache as it grows.
    pretok = start_pretokenize()
    log(f"initial pretokenize launched in background (pid {pretok.pid if pretok else 'n/a'}).")

    # if there is no cache at all yet, wait briefly for the first flush so the
    # trainer has something to chew on (otherwise it just retries).
    waited = 0
    while not os.path.exists(CACHE_NPY) and waited < 600:
        time.sleep(5); waited += 5

    proc = start_trainer()
    log(f"trainer started (pid {proc.pid}).")
    last_listen = 0.0
    last_pretok = time.time()
    try:
        while True:
            if proc.poll() is not None:
                log(f"trainer exited (code {proc.returncode}); restarting in {RESTART_DELAY_SEC}s.")
                time.sleep(RESTART_DELAY_SEC)
                proc = start_trainer()
                log(f"trainer restarted (pid {proc.pid}).")
            now = time.time()
            if now - last_listen >= LISTEN_INTERVAL_SEC:
                if os.path.exists(os.path.join(HERE, "checkpoints", "latest.pt")):
                    run_listen()
                last_listen = now
            # fold in newly recorded sound — but only if no encode is already running
            if now - last_pretok >= PRETOK_INTERVAL_SEC and (pretok is None or pretok.poll() is not None):
                pretok = start_pretokenize()
                last_pretok = now
            time.sleep(5)
    finally:
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            os.remove(LOCK)
        except Exception:
            pass


if __name__ == "__main__":
    main()
