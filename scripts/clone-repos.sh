#!/bin/bash
# Clone all jarvis repositories
# Run from ~/jarvis or specify JARVIS_ROOT

set -e

JARVIS_ROOT="${JARVIS_ROOT:-$HOME/jarvis}"
cd "$JARVIS_ROOT"

echo "Cloning jarvis repositories into $JARVIS_ROOT..."

# All repos — "name|url" format (bash 3.2 compatible, no associative arrays)
REPOS=(
    "jarvis-admin|git@github.com:alexberardi/jarvis-admin.git"
    "jarvis-auth|git@github.com:alexberardi/jarvis-auth.git"
    "jarvis-auth-client|git@github.com:alexberardi/jarvis-auth-client.git"
    "jarvis-command-center|git@github.com:alexberardi/jarvis-command-center.git"
    "jarvis-config-client|git@github.com:alexberardi/jarvis-config-client.git"
    "jarvis-config-service|git@github.com:alexberardi/jarvis-config-service.git"
    "jarvis-data-services|git@github.com:alexberardi/jarvis-data-services.git"
    "jarvis-installer|git@github.com:alexberardi/jarvis-installer.git"
    "jarvis-llm-proxy-api|git@github.com:alexberardi/jarvis-llm-proxy-api.git"
    "jarvis-log-client|git@github.com:alexberardi/jarvis-log-client.git"
    "jarvis-logs|git@github.com:alexberardi/jarvis-logs.git"
    "jarvis-mcp|git@github.com:alexberardi/jarvis-mcp.git"
    "jarvis-node-mobile|git@github.com:alexberardi/jarvis-node-mobile.git"
    "jarvis-notifications|git@github.com:alexberardi/jarvis-notifications.git"
    "jarvis-node-setup|git@github.com:alexberardi/jarvis-node-setup.git"
    "jarvis-ocr-service|git@github.com:alexberardi/jarvis-ocr-service.git"
    "jarvis-recipes-mobile|git@github.com:alexberardi/jarvis-recipes-mobile.git"
    "jarvis-recipes-server|git@github.com:alexberardi/jarvis-recipes-server.git"
    "jarvis-settings-client|git@github.com:alexberardi/jarvis-settings-client.git"
    "jarvis-settings-server|git@github.com:alexberardi/jarvis-settings-server.git"
    "jarvis-tts|git@github.com:alexberardi/jarvis-tts.git"
    "jarvis-web|git@github.com:alexberardi/jarvis-web.git"
    "jarvis-whisper-api|git@github.com:alexberardi/jarvis-whisper-api.git"
)

cloned=0
failed=()
for entry in "${REPOS[@]}"; do
    repo="${entry%%|*}"
    url="${entry#*|}"
    if [ -d "$repo" ]; then
        echo "✓ $repo already exists, skipping"
    else
        echo "→ Cloning $repo..."
        if git clone "$url" "$repo"; then
            cloned=$((cloned + 1))
        else
            echo "✗ $repo FAILED to clone"
            failed+=("$repo")
        fi
    fi
done

echo ""
if [ ${#failed[@]} -gt 0 ]; then
    echo "Done with ERRORS: ${#REPOS[@]} listed, ${cloned} newly cloned, ${#failed[@]} FAILED:"
    printf '  ✗ %s\n' "${failed[@]}"
    echo ""
    echo "A missing repo no longer aborts the run — but the stack is incomplete"
    echo "until these resolve (./jarvis start --all silently skips absent dirs)."
    exit 1
fi
echo "Done! ${#REPOS[@]} repositories (${cloned} newly cloned)."
