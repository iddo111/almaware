"""VAF-10 proof: the cycle's exit code is data, and one cycle at a time.

`rc=$?` was captured and only echoed. A cycle that failed every time for a week
produced an identical-looking journal (cycle start / cycle done rc=1 / sleeping
900s), a cycles.jsonl that quietly stopped growing, and no alarm anywhere. And
there was no lock: train_loop.sh would race run_loop.sh on state/round.json and
current.json with no compare-and-swap, so one of two concurrent promotions
would silently lose.

The alarm threshold is DERIVED from the loop's own sleep - one hour of
consecutive failures - and the loop keeps sleeping and retrying. It must never
restart or kill anything.

FAILS on the pre-revision code, PASSES on the fixed code. Needs bash, flock
and timeout (i.e. run it on the box, not on Windows).
"""
import json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import proof_common

code = proof_common.use_code(sys.argv)
loop = code / "run_loop.sh"


def sandbox(rc: str) -> Path:
    home = Path(tempfile.mkdtemp(prefix="vaf-proof-10-"))
    project = home / "voice-ant-farm"
    (project / "state").mkdir(parents=True)
    (project / "logs").mkdir()
    (project / "recordings").mkdir()
    shutil.copyfile(loop, project / "run_loop.sh")
    binary = home / "bin"
    binary.mkdir()
    stub = binary / "python3"
    stub.write_text(
        "#!/bin/sh\n"
        f'echo RAN >> "{home}/ran.log"\n'
        f'exit "$(cat "{home}/rc")"\n',
        encoding="utf-8",
    )
    stub.chmod(0o755)
    (home / "rc").write_text(rc, encoding="utf-8")
    return home


def run(home: Path, seconds: int, **env) -> subprocess.CompletedProcess:
    environment = dict(os.environ)
    environment.update({
        "HOME": str(home), "PATH": f"{home / 'bin'}{os.pathsep}{os.environ['PATH']}",
    })
    environment.update(env)
    return subprocess.run(
        ["timeout", str(seconds), "bash", str(home / "voice-ant-farm" / "run_loop.sh")],
        capture_output=True, text=True, env=environment,
    )


def events(home: Path) -> list[dict]:
    path = home / "voice-ant-farm" / "logs" / "cycles.jsonl"
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            out.append({"event": "UNPARSEABLE", "raw": line[:80]})
    return out


checks = []

# --- failing cycles must raise an alarm, and recovery must clear it ----------
home = sandbox("1")
proc = subprocess.Popen(
    ["timeout", "14", "bash", str(home / "voice-ant-farm" / "run_loop.sh")],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    env={**os.environ, "HOME": str(home),
         "PATH": f"{home / 'bin'}{os.pathsep}{os.environ['PATH']}",
         "VAF_SLEEP_SECONDS": "1", "VAF_FAIL_ALARM_AFTER": "3"},
)
time.sleep(7)
alarmed = events(home)
unhealthy_during = (home / "voice-ant-farm" / "state" / "UNHEALTHY").exists()
(home / "rc").write_text("0", encoding="utf-8")
time.sleep(5)
recovered = events(home)
unhealthy_after = (home / "voice-ant-farm" / "state" / "UNHEALTHY").exists()
proc.wait(timeout=20)
alive = proc.stdout.read()

failed = [e for e in alarmed if e.get("event") == "cycle_failed"]
checks.append((
    "a run of failing cycles writes a loud line into cycles.jsonl",
    bool(failed) and failed[0]["rc"] == 1,
    f"{len(failed)} cycle_failed events, first = "
    f"rc={failed[0]['rc'] if failed else '-'} "
    f"consecutive={failed[0]['consecutive_failures'] if failed else '-'}",
))
checks.append((
    "the failure raises a marker a reader (status.sh) can see",
    unhealthy_during, f"state/UNHEALTHY present during the outage: {unhealthy_during}",
))
checks.append((
    "recovery is recorded and the marker is cleared",
    any(e.get("event") == "cycle_recovered" for e in recovered) and not unhealthy_after,
    f"cycle_recovered logged={any(e.get('event') == 'cycle_recovered' for e in recovered)}, "
    f"UNHEALTHY still present={unhealthy_after}",
))
checks.append((
    "the loop keeps sleeping and retrying instead of stopping anything",
    alive.count("cycle start") >= 3 and "kill" not in alive and "restart" not in alive,
    f"{alive.count('cycle start')} cycles attempted across the outage",
))

# --- the derived threshold ---------------------------------------------------
derived = run(sandbox("0"), 2, VAF_SLEEP_SECONDS="900")
checks.append((
    "the alarm threshold is derived from the loop's own sleep, not hand-picked",
    "fail_alarm_after=4" in derived.stdout,
    f"at 900s sleep the loop announces: "
    f"{[l for l in derived.stdout.splitlines() if 'loop start' in l] or derived.stdout[:120]!r}",
))

# --- one cycle at a time -----------------------------------------------------
locked = sandbox("0")
lock = locked / "voice-ant-farm" / "state" / ".lock"
lock.touch()
holder = subprocess.Popen(["flock", "-x", str(lock), "sleep", "6"])
time.sleep(0.5)
run(locked, 4, VAF_SLEEP_SECONDS="1")
holder.wait(timeout=20)
skipped = [e for e in events(locked) if e.get("event") == "cycle_skipped"]
ran_log = locked / "ran.log"
checks.append((
    "a second loop cannot run a cycle while the first holds the lock",
    bool(skipped) and not ran_log.exists(),
    f"{len(skipped)} cycle_skipped events, python3 invoked "
    f"{len(ran_log.read_text().splitlines()) if ran_log.exists() else 0} times",
))

raise SystemExit(proof_common.report("VAF-10", checks))
