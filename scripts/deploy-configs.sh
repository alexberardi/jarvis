#!/bin/bash
# Deploy configs: Copy from this repo TO system locations
# Use this on a new machine after cloning

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JARVIS_ROOT="$(dirname "$SCRIPT_DIR")"
CONFIGS_DIR="$JARVIS_ROOT/configs"

echo "Deploying configs from $CONFIGS_DIR to system..."

# Tmuxinator config
if [ -f "$CONFIGS_DIR/tmuxinator-jarvis.yml" ]; then
    mkdir -p "$HOME/.config/tmuxinator"
    cp "$CONFIGS_DIR/tmuxinator-jarvis.yml" "$HOME/.config/tmuxinator/jarvis.yml"
    echo "✓ tmuxinator/jarvis.yml"
else
    echo "✗ tmuxinator-jarvis.yml not in repo"
fi

# Neovim config
if [ -d "$CONFIGS_DIR/nvim" ]; then
    if [ -d "$HOME/.config/nvim" ]; then
        echo "⚠ nvim config already exists at ~/.config/nvim"
        read -p "  Overwrite? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "  Skipping nvim"
        else
            rm -rf "$HOME/.config/nvim"
            cp -r "$CONFIGS_DIR/nvim" "$HOME/.config/nvim"
            echo "✓ nvim/"
        fi
    else
        mkdir -p "$HOME/.config"
        cp -r "$CONFIGS_DIR/nvim" "$HOME/.config/nvim"
        echo "✓ nvim/"
    fi
else
    echo "✗ nvim config not in repo"
fi

echo ""
echo "Done! You may need to:"
echo "  - Run 'nvim' to install plugins (Lazy.nvim will auto-install)"
echo "  - Install tmuxinator: 'gem install tmuxinator'"
echo "  - Start jarvis session: 'tmuxinator start jarvis'"
