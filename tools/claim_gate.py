#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
claim_gate.py - PreToolUse hook (Write|Edit). FIX 3 of the 2026-08-31 EMDR commission.

THE RULE IT ENFORCES: a NEW top-level directory under D:\CLAUDE whose name-stem
already appears in ARTIFACTS.tsv or MEMORY.md may not be created silently - the
hook refuses and prints what already exists. A RAMCHAT line mentioning the new
directory's name lifts the refusal (claim-before-build, finally mechanical:
the advisory rule was never once exercised in six months of EMDR rebuilds).

FAIL-OPEN BY DESIGN: any internal error, missing file, or unparseable input
exits 0 with no output. A broken gate must never brick the workspace.
"""
import io
import json
import os
import re
import sys

ROOT = r"D:\CLAUDE"
TSV = os.path.join(ROOT, "ARTIFACTS.tsv")
MEMORY = r"C:\Users\<user>\.claude\projects\D--CLAUDE\memory\MEMORY.md"
RAMCHAT = os.path.join(ROOT, "RAMCHAT", "ramchat_session.json")


def allow():
    sys.exit(0)


def deny(new_dir, matches):
    lines = "\n".join("  - " + m for m in matches[:7])
    msg = (
        "CLAIM GATE (EMDR-commission FIX 3): refusing to create new top-level dir "
        "'%s' - its name matches EXISTING work:\n%s\n"
        "REUSE the existing artifact, or claim first: cd D:\\CLAUDE\\RAMCHAT && "
        "python ramlink.py post <your-name> \"CLAIM: building %s because <why the "
        "existing ones don't serve>\" - then retry." % (new_dir, lines, new_dir)
    )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": msg,
        }
    }))
    sys.exit(0)


def main():
    data = json.load(sys.stdin)
    if data.get("tool_name") not in ("Write", "Edit"):
        allow()
    fp = (data.get("tool_input") or {}).get("file_path") or ""
    fp = os.path.normpath(fp)
    root = os.path.normpath(ROOT)
    if not fp.lower().startswith(root.lower() + os.sep):
        allow()
    rel = fp[len(root) + 1:]
    parts = rel.split(os.sep)
    if len(parts) < 2:
        allow()                                   # a file directly in the root
    top = parts[0]
    if os.path.isdir(os.path.join(root, top)):
        allow()                                   # dir already exists - not a NEW project
    # name-stem tokens: alphabetic runs >= 4 chars, lowercased ("emdr2" -> "emdr")
    tokens = [t for t in re.findall(r"[a-zA-Z\u0590-\u05ff]{4,}", top.lower())]
    if not tokens:
        allow()
    # a RAMCHAT claim naming the new dir lifts the gate
    try:
        with io.open(RAMCHAT, encoding="utf-8", errors="replace") as fh:
            if top.lower() in fh.read().lower():
                allow()
    except OSError:
        pass
    matches = []
    for src in (TSV, MEMORY):
        try:
            with io.open(src, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    low = line.lower()
                    if any(t in low for t in tokens):
                        matches.append(os.path.basename(src) + ": " + line.strip()[:160])
                        if len(matches) >= 12:
                            break
        except OSError:
            continue
    if matches:
        deny(top, matches)
    allow()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)                                # fail-open, always
