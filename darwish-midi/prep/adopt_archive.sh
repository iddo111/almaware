#!/bin/bash
# adopt_archive.sh — one-time READ-ONLY cp of the archived Darwish-MIDI corpus
# into Chai's own food/ tree. Run on eran4. Never writes into ~/darwish-ai;
# zero systemctl calls (the archive order is enforced here in code, not memory).
set -euo pipefail

ARCHIVE_ROOT="$HOME/darwish-ai"
ARCHIVE_TOKENS="$ARCHIVE_ROOT/tokens-midi"
ARCHIVE_SPLIT="$ARCHIVE_ROOT/code-midi/split.json"
DEST_ROOT="$HOME/darwish-midi"

# realpath of the archive root, even if it does not (yet) exist, so the guard
# below still works from string comparison alone.
ARCHIVE_REAL="$ARCHIVE_ROOT"
if [ -d "$ARCHIVE_ROOT" ]; then
    ARCHIVE_REAL="$(cd "$ARCHIVE_ROOT" && pwd)"
fi

guard_dest() {
    # Refuse if the destination path resolves inside the archive.
    local target="$1"
    local parent
    parent="$(dirname "$target")"
    mkdir -p "$parent" 2>/dev/null || true
    local resolved
    if [ -d "$parent" ]; then
        resolved="$(cd "$parent" && pwd)/$(basename "$target")"
    else
        resolved="$target"
    fi
    case "$resolved" in
        "$ARCHIVE_REAL"|"$ARCHIVE_REAL"/*)
            echo "REFUSING: '$target' resolves inside $ARCHIVE_REAL — the archive is read-only." >&2
            exit 1
            ;;
    esac
}

for d in "$DEST_ROOT" "$DEST_ROOT/food" "$DEST_ROOT/state" \
         "$DEST_ROOT/songs/outbox" "$DEST_ROOT/feedback/inbox" "$DEST_ROOT/results"; do
    guard_dest "$d"
done

if [ ! -d "$ARCHIVE_TOKENS" ]; then
    echo "ERROR: $ARCHIVE_TOKENS not found — is the archive still at ~/darwish-ai?" >&2
    exit 1
fi
if [ ! -f "$ARCHIVE_SPLIT" ]; then
    echo "ERROR: $ARCHIVE_SPLIT not found" >&2
    exit 1
fi

mkdir -p "$DEST_ROOT/food" "$DEST_ROOT/state" "$DEST_ROOT/songs/outbox" \
         "$DEST_ROOT/feedback/inbox" "$DEST_ROOT/results"

cp -n "$ARCHIVE_TOKENS"/*.json "$DEST_ROOT/food/"
cp "$ARCHIVE_SPLIT" "$DEST_ROOT/food/split.json"

n_json=$(find "$DEST_ROOT/food" -maxdepth 1 -name '*.json' ! -name 'split.json' | wc -l)
echo "adopted: $n_json token shard(s) -> $DEST_ROOT/food/"
if [ -f "$DEST_ROOT/food/split.json" ]; then
    echo "split.json: present -> $DEST_ROOT/food/split.json"
else
    echo "split.json: MISSING"
fi
echo "archive untouched: this script only reads from $ARCHIVE_REAL (plain cp, no writes there)"
echo "systemctl calls made by this script: 0"
