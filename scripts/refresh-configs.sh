#!/bin/bash
# Refresh configs: Copy from system locations INTO this repo
# Use this to backup your current configs before committing

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JARVIS_ROOT="$(dirname "$SCRIPT_DIR")"
CONFIGS_DIR="$JARVIS_ROOT/configs"

echo "Refreshing configs from system into $CONFIGS_DIR..."

# Tmuxinator config
if [ -f "$HOME/.config/tmuxinator/jarvis.yml" ]; then
    cp "$HOME/.config/tmuxinator/jarvis.yml" "$CONFIGS_DIR/tmuxinator-jarvis.yml"
    echo "✓ tmuxinator/jarvis.yml"
else
    echo "✗ tmuxinator/jarvis.yml not found"
fi

# Neovim config (entire directory)
if [ -d "$HOME/.config/nvim" ]; then
    rm -rf "$CONFIGS_DIR/nvim"
    cp -r "$HOME/.config/nvim" "$CONFIGS_DIR/nvim"
    # Remove lazy-lock.json (machine-specific plugin versions)
    rm -f "$CONFIGS_DIR/nvim/lazy-lock.json"
    echo "✓ nvim/ (excluding lazy-lock.json)"
else
    echo "✗ nvim config not found"
fi

echo ""
echo "Done! Configs refreshed. Review changes with 'git diff' then commit."
