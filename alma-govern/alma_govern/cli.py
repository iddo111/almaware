"""ALMA-Govern fleet-health CLI.

Runs the detectors on THIS node and ALERTS (logs + threshold exit code).
The optional "protect" action is OFF by default and, even when enabled, only
PRINTS the recommended advisory command -- it never executes anything.

Usage:
    python -m alma_govern.cli check                 # live check on this node
    python -m alma_govern.cli check --json          # machine-readable
    python -m alma_govern.cli check --from snap.json # offline, from a snapshot file
    python -m alma_govern.cli check --protect        # also print advisory actions
    python -m alma_govern.cli watch --interval 10    # loop, alert on change

Exit code == worst severity (0 OK, 1 INFO, 2 WARN, 3 CRITICAL) so it plugs
straight into monitoring/systemd.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from typing import Any, Dict

from .fleet_health import Severity, Thresholds, assess_node, NodeAssessment

log = logging.getLogger("alma_govern")


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s alma-govern %(levelname)s %(message)s",
    )


def _load_snapshot(path: str) -> Dict[str, Any]:
    with open(path) as fh:
        return json.load(fh)


def _live_snapshot(net_interval: float) -> Dict[str, Any]:
    # imported lazily so `check --from` works even where psutil/os bits differ
    from .collectors import collect_snapshot
    return collect_snapshot(net_interval=net_interval)


def _emit(assessment: NodeAssessment, as_json: bool, show_protect: bool) -> None:
    if as_json:
        print(json.dumps(assessment.to_dict(), indent=2))
        return
    lvl = assessment.severity
    print(f"== ALMA-Govern fleet-health :: {assessment.node} :: "
          f"{lvl.label()} ==")
    for f in assessment.findings:
        logfn = {
            Severity.OK: log.info,
            Severity.INFO: log.info,
            Severity.WARN: log.warning,
            Severity.CRITICAL: log.error,
        }[f.severity]
        logfn(str(f) if not f.recommended_action else
              f"[{f.severity.label()}] {f.detector}: {f.summary}")
        if show_protect and f.recommended_action:
            # ADVISORY ONLY -- printed, never executed.
            print(f"    ADVISORY (not executed): {f.recommended_action}")


def cmd_check(args: argparse.Namespace) -> int:
    if args.from_file:
        snap = _load_snapshot(args.from_file)
        node = snap.get("node", "offline-snapshot")
    else:
        snap = _live_snapshot(args.net_interval)
        node = snap.get("node", "local")

    th = Thresholds()
    assessment = assess_node(node, snap, th)
    _emit(assessment, args.json, args.protect)
    return int(assessment.severity)


def cmd_watch(args: argparse.Namespace) -> int:
    last = None
    try:
        while True:
            snap = _live_snapshot(args.net_interval)
            node = snap.get("node", "local")
            assessment = assess_node(node, snap, Thresholds())
            sev = assessment.severity
            if sev != last or sev >= Severity.WARN:
                _emit(assessment, args.json, args.protect)
                last = sev
            time.sleep(max(1.0, args.interval))
    except KeyboardInterrupt:
        return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="alma-govern",
        description="ALMA-Govern fleet-health guard (detect network storm / "
                    "OOM / GPU faults). Protect actions are advisory only.",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="one-shot health check on this node")
    c.add_argument("--json", action="store_true", help="machine-readable output")
    c.add_argument("--from", dest="from_file", metavar="FILE",
                   help="read a JSON snapshot instead of live metrics (offline)")
    c.add_argument("--protect", action="store_true",
                   help="also print advisory protect actions (never executed)")
    c.add_argument("--net-interval", type=float, default=0.5)
    c.set_defaults(func=cmd_check)

    w = sub.add_parser("watch", help="loop and alert on change / on WARN+")
    w.add_argument("--interval", type=float, default=10.0)
    w.add_argument("--json", action="store_true")
    w.add_argument("--protect", action="store_true")
    w.add_argument("--net-interval", type=float, default=0.5)
    w.set_defaults(func=cmd_watch)
    return p


def main(argv=None) -> int:
    p = build_parser()
    args = p.parse_args(argv)
    _setup_logging(args.verbose)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
