#!/bin/bash
# Resolve workspace directory: derives clone path from REPO_URL,
# detects devcontainer mode, and skips clone when repo already exists.
#
# Exports: WORKSPACE_DIR
# Expects: REPO_URL, REPO_BRANCH (optional), WORKSPACE_DIR (optional override)
# Detects: DEVCONTAINER, REMOTE_CONTAINERS env vars

# If WORKSPACE_DIR is already set (explicit override), use it
if [ -z "${WORKSPACE_DIR:-}" ]; then
    if [ -n "${REPO_URL:-}" ]; then
        # Derive repo name from URL (handles both .git and non-.git URLs)
        REPO_NAME=$(basename "${REPO_URL%.git}")
        WORKSPACE_DIR="/workspaces/${REPO_NAME}"
    else
        WORKSPACE_DIR="/workspaces/project"
    fi
fi

export WORKSPACE_DIR

# Detect devcontainer mode
if [ -n "${DEVCONTAINER:-}" ] || [ -n "${REMOTE_CONTAINERS:-}" ]; then
    # In devcontainer mode, VS Code has already cloned the repo
    if [ -d "${WORKSPACE_DIR}/.git" ]; then
        log "Devcontainer mode: using existing repo at ${WORKSPACE_DIR}"
        return 0 2>/dev/null || exit 0
    fi
    # If the derived path doesn't exist, check for any repo in /workspaces
    if [ -n "${REPO_URL:-}" ]; then
        REPO_NAME=$(basename "${REPO_URL%.git}")
        EXISTING_REPO=$(find /workspaces -maxdepth 2 -name ".git" -type d 2>/dev/null | while read gitdir; do
            dir=$(dirname "$gitdir")
            if [ "$(basename "$dir")" = "$REPO_NAME" ]; then
                echo "$dir"
                break
            fi
        done)
        if [ -n "$EXISTING_REPO" ]; then
            WORKSPACE_DIR="$EXISTING_REPO"
            export WORKSPACE_DIR
            log "Devcontainer mode: found existing repo at ${WORKSPACE_DIR}"
            return 0 2>/dev/null || exit 0
        fi
    fi
fi

# Standalone mode: clone or pull
if [ -n "${REPO_URL:-}" ] && [ ! -d "${WORKSPACE_DIR}/.git" ]; then
    log "Cloning project repo: ${REPO_URL} (branch: ${REPO_BRANCH:-main})"
    git clone --branch "${REPO_BRANCH:-main}" "${REPO_URL}" "${WORKSPACE_DIR}"
elif [ -d "${WORKSPACE_DIR}/.git" ]; then
    log "Project repo already cloned, pulling latest..."
    cd "${WORKSPACE_DIR}"
    git fetch origin
    git pull --ff-only origin "${REPO_BRANCH:-main}" 2>/dev/null || true
fi
