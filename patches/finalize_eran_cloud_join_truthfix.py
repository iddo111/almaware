"""Add graceful URL-policy handling to the staged Eran Cloud truth-fix."""

from pathlib import Path


SOURCE = Path(r"D:\CLAUDE\eran-cloud\join.py.truthfix")
TARGET = Path(r"D:\CLAUDE\eran-cloud\join.py.truthfix2")


def main() -> None:
    if TARGET.exists():
        raise RuntimeError(f"refusing to overwrite staged file: {TARGET}")
    text = SOURCE.read_text(encoding="utf-8")
    old = "    coord = CoordinatorClient(args.coordinator, dry_run=dry_run)\n"
    new = """    try:
        coord = CoordinatorClient(args.coordinator, dry_run=dry_run)
    except ValueError as exc:
        print(f"[error] coordinator refused: {exc}")
        return 2
"""
    if text.count(old) != 1:
        raise RuntimeError(f"expected one CoordinatorClient construction, found {text.count(old)}")
    TARGET.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
