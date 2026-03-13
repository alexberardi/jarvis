#!/bin/bash
# Configure git credentials from environment variables
# Called by entrypoint scripts before any git operations

set -e

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [setup-credentials] $*"
}

if [ -z "${GH_TOKEN:-}" ]; then
    log "WARNING: GH_TOKEN not set — git operations requiring auth will fail"
    return 0 2>/dev/null || exit 0
fi

# Configure git credential store with scoped token
git config --global credential.helper store
echo "https://${GH_USERNAME:-git}:${GH_TOKEN}@github.com" > ~/.git-credentials

# Configure git identity if provided
if [ -n "${GH_EMAIL:-}" ]; then
    git config --global user.email "${GH_EMAIL}"
fi
if [ -n "${GH_USERNAME:-}" ]; then
    git config --global user.name "${GH_USERNAME}"
fi

# Authenticate GitHub CLI
echo "${GH_TOKEN}" | gh auth login --with-token 2>/dev/null || true

log "Git credentials configured"
