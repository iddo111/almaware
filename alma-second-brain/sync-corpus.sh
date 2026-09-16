#!/bin/bash
# Push the corpus from Windows to a DGX box, and pull back anything the brain captured
# while it was running there. Run from Git Bash:  ./sync-corpus.sh [eran4]
#
# The corpus is ~600 KB of markdown. This is deliberately a dumb file copy and not a
# database: the originals stay authoritative on Windows, the fleet gets a read-only
# mirror, and the only thing that ever travels back is captured/.
set -e
BOX="${1:-eran4}"
REMOTE="/home/${BOX}/brain-corpus"
STAGE="/tmp/brain-corpus-stage"

echo "staging…"
rm -rf "$STAGE"
mkdir -p "$STAGE"/{claude-memory,git-brain,keshev-b,ramchat,keshev,captured}

# markdown only, no snapshots (point-in-time dupes), no .git
cd "$HOME/.claude/projects" && find . -name '*.md' -not -path '*/.git/*' \
  -exec cp --parents {} "$STAGE/claude-memory/" \; 2>/dev/null || true
cd "$HOME/Claude-Memory-" && find . -name '*.md' -not -path './snapshots/*' -not -path '*/.git/*' \
  -exec cp --parents {} "$STAGE/git-brain/" \; 2>/dev/null || true
cp /d/CLAUDE/keshev-b/*.md "$STAGE/keshev-b/" 2>/dev/null || true

cp /d/CLAUDE/RAMCHAT/ramchat_session.json "$STAGE/ramchat/" 2>/dev/null || true
cp /d/CLAUDE/RAMCHAT/current_council.json "$STAGE/ramchat/" 2>/dev/null || true
cp /d/CLAUDE/mic-rebuild/state/corpus/manifest.jsonl "$STAGE/keshev/" 2>/dev/null || true

echo "staged: $(find "$STAGE" -type f | wc -l) files, $(du -sh "$STAGE" | cut -f1)"

# pull back anything captured on the box BEFORE overwriting it
ssh "$BOX" "mkdir -p $REMOTE/captured" 2>/dev/null || true
scp -q -r "$BOX:$REMOTE/captured/." "$STAGE/captured/" 2>/dev/null || true
BACK=$(find "$STAGE/captured" -name '*.md' 2>/dev/null | wc -l)
if [ "$BACK" -gt 0 ]; then
  echo "pulling back $BACK captured note(s) to the live memory dir"
  cp -n "$STAGE"/captured/*.md "$HOME/.claude/projects/C--Users-iddo1--claude/memory/" 2>/dev/null || true
fi

echo "pushing to $BOX:$REMOTE …"
ssh "$BOX" "mkdir -p $REMOTE"
scp -q -r "$STAGE/." "$BOX:$REMOTE/"
ssh "$BOX" "find $REMOTE -type f | wc -l | xargs echo 'on box:' ; du -sh $REMOTE | cut -f1"
echo "done. reindex with:  curl -s -X POST http://<box>:8960/reindex"
