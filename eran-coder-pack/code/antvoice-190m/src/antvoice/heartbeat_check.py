"""Standalone heartbeat watchdog command; no neural runtime import."""

from __future__ import annotations

import argparse
import json

from .safety import assert_fresh_heartbeat


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--heartbeat", required=True)
    parser.add_argument("--max-age-seconds", type=float, default=180.0)
    parser.add_argument("--skip-pid-check", action="store_true")
    args = parser.parse_args()
    payload = assert_fresh_heartbeat(
        args.heartbeat,
        max_age_seconds=args.max_age_seconds,
        require_live_pid=not args.skip_pid_check,
    )
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
