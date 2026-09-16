#!/usr/bin/env python
"""continuous_trainer.py — always-on, throttled voice-adaptation trainer.

Watches profiles/<user>/samples.jsonl and retrains the personalized Whisper LoRA
adapter (reusing learner.py) in *throttled bursts* whenever enough NEW voice
samples have accumulated, then the mic can load the exported CT2 model. Runs
forever, yields the GPU to the live mic, and self-restarts via ensure-trainer.ps1.

Resource policy ("~40%"): BELOW_NORMAL process priority + capped CPU threads +
bursty cadence (not a constant GPU peg) + yields when the GPU-maestro says the
live mic/STT is busy. Training itself runs as an ISOLATED subprocess so a crash
or sys.exit in learner.train() can never kill this loop.

Runs fine even before the GPU deps are installed — it idles, logs "deps missing",
and the moment torch/transformers/peft/datasets/soundfile appear it starts training.

"""
from __future__ import annotations

import argparse
import json
import logging
import multiprocessing
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent.resolve()
sys.path.insert(0, str(HERE))
import learner  # reuse the existing LoRA pipeline (stdlib-only at import time)

# ── cadence / throttle (env-overridable) ────────────────────────────────────────
NEW_SAMPLES_TO_TRAIN = int(os.getenv("VT_NEW_SAMPLES", "15"))     # train after N new samples
MIN_INTERVAL_S       = int(os.getenv("VT_MIN_INTERVAL", "1800"))  # >= 30 min between bursts
POLL_S               = int(os.getenv("VT_POLL", "60"))            # check cadence
GPU_MEM_FRACTION     = os.getenv("VT_GPU_FRACTION", "0.4")        # passed to training subprocess
CPU_FRACTION         = float(os.getenv("VT_CPU_FRACTION", "0.4"))
GPU_MAESTRO_URL      = os.getenv("VT_MAESTRO", "http://127.0.0.1:8078")

log = logging.getLogger("continuous_trainer")

def _setup_logging(profile):
    Path(profile.profile_dir).mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(Path(profile.profile_dir) / "continuous_trainer.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[fh, logging.StreamHandler(sys.stdout)])

def _lower_priority():
    try:
        if os.name == "nt":
            import ctypes
            BELOW_NORMAL = 0x00004000
            k = ctypes.windll.kernel32
            k.SetPriorityClass(k.GetCurrentProcess(), BELOW_NORMAL)
        else:
            os.nice(15)
    except Exception as e:  # noqa: BLE001
        log.warning("could not lower priority: %s", e)

def _cpu_threads() -> int:
    return max(1, int(multiprocessing.cpu_count() * CPU_FRACTION))

def _maestro_ok() -> bool:
    """Yield the GPU to the live mic: ask the GPU-maestro if STT is busy.
    Fails OPEN (returns True) when the maestro isn't reachable."""
    try:
        with urllib.request.urlopen(GPU_MAESTRO_URL + "/status", timeout=2) as r:
            data = json.loads(r.read().decode())
        return not (data.get("busy") or data.get("stt_active") or data.get("mic_active"))
    except Exception:
        return True

def _state_path(profile):
    return Path(profile.profile_dir) / ".trainer_state.json"

def _load_state(profile) -> dict:
    p = _state_path(profile)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return {"last_trained_samples": 0, "last_train_ts": 0}

def _save_state(profile, st: dict):
    _state_path(profile).write_text(json.dumps(st), encoding="utf-8")

def _train_once(username: str, profiles_dir: str | None) -> bool:
    """Run one isolated, throttled training burst via the learner CLI."""
    env = dict(os.environ)
    n = str(_cpu_threads())
    env["OMP_NUM_THREADS"] = n
    env["MKL_NUM_THREADS"] = n
    env["VT_GPU_FRACTION"] = str(GPU_MEM_FRACTION)
    env["PYTORCH_CUDA_ALLOC_CONF"] = "max_split_size_mb:256"
    cmd = [sys.executable, str(HERE / "learner.py"), "--train", "--user", username]
    if profiles_dir:
        cmd += ["--profiles-dir", profiles_dir]
    flags = subprocess.BELOW_NORMAL_PRIORITY_CLASS if os.name == "nt" else 0
    log.info("training burst -> %s", " ".join(cmd))
    try:
        p = subprocess.run(cmd, env=env, creationflags=flags)
        return p.returncode == 0
    except Exception as e:  # noqa: BLE001
        log.exception("training subprocess failed: %s", e)
        return False

def run(username: str, profiles_dir: str | None = None):
    _lower_priority()
    os.environ["OMP_NUM_THREADS"] = str(_cpu_threads())
    profile = learner.VoiceProfile(username=username, profiles_dir=profiles_dir)
    _setup_logging(profile)
    log.info("=== continuous_trainer up for user=%s (poll=%ss, burst@%d new samples, >=%ss apart) ===",
             username, POLL_S, NEW_SAMPLES_TO_TRAIN, MIN_INTERVAL_S)
    warned_deps = False
    while True:
        try:
            missing = learner._check_deps()
            if missing:
                if not warned_deps:
                    log.warning("waiting for training deps: %s (loop will auto-train once installed)",
                                ", ".join(missing))
                    warned_deps = True
                time.sleep(POLL_S)
                continue
            warned_deps = False
            st = _load_state(profile)
            total = profile.sample_count()
            new = total - int(st.get("last_trained_samples", 0))
            cooled = (time.time() - float(st.get("last_train_ts", 0))) >= MIN_INTERVAL_S
            if new >= NEW_SAMPLES_TO_TRAIN and cooled and _maestro_ok():
                log.info("burst: %d new samples (total %d)", new, total)
                ok = _train_once(username, profiles_dir)
                if ok:
                    st["last_trained_samples"] = total
                    st["last_train_ts"] = time.time()
                    _save_state(profile, st)
                    log.info("burst done; adapter=%s ct2=%s",
                             profile.get_adapter_path() is not None,
                             profile.get_ct2_model_path() is not None)
                else:
                    log.warning("burst failed; will retry next cycle (see training.log)")
            else:
                log.info("idle (new=%d/%d, cooled=%s)", new, NEW_SAMPLES_TO_TRAIN, cooled)
        except Exception as e:  # noqa: BLE001
            log.exception("loop error: %s", e)
        time.sleep(POLL_S)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Always-on throttled voice-adaptation trainer")
    ap.add_argument("--user", default=os.getenv("USERNAME") or "iddo1")
    ap.add_argument("--profiles-dir", default=None)
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    run(a.user, a.profiles_dir)
