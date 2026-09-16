#!/usr/bin/env bash
# Mibox Armbian build — gh auth refresh helper
# Adds the 'workflow' scope so the staged YAML can be pushed to the iddo111/build fork.
# Run from this PC (Iddo). Requires interactive browser or device-code paste.
#
# Updated 2026-04-30 — verified gh auth status currently shows scopes:
#   'gist', 'read:org', 'repo'      ← missing 'workflow'

set -euo pipefail

echo "Current gh auth status:"
gh auth status || true
echo
echo "Refreshing token to add 'workflow' scope..."
echo "(A browser tab will open. Approve the requested scopes.)"
echo

# Primary path — opens browser
gh auth refresh -h github.com -s repo,workflow

# Browserless fallback (uncomment if no browser available; will print a device code)
# gh auth refresh -s repo,workflow --hostname github.com

echo
echo "Verifying refreshed scopes:"
gh auth status

echo
echo "Expected: Token scopes line includes 'workflow'."
echo "If yes — Mibox Armbian Iteration 2 can now push the YAML and trigger the build."
echo "Resume from: D:\\CLAUDE\\mibox-armbian-mission\\STATUS.md"
