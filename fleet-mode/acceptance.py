#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Live acceptance for FLEET MODE. Re-runnable, and it touches NOTHING real.

It creates its own throwaway user unit (fleetmode-selftest.service = sleep infinity)
on eran3 and eran4, drives a real mode switch and a real PAUSE/RESUME round trip
against those, verifies every step by re-probing systemctl --user, and then removes
the units again. No production service is ever started or stopped to "test" this.

    python acceptance.py            # full run, creates + removes the selftest units
    python acceptance.py --keep     # leave the units in place for a second run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fleet_mode as fm  # noqa: E402

SELFTEST_MODES = Path(__file__).resolve().parent / "state" / "modes.selftest.json"
HOSTS = ["eran3", "eran4"]
UNIT_BODY = """[Unit]
Description=FLEET MODE selftest placeholder - safe to delete
[Service]
Type=simple
ExecStart=/bin/sleep infinity
Restart=no
"""


def install_units() -> None:
    for h in HOSTS:
        fm._ssh(h, ["mkdir", "-p", ".config/systemd/user"], timeout=30)
        # A FIXED script, hard-coded in this file. Nothing in it is user-supplied and
        # nothing reaches it from the web page - server.py never runs shell strings at
        # all. This is test scaffolding, deliberately outside the control path.
        script = (
            "cat > $HOME/.config/systemd/user/fleetmode-selftest.service <<'EOF'\n"
            + UNIT_BODY + "EOF\nsystemctl --user daemon-reload"
        )
        rc, _, err = fm._ssh(h, ["sh", "-c", script], timeout=60)
        print(f"  install {h}: rc={rc} {err.strip()[:120]}")


def remove_units() -> None:
    for h in HOSTS:
        rc, _, err = fm._ssh(h, [
            "sh", "-c",
            "systemctl --user stop fleetmode-selftest.service 2>/dev/null; "
            "rm -f $HOME/.config/systemd/user/fleetmode-selftest.service; "
            "systemctl --user daemon-reload"], timeout=60)
        print(f"  remove {h}: rc={rc} {err.strip()[:120]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    failures = []

    print("\n### 0. THE REFUSAL - a mode naming ERAN must not even load ###")
    import json
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "evil.json"
        p.write_text(json.dumps({"modes": {"maintenance": {"units": [
            {"host": "eran1", "unit": "eranb-life.service", "want": "stop"}]}}}),
            encoding="utf-8")
        try:
            fm.load_modes(p)
            failures.append("REFUSAL: a mode naming eranb-life.service LOADED")
            print("  FAIL - it loaded. The gate is broken. Do not run this program.")
        except fm.ProtectedUnitError as exc:
            print("  PASS - refused:", str(exc).splitlines()[0])
            print("        ", str(exc).splitlines()[-1])

    print("\n### 1. install the throwaway selftest units ###")
    install_units()

    modes = fm.load_modes(SELFTEST_MODES)
    mu = fm.managed_units(modes)
    hosts = sorted({h for h, _ in mu})

    def snap(tag):
        pr = fm.probe_fleet(hosts, of_interest=mu)
        st = {f"{h}/{u.replace('.service','')}": fm.unit_state(pr, h, u) for h, u in mu}
        print(f"  {tag:<22} {st}")
        return pr

    print("\n### 2. MODE SWITCH, verified by re-probing systemctl --user ###")
    pr = snap("BEFORE")
    plan = fm.plan_mode(modes["selftest_on"], pr)
    print(f"  plan: {[(p['want'], p['host'], p['unit']) for p in plan]}")
    out = fm.execute_plan(plan, actor="acceptance", reason="mode:selftest_on")
    print(f"  {out['result']}  ok={out['verified_ok']} fail={out['verified_fail']} {out['elapsed_s']}s")
    if out["result"] != "OK" or out["verified_ok"] != 2:
        failures.append("MODE SWITCH did not verify")
    pr = snap("AFTER SWITCH")

    print("\n### 3. PAUSE -> RESUME exact round trip ###")
    before = sorted(f"{h}/{u}" for h, u in mu if fm.unit_state(pr, h, u) == "active")
    print(f"  running before pause: {before}")
    out = fm.do_pause(modes, actor="acceptance")
    print(f"  PAUSE  {out['result']} ok={out['verified_ok']} fail={out['verified_fail']}")
    pr = snap("AFTER PAUSE")
    out = fm.do_resume(actor="acceptance")
    print(f"  RESUME {out['result']} ok={out['verified_ok']} fail={out['verified_fail']}")
    pr = snap("AFTER RESUME")
    after = sorted(f"{h}/{u}" for h, u in mu if fm.unit_state(pr, h, u) == "active")
    print(f"  running after resume: {after}")
    if before != after or not before:
        failures.append(f"ROUND TRIP: before={before} after={after}")
        print("  FAIL - the round trip did not restore the exact set")
    else:
        print("  PASS - exact round trip")

    print("\n### 4. the log can say FAIL ###")
    out = fm.execute_plan(
        [{"host": "eran4", "unit": "there-is-no-such-unit.service",
          "want": "start", "from_state": "inactive"}],
        actor="acceptance", reason="prove the log can say FAIL")
    if out["result"] == "FAIL":
        print(f"  PASS - recorded FAIL (rc={out['actions'][0]['rc']}, "
              f"after_state={out['actions'][0]['after_state']})")
    else:
        failures.append("a nonexistent unit did not produce FAIL")
        print("  FAIL - a missing unit was reported OK")

    print("\n### 5. cleanup ###")
    pr = fm.probe_fleet(hosts, of_interest=mu)
    fm.execute_plan(fm.plan_mode(modes["selftest_off"], pr),
                    actor="acceptance", reason="cleanup")
    if not args.keep:
        remove_units()
    snap("FINAL")

    print(f"\n=== acceptance: {'PASS' if not failures else 'FAIL'} ===")
    for f in failures:
        print("  ", f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
