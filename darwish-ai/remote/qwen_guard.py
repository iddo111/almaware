# qwen_guard.py — every 15 min: if Qwen (eran1 head, via Tailscale) is unhealthy
# or slower than 90% of baseline, STOP darwish-brain. Right-of-way enforcement.
import json
import subprocess
import urllib.request

HEAD = "http://<tailnet-ip>:8080"
BASELINE_TPS = 6.5      # measured 2026-08-08 (median of 3, tokenizer already running)
FLOOR = BASELINE_TPS * 0.90

def stop(reason: str):
    subprocess.run(["systemctl", "--user", "stop", "darwish-brain"], check=False)
    print(f"GUARD-STOP: {reason}", flush=True)

try:
    with urllib.request.urlopen(HEAD + "/health", timeout=10) as r:
        if json.load(r).get("status") != "ok":
            raise RuntimeError("health not ok")
except Exception as exc:
    # Qwen down/reloading is NOT darwish-brain's fault; don't stop for that.
    print(f"guard: qwen health unreachable ({exc}) - no action", flush=True)
    raise SystemExit(0)

req = urllib.request.Request(
    HEAD + "/v1/chat/completions",
    data=json.dumps({
        "model": "qwen3-coder-480b",
        "messages": [{"role": "user", "content": "Say the numbers 1 to 10."}],
        "max_tokens": 16,
    }).encode(),
    headers={"Content-Type": "application/json"},
)
try:
    with urllib.request.urlopen(req, timeout=120) as r:
        tps = json.load(r)["timings"]["predicted_per_second"]
except Exception as exc:
    print(f"guard: timed gen failed ({exc}) - no action", flush=True)
    raise SystemExit(0)

if tps < FLOOR:
    stop(f"qwen {tps:.2f} tok/s < floor {FLOOR:.2f}")
else:
    # Self-regulating: Qwen is healthy, so the brain may run. `start` is
    # idempotent - if it's already running this is a no-op. This is what lets
    # the brain wait out one-off GPU storms (e.g. corpus tokenization) and
    # resume by itself. 24/7 with right-of-way, no human in the loop.
    subprocess.run(["systemctl", "--user", "start", "darwish-brain"], check=False)
    print(f"guard: qwen {tps:.2f} tok/s ok (floor {FLOOR:.2f}) - brain allowed", flush=True)
