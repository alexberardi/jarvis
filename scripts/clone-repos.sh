#!/bin/bash
# Clone all jarvis repositories
# Run from ~/jarvis or specify JARVIS_ROOT

set -e

JARVIS_ROOT="${JARVIS_ROOT:-$HOME/jarvis}"
cd "$JARVIS_ROOT"

echo "Cloning jarvis repositories into $JARVIS_ROOT..."

# All repos with their GitHub URLs
declare -A REPOS=(
    ["jarvis-admin"]="git@github.com:alexberardi/jarvis-admin.git"
    ["jarvis-auth"]="git@github.com:alexberardi/jarvis-auth.git"
    ["jarvis-auth-client"]="git@github.com:alexberardi/jarvis-auth-client.git"
    ["jarvis-command-center"]="git@github.com:alexberardi/jarvis-command-center.git"
    ["jarvis-config-client"]="git@github.com:alexberardi/jarvis-config-client.git"
    ["jarvis-config-service"]="git@github.com:alexberardi/jarvis-config-service.git"
    ["jarvis-installer"]="git@github.com:alexberardi/jarvis-installer.git"
    ["jarvis-llm-proxy-api"]="git@github.com:alexberardi/jarvis-llm-proxy-api.git"
    ["jarvis-log-client"]="git@github.com:alexberardi/jarvis-log-client.git"
    ["jarvis-logs"]="git@github.com:alexberardi/jarvis-logs.git"
    ["jarvis-mcp"]="git@github.com:alexberardi/jarvis-mcp.git"
    ["jarvis-node-mobile"]="git@github.com:alexberardi/jarvis-node-mobile.git"
    ["jarvis-node-setup"]="git@github.com:alexberardi/jarvis-node-setup.git"
    ["jarvis-ocr-service"]="git@github.com:alexberardi/jarvis-ocr-service.git"
    ["jarvis-recipes-mobile"]="git@github.com:alexberardi/jarvis-recipes-mobile.git"
    ["jarvis-recipes-server"]="git@github.com:alexberardi/jarvis-recipes-server.git"
    ["jarvis-settings-client"]="git@github.com:alexberardi/jarvis-settings-client.git"
    ["jarvis-tts"]="git@github.com:alexberardi/jarvis-tts.git"
    ["jarvis-whisper-api"]="git@github.com:alexberardi/jarvis-whisper-api.git"
)

for repo in "${!REPOS[@]}"; do
    if [ -d "$repo" ]; then
        echo "✓ $repo already exists, skipping"
    else
        echo "→ Cloning $repo..."
        git clone "${REPOS[$repo]}" "$repo"
    fi
done

echo ""
echo "Done! Cloned ${#REPOS[@]} repositories."
