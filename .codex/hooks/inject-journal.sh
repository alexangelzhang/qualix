#!/bin/bash
# SessionStart hook: inject the most recent session journal into context
JOURNAL_DIR="$(dirname "$0")/../journals"

if [ ! -d "$JOURNAL_DIR" ]; then
  exit 0
fi

# Find the most recent journal file (sorted by filename, newest last)
LATEST=$(ls -1 "$JOURNAL_DIR"/journal-*.md 2>/dev/null | sort -V | tail -1)

if [ -z "$LATEST" ]; then
  exit 0
fi

# Check file age — skip if older than 7 days
if [ "$(uname)" = "Darwin" ]; then
  FILE_AGE=$(( $(date +%s) - $(stat -f %m "$LATEST") ))
else
  FILE_AGE=$(( $(date +%s) - $(stat -c %Y "$LATEST") ))
fi

if [ "$FILE_AGE" -gt 604800 ]; then
  exit 0
fi

echo "--- Session Journal (from $(basename "$LATEST")) ---"
cat "$LATEST"
echo "--- End Journal ---"
