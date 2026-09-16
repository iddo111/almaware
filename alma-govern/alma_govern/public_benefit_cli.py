"""Command-line interface for the pure public-benefit proposal gate."""

import argparse
import json
from pathlib import Path

from .public_benefit import (
    Decision,
    InitiativeProposal,
    assess_public_benefit,
)


def load_proposal(path: str) -> InitiativeProposal:
    """Load a strict JSON proposal; missing or unknown fields are invalid."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("proposal must be a JSON object")
    return InitiativeProposal(**payload)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="alma-public-benefit",
        description="Fail-closed public-benefit gate for an initiative JSON file.",
    )
    parser.add_argument("proposal", help="path to a proposal JSON file")
    args = parser.parse_args(argv)

    try:
        proposal = load_proposal(args.proposal)
        result = assess_public_benefit(proposal)
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"decision": "INVALID", "error": str(exc)},
                         ensure_ascii=False, sort_keys=True))
        return 4

    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    return {
        Decision.APPROVE: 0,
        Decision.PAUSE: 2,
        Decision.REJECT: 3,
    }[result.decision]


if __name__ == "__main__":
    raise SystemExit(main())
