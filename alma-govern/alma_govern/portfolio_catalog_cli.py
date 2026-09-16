"""CLI for validating the curated ALMA portfolio catalog."""

import argparse
import json
from pathlib import Path

from .portfolio_catalog import load_and_validate


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="alma-portfolio-catalog")
    parser.add_argument("catalog")
    parser.add_argument("--workspace-root")
    args = parser.parse_args(argv)
    try:
        issues = load_and_validate(
            Path(args.catalog),
            Path(args.workspace_root) if args.workspace_root else None,
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, sort_keys=True))
        return 4
    result = {
        "valid": not issues,
        "issue_count": len(issues),
        "issues": [issue.to_dict() for issue in issues],
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not issues else 2


if __name__ == "__main__":
    raise SystemExit(main())

