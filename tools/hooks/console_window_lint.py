"""PostToolUse(Write|Edit) hook, log-only. Warns when a .py file spawns a
console exe (ssh/wsl/git/cmd/powershell) via subprocess without
CREATE_NO_WINDOW -- the exact cause of the 2026-09-15 popup-storm
(Windows Terminal stealing focus repeatedly; see project_handoff_20260915_night
memory). Never blocks: always exits 0.
"""
import json
import os
import re
import sys

RISKY = re.compile(
    r"subprocess\.(Popen|run|call|check_call|check_output)\([^)]*\b"
    r"(ssh|wsl|git|cmd|powershell)\b",
    re.IGNORECASE,
)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    ti = data.get("tool_input", {}) or {}
    f = ti.get("file_path") or ti.get("filePath") or ""
    if not f.endswith(".py") or not os.path.isfile(f):
        return
    try:
        src = open(f, encoding="utf-8", errors="ignore").read()
    except Exception:
        return
    if RISKY.search(src) and "CREATE_NO_WINDOW" not in src:
        print(
            f"[console-window-lint] {f} spawns a console exe (ssh/wsl/git/cmd/"
            f"powershell) via subprocess without CREATE_NO_WINDOW -- likely to "
            f"pop a Windows Terminal window (2026-09-15 popup-storm bug)."
        )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
