#!/bin/bash
# Pull latest changes for all jarvis repositories
# Run from ~/jarvis or specify JARVIS_ROOT

set -e

JARVIS_ROOT="${JARVIS_ROOT:-$HOME/jarvis}"
cd "$JARVIS_ROOT"

echo "Pulling latest for all jarvis repos in $JARVIS_ROOT..."
echo ""

SUCCEEDED=0
FAILED=0
SKIPPED=0

for dir in jarvis-*/; do
    repo=$(basename "$dir")

    # Skip if not a git repo
    if [ ! -d "$dir/.git" ]; then
        echo "⊘ $repo — not a git repo, skipping"
        ((SKIPPED++))
        continue
    fi

    # Check for uncommitted changes
    if ! git -C "$dir" diff --quiet 2>/dev/null || ! git -C "$dir" diff --cached --quiet 2>/dev/null; then
        echo "⚠ $repo — has uncommitted changes, skipping"
        ((SKIPPED++))
        continue
    fi

    # Pull
    if git -C "$dir" pull --ff-only 2>/dev/null; then
        echo "✓ $repo"
        ((SUCCEEDED++))
    else
        echo "✗ $repo — pull failed (diverged branch?)"
        ((FAILED++))
    fi
done

echo ""
echo "Done! Pulled: $SUCCEEDED, Skipped: $SKIPPED, Failed: $FAILED"
