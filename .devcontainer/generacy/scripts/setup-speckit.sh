#!/bin/bash
# Setup and verify speckit commands and Agency MCP server
# Usage:
#   setup-speckit.sh           # Run full setup (clone agency, build, re-run setup build)
#   setup-speckit.sh --verify  # Verify speckit is ready (exit 1 if not)

SETUP_LOG="${SETUP_LOG:-/tmp/generacy-setup.log}"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [setup-speckit] $*"
}

verify_speckit() {
    local ok=true

    # Check for representative slash command
    if [ ! -f "$HOME/.claude/commands/specify.md" ]; then
        log "VERIFY FAIL: ~/.claude/commands/specify.md not found"
        ok=false
    fi

    # Check for Agency MCP server entry in user-level Claude config
    if [ ! -f "$HOME/.claude.json" ]; then
        log "VERIFY FAIL: ~/.claude.json not found"
        ok=false
    elif ! grep -q "agency" "$HOME/.claude.json" 2>/dev/null; then
        log "VERIFY FAIL: agency MCP server not found in ~/.claude.json"
        ok=false
    fi

    if [ "$ok" = true ]; then
        log "Speckit verification passed"
        return 0
    else
        return 1
    fi
}

# --verify mode: just check and exit
if [ "$1" = "--verify" ]; then
    verify_speckit
    exit $?
fi

# Full setup mode — recover speckit via npm (no git clone needed)
log "Installing @generacy-ai/agency-plugin-spec-kit from npm..."
npm install -g @generacy-ai/agency-plugin-spec-kit 2>>"$SETUP_LOG" || {
    log "ERROR: npm install -g @generacy-ai/agency-plugin-spec-kit failed"
    exit 1
}
log "agency-plugin-spec-kit installed"

# Re-run generacy setup build to trigger Phase 4 (copies command files)
if command -v generacy >/dev/null 2>&1; then
    log "Re-running generacy setup build..."
    generacy setup build 2>>"$SETUP_LOG" || {
        log "ERROR: generacy setup build failed"
        exit 1
    }
fi

# Verify the result
if verify_speckit; then
    log "Setup complete — speckit is ready"
else
    log "WARNING: Setup completed but verification failed"
    exit 1
fi
